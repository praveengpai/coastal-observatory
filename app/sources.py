"""Outside data sources: what each one is, when it last answered, and a way to fetch it now.

Keys and passwords live only in the server's .env file, never in the database or a web form.
The Admin tab shows whether each key is present, never its value.
"""
import os
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import config, imd, translate, weather
from .models import SourceStatus, SyncState, Weather

SOURCES = [
    {"key": "open_meteo", "name": "Open-Meteo weather forecast", "what": "7-day rain, temperature and humidity for Kochi",
     "schedule": "Twice a day", "key_env": None, "fetch": True},
    {"key": "imd", "name": "IMD (India Meteorological Department)",
     "what": "Official district warnings and rainfall, once IMD grants API access", "schedule": "Every 3 hours",
     "key_env": "OBS_IMD_API_KEY", "fetch": True},
    {"key": "tides", "name": "Tide table", "what": "Daily high tide, uploaded by NIO as a CSV on the Scientist tab",
     "schedule": "Uploaded by hand", "key_env": None, "fetch": False},
    {"key": "odk", "name": "ODK Central (field forms)", "what": "Camp, household, water and report forms from the phones",
     "schedule": "Every 15 minutes", "key_env": "OBS_ODK_PASSWORD", "fetch": True},
    {"key": "sarvam", "name": "Sarvam AI translation", "what": "English to Malayalam for messages the team writes",
     "schedule": "When a message is saved", "key_env": "OBS_SARVAM_API_KEY", "fetch": False},
]


def record(db: Session, key: str, ok: bool, detail: str | None = None, error: str | None = None):
    row = db.get(SourceStatus, key) or SourceStatus(key=key)
    now = datetime.utcnow()
    row.last_attempt = now
    if ok:
        row.last_ok, row.last_error, row.detail = now, None, (detail or "")[:300]
    else:
        row.last_error = (error or "Failed")[:300]
    db.merge(row)
    db.commit()


def _iso(v):
    return v.isoformat() if v else None


def status(db: Session):
    out = []
    for s in SOURCES:
        row = db.get(SourceStatus, s["key"])
        item = {k: s[k] for k in ("key", "name", "what", "schedule", "fetch")}
        item["needs_key"] = bool(s["key_env"])
        item["key_present"] = bool(os.environ.get(s["key_env"])) if s["key_env"] else None
        item["last_ok"] = _iso(row.last_ok) if row else None
        item["last_attempt"] = _iso(row.last_attempt) if row else None
        item["last_error"] = row.last_error if row else None
        item["detail"] = row.detail if row else None
        if s["key"] == "open_meteo":
            last_day = db.query(func.max(Weather.day)).filter(Weather.rain_mm.isnot(None)).scalar()
            item["coverage"] = f"Forecast up to {last_day}" if last_day else "No forecast yet"
        elif s["key"] == "tides":
            last_day = db.query(func.max(Weather.day)).filter(Weather.tide_max_m.isnot(None)).scalar()
            item["coverage"] = f"Tides up to {last_day}" if last_day else "No tide table yet"
        elif s["key"] == "odk":
            runs = [x.last_run for x in db.query(SyncState) if x.last_run]
            item["coverage"] = f"Last sync {max(runs).isoformat(timespec='minutes')} UTC" if runs else "Not synced yet"
            item["key_present"] = bool(config.ODK_URL and config.ODK_EMAIL and config.ODK_PASSWORD) \
                if config.FORM_SERVER == "odk" else bool(os.environ.get("OBS_KOBO_TOKEN"))
        elif s["key"] == "sarvam":
            item["key_present"] = translate.enabled()
            item["coverage"] = f"Model {translate.MODEL}"
        elif s["key"] == "imd":
            item["coverage"] = "Waiting for IMD API access" if not imd.enabled() else (row.detail if row else "")
        out.append(item)
    return out


def fetch(db: Session, key: str):
    """Fetch one source now. Returns a short result; records success or failure for the panel."""
    try:
        if key == "open_meteo":
            n = weather.fetch_forecast(db)
            result = f"{n} days of forecast"
        elif key == "imd":
            result = imd.fetch(db)
        elif key == "odk":
            if config.FORM_SERVER == "kobo":
                from . import sync_kobo
                counts = sync_kobo.run_sync(db)
            else:
                if not config.ODK_URL:
                    raise RuntimeError("ODK Central is not configured on the server.")
                from . import sync_odk
                counts = sync_odk.run_sync(db)
            result = f"{sum(v for v in counts.values() if isinstance(v, int))} new submissions"
        else:
            raise ValueError("This source cannot be fetched from here.")
    except Exception as exc:  # recorded for the panel, then reported to the caller
        record(db, key, False, error=str(exc))
        raise
    record(db, key, True, detail=result)
    return result
