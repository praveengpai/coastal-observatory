"""IDSP module: Integrated Disease Surveillance Programme workspace inside the Observatory.

How it works
------------
* Collect once, use many. IDSP staff fill the IDSP Form S on their phones (obs_idsp_s). Everyone else
  keeps using their own forms, and the IDSP-relevant parts of those records are captured here quietly.
* Every record about the same illness episode joins one case (same household, same person, same
  syndrome group, onset within 14 days), so an episode is counted once however many people report it.
* A record from outside the IDSP module (volunteer, ward member, camp doctor) is a COMMUNITY SIGNAL:
  status "unverified". It never enters IDSP counts, exports or outbreak alerts until an IDSP worker
  (ASHA, JPHN or medical officer) confirms it, either on the dashboard or by filing Form S for it.
  Form S itself counts as verified: the health worker has seen the case.
* Tiers follow IDSP: S (syndromic, health worker), P (presumptive, medical officer), L (laboratory).
* Syndromes and diseases follow the IHIP Form S and Form P lists; the reporting week runs Monday to
  Sunday, as in the IDSP form guidelines. Alert thresholds are starting values the District
  Surveillance Officer can change on the IDSP tab.
"""
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .models import (Household, IdspAlert, IdspCase, IdspNil, IdspOrigin, Person, PersonPII, Report, Setting,
                     Site, StationRecord)

# ------------------------------------------------------------------ IHIP lists

# Form S syndromes (IHIP), in IHIP order. Code, label, short label for charts.
S_SYNDROMES = [
    ("fever_lt7", "Only fever, less than 7 days"),
    ("fever_ge7", "Only fever, 7 days or more"),
    ("fever_rash", "Fever with rash"),
    ("fever_bleed", "Fever with bleeding"),
    ("fever_altered", "Fever with altered sensorium"),
    ("cough_fever", "Cough with fever, up to 2 weeks"),
    ("cough", "Cough without fever, up to 2 weeks"),
    ("cough_fever_2w", "Cough with fever, more than 2 weeks"),
    ("cough_2w", "Cough without fever, more than 2 weeks"),
    ("lws_blood", "Loose watery stools with blood, under 2 weeks"),
    ("lws", "Loose watery stools without blood, under 2 weeks"),
    ("jaundice", "Jaundice, under 4 weeks"),
    ("afp", "Acute flaccid paralysis"),
    ("malaria_pv", "Malaria vivax, RDT positive"),
    ("malaria_pf", "Malaria falciparum, RDT positive"),
    ("malaria_mix", "Malaria mixed, RDT positive"),
    ("animal_bite", "Animal bite"),
    ("snake_bite", "Snake bite"),
    ("aes", "Acute encephalitis syndrome"),
    ("ili", "ARI / influenza-like illness (ILI)"),
    ("sari", "ARI / severe acute respiratory infection (SARI)"),
    ("unusual", "Other unusual health condition"),
]
S_LABEL = dict(S_SYNDROMES)

# Form P diseases (IHIP), the ones most relevant to a coastal water project first.
P_DISEASES = [
    ("cholera", "Cholera"), ("shigellosis", "Shigellosis"), ("typhoid", "Typhoid"),
    ("nts", "Non-typhoidal salmonellosis"), ("hav", "Viral hepatitis A"), ("hev", "Viral hepatitis E"),
    ("lepto", "Leptospirosis"), ("dengue", "Dengue"), ("chikungunya", "Chikungunya"), ("malaria", "Malaria"),
    ("malaria_pv", "Malaria, Plasmodium vivax"), ("scrub", "Scrub typhus"), ("measles", "Measles"),
    ("rubella", "Rubella"), ("chickenpox", "Chickenpox"), ("mumps", "Mumps"), ("diphtheria", "Diphtheria"),
    ("pertussis", "Pertussis"), ("meningitis", "Meningitis"), ("mening_mc", "Meningococcal meningitis"),
    ("je", "Japanese encephalitis"), ("kfd", "Kyasanur forest disease"), ("rabies", "Human rabies"),
    ("anthrax", "Anthrax"), ("cchf", "Crimean-Congo haemorrhagic fever"),
]
P_LABEL = dict(P_DISEASES)

LAB_TESTS = [
    ("stool_culture", "Stool culture"), ("cholera_rdt", "Cholera RDT"), ("hav_igm", "Hepatitis A IgM"),
    ("hev_igm", "Hepatitis E IgM"), ("lepto_igm", "Leptospira IgM / MAT"), ("dengue_ns1", "Dengue NS1 / IgM"),
    ("blood_culture", "Blood culture (typhoid)"), ("malaria", "Malaria smear or RDT"),
    ("scrub_igm", "Scrub typhus IgM"), ("other", "Other"),
]
LAB_LABEL = dict(LAB_TESTS)
# A positive test confirms this Form P disease (used when the medical officer has not set one).
LAB_CONFIRMS = {"cholera_rdt": "cholera", "hav_igm": "hav", "hev_igm": "hev", "lepto_igm": "lepto",
                "dengue_ns1": "dengue", "blood_culture": "typhoid", "scrub_igm": "scrub", "malaria": "malaria"}

# Syndromes that belong to one episode when the same person reports them close together.
GROUP = {"lws": "diarrhoeal", "lws_blood": "diarrhoeal", "jaundice": "jaundice",
         "fever_lt7": "fever", "fever_ge7": "fever", "fever_rash": "fever", "fever_bleed": "fever",
         "fever_altered": "fever", "aes": "fever", "cough_fever": "respiratory", "cough": "respiratory",
         "cough_fever_2w": "respiratory", "cough_2w": "respiratory", "ili": "respiratory", "sari": "respiratory",
         "malaria_pv": "fever", "malaria_pf": "fever", "malaria_mix": "fever"}
GROUP_LABEL = {"diarrhoeal": "Diarrhoeal", "fever": "Fever", "respiratory": "Respiratory", "jaundice": "Jaundice",
               "other": "Other"}
WATER_BORNE = {"lws", "lws_blood", "jaundice"}
SOURCE_LABEL = {"community": "Community report", "camp": "Camp doctor", "idsp": "IDSP Form S"}
STATUS_LABEL = {"unverified": "Awaiting verification", "verified": "Verified", "not_case": "Not a case",
                "duplicate": "Duplicate", "unreachable": "Could not be reached"}
