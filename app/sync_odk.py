"""Pulls submissions from ODK Central and loads them into the Observatory database.

Each form has an `ingest_*` function that takes one flattened submission (a dict of
field name -> value). They are idempotent: re-running a sync never duplicates rows.
"""
from datetime import date, datetime, timezone

import requests
from sqlalchemy.orm import Session

from . import config
from .models import (HomeVisit, Household, HouseholdSurvey, LabResult, Person, PersonPII, Registration,
                     Site, StationRecord, SyncState, WaterSample)

PII_FIELDS = {"name", "phone", "home_address"}
DR_ORDER = ["none", "ungradable", "mild", "moderate", "severe", "pdr"]


# ------------------------------------------------------------------ helpers

def flatten(sub: dict) -> dict:
    """Merge nested ODK groups into one dict. GeoJSON points are kept as values."""
    out = {}

    def walk(d):
        for k, v in d.items():
            if k == "__system":
                out["_submitted_at"] = v.get("submissionDate")
                out["_review_state"] = v.get("reviewState")
                continue
            if isinstance(v, dict) and not ("type" in v and "coordinates" in v):
                walk(v)
            else:
                out[k] = v
    walk(sub)
    out["_instance_id"] = sub.get("__id") or out.get("instanceID")
    return out


def _int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bool(v):
    return None if v in (None, "") else v == "yes"


def _date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _point(v):
    if isinstance(v, dict) and v.get("coordinates"):
        lon, lat = v["coordinates"][0], v["coordinates"][1]
        return lat, lon
    return None, None


def _site(db: Session, code: str):
    if code and not db.get(Site, code):
        db.add(Site(code=code, label=code, site_type="unknown"))
        db.flush()


def _household(db: Session, hh_id: str, site: str, lat=None, lon=None):
    if not hh_id:
        return
    hh = db.get(Household, hh_id)
    if not hh:
        db.add(Household(hh_id=hh_id, site_code=site, lat=lat, lon=lon))
        db.flush()
    elif lat and not hh.lat:
        hh.lat, hh.lon = lat, lon


# ------------------------------------------------------------------ form ingesters

def ingest_registration(db: Session, f: dict):
    iid, site, pid, hh = f["_instance_id"], f.get("camp_site"), f.get("person_id"), f.get("hh_id")
    _site(db, site)
    on = _date(f.get("today"))
    _household(db, hh, site)
    consent = f.get("consent_research") == "yes"
    person = db.get(Person, pid) or Person(person_id=pid, site_code=site)
    person.hh_id, person.sex, person.age = hh, f.get("sex"), _int(f.get("age"))
    person.resident, person.consent_research = f.get("resident") != "no", consent
    person.registered_on = person.registered_on or on
    db.merge(person)
    db.merge(PersonPII(person_id=pid, name=f.get("name"), phone=f.get("phone"),
                       contact_ok=f.get("contact_ok") == "yes", home_address=f.get("home_address")))
    data = {k: v for k, v in f.items() if k not in PII_FIELDS}
    db.merge(Registration(
        instance_id=iid, person_id=pid, hh_id=hh, site_code=site, camp_id=f.get("camp_id"),
        submitted_at=_dt(f.get("_submitted_at")), collected_on=on, age=_int(f.get("age")), sex=f.get("sex"),
        occupation=f.get("occupation"), symptoms=f.get("sx") if consent else None,
        conditions=f.get("conditions"), tobacco=f.get("tobacco"), wade=_bool(f.get("wade")) if consent else None,
        data=data))
    if consent and f.get("first_member") == "yes" and f.get("hh_size") not in (None, ""):
        db.merge(HouseholdSurvey(
            instance_id=iid, hh_id=hh, site_code=site, collected_on=on, hh_size=_int(f.get("hh_size")),
            hh_n60=_int(f.get("hh_n60")), hh_n5=_int(f.get("hh_n5")), water_drink=f.get("water_drink"),
            treat=f.get("treat"), storage=f.get("storage"), salty=f.get("salty"), toilet=f.get("toilet"),
            septic_dist=f.get("septic_dist"), flood=_bool(f.get("flood")), flood_times=_int(f.get("flood_times")),
            animals=f.get("animals"), rats=f.get("rats"), tds=_int(f.get("tds"))))


def ingest_station(db: Session, f: dict):
    site = f.get("camp_site")
    _site(db, site)
    station = f.get("role")
    dr = [x for x in (f.get("dr_r"), f.get("dr_l")) if x in DR_ORDER]
    referral = None
    for key in ("doc_referral", "eye_referral", "dent_referral"):
        if f.get(key) and f.get(key) != "none":
            referral = f.get(key)
    db.merge(StationRecord(
        instance_id=f["_instance_id"], person_id=f.get("person_id"), site_code=site, camp_id=f.get("camp_id"),
        station=station, collected_on=_date(f.get("today")), age=_int(f.get("age")),
        sbp=_float(f.get("sbp")), dbp=_float(f.get("dbp")), glucose=_float(f.get("glucose")), bmi=_float(f.get("bmi")),
        u_protein=f.get("u_protein"), u_sg=_float(f.get("u_sg")), hb=_float(f.get("hb")),
        va_r=f.get("va_r"), va_l=f.get("va_l"), cataract=f.get("cataract"),
        dr_worst=max(dr, key=DR_ORDER.index) if dr else None,
        caries_n=_int(f.get("caries_n")), lesion=f.get("lesion"),
        alone=_bool(f.get("alone")), evac=_bool(f.get("evac")), heat_sx=_bool(f.get("heat_sx")),
        falls=_int(f.get("falls")), cfs=_int(f.get("cfs")), minicog=_int(f.get("minicog_score")),
        phq2=_int(f.get("phq2_score")), referral=referral, followup=_bool(f.get("followup")),
        data={k: v for k, v in f.items() if k not in PII_FIELDS}))


