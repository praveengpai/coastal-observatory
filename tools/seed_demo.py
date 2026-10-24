"""Fill a STAGING or TRAINING database with realistic dummy data.

Every record goes through the same ingest code as real ODK submissions, so this also
tests the sync path. Refuses to run when OBS_ENVIRONMENT=production.

    python -m tools.seed_demo            # adds demo data
    python -m tools.seed_demo --reset    # wipes the database first
"""
import random
import sys
import uuid
from datetime import date, timedelta

from app import config
from app.db import Base, SessionLocal, engine, init_db
from app.models import Site, User, Weather
from app.security import hash_password
from app.sync_odk import ingest, upsert_lab

DEMO_SITES = [  # code, label, type, lat, lon, water positivity, median TDS, share elders vulnerable
    ("DMA", "[DEMO] Coastal village A", "village", 9.968, 76.243, 0.28, 850, 0.30),
    ("DMB", "[DEMO] Coastal village B", "village", 9.955, 76.250, 0.08, 1600, 0.22),
    ("DMC", "[DEMO] Island ward", "village", 9.990, 76.255, 0.07, 900, 0.30),
    ("DC1", "[DEMO] Canal colony 1", "colony", 9.962, 76.288, 0.30, 540, 0.12),
    ("DC2", "[DEMO] Canal colony 2", "colony", 9.958, 76.292, 0.44, 560, 0.18),
    ("DF1", "[DEMO] Flats complex 1", "flats", 9.992, 76.302, 0.16, 310, 0.06),
]
DEMO_USERS = [  # username, name, role, sites
    ("admin", "Demo administrator", "admin", "*"),
    ("coordinator", "Demo coordinator", "coordinator", "*"),
    ("scientist", "Demo NIO scientist", "scientist", "*"),
    ("doctor", "Demo CEDAC doctor", "doctor", "*"),
    ("asha", "Demo ASHA worker", "asha", "DC2 DMA"),
    ("ward", "Demo ward member", "ward", "DC2 DC1"),
]
DEMO_PASSWORD = "demo-password-2026"
FIRST = ["Lakshmi", "Mary", "Fathima", "Sreedevi", "Thomas", "Abdul", "Rajan", "Joseph", "Leela", "Ammini",
         "Kunjumon", "Saramma", "Vasu", "Khadeeja", "Philomina", "Gopalan", "Anitha", "Biju", "Reshma", "Shaji"]
LAST = ["K", "P", "M", "V", "T", "A", "S", "R", "N", "J"]


def sub(**groups):
    """Build a submission shaped like ODK Central's OData output."""
    s = {"__id": f"uuid:{uuid.uuid4()}", "__system": {"submissionDate": "2026-11-14T10:00:00.000Z",
                                                     "reviewState": None}}
    s.update(groups)
    return s