SUSPECT_LABEL = {"cholera": "suspected cholera", "typhoid": "suspected typhoid", "lepto": "suspected leptospirosis",
                 "dengue": "suspected dengue, malaria or chikungunya", "hepatitis": "suspected hepatitis"}
EPISODE_DAYS = 14

# Community report condition (household report forms) -> Form S syndrome and suspicion.
def _from_condition(condition: str, days_ill):
    fever = "fever_ge7" if (days_ill or 0) >= 7 else "fever_lt7"
    return {
        "diarrhoea": ("lws", None), "dysentery": ("lws_blood", None), "cholera": ("lws", "cholera"),
        "jaundice": ("jaundice", "hepatitis"), "typhoid": (fever, "typhoid"), "fever": (fever, None),
        "lepto": (fever, "lepto"), "vector": (fever, "dengue"), "resp": ("ili", None),
    }.get(condition or "", (None, None))


# Camp doctor diagnosis (station form) -> Form S syndrome and suspicion.
CAMP_DX = {"diarrhoea": ("lws", None), "lepto_susp": ("fever_lt7", "lepto")}

# ------------------------------------------------------------------ thresholds (DSO-editable)

THRESHOLDS = [  # key, default, label
    ("verify_hours", 72, "Hours to verify a community signal"),
    ("urgent_verify_hours", 24, "Hours to verify an urgent signal"),
    ("cluster_radius_m", 500, "Cluster radius (metres)"),
    ("add_cluster_n", 3, "Diarrhoea cluster: verified cases"),
    ("add_cluster_days", 7, "Diarrhoea cluster: within days"),
    ("jaundice_n", 2, "Jaundice cluster: verified cases"),
    ("jaundice_days", 30, "Jaundice cluster: within days"),
    ("lepto_n", 2, "Leptospirosis signal: cases in a ward"),
    ("lepto_days", 14, "Leptospirosis signal: within days"),
    ("water_days", 14, "Water link: positive sample within days"),
    ("water_radius_m", 250, "Water link: sample within metres of a case"),
    ("baseline_sd", 2, "Rise above baseline: standard deviations"),
]
TH_DEFAULT = {k: v for k, v, _ in THRESHOLDS}


def thresholds(db: Session) -> dict:
    out = dict(TH_DEFAULT)
    for row in db.query(Setting).filter(Setting.key.like("idsp.%")):
        k = row.key[5:]
        if k in out and row.value not in (None, ""):
            try:
                out[k] = float(row.value) if "." in row.value else int(row.value)
            except ValueError:
                pass
    return out


def set_thresholds(db: Session, values: dict):
    for k, v in values.items():
        if k not in TH_DEFAULT:
            raise KeyError(k)
        db.merge(Setting(key=f"idsp.{k}", value=None if v is None else str(v)))
    db.commit()


# ------------------------------------------------------------------ weeks

def week_start(d: date) -> date:
    """IDSP reporting week: Monday to Sunday."""
    return d - timedelta(days=d.weekday())


def week_label(ws: date) -> str:
    we = ws + timedelta(days=6)
    return f"Week {ws.isocalendar()[1]}, {ws:%d %b} to {we:%d %b %Y}"


def tier(c: IdspCase) -> str:
    if c.lab_result == "positive":
        return "L"
    if c.p_diagnosis:
        return "P"
    return "S"


def _add_word(text: str, word: str | None) -> str:
    words = (text or "").split()
    if word and word not in words:
        words.append(word)
    return " ".join(words)


# ------------------------------------------------------------------ episodes

def _compatible(c: IdspCase, person_id, age, sex) -> bool:
    if c.person_id and person_id:
        return c.person_id == person_id
    if c.sex and sex and c.sex != sex:
        return False
    if c.age is not None and age is not None and abs(c.age - age) > 2:
        return False
    return True


def find_episode(db: Session, hh_id, person_id, age, sex, syndrome, when: date):
    """An existing case for the same person, syndrome group and onset (within 14 days), or None."""
    if not hh_id:
        return None
    grp = GROUP.get(syndrome, syndrome)
    for c in (db.query(IdspCase).filter(IdspCase.hh_id == hh_id, IdspCase.status != "duplicate")
              .order_by(IdspCase.id)):
        if GROUP.get(c.syndrome, c.syndrome) != grp:
            continue
        ref = c.onset or c.first_reported
        if ref and when and abs((ref - when).days) > EPISODE_DAYS:
            continue
        if _compatible(c, person_id, age, sex):
            return c
    return None


def add_record(db: Session, kind: str, key: str, *, site, hh_id, person_id, age, sex, syndrome, suspect=None,
               onset=None, reported_on=None, role=None, urgent=False, admitted=False, died=False,
               water_source=None, work_days=0, carer_days=0, school_days=0):
    """Attach one source record to its episode, creating the case if it is new. Idempotent on `key`.

    kind: "idsp" (IDSP Form S, counts as verified), "community" or "camp" (signals to verify).
    """
    if db.get(IdspOrigin, key):
        return None
    when = onset or reported_on
    c = find_episode(db, hh_id, person_id, age, sex, syndrome, when)
    if c is None:
        c = IdspCase(site_code=site, hh_id=hh_id, person_id=person_id or None, age=age, sex=sex, syndrome=syndrome,
                     suspect=suspect, status="unverified", first_source=kind, sources="", reporter_roles="",
                     onset=onset, first_reported=reported_on, work_days=0, carer_days=0, school_days=0,
                     urgent=False, admitted=False, died=False)
        db.add(c)
        db.flush()
    else:
        if kind == "idsp" and not (c.syndrome == "lws_blood" and syndrome == "lws"):
            c.syndrome = syndrome                       # the health worker's syndrome is the more exact one
        elif syndrome == "lws_blood" and c.syndrome == "lws":
            c.syndrome = "lws_blood"
        if suspect == "cholera" or (suspect and not c.suspect):
            c.suspect = suspect
        c.person_id = c.person_id or person_id or None
        c.age = c.age if c.age is not None else age
        c.sex = c.sex or sex
        if onset and (not c.onset or onset < c.onset):
            c.onset = onset
        if reported_on and (not c.first_reported or reported_on < c.first_reported):
            c.first_reported, c.first_source = reported_on, kind
        if kind != "idsp" and c.status in ("not_case", "unreachable"):
            # a new report about someone found well or not reached earlier: check again
            c.status, c.verified_on, c.verified_by = "unverified", None, None
            c.verify_note = f"Reopened: reported again on {reported_on}"
    c.sources = _add_word(c.sources, kind)
    c.reporter_roles = _add_word(c.reporter_roles, role)
    c.urgent = bool(c.urgent or urgent or admitted or died or suspect == "cholera" or
                    (syndrome == "lws_blood" and age is not None and age < 5))
    c.admitted, c.died = bool(c.admitted or admitted), bool(c.died or died)
    c.water_source = c.water_source or water_source
    c.work_days = max(c.work_days or 0, work_days or 0)
    c.carer_days = max(c.carer_days or 0, carer_days or 0)
    c.school_days = max(c.school_days or 0, school_days or 0)
    if kind == "idsp":
        if reported_on and (not c.idsp_reported or reported_on < c.idsp_reported):
            c.idsp_reported = reported_on
        if c.status != "verified":
            c.status, c.verified_on = "verified", reported_on
            c.verified_by = f"Form S ({role or 'IDSP worker'})"
    db.add(IdspOrigin(key=key, case_id=c.id, kind=kind, reported_on=reported_on, site_code=site, role=role))
    db.flush()
    return c


