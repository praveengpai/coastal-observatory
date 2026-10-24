"""Sync from KoboToolbox (free hosted form server) instead of ODK Central.

Set in .env:
    OBS_FORM_SERVER=kobo
    OBS_KOBO_URL=https://kf.kobotoolbox.org          (or https://eu.kobotoolbox.org)
    OBS_KOBO_TOKEN=<API token from Kobo: Account settings → Security>
    OBS_KOBO_ASSETS=obs_camp_registration=aBc123,obs_camp_station=dEf456,obs_household_visit=gHi789,obs_water_sample=jKl012
The same XLSForms and sites.csv are used; field names are identical, so the ingest code is shared.
"""
import json
import os
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from .models import SyncState
from .sync_odk import INGESTERS

GEO_FIELDS = {"gps", "camp_gps"}


def flatten_kobo(rec: dict) -> dict:
    """Kobo keys look like 'camp/camp_site'; keep the last segment, convert geopoints to GeoJSON."""
    out = {}
    for k, v in rec.items():
        name = k.split("/")[-1]
        if name in GEO_FIELDS and isinstance(v, str) and v.strip():
            parts = v.split()
            if len(parts) >= 2:
                v = {"type": "Point", "coordinates": [float(parts[1]), float(parts[0])]}
        out.setdefault(name, v)
    out["_instance_id"] = rec.get("meta/instanceID") or (f"uuid:{rec['_uuid']}" if rec.get("_uuid") else None)
    out["_submitted_at"] = rec.get("_submission_time")
    status = rec.get("_validation_status") or {}
    out["_review_state"] = "rejected" if status.get("uid") == "validation_status_not_approved" else None
    return out


def ingest_kobo(db: Session, form_id: str, rec: dict) -> bool:
    f = flatten_kobo(rec)
    if f["_review_state"] == "rejected":
        return False
    INGESTERS[form_id](db, f)
    return True


def assets() -> dict:
    raw = os.environ.get("OBS_KOBO_ASSETS", "")
    return dict(pair.split("=", 1) for pair in raw.split(",") if "=" in pair)


def run_sync(db: Session) -> dict:
    url = os.environ.get("OBS_KOBO_URL", "https://kf.kobotoolbox.org").rstrip("/")
    headers = {"Authorization": f"Token {os.environ['OBS_KOBO_TOKEN']}"}
    counts = {}
    for form_id, uid in assets().items():
        if form_id not in INGESTERS:
            continue
        state = db.get(SyncState, form_id) or SyncState(form_id=form_id, count=0)
        params = {"format": "json", "limit": 1000, "sort": json.dumps({"_submission_time": 1})}
        if state.last_submission:
            params["query"] = json.dumps({"_submission_time": {"$gt": state.last_submission}})
        next_url, n, latest = f"{url}/api/v2/assets/{uid}/data/", 0, state.last_submission
        while next_url:
            r = requests.get(next_url, headers=headers, params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            for rec in body.get("results", []):
                if ingest_kobo(db, form_id, rec):
                    n += 1
                st = rec.get("_submission_time")
                if st and (latest is None or st > latest):
                    latest = st
            next_url, params = body.get("next"), None
        state.last_submission, state.last_run, state.count = latest, datetime.utcnow(), (state.count or 0) + n
        db.merge(state)
        db.commit()
        counts[form_id] = n
    return counts
