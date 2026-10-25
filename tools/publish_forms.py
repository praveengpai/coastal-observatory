"""Publish every form in forms/dist to ODK Central and give the right phone accounts access.

    docker compose exec app python -m tools.publish_forms

Uses the Observatory's sync account (a Project Manager), so no one types an admin password.
Order matters: camp registration goes first because it creates the "persons" household list that the
report forms read. sites.csv is attached wherever a form asks for it; persons.csv is linked to the list.
Phone accounts named in ACCESS are created if missing. Re-running is safe: forms get a new version.
"""
from datetime import datetime, timezone
from pathlib import Path

from app import reports, sync_odk
from app.db import SessionLocal, init_db
from app.models import ReportForm

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["obs_camp_registration", "obs_camp_station", "obs_household_visit", "obs_water_sample",
         "obs_report_diarrhoea", "obs_report_health", "obs_report_onehealth"]
FIELD, WARD, TRAINING, NIO = "Field team (ASHA / volunteer)", "Ward members", "Training phone", "NIO water sampling"
ACCESS = {  # report forms only; the camp forms keep the access set up by setup_central
    "obs_report_diarrhoea": [FIELD, WARD, TRAINING],
    "obs_report_health": [FIELD, WARD, TRAINING],
    "obs_report_onehealth": [FIELD, WARD, NIO, TRAINING],
}


def main():
    c = sync_odk.Central()
    base = f"{c.url}/v1/projects/{c.project}"
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    sites = (ROOT / "forms" / "sites.csv").read_bytes()

    users = {u["name"]: u["id"] for u in c.app_users()}
    for name in {n for names in ACCESS.values() for n in names} - set(users):
        r = c.s.post(f"{base}/app-users", json={"displayName": name}, timeout=30)
        r.raise_for_status()
        users[name] = r.json()["id"]
        print(f"  created phone account: {name}")
    role_id = {x["system"]: x["id"] for x in c.s.get(f"{c.url}/v1/roles", timeout=30).json()}["app-user"]

    for form_id in ORDER:
        xlsx = (ROOT / "forms" / "dist" / f"{form_id}.xlsx").read_bytes()
        headers = {"Content-Type": sync_odk.XLSX, "X-XlsForm-FormId-Fallback": form_id}
        r = c.s.post(f"{base}/forms?ignoreWarnings=true", data=xlsx, headers=headers, timeout=120)
        if r.status_code == 409:
            r = c.s.post(f"{base}/forms/{form_id}/draft?ignoreWarnings=true", data=xlsx, headers=headers, timeout=120)
        if r.status_code >= 400:
            raise SystemExit(f"{form_id}: ODK Central refused the form ({r.status_code}): {r.text[:400]}")
        atts = c.s.get(f"{base}/forms/{form_id}/draft/attachments", timeout=30).json()
        for a in atts:
            if a["name"] == "sites.csv":
                c.s.post(f"{base}/forms/{form_id}/draft/attachments/sites.csv", data=sites,
                         headers={"Content-Type": "text/csv"}, timeout=60).raise_for_status()
            elif a["name"] == "persons.csv" and not a.get("datasetExists"):
                c.s.patch(f"{base}/forms/{form_id}/draft/attachments/persons.csv", json={"dataset": True}, timeout=30)
        r = c.s.post(f"{base}/forms/{form_id}/draft/publish", params={"version": version}, timeout=60)
        if r.status_code >= 400:
            raise SystemExit(f"{form_id}: publishing failed ({r.status_code}): {r.text[:400]}")
        for name in ACCESS.get(form_id, []):
            r = c.s.post(f"{base}/forms/{form_id}/assignments/{role_id}/{users[name]}", timeout=30)
            if r.status_code not in (200, 409):
                raise SystemExit(f"{form_id}: could not give {name} access: {r.text[:200]}")
        print(f"  published {form_id} (version {version})" +
              (f" → {', '.join(ACCESS[form_id])}" if form_id in ACCESS else ""))

    init_db()
    db = SessionLocal()
    reports.ensure_defaults(db)
    for form_id, names in ACCESS.items():
        f = db.get(ReportForm, form_id)
        f.phone_groups = ", ".join(names)
    db.commit()
    db.close()
    print("Done. Phones get the new forms when they next refresh (ODK Collect: Download form).")
    print("Ward members' phone QR: ODK Central → this project → App Users → Ward members.")


if __name__ == "__main__":
    main()