# ------------------------------------------------------------------ capture from other modules

def capture_signals(db: Session, since_days: int = 30, today: date | None = None) -> dict:
    """Turn new household reports and camp diagnoses into community signals. Idempotent; run after each sync.

    Records older than `since_days` are noted but not queued, so switching the module on does not flood the
    verification queue with old, unverifiable reports.
    """
    db.flush()
    seen = {k for (k,) in db.query(IdspOrigin.key)}
    cutoff = (today or date.today()) - timedelta(days=since_days)
    n = Counter()
    for r in db.query(Report).filter(Report.condition.isnot(None)).order_by(Report.reported_on, Report.instance_id):
        key = f"community:{r.instance_id}"
        if key in seen:
            continue
        syndrome, suspect = _from_condition(r.condition, r.days_ill)
        if not syndrome or not r.hh_id or not r.reported_on or r.reported_on < cutoff:
            db.add(IdspOrigin(key=key, case_id=None, kind="community", reported_on=r.reported_on,
                              site_code=r.site_code, role=r.reporter_role))
            continue
        d = r.data or {}
        add_record(db, "community", key, site=r.site_code, hh_id=r.hh_id, person_id=r.person_id, age=r.age,
                   sex=r.sex, syndrome=syndrome, suspect=suspect, onset=r.onset, reported_on=r.reported_on,
                   role=r.reporter_role, urgent=bool(r.danger), admitted=r.care == "admitted",
                   water_source=d.get("water_src"), work_days=r.work_days, carer_days=r.carer_days,
                   school_days=r.school_days)
        n["community"] += 1
    for s in db.query(StationRecord).filter(StationRecord.station == "doctor"):
        key = f"camp:{s.instance_id}"
        if key in seen:
            continue
        dx = set(str((s.data or {}).get("dx") or "").split())
        hit = next((CAMP_DX[x] for x in ("diarrhoea", "lepto_susp") if x in dx), None)
        person = db.get(Person, s.person_id) if s.person_id else None
        if not hit or not person or not person.hh_id or not s.collected_on or s.collected_on < cutoff:
            db.add(IdspOrigin(key=key, case_id=None, kind="camp", reported_on=s.collected_on, site_code=s.site_code,
                              role="doctor"))
            continue
        add_record(db, "camp", key, site=s.site_code, hh_id=person.hh_id, person_id=person.person_id, age=s.age,
                   sex=person.sex, syndrome=hit[0], suspect=hit[1], onset=None, reported_on=s.collected_on,
                   role="camp_doctor")
        n["camp"] += 1
    db.commit()
    return dict(n)


# ------------------------------------------------------------------ IDSP Form S (phones)

FORM_ID = "obs_idsp_s"
PRIVATE_FIELDS = {"new_name", "name"}


def ingest_s_form(db: Session, f: dict, helpers):
    """One IDSP Form S submission: a case, or a nil report for the week. `helpers` is sync_odk."""
    _int, _date = helpers._int, helpers._date
    iid, on, role = f["_instance_id"], _date(f.get("today")), f.get("role")
    if f.get("report_type") == "nil":
        site = f.get("nil_site")
        if not site or not on:
            return
        helpers._site(db, site)
        ws = week_start(on) - (timedelta(days=7) if f.get("nil_week") == "last" else timedelta(0))
        db.merge(IdspNil(instance_id=iid, site_code=site, week_start=ws, reported_on=on, role=role))
        return
    hh = f.get("hh_id") or None
    site = f.get("camp_site") or (hh.split("-")[0] if hh else None)
    syndrome = f.get("syndrome")
    if not site or not hh or syndrome not in S_LABEL:
        return
    helpers._site(db, site)
    lat, lon = helpers._point(f.get("gps"))
    helpers._household(db, hh, site, lat, lon)
    named = f.get("consent_named") == "yes"
    pid = (f.get("person_id") or None) if named else None
    age = _int(f.get("p_age"))
    if named and pid and f.get("in_list_eff") == "no" and not db.get(Person, pid):
        db.add(Person(person_id=pid, hh_id=hh, site_code=site, sex=f.get("p_sex"), age=age, resident=True,
                      consent_research=False, registered_on=on))
        db.flush()
        db.merge(PersonPII(person_id=pid, name=f.get("new_name"), contact_ok=False))
    suspect = None
    if syndrome in ("lws", "lws_blood") and f.get("dehydration") == "severe" and (age or 0) >= 2:
        suspect = "cholera"                      # WHO suspected-cholera definition, outside an outbreak
    elif syndrome.startswith("fever") and f.get("water_contact") == "yes":
        suspect = "lepto"
    elif syndrome == "jaundice":
        suspect = "hepatitis"
    outcome = f.get("outcome")
    working = f.get("activity") in {"daily_wage", "fishing", "salaried", "self_emp", "home"}
    add_record(db, "idsp", f"idsp:{iid}", site=site, hh_id=hh, person_id=pid, age=age, sex=f.get("p_sex") or None,
               syndrome=syndrome, suspect=suspect, onset=_date(f.get("onset")), reported_on=on, role=role,
               urgent=f.get("dehydration") == "severe", admitted=outcome == "admitted", died=outcome == "died",
               water_source=f.get("water_src"), work_days=(_int(f.get("work_days")) or 0) if working else 0,
               carer_days=_int(f.get("carer_days")) or 0, school_days=_int(f.get("school_days")) or 0)


