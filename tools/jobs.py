"""Scheduled jobs, run from cron inside the app container (see deploy/crontab).

    python -m tools.jobs sync      # pull new ODK submissions (every 15 minutes)
    python -m tools.jobs weather   # refresh the 7-day forecast, and IMD once access is set up (twice a day)
    python -m tools.jobs rules     # draft advisories and ward decisions; IDSP signals and alerts (hourly)
"""
import sys

from app import analytics, config, idsp, imd, rules, sources
from app.db import SessionLocal, init_db

if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else ""
    init_db()
    db = SessionLocal()
    if job == "sync":
        if config.FORM_SERVER == "odk" and not config.ODK_URL:
            print("ODK Central not configured")
        else:
            print(sources.fetch(db, "odk"))
    elif job == "weather":
        print(sources.fetch(db, "open_meteo"))
        if imd.enabled():
            try:
                print(sources.fetch(db, "imd"))
            except imd.NotReady as exc:
                print(exc)
    elif job == "rules":
        codes = [s.code for s in analytics.site_codes(db)]
        print(rules.generate(db, codes))
        print("IDSP signals:", idsp.capture_signals(db), idsp.generate_alerts(db, codes))
    else:
        raise SystemExit(__doc__)
