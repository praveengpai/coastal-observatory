"""Add IDSP module demo data on top of the Observatory demo data. STAGING or TRAINING only.

    python -m tools.seed_idsp_demo           # adds IDSP demo users, Form S entries, verifications and alerts
    python -m tools.seed_idsp_demo --force   # run again even if IDSP demo data was already added

Every record goes through the real code: Form S submissions through the ODK ingest, community signals
through signal capture, and verifications, Form P, lab results and alerts through the same functions the
dashboard calls. Refuses to run when OBS_ENVIRONMENT=production.
"""
import random
import sys
import uuid
from datetime import date, datetime, timedelta

from app import analytics, config, idsp
from app.db import SessionLocal, init_db
from app.models import Household, IdspAlert, IdspCase, Person, Setting, Site, User, WaterSample
from app.security import hash_password
from app.sync_odk import ingest, upsert_lab

DEMO_PASSWORD = "demo-password-2026"
IDSP_USERS = [  # username, name, role, sites
    ("jphn", "Demo JPHN, sub-centre", "jphn", "DC1 DC2 DMA"),
    ("mo", "Demo PHC medical officer", "mo", "*"),
    ("dso", "Demo District Surveillance Officer", "dso", "*"),
    ("lab", "Demo laboratory technician", "lab", "*"),
]
MARKER = "idsp.demo_loaded"
ACTIVITIES = ["daily_wage", "fishing", "home", "salaried"]


def _sub(**fields):
    return {"__id": f"uuid:{uuid.uuid4()}", "__system": {"submissionDate": "2026-11-14T10:00:00.000Z",
                                                        "reviewState": None}, **fields}


class Demo:
    def __init__(self, db, rnd, today):
        self.db, self.rnd, self.today = db, rnd, today
        self.sites = {s.code: s for s in db.query(Site)}

    # ---- places
    def hh_pos(self, hh_id):
        h = self.db.get(Household, hh_id)
        if h and h.lat is not None:
            return h.lat, h.lon
        s = self.sites.get(hh_id.split("-")[0])
        r = random.Random(hh_id)                       # the same household always lands in the same place
        return (s.lat + r.uniform(-0.004, 0.004), s.lon + r.uniform(-0.004, 0.004)) if s and s.lat else (None, None)

    def place(self, hh_id, lat, lon):
        h = self.db.get(Household, hh_id)
        if h:
            h.lat, h.lon = lat, lon

    # ---- Form S, through the real ingest
    def s_form(self, day, hh_id, syndrome, person=None, age=None, sex=None, role="asha", onset=None, outcome="home",
               dehydration="none", water_contact="no", water_src="own_well", days_ill=None):
        lat, lon = self.hh_pos(hh_id)
        days_ill = days_ill if days_ill is not None else self.rnd.randint(1, 5)
        act = "child" if (age or 30) < 5 else "student" if (age or 30) < 18 else "retired" if (age or 30) >= 65 \
            else self.rnd.choice(ACTIVITIES)
        f = dict(today=day.isoformat(), role=role, report_type="case", hh_id=hh_id, camp_site=hh_id.split("-")[0],
                 consent_named="yes" if person else "no", in_list_eff="yes", person_id=person or "",
                 p_age=age, p_sex=sex, syndrome=syndrome, outcome=outcome, water_src=water_src, sample_taken="no",
                 onset=(onset or day - timedelta(days=self.rnd.randint(0, 2))).isoformat(), days_ill=days_ill,
                 activity=act, work_days=self.rnd.randint(1, max(1, days_ill)) if act in ACTIVITIES else None,
                 school_days=self.rnd.randint(1, max(1, days_ill)) if act == "student" else None,
                 carer_days=self.rnd.choice([0, 0, 1, 2]), care=self.rnd.choice(["govt", "govt", "pharmacy", "home"]))
        if syndrome in ("lws", "lws_blood"):
            f["dehydration"] = dehydration
        if syndrome.startswith("fever"):
            f["water_contact"] = water_contact
        if lat is not None:
            f["gps"] = {"type": "Point", "coordinates": [lon, lat, 0]}
        ingest(self.db, idsp.FORM_ID, _sub(**f))
        self.db.flush()

    def nil(self, day, site, week="this"):
        ingest(self.db, idsp.FORM_ID, _sub(today=day.isoformat(), role="asha", report_type="nil", nil_site=site,
                                           nil_week=week))

    def community(self, day, hh_id, form, person=None, age=None, sex=None, role="volunteer", **extra):
        base = dict(today=day.isoformat(), role=role, hh_id=hh_id, camp_site=hh_id.split("-")[0],
                    consent_named="yes" if person else "no", in_list_eff="yes", person_id=person or "", p_age=age,
                    p_sex=sex, impact={"onset": (day - timedelta(days=1)).isoformat(), "still_ill": "yes",
                                       "days_ill": 2, "activity": "daily_wage", "work_days": 1, "carer_days": 0,
                                       "care": "pharmacy"})
        base.update(extra)
        ingest(self.db, form, _sub(**base))

    def people(self, site, min_age=0, max_age=120):
        return [p for p in self.db.query(Person).filter(Person.site_code == site)
                if p.age is not None and min_age <= p.age <= max_age and p.hh_id]