# ------------------------------------------------------------------ actions

VERIFY_OUTCOMES = ("verified", "not_case", "duplicate", "unreachable")


def verify(db: Session, c: IdspCase, outcome: str, username: str, role: str, note: str | None = None,
           duplicate_of: int | None = None, today: date | None = None):
    if outcome not in VERIFY_OUTCOMES:
        raise ValueError("Outcome must be verified, not_case, duplicate or unreachable.")
    if c.status == "duplicate":
        raise ValueError(f"This case is already merged into case {c.duplicate_of}.")
    if outcome == "duplicate":
        other = db.get(IdspCase, duplicate_of) if duplicate_of else None
        if not other or other.id == c.id:
            raise ValueError("Give the case number this one duplicates.")
        if other.status == "duplicate":
            raise ValueError(f"Case {other.id} is itself a duplicate of case {other.duplicate_of}; use that number.")
        if other.site_code != c.site_code:
            raise ValueError("A case can only duplicate a case in the same ward.")
        other.sources = " ".join(sorted(set(other.sources.split()) | set(c.sources.split())))
        other.reporter_roles = " ".join(sorted(set(other.reporter_roles.split()) | set(c.reporter_roles.split())))
        if c.first_reported and (not other.first_reported or c.first_reported < other.first_reported):
            other.first_reported, other.first_source = c.first_reported, c.first_source
        if c.onset and (not other.onset or c.onset < other.onset):
            other.onset = c.onset
        other.urgent, other.admitted, other.died = (other.urgent or c.urgent, other.admitted or c.admitted,
                                                    other.died or c.died)
        other.work_days = max(other.work_days or 0, c.work_days or 0)
        other.carer_days = max(other.carer_days or 0, c.carer_days or 0)
        other.school_days = max(other.school_days or 0, c.school_days or 0)
        db.query(IdspOrigin).filter(IdspOrigin.case_id == c.id).update({"case_id": other.id})
        c.duplicate_of = other.id
    c.status = outcome
    c.verified_on = today or date.today()
    c.verified_by = f"{username} ({role})"
    c.verify_note = (note or "").strip()[:300] or None
    db.commit()


def set_presumptive(db: Session, c: IdspCase, diagnosis: str, username: str, today: date | None = None):
    if diagnosis not in P_LABEL:
        raise ValueError("Unknown Form P disease.")
    c.p_diagnosis, c.p_by, c.p_on, c.p_from_lab = diagnosis, username, today or date.today(), False
    if c.status != "verified":                      # the medical officer has seen the patient
        c.status, c.verified_on, c.verified_by = "verified", c.p_on, f"{username} (mo)"
    db.commit()


def set_lab(db: Session, c: IdspCase, test: str, result: str, username: str, sample_on: date | None = None,
            sample_id: str | None = None, today: date | None = None):
    if test not in LAB_LABEL:
        raise ValueError("Unknown test.")
    if result not in ("positive", "negative", "pending"):
        raise ValueError("Result must be positive, negative or pending.")
    c.lab_test, c.lab_result, c.lab_by = test, result, username
    c.lab_sample_on = sample_on or c.lab_sample_on
    c.lab_sample_id = (sample_id or "").strip()[:40] or c.lab_sample_id
    c.lab_on = today or date.today()
    if result == "positive" and not c.p_diagnosis and test in LAB_CONFIRMS:
        c.p_diagnosis, c.p_by, c.p_on, c.p_from_lab = LAB_CONFIRMS[test], username, c.lab_on, True
    elif result != "positive" and c.p_from_lab:
        c.p_diagnosis = c.p_by = c.p_on = None      # the diagnosis came only from the result now corrected
        c.p_from_lab = False
    db.commit()


# ------------------------------------------------------------------ reading

def _names(db: Session, cases, show_pii: bool):
    if not show_pii:
        return {}
    ids = [c.person_id for c in cases if c.person_id]
    return {p.person_id: p for p in db.query(PersonPII).filter(PersonPII.person_id.in_(ids or [""]))}


def _due(c: IdspCase, th: dict):
    if not c.first_reported:
        return None
    hours = th["urgent_verify_hours"] if c.urgent else th["verify_hours"]
    return c.first_reported + timedelta(days=math.ceil(hours / 24))


def case_row(c: IdspCase, names: dict, show_pii: bool, th: dict, today: date) -> dict:
    who = names.get(c.person_id)
    due = _due(c, th)
    return {
        "id": c.id, "site": c.site_code, "hh_id": c.hh_id, "person_id": c.person_id,
        "name": who.name if who else None, "phone": who.phone if (who and show_pii) else None,
        "age": c.age, "sex": c.sex, "syndrome": c.syndrome, "syndrome_label": S_LABEL.get(c.syndrome, c.syndrome),
        "group": GROUP.get(c.syndrome, "other"), "suspect": SUSPECT_LABEL.get(c.suspect) if c.suspect else None,
        "status": c.status, "status_label": STATUS_LABEL.get(c.status, c.status), "tier": tier(c),
        "first_source": SOURCE_LABEL.get(c.first_source, c.first_source),
        "sources": [SOURCE_LABEL.get(s, s) for s in c.sources.split()], "reported_by": c.reporter_roles,
        "onset": _iso(c.onset), "first_reported": _iso(c.first_reported), "verified_on": _iso(c.verified_on),
        "verified_by": c.verified_by, "note": c.verify_note, "due": _iso(due),
        "overdue": bool(c.status == "unverified" and due and today > due),
        "escalated": bool(c.status == "unverified" and due and today > due),
        "days_waiting": (today - c.first_reported).days if (c.status == "unverified" and c.first_reported) else None,
        "urgent": c.urgent, "admitted": c.admitted, "died": c.died, "water_source": c.water_source,
        "work_days": c.work_days, "carer_days": c.carer_days, "school_days": c.school_days,
        "p_diagnosis": P_LABEL.get(c.p_diagnosis) if c.p_diagnosis else None, "p_by": c.p_by,
        "lab_test": LAB_LABEL.get(c.lab_test) if c.lab_test else None, "lab_result": c.lab_result,
        "lab_sample_id": c.lab_sample_id, "lab_sample_on": _iso(c.lab_sample_on),
        "duplicate_of": c.duplicate_of,
    }


