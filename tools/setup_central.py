"""One-time setup of ODK Central for the Observatory. Run inside the app container:

    docker compose exec app python -m tools.setup_central https://odk.example.org

Asks for the ODK Central admin email and password (typed by a person, never stored), then:
  1. creates the project "Coastal One Health Observatory" (or reuses it)
  2. uploads and publishes the four forms with forms/sites.csv attached
  3. creates a sync web user (Project Manager) with a random password for the Observatory
  4. creates phone accounts (App Users) for each role, with access to the right forms
  5. loads sites.csv into the Observatory database
Prints the OBS_ODK_* lines to add to .env.
"""
import csv
import getpass
import secrets
import sys
from datetime import datetime
from pathlib import Path

import requests

from app.db import SessionLocal, init_db
from app.models import Site

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "Coastal One Health Observatory"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMS = ["obs_camp_registration", "obs_camp_station", "obs_household_visit", "obs_water_sample"]
APP_USERS = {
    "Camp welcome desk": ["obs_camp_registration"],
    "Camp station": ["obs_camp_station"],
    "Field team (ASHA / volunteer)": ["obs_household_visit", "obs_water_sample", "obs_camp_registration"],
    "NIO water sampling": ["obs_water_sample"],
    "Training phone": FORMS,
}


def main(url):
    url = url.rstrip("/")
    s = requests.Session()
    email = input("ODK Central admin email: ").strip()
    pw = getpass.getpass("ODK Central admin password: ")
    r = s.post(f"{url}/v1/sessions", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    del pw

    def ok(resp, what):
        if resp.status_code >= 400:
            raise SystemExit(f"{what} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json() if resp.content else {}

    # 1. project
    projects = ok(s.get(f"{url}/v1/projects", timeout=30), "List projects")
    project = next((p for p in projects if p["name"] == PROJECT), None)
    if not project:
        project = ok(s.post(f"{url}/v1/projects", json={"name": PROJECT}, timeout=30), "Create project")
    pid = project["id"]
    print(f"Project {PROJECT} (id {pid})")

    # 2. forms
    sites_csv = (ROOT / "forms" / "sites.csv").read_bytes()
    version = datetime.now().strftime("%Y%m%d%H%M")
    base = f"{url}/v1/projects/{pid}/forms"
    for form_id in FORMS:
        xlsx = (ROOT / "forms" / "dist" / f"{form_id}.xlsx").read_bytes()
        headers = {"Content-Type": XLSX, "X-XlsForm-FormId-Fallback": form_id}
        r = s.post(f"{base}?ignoreWarnings=true", data=xlsx, headers=headers, timeout=120)
        if r.status_code == 409:   # form exists: upload as a new draft
            r = s.post(f"{base}/{form_id}/draft?ignoreWarnings=true", data=xlsx, headers=headers, timeout=120)
        ok(r, f"Upload {form_id}")
        ok(s.post(f"{base}/{form_id}/draft/attachments/sites.csv", data=sites_csv,
                  headers={"Content-Type": "text/csv"}, timeout=60), f"Attach sites.csv to {form_id}")
        ok(s.post(f"{base}/{form_id}/draft/publish", params={"version": version}, timeout=60), f"Publish {form_id}")
        print(f"  published {form_id} (version {version})")

    roles = {r["system"]: r["id"] for r in ok(s.get(f"{url}/v1/roles", timeout=30), "List roles")}

    # 3. sync user
    host = url.split("//", 1)[-1]
    sync_email = f"observatory-sync@{host}"
    sync_pw = secrets.token_urlsafe(24)
    users = ok(s.get(f"{url}/v1/users", params={"q": sync_email}, timeout=30), "Find sync user")
    user = next((u for u in users if u.get("email") == sync_email), None)
    if user:
        print("  sync user already exists (its password is already in .env; reset it in Central if lost)")
        sync_pw = None
    else:
        user = ok(s.post(f"{url}/v1/users", json={"email": sync_email, "password": sync_pw}, timeout=30), "Create sync user")
        print(f"  created sync user {sync_email}")
    r = s.post(f"{url}/v1/projects/{pid}/assignments/{roles['manager']}/{user['id']}", timeout=30)
    if r.status_code not in (200, 409):
        ok(r, "Assign sync user")

    # 4. phone accounts
    existing = {a["displayName"]: a for a in ok(s.get(f"{url}/v1/projects/{pid}/app-users", timeout=30), "List app users")}
    for name, forms in APP_USERS.items():
        au = existing.get(name) or ok(s.post(f"{url}/v1/projects/{pid}/app-users", json={"displayName": name}, timeout=30),
                                      f"Create app user {name}")
        for form_id in forms:
            r = s.post(f"{base}/{form_id}/assignments/{roles['app-user']}/{au['id']}", timeout=30)
            if r.status_code not in (200, 409):
                ok(r, f"Give {name} access to {form_id}")
        print(f"  phone account: {name} → {', '.join(forms)}")

    # 5. sites into the Observatory database
    init_db()
    db = SessionLocal()
    rows = list(csv.DictReader(sites_csv.decode("utf-8-sig").splitlines()))
    for row in rows:
        f = lambda k: float(row[k]) if row.get(k, "").strip() else None  # noqa: E731
        db.merge(Site(code=row["name"].strip(), label=row["label"].strip(), site_type=row["site_type"].strip(),
                      lat=f("lat"), lon=f("lon"), active=True))
    db.commit()
    print(f"  {len(rows)} site(s) loaded into the Observatory")

    lines = [f"OBS_ODK_URL={url}", f"OBS_ODK_PROJECT_ID={pid}", f"OBS_ODK_EMAIL={sync_email}"]
    if sync_pw:
        lines.append(f"OBS_ODK_PASSWORD={sync_pw}")
    out = Path("/tmp/odk.env")
    out.write_text("\n".join(lines) + "\n")
    out.chmod(0o600)
    print("\nDone. Settings for .env written to /tmp/odk.env inside the container. On the host:")
    print("  docker compose exec app cat /tmp/odk.env >> .env && docker compose exec app rm /tmp/odk.env && docker compose up -d")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
