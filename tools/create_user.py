"""Create the first administrator (or any user) from the server console.

    python -m tools.create_user <username> "<Full name>" <role> [sites]

Roles: admin, coordinator, scientist, doctor, asha, ward. Sites: space-separated codes or * (all).
The password is asked for interactively and never appears in shell history.
"""
import getpass
import sys

from app.db import SessionLocal, init_db
from app.models import User
from app.security import ROLES, hash_password

if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[3] not in ROLES:
        raise SystemExit(__doc__)
    username, name, role = sys.argv[1], sys.argv[2], sys.argv[3]
    sites = sys.argv[4] if len(sys.argv) > 4 else "*"
    pw = getpass.getpass("Password (10+ characters): ")
    if pw != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    init_db()
    db = SessionLocal()
    db.merge(User(username=username, full_name=name, role=role, sites=sites, password_hash=hash_password(pw), active=True))
    db.commit()
    print(f"Saved {role} '{username}'.")