def _iso(d):
    return d.isoformat() if d else None


def queue(db: Session, codes, show_pii: bool, today: date | None = None):
    """Community signals waiting for an IDSP worker: urgent first, then overdue, then oldest."""
    today = today or date.today()
    th = thresholds(db)
    rows = (db.query(IdspCase).filter(IdspCase.site_code.in_(codes or [""]), IdspCase.status == "unverified")
            .all())
    names = _names(db, rows, show_pii)
    out = [case_row(c, names, show_pii, th, today) for c in rows]
    out.sort(key=lambda r: (not r["urgent"], not r["overdue"], r["first_reported"] or "", r["id"]))
    return out


def cases(db: Session, codes, show_pii: bool, ws: date | None = None, status: str | None = None,
          today: date | None = None, limit=500):
    today = today or date.today()
    th = thresholds(db)
    q = db.query(IdspCase).filter(IdspCase.site_code.in_(codes or [""]))
    if ws:
        q = q.filter(IdspCase.first_reported >= ws, IdspCase.first_reported <= ws + timedelta(days=6))
    if status:
        q = q.filter(IdspCase.status == status)
    rows = q.order_by(IdspCase.first_reported.desc(), IdspCase.id.desc()).limit(limit).all()
    names = _names(db, rows, show_pii)
    return [case_row(c, names, show_pii, th, today) for c in rows]


def _age_band(age):
    return None if age is None else ("le5" if age <= 5 else "gt5")


def _count_table(rows, keyfn, labels):
    table = {code: Counter() for code, _ in labels}
    for c in rows:
        k = keyfn(c)
        if k not in table:
            continue
        band, sex = _age_band(c.age), (c.sex or "").lower()
        col = f"{sex}_{band}" if sex in ("m", "f") and band else "unknown"
        table[k][col] += 1
        table[k]["total"] += 1
    out = []
    for code, label in labels:
        t = table[code]
        out.append({"code": code, "label": label, "m_le5": t["m_le5"], "m_gt5": t["m_gt5"], "f_le5": t["f_le5"],
                    "f_gt5": t["f_gt5"], "unknown": t["unknown"], "total": t["total"]})
    return out


def weekly(db: Session, codes, ws: date, today: date | None = None):
    """The week's Form S, P and L in IHIP layout, from VERIFIED cases only, plus reporting completeness."""
    today = today or date.today()
    we = ws + timedelta(days=6)
    week = (db.query(IdspCase).filter(IdspCase.site_code.in_(codes or [""]), IdspCase.first_reported >= ws,
                                      IdspCase.first_reported <= we).all())
    verified = [c for c in week if c.status == "verified"]
    s_rows = _count_table(verified, lambda c: c.syndrome, S_SYNDROMES)
    p_rows = [r for r in _count_table(verified, lambda c: c.p_diagnosis, P_DISEASES) if r["total"]]
    l_cases = (db.query(IdspCase).filter(IdspCase.site_code.in_(codes or [""]), IdspCase.lab_test.isnot(None),
                                         IdspCase.lab_on >= ws, IdspCase.lab_on <= we).all())
    l_rows = [{"id": c.id, "site": c.site_code, "test": LAB_LABEL.get(c.lab_test), "result": c.lab_result,
               "sample_on": _iso(c.lab_sample_on), "sample_id": c.lab_sample_id,
               "provisional": P_LABEL.get(c.p_diagnosis) or S_LABEL.get(c.syndrome)} for c in l_cases]
    # completeness: a site has reported if an IDSP worker sent Form S (case or nil) or verified a signal that week
    form_s = {o.site_code for o in db.query(IdspOrigin).filter(IdspOrigin.kind == "idsp",
                                                               IdspOrigin.reported_on >= ws,
                                                               IdspOrigin.reported_on <= we)}
    nil = {n.site_code for n in db.query(IdspNil).filter(IdspNil.week_start == ws)}
    checked = {c.site_code for c in db.query(IdspCase).filter(IdspCase.verified_on >= ws, IdspCase.verified_on <= we,
                                                              IdspCase.verified_by.notlike("Form S%"))}
    sites = []
    for code in codes:
        n_cases = sum(1 for c in verified if c.site_code == code)
        if code in form_s or code in checked:
            state = "Reported" if n_cases else "Reported, no cases"
        elif code in nil:
            state = "Nil report"
        else:
            state = "Not reported"
        site = db.get(Site, code)
        sites.append({"site": code, "label": site.label if site else code, "state": state, "cases": n_cases})
    reported = sum(1 for s in sites if s["state"] != "Not reported")
    return {
        "week_start": ws.isoformat(), "week_end": we.isoformat(), "label": week_label(ws),
        "complete": today > we, "form_s": s_rows, "form_p": p_rows, "form_l": l_rows,
        "verified": len(verified), "pending": sum(1 for c in week if c.status == "unverified"),
        "excluded": sum(1 for c in week if c.status in ("not_case", "duplicate", "unreachable")),
        "sites": sites, "completeness": round(reported / len(sites), 3) if sites else None,
        "note": "Counts only verified cases, by the date the illness first came to notice. Cases verified "
                "later are added to the week they belong to. Age bands follow IHIP: up to 5 years, over 5.",
    }


# ------------------------------------------------------------------ CSV exports

def weekly_csv_rows(data: dict):
    head = ["form", "code", "syndrome_or_disease", "male_le5", "male_gt5", "female_le5", "female_gt5",
            "age_or_sex_unknown", "total", "week_start", "week_end"]
    rows = [head]
    for form, items in (("S", data["form_s"]), ("P", data["form_p"])):
        for r in items:
            rows.append([form, r["code"], r["label"], r["m_le5"], r["m_gt5"], r["f_le5"], r["f_gt5"], r["unknown"],
                         r["total"], data["week_start"], data["week_end"]])
    return rows