def main(reset=False):
    if config.ENVIRONMENT == "production":
        sys.exit("Refusing to load demo data into a production database.")
    if reset:
        Base.metadata.drop_all(engine)
    init_db()
    rnd = random.Random(2026)
    db = SessionLocal()
    today = date.today()
    for code, label, st, lat, lon, *_ in DEMO_SITES:
        db.merge(Site(code=code, label=label, site_type=st, lat=lat, lon=lon, active=True))
    db.merge(Site(code="TST", label="Training / test site", site_type="test", lat=9.98, lon=76.30, active=True))
    for u, name, role, sites in DEMO_USERS:
        db.merge(User(username=u, full_name=name, role=role, sites=sites, password_hash=hash_password(DEMO_PASSWORD)))
    db.commit()

    person_no = sample_no = 0
    for code, label, st, lat, lon, positivity, tds_med, vuln in DEMO_SITES:
        camp_day = today - timedelta(days=rnd.randint(20, 40))
        camp = {"camp_site": code, "role": "volunteer"}
        for h in range(1, rnd.randint(22, 30)):
            hh = f"{code}-{h:03d}"
            hlat, hlon = lat + rnd.uniform(-0.004, 0.004), lon + rnd.uniform(-0.004, 0.004)
            septic = rnd.choice(["lt10", "lt10", "10to30", "gt30"]) if st != "flats" else None
            hh_risk = positivity * (1.6 if septic == "lt10" else 0.8)
            tds = max(80, int(rnd.gauss(tds_med, tds_med * 0.3)))
            size = rnd.randint(1, 6)
            for m in range(1, min(size, rnd.randint(1, 4)) + 1):
                person_no += 1
                pid = f"OBS-P-{person_no:06d}"
                age = rnd.choice([rnd.randint(2, 17), rnd.randint(18, 59), rnd.randint(60, 90), rnd.randint(60, 85)])
                sex = rnd.choice(["m", "f"])
                consent = rnd.random() < 0.93
                first = m == 1
                reg = sub(
                    camp=camp, today=camp_day.isoformat(), camp_id=f"{code}-{camp_day:%Y%m%d}", site_type=st,
                    consent={"consent_research": "yes" if consent else "no"},
                    person_id=pid, hh_id=hh,
                    person={"name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", "age": age, "sex": sex,
                            "phone": f"9{rnd.randint(100000000, 999999999)}", "resident": "yes"},
                    first_member="yes" if first else "no", contact_ok="yes",
                    hist={"conditions": rnd.choice(["none", "htn", "dm", "htn dm", "none", "none"]) if age >= 30 else "none",
                          "tobacco": rnd.choice(["never", "never", "past", "current"]) if age >= 12 else None},
                    indiv={"occ_g": {"occupation": rnd.choice(["fishing", "fish_proc", "manual", "home", "retired"]),
                                     "wade": rnd.choice(["yes", "no", "no"])},
                           "sx_g": {"sx": "diarrhoea" if rnd.random() < hh_risk * 0.4 else rnd.choice(["none"] * 5 + ["fever", "skin"])}},
                )
                if first and consent:
                    reg["household"] = {
                        "hh_people": {"hh_size": size, "hh_n60": rnd.randint(0, 2), "hh_n5": rnd.randint(0, 1)},
                        "hh_water": {"water_drink": {"flats": "tanker", "colony": "own_well"}.get(st, rnd.choice(["own_well", "shared_well", "tap"])),
                                     "cook_same": "yes", "treat": rnd.choice(["none", "boil", "boil", "filter"]),
                                     "storage": rnd.choice(["covered", "open", "covered"])},
                        "hh_salt": {"salty": "often" if tds > 1000 else rnd.choice(["never", "sometimes"]),
                                    "toilet": "septic", "septic_dist": septic},
                        "hh_flood": {"flood": rnd.choice(["yes", "no"]), "animals": rnd.choice(["none", "poultry", "dog cat"]),
                                     "rats": rnd.choice(["never", "sometimes", "often"])},
                        "hh_tds": {"bottle": "yes", "tds": tds},
                    }
                ingest(db, "obs_camp_registration", reg)
                st_base = {"camp": {"camp_site": code}, "today": camp_day.isoformat(), "person_id": pid, "age": age,
                           "camp_id": f"{code}-{camp_day:%Y%m%d}"}
                if age >= 18:
                    sbp = rnd.gauss(118 + 0.45 * (age - 30) + 0.012 * (tds - 500) * (age >= 60), 12)
                    dbp = rnd.gauss(76 + 0.1 * (age - 30), 8)
                    ingest(db, "obs_camp_station", sub(**{
                        **st_base, "camp": {"camp_site": code, "role": "meas"},
                        "sbp": round(sbp), "dbp": round(min(dbp, sbp - 20)), "glucose": round(rnd.gauss(118, 35)),
                        "bmi": round(rnd.gauss(24, 4), 1), "u_protein": rnd.choice(["neg", "neg", "neg", "trace", "p1"]),
                        "u_sg": round(rnd.uniform(1.002, 1.025), 3)}))
                if age >= 40 and rnd.random() < 0.7:
                    ingest(db, "obs_camp_station", sub(**{**st_base, "camp": {"camp_site": code, "role": "eye"}},
                                                       va_r=rnd.choice(["6_6", "6_9", "6_12", "6_18", "6_60"]),
                                                       va_l=rnd.choice(["6_6", "6_9", "6_12", "6_24"]),
                                                       cataract=rnd.choice(["none", "none", "right", "both"]),
                                                       dr_r=rnd.choice(["none", "none", "mild", "moderate"]),
                                                       eye_referral=rnd.choice(["none"] * 5 + ["glasses", "cataract"])))
                if rnd.random() < 0.5:
                    ingest(db, "obs_camp_station", sub(**{**st_base, "camp": {"camp_site": code, "role": "dental"}},
                                                       caries_n=rnd.randint(0, 6), lesion=rnd.choice(["none"] * 12 + ["leuko"]),
                                                       dent_referral=rnd.choice(["none"] * 5 + ["treatment"])))
                if age >= 60:
                    ingest(db, "obs_camp_station", sub(**{**st_base, "camp": {"camp_site": code, "role": "geri"}},
                                                       alone="yes" if rnd.random() < vuln * 0.8 else "no",
                                                       evac="yes" if rnd.random() < vuln * 0.5 else "no",
                                                       heat_sx="yes" if rnd.random() < 0.25 else "no",
                                                       falls=rnd.choice([0, 0, 0, 1, 2, 3]), cfs=rnd.choice([2, 3, 3, 3, 4, 4, 4, 4, 5, 6]),
                                                       minicog_score=rnd.randint(1, 5), phq2_score=rnd.randint(0, 5)))
                if rnd.random() < 0.6:
                    ingest(db, "obs_camp_station", sub(**{**st_base, "camp": {"camp_site": code, "role": "doctor"}},
                                                       dx=rnd.choice(["well", "htn_new", "dm_unc", "diarrhoea", "msk"]),
                                                       doc_referral=rnd.choice(["none"] * 6 + ["phc", "mch"]),
                                                       followup=rnd.choice(["yes", "no"])))
            # water samples: two rounds
            for rnd_i, day in enumerate([camp_day - timedelta(days=7), camp_day + timedelta(days=14)]):
                if rnd.random() < 0.55 or day > today:
                    continue
                sample_no += 1
                sid = f"WS-{sample_no:06d}"
                rain = rnd.random() < 0.35
                flooded = rnd.random() < 0.2
                p = min(0.95, hh_risk * (1.8 if rain else 1) * (1.5 if flooded else 1))
                positive = rnd.random() < p
                aq = positive if rnd.random() < 0.88 else not positive
                ingest(db, "obs_water_sample", sub(
                    camp={"camp_site": code, "role": "nio"}, today=day.isoformat(), point_type="household",
                    hh_id=hh, sample={"sample_id": sid, "source": {"flats": "sump"}.get(st, "own_well"),
                                      "taken_at": rnd.choice(["source", "source", "stored"]),
                                      "gps": {"type": "Point", "coordinates": [hlon, hlat, 0]}},
                    field={"tds": tds, "water_temp": round(rnd.uniform(27, 31), 1), "rain_48h": "yes" if rain else "no",
                           "flooded_7d": "yes" if flooded else "no"},
                    aq={"aquadip": "pos" if aq else "neg", "to_lab": "yes"}))
                if rnd.random() < 0.6:
                    upsert_lab(db, sid, "nio_lab", positive=positive, tested_on=day + timedelta(days=2),
                               ecoli_cfu=round(rnd.uniform(5, 400)) if positive else 0,
                               vibrio=rnd.choice(["detected", "not_detected"]) if positive else "not_detected")
        # weekly household visits for 8 weeks
        hh_ids = [f"{code}-{h:03d}" for h in range(1, 20)]
        for w in range(8, 0, -1):
            day = today - timedelta(weeks=w) + timedelta(days=rnd.randint(0, 4))
            trend = positivity * (1 + (8 - w) / 8)
            for hh in rnd.sample(hh_ids, 8):
                ill = rnd.random() < trend * 0.22
                ingest(db, "obs_household_visit", sub(
                    camp={"camp_site": code, "role": "asha"}, today=day.isoformat(), hh_id=hh,
                    reason="routine result" if rnd.random() < 0.4 else "routine",
                    illness={"anyone_ill": "yes" if ill else "no", "n_diarrhoea": rnd.choice([1, 1, 1, 2]) if ill else 0,
                             "n_fever": rnd.randint(0, 1) if ill else 0, "n_heat": rnd.randint(0, 1) if ill else 0},
                    advgrp={"advice": rnd.choice(["result boil", "boil", "none", "heat"])}))
        db.commit()

    for i in range(-2, 8):
        day = today + timedelta(days=i)
        db.merge(Weather(day=day, rain_mm=round(max(0, rnd.gauss([5, 12, 35, 70, 110, 60, 20, 8, 4, 2][i + 2], 5)), 1),
                         temp_max=[30.5, 31, 30.8, 30.2, 29.4, 29.0, 30.1, 31.8, 32.6, 31.2][i + 2], rh_mean=[74, 72, 76, 82, 88, 86, 80, 75, 72, 74][i + 2],
                         tide_max_m=[0.8, 0.9, 0.8, 0.9, 1.2, 1.5, 1.3, 1.0, 0.8, 0.8][i + 2]))
    db.commit()
    from app import rules
    from app.analytics import site_codes
    from app.models import Advisory, StationRecord
    # some referrals followed up, some still pending
    for r in db.query(StationRecord).filter(StationRecord.referral.isnot(None)).all():
        if rnd.random() < 0.6 and r.collected_on:
            ingest(db, "obs_household_visit", sub(
                camp={"camp_site": r.site_code, "role": "asha"},
                today=(r.collected_on + timedelta(days=rnd.randint(3, 15))).isoformat(),
                hh_id=f"{r.site_code}-001", reason="referral",
                refgrp={"ref_person": r.person_id, "ref_status": rnd.choice(["went", "went", "went", "not_yet"])},
                illness={"anyone_ill": "no"}, advgrp={"advice": "none"}))
    db.commit()
    rules.generate(db, [s.code for s in site_codes(db)])
    for a in db.query(Advisory).all():
        x = rnd.random()
        if x < 0.5:
            a.status, a.reviewed_by = ("sent" if x < 0.35 else "approved"), "doctor"
    db.commit()
    print(f"Demo data loaded: {person_no} people, {sample_no} water samples, {len(DEMO_SITES)} sites.")
    print(f"Demo logins (password '{DEMO_PASSWORD}'): " + ", ".join(u for u, *_ in DEMO_USERS))
    db.close()


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
