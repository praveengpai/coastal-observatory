"""Passwords, tokens and role checks. Standard library hashing (PBKDF2-SHA256) and PyJWT."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import User

ITERATIONS = 310_000
ROLES = ("admin", "coordinator", "scientist", "doctor", "asha", "ward")
PII_ROLES = {"admin", "coordinator", "doctor", "asha"}
MAX_FAILED = 5
LOCK_MINUTES = 15


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(digest))
    except Exception:
        return False


def make_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user.username, "role": user.role, "sites": user.sites,
               "iat": now, "exp": now + timedelta(hours=config.TOKEN_HOURS)}
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.get(User, username)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not user or not user.active:
        return None
    if user.locked_until and user.locked_until > now:
        raise HTTPException(423, "Account locked after repeated failed logins. Try again in 15 minutes.")
    if verify_password(password, user.password_hash):
        user.failed_logins, user.locked_until = 0, None
        db.commit()
        return user
    user.failed_logins += 1
    if user.failed_logins >= MAX_FAILED:
        user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        user.failed_logins = 0
    db.commit()
    return None


class Principal:
    def __init__(self, username: str, role: str, sites: str):
        self.username, self.role = username, role
        self.sites = None if sites.strip() in ("*", "") else set(sites.split())

    def can_see_site(self, code: str) -> bool:
        return self.sites is None or code in self.sites

    @property
    def pii(self) -> bool:
        return self.role in PII_ROLES


def current_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in.")
    try:
        payload = jwt.decode(auth[7:], config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired. Please sign in again.")
    user = db.get(User, payload["sub"])
    if not user or not user.active:
        raise HTTPException(401, "Account disabled.")
    request.state.username = user.username
    return Principal(user.username, user.role, user.sites)


def require(*roles):
    def dep(p: Principal = Depends(current_user)) -> Principal:
        if p.role not in roles:
            raise HTTPException(403, "Your role cannot open this page.")
        return p
    return dep