def linelist_csv_rows(case_rows, show_pii: bool):
    head = ["case_id", "site", "household", "person_id"] + (["name", "phone"] if show_pii else []) + [
        "age", "sex", "form_s_syndrome", "suspicion", "form_p_disease", "test_requested", "sample_date",
        "specimen_id", "lab_result", "onset", "first_reported", "verified_on", "verified_by", "first_source",
        "sources", "admitted", "died", "water_source", "status"]
    rows = [head]
    for r in case_rows:
        rows.append([r["id"], r["site"], r["hh_id"], r["person_id"]] + ([r["name"], r["phone"]] if show_pii else []) + [
            r["age"], r["sex"], r["syndrome_label"], r["suspect"], r["p_diagnosis"], r["lab_test"], r["lab_sample_on"],
            r["lab_sample_id"], r["lab_result"], r["onset"], r["first_reported"], r["verified_on"], r["verified_by"],
            r["first_source"], "; ".join(r["sources"]), "yes" if r["admitted"] else "no", "yes" if r["died"] else "no",
            r["water_source"], r["status_label"]])
    return rows


# ------------------------------------------------------------------ alerts

def _haversine_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _positions(db: Session, cs):
    ids = {c.hh_id for c in cs if c.hh_id}
    return {h.hh_id: (h.lat, h.lon) for h in db.query(Household).filter(Household.hh_id.in_(ids or [""]))
            if h.lat is not None and h.lon is not None}