def ingest_home_visit(db: Session, f: dict):
    site, hh = f.get("camp_site"), f.get("hh_id")
    _site(db, site)
    _household(db, hh, site)
    n = lambda k: _int(f.get(k)) or 0  # noqa: E731
    db.merge(HomeVisit(
        instance_id=f["_instance_id"], hh_id=hh, site_code=site, visit_on=_date(f.get("today")), role=f.get("role"),
        reason=f.get("reason"), n_diarrhoea=n("n_diarrhoea"), n_diarrhoea_u5=n("n_diarrhoea_u5"),
        n_fever=n("n_fever"), n_jaundice=n("n_jaundice"), n_skin=n("n_skin"), n_eye=n("n_eye"),
        n_wound=n("n_wound"), n_heat=n("n_heat"), n_hosp=n("n_hosp"), ref_person=f.get("ref_person"),
        ref_status=f.get("ref_status"), eld_evac=_bool(f.get("eld_evac")), advice=f.get("advice")))


def ingest_water_sample(db: Session, f: dict):
    site, hh = f.get("camp_site"), f.get("hh_id") if f.get("point_type") == "household" else None
    _site(db, site)
    lat, lon = _point(f.get("gps"))
    _household(db, hh, site, lat, lon)
    sid = f.get("sample_id")
    db.merge(WaterSample(
        sample_id=sid, instance_id=f["_instance_id"], site_code=site, hh_id=hh, point_type=f.get("point_type"),
        source=f.get("source"), taken_at=f.get("taken_at"), collected_on=_date(f.get("today")), lat=lat, lon=lon,
        tds=_int(f.get("tds")), water_temp=_float(f.get("water_temp")), rain_48h=_bool(f.get("rain_48h")),
        flooded_7d=_bool(f.get("flooded_7d")), to_lab=_bool(f.get("to_lab"))))
    if f.get("aquadip") in ("pos", "neg"):
        upsert_lab(db, sid, "aquadip", positive=f["aquadip"] == "pos", tested_on=_date(f.get("today")))


def upsert_lab(db: Session, sample_id: str, method: str, **values):
    row = db.query(LabResult).filter_by(sample_id=sample_id, method=method).one_or_none()
    if not row:
        row = LabResult(sample_id=sample_id, method=method)
        db.add(row)
    for k, v in values.items():
        setattr(row, k, v)


INGESTERS = {
    "obs_camp_registration": ingest_registration,
    "obs_camp_station": ingest_station,
    "obs_household_visit": ingest_home_visit,
    "obs_water_sample": ingest_water_sample,
}


def ingest(db: Session, form_id: str, submission: dict):
    f = flatten(submission)
    if f.get("_review_state") == "rejected":
        return False
    INGESTERS[form_id](db, f)
    return True


# ------------------------------------------------------------------ ODK Central client

class Central:
    def __init__(self, url=None, email=None, password=None, project=None):
        self.url = (url or config.ODK_URL).rstrip("/")
        self.project = project or config.ODK_PROJECT_ID
        self.s = requests.Session()
        r = self.s.post(f"{self.url}/v1/sessions",
                        json={"email": email or config.ODK_EMAIL, "password": password or config.ODK_PASSWORD},
                        timeout=30)
        r.raise_for_status()
        self.s.headers["Authorization"] = f"Bearer {r.json()['token']}"

    def submissions(self, form_id: str, since: str | None = None, page: int = 500):
        skip = 0
        params = {"$top": page}
        if since:
            params["$filter"] = f"__system/submissionDate gt {since}"
        while True:
            params["$skip"] = skip
            r = self.s.get(f"{self.url}/v1/projects/{self.project}/forms/{form_id}.svc/Submissions",
                           params=params, timeout=60)
            r.raise_for_status()
            rows = r.json().get("value", [])
            yield from rows
            if len(rows) < page:
                break
            skip += page


def run_sync(db: Session, central: Central | None = None) -> dict:
    """Pull new submissions for all four forms. Returns counts per form."""
    central = central or Central()
    counts = {}
    for form_id in INGESTERS:
        state = db.get(SyncState, form_id) or SyncState(form_id=form_id, count=0)
        n, latest = 0, state.last_submission
        for sub in central.submissions(form_id, since=state.last_submission):
            if ingest(db, form_id, sub):
                n += 1
            sd = sub.get("__system", {}).get("submissionDate")
            if sd and (latest is None or sd > latest):
                latest = sd
        state.last_submission, state.last_run, state.count = latest, datetime.utcnow(), (state.count or 0) + n
        db.merge(state)
        db.commit()
        counts[form_id] = n
    return counts
