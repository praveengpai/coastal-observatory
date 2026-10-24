"""Scheduled jobs, run from cron inside the app container (see deploy/crontab).

    python -m tools.jobs sync      # pull new ODK submissions (every 15 minutes)
    python -m tools.jobs weather   # refresh the 7-day forecast (twice a day)
    python -m tools.jobs rules     # draft advisories and ward decisions (hourly)
"""
import sys

from app import analytics, config, rules, sync_odk, weather
from app.db import SessionLocal, init_db

if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else ""
    init_db()
    db = SessionLocal()
    if job == "sync":
        if config.FORM_SERVER == "kobo":
            from app import sync_kobo
            print(sync_kobo.run_sync(db))
        else:
            print(sync_odk.run_sync(db) if config.ODK_URL else "ODK Central not configured")
    elif job == "weather":
        print(weather.fetch_forecast(db), "days")
    elif job == "rules":
        print(rules.generate(db, [s.code for s in analytics.site_codes(db)]))
    else:
        raise SystemExit(__doc__)