def clusters(db: Session, cs, radius_m: float):
    """Groups of neighbouring cases in ONE ward: same household or within radius_m. A case whose household
    has no GPS point yet joins every group in its ward (so a missing location never hides a cluster) but
    never links two groups together; with no located group in the ward, the unlocated cases form one group."""
    pos = _positions(db, cs)
    out = []
    for site in sorted({c.site_code for c in cs}):
        here = [c for c in cs if c.site_code == site]
        located = [c for c in here if c.hh_id in pos]
        loose = [c for c in here if c.hh_id not in pos]
        parent = list(range(len(located)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(located)):
            for j in range(i + 1, len(located)):
                a, b = located[i], located[j]
                if a.hh_id == b.hh_id or _haversine_m(pos[a.hh_id], pos[b.hh_id]) <= radius_m:
                    parent[find(i)] = find(j)
        groups = defaultdict(list)
        for i, c in enumerate(located):
            groups[find(i)].append(c)
        if groups:
            out += [g + loose for g in groups.values()]
        elif loose:
            out.append(loose)
    return out


def water_links(db: Session, cs, today: date, days: int, radius_m: float):
    """Water samples from the cases' households or within radius_m of them, in the past `days` days."""
    from . import analytics
    pos = _positions(db, cs)
    sites = sorted({c.site_code for c in cs})
    out = []
    for s, positive, labs in analytics.sample_results(db, sites, today - timedelta(days=days)):
        near = s.hh_id in {c.hh_id for c in cs}
        if not near and s.lat is not None:
            near = any(_haversine_m((s.lat, s.lon), p) <= radius_m for p in pos.values())
        if near and (s.collected_on is None or s.collected_on <= today):
            out.append({"sample_id": s.sample_id, "hh_id": s.hh_id, "source": s.source, "collected_on": _iso(s.collected_on),
                        "result": None if positive is None else ("positive" if positive else "negative"),
                        "method": "NIO lab" if "nio_lab" in labs else "Aquadip©"})
    out.sort(key=lambda x: x["collected_on"] or "", reverse=True)
    out.sort(key=lambda x: x["result"] != "positive")
    return out


def _upsert_alert(db: Session, key, site, kind, severity, title, reason, send_to, response, case_ids, links=None):
    a = db.query(IdspAlert).filter_by(rule_key=key).one_or_none()
    ids = " ".join(str(i) for i in sorted(case_ids))
    if a:
        if a.status != "closed" and a.case_ids != ids:
            a.reason, a.case_ids, a.title = reason, ids, title
            if links is not None:
                a.links = links
        return 0
    db.add(IdspAlert(rule_key=key, site_code=site, kind=kind, severity=severity, title=title, reason=reason,
                     send_to=send_to, response=response, case_ids=ids, links=links or {}, status="open",
                     opened_at=datetime.utcnow()))
    db.flush()
    return 1


def generate_alerts(db: Session, codes, today: date | None = None) -> dict:
    """Early-warning alerts from VERIFIED cases. Unverified signals only create verification tasks."""
    today = today or date.today()
    th = thresholds(db)
    wk = today.isocalendar()
    wtag = f"{wk[0]}-W{wk[1]:02d}"
    R = th["cluster_radius_m"]
    n_new = 0
    horizon = today - timedelta(days=max(th["jaundice_days"], th["add_cluster_days"], th["lepto_days"],
                                         th["water_days"], 56))
    recent = (db.query(IdspCase).filter(IdspCase.site_code.in_(codes or [""]), IdspCase.status == "verified",
                                        IdspCase.first_reported >= horizon, IdspCase.first_reported <= today).all())

    def within(c, days):
        return c.first_reported and today - timedelta(days=days) <= c.first_reported <= today

    # 1. Diarrhoea and jaundice clusters
    for kind, syn, n_key, d_key, title, send_to, response in [
        ("add_cluster", {"lws", "lws_blood"}, "add_cluster_n", "add_cluster_days",
         "Cluster of acute diarrhoeal disease", "JPHN, MO", "Field visit and water sample within 48 hours"),
        ("jaundice_cluster", {"jaundice"}, "jaundice_n", "jaundice_days",
         "Cluster of acute jaundice", "MO, DSO", "Investigation and water source check"),
    ]:
        cs = [c for c in recent if c.syndrome in syn and within(c, th[d_key])]
        for grp in clusters(db, cs, R):
            if len(grp) < th[n_key]:
                continue
            site = grp[0].site_code
            links = water_links(db, grp, today, 30, th["water_radius_m"])
            pos = [w for w in links if w["result"] == "positive"]
            homes = sorted({c.hh_id for c in grp})
            reason = (f"{len(grp)} verified cases within {int(R)} m in {th[d_key]} days "
                      f"({', '.join(homes[:12])}{f' and {len(homes) - 12} more' if len(homes) > 12 else ''})")
            if pos:
                reason += f"; {len(pos)} positive water sample(s) within {int(th['water_radius_m'])} m"
            n_new += _upsert_alert(db, f"{kind}:{site}:{wtag}:{min(c.id for c in grp)}", site, kind, "high", title,
                                   reason, send_to, response,
                                   [c.id for c in grp], {"water": links})
    # 2. Single cases that need action the same day
    for c in recent:
        if not within(c, 14):
            continue
        if c.suspect == "cholera" or (c.syndrome == "lws_blood" and c.age is not None and c.age < 5):
            what = "Suspected cholera" if c.suspect == "cholera" else "Bloody diarrhoea in a child under 5"
            n_new += _upsert_alert(db, f"immediate:{c.id}", c.site_code, "immediate", "immediate",
                                   f"{what} at {c.hh_id}", f"Case {c.id} at {c.hh_id}, age {c.age if c.age is not None else 'not recorded'}, verified "
                                   f"{c.verified_on.strftime('%d %b') if c.verified_on else ''} by {c.verified_by}", "MO, DSO",
                                   "Investigate today", [c.id], {"water": water_links(db, [c], today, 30, th["water_radius_m"])})
        if (c.admitted or c.died) and (c.syndrome in WATER_BORNE or GROUP.get(c.syndrome) == "fever"):
            n_new += _upsert_alert(db, f"severe:{c.id}", c.site_code, "severe", "immediate",
                                   f"{'Death' if c.died else 'Hospital admission'}: {S_LABEL[c.syndrome].lower()}",
                                   f"Case {c.id} at {c.hh_id}", "MO, DSO", "Review the case today", [c.id])
    # 3. Leptospirosis signal per ward
    for code in codes:
        cs = [c for c in recent if c.site_code == code and within(c, th["lepto_days"]) and
              (c.suspect == "lepto" or c.p_diagnosis == "lepto")]
        if len(cs) >= th["lepto_n"]:
            n_new += _upsert_alert(db, f"lepto:{code}:{wtag}", code, "lepto", "high",
                                   "Leptospirosis signal", f"{len(cs)} suspected or diagnosed cases in "
                                   f"{th['lepto_days']} days", "MO, DSO", "Review prophylaxis for exposed people",
                                   [c.id for c in cs])
    # 4. Water: a positive sample from a case's household or close to it, with verified water-borne illness.
    #    (A positive sample alone is handled by the Observatory's water advisories and ASHA tasks, not repeated here.)
    for code in codes:
        ill = [c for c in recent if c.site_code == code and c.syndrome in WATER_BORNE and within(c, th["water_days"])]
        if not ill:
            continue
        links = water_links(db, ill, today, th["water_days"], th["water_radius_m"])
        positives = [w for w in links if w["result"] == "positive"]
        if not positives:
            continue
        samples = ", ".join(w["sample_id"] for w in positives[:6]) + (" …" if len(positives) > 6 else "")
        n_new += _upsert_alert(db, f"water_link:{code}:{wtag}", code, "water_link", "high",
                               "Contaminated water next to water-borne illness",
                               f"{len(positives)} positive sample(s) ({samples}) within {int(th['water_radius_m'])} m "
                               f"of a verified water-borne case; {len(ill)} such case(s) in this ward in "
                               f"{th['water_days']} days",
                               "JPHN, MO, ward member", "Household advice and active case search",
                               [c.id for c in ill], {"water": links})
    # 5. Rise above the ward's own baseline (water-borne, weekly)
    this_ws = week_start(today)
    for code in codes:
        weeks = Counter()
        hist = (db.query(IdspCase).filter(IdspCase.site_code == code, IdspCase.status == "verified",
                                          IdspCase.syndrome.in_(WATER_BORNE)).all())
        for c in hist:
            if c.first_reported:
                weeks[week_start(c.first_reported)] += 1
        first = min(weeks) if weeks else None
        if not first:
            continue
        prior = []
        w = first
        while w < this_ws:
            prior.append(weeks.get(w, 0))
            w += timedelta(days=7)
        if len(prior) < 8:
            continue
        mean, sd = statistics.mean(prior), statistics.pstdev(prior)
        now = weeks.get(this_ws, 0)
        if now >= 3 and now > mean + th["baseline_sd"] * sd:
            n_new += _upsert_alert(db, f"baseline:{code}:{wtag}", code, "baseline", "watch",
                                   "Water-borne illness above this ward's usual level",
                                   f"{now} cases this week; usual {mean:.1f} ± {sd:.1f} over {len(prior)} weeks",
                                   "DSO", "Review the trend with the MO", [])
    db.commit()
    return {"alerts_created": n_new}


def alert_rows(db: Session, codes, include_closed_days=30, today: date | None = None):
    today = today or date.today()
    since = datetime.combine(today - timedelta(days=include_closed_days), datetime.min.time())
    q = (db.query(IdspAlert).filter(IdspAlert.site_code.in_(codes or [""]))
         .filter((IdspAlert.status != "closed") | (IdspAlert.closed_at >= since)))
    order = {"immediate": 0, "high": 1, "watch": 2}
    rows = sorted(q.all(), key=lambda a: (a.status == "closed", order.get(a.severity, 3), -a.id))
    out = []
    for a in rows:
        out.append({"id": a.id, "site": a.site_code, "kind": a.kind, "severity": a.severity, "title": a.title,
                    "reason": a.reason, "send_to": a.send_to, "response": a.response, "status": a.status,
                    "case_ids": [int(x) for x in a.case_ids.split()], "water": (a.links or {}).get("water", [])[:8],
                    "opened_at": _iso(a.opened_at), "ack_by": a.ack_by, "ack_at": _iso(a.ack_at),
                    "closed_by": a.closed_by, "closed_at": _iso(a.closed_at), "action_taken": a.action_taken,
                    "hours_open": round(((a.closed_at or datetime.utcnow()) - a.opened_at).total_seconds() / 3600, 1)
                    if a.opened_at else None})
    return out


def act_on_alert(db: Session, a: IdspAlert, action: str, username: str, note: str | None = None):
    now = datetime.utcnow()
    if action == "acknowledge":
        if a.status == "closed":
            raise ValueError("This alert is already closed.")
        a.status, a.ack_by, a.ack_at = "acknowledged", a.ack_by or username, a.ack_at or now
    elif action == "close":
        if not (note or "").strip():
            raise ValueError("Say what was done before closing the alert.")
        a.ack_by, a.ack_at = a.ack_by or username, a.ack_at or now
        a.status, a.closed_by, a.closed_at, a.action_taken = "closed", username, now, note.strip()[:500]
    elif action == "reopen":
        a.status, a.closed_by, a.closed_at = "acknowledged" if a.ack_at else "open", None, None
    else:
        raise ValueError("Action must be acknowledge, close or reopen.")
    db.commit()


# ------------------------------------------------------------------ overview for the IDSP tab

def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def overview(db: Session, codes, ws: date, today: date | None = None):
    today = today or date.today()
    th = thresholds(db)
    allc = db.query(IdspCase).filter(IdspCase.site_code.in_(codes or [""])).all()
    verified = [c for c in allc if c.status == "verified"]
    we = ws + timedelta(days=6)
    in_week = [c for c in verified if c.first_reported and ws <= c.first_reported <= we]
    prev_ws = ws - timedelta(days=7)
    prev = [c for c in verified if c.first_reported and prev_ws <= c.first_reported < ws]
    open_signals = [c for c in allc if c.status == "unverified"]
    overdue = [c for c in open_signals if _due(c, th) and today > _due(c, th)]

    # How community reporting helps IDSP (past 90 days)
    since = today - timedelta(days=90)
    v90 = [c for c in verified if c.first_reported and c.first_reported >= since]
    community_first = [c for c in v90 if c.first_source in ("community", "camp")]
    community_only = [c for c in community_first if "idsp" not in c.sources.split()]
    lead = [(c.idsp_reported - c.first_reported).days for c in community_first
            if c.idsp_reported and c.first_reported and c.idsp_reported >= c.first_reported]
    checked = [c for c in allc if c.first_source in ("community", "camp") and c.first_reported and
               c.first_reported >= since and c.status != "unverified" and c.verified_on]
    on_time = [c for c in checked if (c.verified_on - c.first_reported).days * 24 <=
               (th["urgent_verify_hours"] if c.urgent else th["verify_hours"])]
    onset_to_report = [(c.first_reported - c.onset).days for c in v90 if c.onset and c.first_reported
                       and c.first_reported >= c.onset]

    # alerts: response times (past 90 days)
    alerts = db.query(IdspAlert).filter(IdspAlert.site_code.in_(codes or [""])).all()
    a90 = [a for a in alerts if a.opened_at and a.opened_at.date() >= since]
    ack_h = [(a.ack_at - a.opened_at).total_seconds() / 3600 for a in a90 if a.ack_at]
    closed48 = [a for a in a90 if a.closed_at and (a.closed_at - a.opened_at).total_seconds() <= 48 * 3600]

    # trend: verified cases per IDSP week by syndrome group, past 12 weeks
    trend = []
    for i in range(11, -1, -1):
        w0 = ws - timedelta(days=7 * i)
        grp = Counter(GROUP.get(c.syndrome, "other") for c in verified
                      if c.first_reported and w0 <= c.first_reported <= w0 + timedelta(days=6))
        trend.append({"week_start": w0.isoformat(), "week": w0.isocalendar()[1],
                      **{g: grp.get(g, 0) for g in GROUP_LABEL}})

    # map: households with cases (past 30 days) and water samples
    from . import analytics
    map_since = today - timedelta(days=30)
    recent = [c for c in allc if c.first_reported and c.first_reported >= map_since and c.status in ("verified", "unverified")]
    pos = _positions(db, recent)
    points = [{"id": c.id, "hh_id": c.hh_id, "site": c.site_code, "lat": pos[c.hh_id][0], "lon": pos[c.hh_id][1],
               "group": GROUP.get(c.syndrome, "other"), "status": c.status} for c in recent if c.hh_id in pos]
    water = [{"sample_id": s.sample_id, "lat": s.lat, "lon": s.lon, "positive": p}
             for s, p, _ in analytics.sample_results(db, codes, map_since) if s.lat is not None and p is not None]
    sites = [{"code": s.code, "label": s.label, "lat": s.lat, "lon": s.lon} for s in db.query(Site)
             .filter(Site.code.in_(codes or [""])) if s.lat is not None]

    # productive days lost, verified water-borne episodes (each counted once), past 12 months
    year = [c for c in verified if c.syndrome in WATER_BORNE and c.first_reported and
            c.first_reported >= today - timedelta(days=365)]
    wk = weekly(db, codes, ws, today)
    return {
        "week": {"start": ws.isoformat(), "end": we.isoformat(), "label": week_label(ws), "complete": today > we},
        "kpi": {
            "verified_week": len(in_week), "verified_prev_week": len(prev),
            "awaiting": len(open_signals), "overdue": len(overdue),
            "urgent_waiting": sum(1 for c in open_signals if c.urgent),
            "alerts_open": sum(1 for a in alerts if a.status != "closed"),
            "completeness": wk["completeness"],
            "median_onset_to_report_days": _median(onset_to_report),
        },
        "community": {
            "verified_90d": len(v90), "first_flagged_by_community": len(community_first),
            "share": round(len(community_first) / len(v90), 3) if v90 else None,
            "found_only_through_community": len(community_only),
            "median_lead_days": _median(lead), "lead_pairs": len(lead),
            "verified_on_time_share": round(len(on_time) / len(checked), 3) if checked else None,
            "signals_checked": len(checked),
            "not_cases": sum(1 for c in checked if c.status == "not_case"),
        },
        "response": {"alerts_90d": len(a90), "median_hours_to_acknowledge": _median(ack_h),
                     "closed_within_48h_share": round(len(closed48) / len(a90), 3) if a90 else None},
        "trend": trend, "groups": GROUP_LABEL,
        "map": {"cases": points, "water": water, "sites": sites,
                "cases_without_location": sum(1 for c in recent if c.hh_id not in pos)},
        "workdays": {"episodes": len(year), "work_days": sum(c.work_days or 0 for c in year),
                     "carer_days": sum(c.carer_days or 0 for c in year),
                     "school_days": sum(c.school_days or 0 for c in year)},
        "weekly": wk,
    }


def meta():
    return {"s_syndromes": [{"code": k, "label": v} for k, v in S_SYNDROMES],
            "p_diseases": [{"code": k, "label": v} for k, v in P_DISEASES],
            "lab_tests": [{"code": k, "label": v} for k, v in LAB_TESTS],
            "thresholds": [{"key": k, "default": d, "label": label} for k, d, label in THRESHOLDS]}
