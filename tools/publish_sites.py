"""Publish a new sites.csv to all four forms on ODK Central, without editing the forms.

    python -m tools.publish_sites forms/sites.csv

For each form: creates a draft, replaces the sites.csv attachment, publishes it with a new
version string. Phones pick up the new site list the next time they fetch blank forms.
Also loads the sites into the Observatory database (same file, same codes).
"""
import csv
import sys
from datetime import datetime

from app.db import SessionLocal, init_db
from app.models import Site
from app.sync_odk import INGESTERS, Central

REQUIRED = {"name", "label", "site_type"}
TYPES = {"village", "colony", "flats", "ward", "test"}


def check(path):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    missing = REQUIRED - set(rows[0].keys() if rows else [])
    if missing:
        raise SystemExit(f"sites.csv is missing columns: {', '.join(sorted(missing))}")
    codes = set()
    for i, r in enumerate(rows, start=2):
        code = r["name"].strip()
        if not (code.isalnum() and code.isupper() and 2 <= len(code) <= 4):
            raise SystemExit(f"Row {i}: site code '{code}' must be 2–4 capital letters or digits (it prints on stickers).")
        if code in codes:
            raise SystemExit(f"Row {i}: duplicate site code {code}.")
        if r["site_type"].strip() not in TYPES:
            raise SystemExit(f"Row {i}: site_type must be one of {', '.join(sorted(TYPES))}.")
        codes.add(code)
    return rows


def main(path):
    rows = check(path)
    init_db()
    db = SessionLocal()
    for r in rows:
        f = lambda k: float(r[k]) if r.get(k, "").strip() else None  # noqa: E731
        db.merge(Site(code=r["name"].strip(), label=r["label"].strip(), site_type=r["site_type"].strip(),
                      lat=f("lat"), lon=f("lon"), active=True))
    db.commit()
    print(f"{len(rows)} sites loaded into the Observatory database.")
    central = Central()
    version = datetime.now().strftime("%Y%m%d%H%M")
    data = open(path, "rb").read()
    base = f"{central.url}/v1/projects/{central.project}/forms"
    for form_id in INGESTERS:
        central.s.post(f"{base}/{form_id}/draft").raise_for_status()
        central.s.post(f"{base}/{form_id}/draft/attachments/sites.csv", data=data,
                       headers={"Content-Type": "text/csv"}).raise_for_status()
        central.s.post(f"{base}/{form_id}/draft/publish", params={"version": version}).raise_for_status()
        print(f"{form_id}: published with new sites list (version {version}).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