def add(db, rnd=None, today=None):
    rnd = rnd or random.Random(2026)
    today = today or date.today()
    d = Demo(db, rnd, today)
    for u, name, role, sites in IDSP_USERS:
        db.merge(User(username=u, full_name=name, role=role, sites=sites, password_hash=hash_password(DEMO_PASSWORD)))
    db.commit()
    codes = [s.code for s in analytics.site_codes(db)]

    # 1. Community reports and camp diagnoses become signals waiting for an IDSP worker
    idsp.capture_signals(db)

    # 2. Most past signals were checked by an ASHA: by filing Form S (the usual way) or on the dashboard
    for c in db.query(IdspCase).filter(IdspCase.status == "unverified").order_by(IdspCase.id).all():
        age_days = (today - c.first_reported).days if c.first_reported else 99
        if age_days <= 4:
            continue                                   # recent: still in the verification queue
        x = rnd.random()
        when = c.first_reported + timedelta(days=rnd.choice([1, 1, 2, 2, 3]))
        if when > today:
            continue
        if x < 0.62:
            d.s_form(when, c.hh_id, c.syndrome, person=c.person_id, age=c.age, sex=c.sex, onset=c.onset,
                     water_contact="yes" if c.suspect == "lepto" else "no")
        elif x < 0.76:
            idsp.verify(db, c, "verified", "asha", "asha", "Visited; confirmed", today=when)
        elif x < 0.86:
            idsp.verify(db, c, "not_case", "asha", "asha", "Visited; no illness matching the report", today=when)
        elif x < 0.90:
            idsp.verify(db, c, "unreachable", "asha", "asha", "House locked on two visits", today=when)
        elif age_days > 12:
            idsp.verify(db, c, "verified", "jphn", "jphn", "Escalated after 72 hours; confirmed by phone",
                        today=c.first_reported + timedelta(days=4))
        # else: left waiting past its deadline, so it shows as escalated to the JPHN
    db.commit()

    # 3. Cases IDSP staff found themselves, and nil reports, over 12 weeks
    weights = [("fever_lt7", 34), ("ili", 22), ("lws", 16), ("cough_fever", 10), ("fever_ge7", 5), ("cough_2w", 3),
               ("animal_bite", 5), ("fever_rash", 2), ("jaundice", 2), ("snake_bite", 1)]
    pool = [k for k, w in weights for _ in range(w)]
    for code in codes:
        people = d.people(code)
        if not people:
            continue
        for w in range(12, 0, -1):
            ws = idsp.week_start(today) - timedelta(days=7 * w)
            n = rnd.choice([0, 0, 1, 1, 2, 2, 3])
            for _ in range(n):
                p = rnd.choice(people)
                day = ws + timedelta(days=rnd.randint(0, 6))
                syn = rnd.choice(pool)
                d.s_form(day, p.hh_id, syn, person=p.person_id, age=p.age, sex=p.sex,
                         days_ill=rnd.randint(7, 10) if syn == "fever_ge7" else None,
                         role=rnd.choice(["asha", "asha", "asha", "jphn"]))
            if n == 0 and rnd.random() < 0.8:
                d.nil(ws + timedelta(days=rnd.randint(4, 6)), code)
    db.commit()

    # 4. This week's story in DC2: a diarrhoea cluster around one shared well, first flagged by a volunteer
    if "DC2" in codes:
        site = d.sites["DC2"]
        homes = ["DC2-005", "DC2-007", "DC2-009", "DC2-011", "DC2-013"]
        for i, hh in enumerate(homes):
            d.place(hh, site.lat + 0.0006 * (i % 3) - 0.0006, site.lon + 0.0005 * (i // 3) - 0.0002)
        pp = {hh: [p for p in db.query(Person).filter(Person.hh_id == hh)] for hh in homes}
        pick = lambda hh, i=0: pp[hh][i] if len(pp[hh]) > i else None  # noqa: E731
        p5, p7, p9, p11, p13 = (pick(h) for h in homes)
        d.s_form(today - timedelta(days=5), "DC2-005", "lws", person=p5 and p5.person_id, age=p5 and p5.age or 34,
                 sex=p5 and p5.sex or "f", water_src="shared_well", dehydration="some")
        d.community(today - timedelta(days=4), "DC2-007", "obs_report_diarrhoea", person=p7 and p7.person_id,
                    age=p7 and p7.age or 9, sex=p7 and p7.sex or "m", role="volunteer", condition="diarrhoea",
                    danger="no", dd={"stools_day": 6, "blood": "no", "vomiting": "yes", "dehyd": "none"},
                    dd_hh={"others_ill": 1, "water_src": "shared_well", "ors_given": "yes"})
        idsp.capture_signals(db)
        d.s_form(today - timedelta(days=3), "DC2-007", "lws", person=p7 and p7.person_id, age=p7 and p7.age or 9,
                 sex=p7 and p7.sex or "m", water_src="shared_well")
        d.s_form(today - timedelta(days=2), "DC2-009", "lws", person=p9 and p9.person_id, age=p9 and p9.age or 63,
                 sex=p9 and p9.sex or "f", water_src="shared_well", outcome="referred", dehydration="some")
        d.community(today - timedelta(days=2), "DC2-011", "obs_report_diarrhoea", person=None, age=3, sex="m",
                    role="ward", condition="dysentery", danger="no",
                    dd={"stools_day": 8, "blood": "yes", "vomiting": "no", "dehyd": "none"},
                    dd_hh={"others_ill": 0, "water_src": "shared_well", "ors_given": "yes"})
        d.community(today - timedelta(days=1), "DC2-013", "obs_report_diarrhoea", person=p13 and p13.person_id,
                    age=p13 and p13.age or 41, sex=p13 and p13.sex or "m", role="volunteer", condition="diarrhoea",
                    danger="no", dd={"stools_day": 4, "blood": "no", "vomiting": "no", "dehyd": "none"},
                    dd_hh={"others_ill": 0, "water_src": "shared_well", "ors_given": "no"})
        idsp.capture_signals(db)
        child = db.query(IdspCase).filter(IdspCase.hh_id == "DC2-011").order_by(IdspCase.id.desc()).first()
        if child and child.status == "unverified":
            idsp.verify(db, child, "verified", "jphn", "jphn", "Child seen; blood in stool, ORS given, referred to PHC",
                        today=today - timedelta(days=1))
        lat, lon = d.hh_pos("DC2-007")
        ingest(db, "obs_water_sample", _sub(
            camp={"camp_site": "DC2", "role": "nio"}, today=(today - timedelta(days=3)).isoformat(),
            point_type="public", sample={"sample_id": "WS-900001", "source": "shared_well", "taken_at": "source",
                                         "gps": {"type": "Point", "coordinates": [lon + 0.0002, lat + 0.0001, 0]}},
            field={"tds": 520, "water_temp": 29.4, "rain_48h": "yes", "flooded_7d": "no"},
            aq={"aquadip": "pos", "to_lab": "yes"}))
        upsert_lab(db, "WS-900001", "nio_lab", positive=True, ecoli_cfu=310, vibrio="not_detected",
                   tested_on=today - timedelta(days=1))
        db.commit()

    # 5. Jaundice in DMA: hepatitis E confirmed by the lab
    if "DMA" in codes:
        adults = d.people("DMA", 18, 60)
        site = d.sites["DMA"]
        for i, p in enumerate(adults[:2]):
            d.place(p.hh_id, site.lat + 0.0012 + 0.0004 * i, site.lon - 0.0010)
            d.s_form(today - timedelta(days=16 - 9 * i), p.hh_id, "jaundice", person=p.person_id, age=p.age,
                     sex=p.sex, water_src="own_well", days_ill=6)
        db.commit()
        jx = db.query(IdspCase).filter(IdspCase.site_code == "DMA", IdspCase.syndrome == "jaundice",
                                       IdspCase.status == "verified").order_by(IdspCase.first_reported).all()
        for i, c in enumerate(jx[-2:]):
            idsp.set_presumptive(db, c, "hev", "mo", today=c.first_reported + timedelta(days=1))
            if i == 0:
                idsp.set_lab(db, c, "hev_igm", "positive", "lab", sample_on=c.first_reported + timedelta(days=1),
                             sample_id=f"DMA-SER-{c.id:04d}", today=c.first_reported + timedelta(days=4))
            else:
                idsp.set_lab(db, c, "hev_igm", "pending", "lab", sample_on=c.first_reported + timedelta(days=1),
                             sample_id=f"DMA-SER-{c.id:04d}", today=c.first_reported + timedelta(days=1))

    # 6. Leptospirosis signal in DC1 after canal flooding
    if "DC1" in codes:
        men = [p for p in d.people("DC1", 20, 60) if p.sex == "m"] or d.people("DC1", 20, 60)
        for i, p in enumerate(men[:2]):
            d.s_form(today - timedelta(days=6 - 3 * i), p.hh_id, "fever_lt7", person=p.person_id, age=p.age,
                     sex=p.sex, water_contact="yes", outcome="referred", role="jphn")
        db.commit()
        for c in (db.query(IdspCase).filter(IdspCase.site_code == "DC1", IdspCase.suspect == "lepto",
                                            IdspCase.status == "verified",
                                            IdspCase.first_reported >= today - timedelta(days=7)).all()):
            idsp.set_presumptive(db, c, "lepto", "mo", today=c.first_reported + timedelta(days=1))
            idsp.set_lab(db, c, "lepto_igm", "pending", "lab", sample_on=c.first_reported + timedelta(days=1),
                         sample_id=f"DC1-SER-{c.id:04d}", today=c.first_reported + timedelta(days=1))

    # 7. Fresh community signals for the verification queue: four this week, two already past their deadline
    fresh = [("DMA", 1, "obs_report_health", "fever", "volunteer"), ("DMB", 2, "obs_report_diarrhoea", "diarrhoea", "ward"),
             ("DC1", 1, "obs_report_health", "jaundice", "volunteer"), ("DF1", 3, "obs_report_health", "resp", "volunteer"),
             ("DMA", 6, "obs_report_diarrhoea", "diarrhoea", "volunteer"), ("DMB", 5, "obs_report_health", "lepto", "ward")]
    for code, ago, form, cond, role in fresh:
        people = d.people(code, 5, 80)
        if code not in codes or not people:
            continue
        p = rnd.choice(people)
        extra = {"dd": {"stools_day": 5, "blood": "no", "vomiting": "no", "dehyd": "none"},
                 "dd_hh": {"others_ill": 0, "water_src": "own_well", "ors_given": "yes"}} if cond == "diarrhoea" else {}
        d.community(today - timedelta(days=ago), p.hh_id, form, person=p.person_id, age=p.age, sex=p.sex, role=role,
                    condition=cond, danger="yes" if cond in ("jaundice", "lepto") else "no", **extra)
    idsp.capture_signals(db)

    # 8. The medical officer's Form P and the lab's results on part of the earlier verified cases
    for c in (db.query(IdspCase).filter(IdspCase.status == "verified", IdspCase.p_diagnosis.is_(None),
                                        IdspCase.first_reported < today - timedelta(days=7)).all()):
        x = rnd.random()
        on = c.first_reported + timedelta(days=1)
        if c.syndrome == "lws_blood" and x < 0.7:
            idsp.set_presumptive(db, c, "shigellosis", "mo", today=on)
            idsp.set_lab(db, c, "stool_culture", rnd.choice(["positive", "negative"]), "lab", sample_on=on,
                         sample_id=f"{c.site_code}-STL-{c.id:04d}", today=on + timedelta(days=3))
        elif c.syndrome == "fever_ge7" and x < 0.5:
            idsp.set_presumptive(db, c, "typhoid", "mo", today=on)
            idsp.set_lab(db, c, "blood_culture", rnd.choice(["positive", "negative", "negative"]), "lab",
                         sample_on=on, sample_id=f"{c.site_code}-BC-{c.id:04d}", today=on + timedelta(days=3))
        elif c.syndrome == "jaundice" and x < 0.6:
            idsp.set_presumptive(db, c, rnd.choice(["hav", "hev"]), "mo", today=on)
        elif c.suspect == "lepto" and x < 0.6:
            idsp.set_presumptive(db, c, "lepto", "mo", today=on)
        elif c.syndrome == "fever_lt7" and x < 0.12:
            idsp.set_presumptive(db, c, "dengue", "mo", today=on)
            idsp.set_lab(db, c, "dengue_ns1", rnd.choice(["positive", "negative"]), "lab", sample_on=on,
                         sample_id=f"{c.site_code}-DN-{c.id:04d}", today=on + timedelta(days=1))
    db.commit()

    # 9. Alerts: earlier weeks (handled and closed, so response times show), then today's (open)
    for k in range(8, 0, -1):
        then = today - timedelta(days=7 * k)
        before = {a.id for a in db.query(IdspAlert)}
        idsp.generate_alerts(db, codes, today=then)
        for a in db.query(IdspAlert).filter(IdspAlert.id.notin_(before or {0})).all():
            a.opened_at = datetime.combine(then, datetime.min.time()) + timedelta(hours=rnd.randint(7, 11))
            a.ack_by, a.ack_at = rnd.choice(["jphn", "mo"]), a.opened_at + timedelta(hours=rnd.choice([1, 2, 3, 5, 9, 20]))
            a.status, a.closed_by = "closed", a.ack_by
            a.closed_at = a.ack_at + timedelta(hours=rnd.choice([6, 18, 26, 40, 70]))
            a.action_taken = {"water": "ASHA visited the households near the sample; advice given; no new cases",
                              "water_link": "Well chlorinated; households advised; active case search done",
                              "add_cluster": "Field visit done; ORS and chlorine given; water samples sent to NIO",
                              }.get(a.kind, "Case reviewed by the medical officer")
        db.commit()
    idsp.generate_alerts(db, codes, today=today)
    for a in db.query(IdspAlert).filter(IdspAlert.status == "open").all():
        a.opened_at = datetime.utcnow() - timedelta(hours=rnd.randint(2, 30))
        if a.kind in ("immediate", "add_cluster"):
            a.status, a.ack_by, a.ack_at = "acknowledged", "mo", a.opened_at + timedelta(hours=1)
    db.merge(Setting(key=MARKER, value=today.isoformat()))
    db.commit()
    n = {s: db.query(IdspCase).filter(IdspCase.status == s).count() for s in idsp.STATUS_LABEL}
    return {"cases": n, "alerts_open": db.query(IdspAlert).filter(IdspAlert.status != "closed").count()}


def main(force=False):
    if config.ENVIRONMENT == "production":
        sys.exit("Refusing to load demo data into a production database.")
    init_db()
    db = SessionLocal()
    try:
        if db.get(Setting, MARKER) and not force:
            sys.exit("IDSP demo data is already loaded (use --force to add it again).")
        if not db.query(Site).filter(Site.code == "DC2").first():
            sys.exit("Load the Observatory demo data first: python -m tools.seed_demo")
        print("IDSP demo data loaded:", add(db))
        print(f"IDSP demo logins (password '{DEMO_PASSWORD}'): " + ", ".join(u for u, *_ in IDSP_USERS))
    finally:
        db.close()


if __name__ == "__main__":
    main(force="--force" in sys.argv)
