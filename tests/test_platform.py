"""End-to-end tests on a throwaway SQLite database loaded with demo data."""
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("OBS_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["OBS_ENVIRONMENT"] = "staging"

from fastapi.testclient import TestClient  # noqa: E402

from app import analytics, sync_odk  # noqa: E402
from app.main import app  # noqa: E402
from tools import seed_demo  # noqa: E402

PW = seed_demo.DEMO_PASSWORD


@pytest.fixture(scope="session")
def client():
    seed_demo.main(reset=True)
    with TestClient(app) as c:
        yield c


def login(client, user):
    r = client.post("/api/auth/login", json={"username": user, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_login_rejects_wrong_password(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password"}).status_code == 401


def test_requires_sign_in(client):
    assert client.get("/api/sites").status_code == 401


@pytest.mark.parametrize("path", ["/api/sites", "/api/summary", "/api/forecast", "/api/stats/trend",
                                  "/api/stats/salinity-bp", "/api/stats/associations", "/api/stats/model",
                                  "/api/quality", "/api/loop", "/api/ageing", "/api/tasks", "/api/decisions",
                                  "/api/advisories", "/api/records/samples", "/api/records/screening",
                                  "/api/queries/elders_salty_high_bp", "/api/admin/audit"])
def test_admin_endpoints(client, path):
    assert client.get(path, headers=login(client, "admin")).status_code == 200


def test_role_permissions(client):
    ward, sci, asha = login(client, "ward"), login(client, "scientist"), login(client, "asha")
    assert client.get("/api/stats/trend", headers=ward).status_code == 403
    assert client.get("/api/tasks", headers=sci).status_code == 403
    assert client.get("/api/export/samples.csv", headers=asha).status_code == 403
    assert client.get("/api/admin/audit", headers=sci).status_code == 403


def test_site_restriction(client):
    sites = client.get("/api/sites", headers=login(client, "asha")).json()
    assert {s["code"] for s in sites} == {"DC2", "DMA"}


def test_scientist_sees_no_pii(client):
    h = login(client, "scientist")
    text = client.get("/api/export/persons.csv", headers=h).text
    assert "phone" not in text.splitlines()[0] and "name" not in text.splitlines()[0]
    q = client.get("/api/queries/elders_alone_or_evac", headers=h).json()
    assert all("name" not in r for r in q["rows"])


def test_asha_sees_names_in_tasks(client):
    tasks = client.get("/api/tasks", headers=login(client, "asha")).json()
    refs = [t for t in tasks if t["kind"] == "referral"]
    assert refs and any("9" in t["detail"] for t in refs)


def test_advisory_needs_doctor_before_sending(client):
    coord, doc = login(client, "coordinator"), login(client, "doctor")
    draft = next(a for a in client.get("/api/advisories", headers=coord).json() if a["status"] == "draft")
    assert client.post(f"/api/advisories/{draft['id']}", json={"status": "sent"}, headers=coord).status_code == 409
    assert client.post(f"/api/advisories/{draft['id']}", json={"status": "approved"}, headers=coord).status_code == 403
    assert client.post(f"/api/advisories/{draft['id']}", json={"status": "approved"}, headers=doc).status_code == 200
    assert client.post(f"/api/advisories/{draft['id']}", json={"status": "sent"}, headers=coord).status_code == 200


def test_scenario_model(client):
    h = login(client, "coordinator")
    lo = client.post("/api/model/scenario", json={"rain_mm": 0, "tide_m": 0.6, "temp_c": 28, "rh": 60}, headers=h).json()
    hi = client.post("/api/model/scenario", json={"rain_mm": 180, "tide_m": 1.6, "temp_c": 36, "rh": 90}, headers=h).json()
    assert hi["contamination_probability"] > lo["contamination_probability"]
    assert hi["heat_index_c"] > lo["heat_index_c"]


def test_lab_and_site_import(client):
    h = login(client, "admin")
    csv_text = "sample_id,method,result,ecoli_cfu,coliform_cfu,vibrio,amr_note,tested_on\nWS-000001,nio_lab,pos,120,,detected,,2026-10-01\nbad,,x,,,,,\n"
    r = client.post("/api/import/lab", files={"file": ("lab.csv", csv_text, "text/csv")}, headers=h).json()
    assert r["imported"] == 1 and r["skipped_rows"] == [3]
    sites = "name,label,site_type,lat,lon\nNEW,New site,village,9.9,76.2\n"
    assert client.post("/api/import/sites", files={"file": ("s.csv", sites, "text/csv")}, headers=h).json()["sites"] == 1


def test_account_lockout(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "ward", "password": "wrong-password-x"})
    assert client.post("/api/auth/login", json={"username": "ward", "password": PW}).status_code == 423


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_install_page_is_public(client):
    r = client.get("/install")
    assert r.status_code == 200 and "org.odk.collect.android" in r.text and "QR" in r.text


def test_flatten_and_rejected_submissions():
    sub = {"__id": "uuid:1", "__system": {"submissionDate": "2026-11-14T10:00:00Z", "reviewState": "rejected"},
           "camp": {"camp_site": "TST"}, "gps": {"type": "Point", "coordinates": [76.3, 9.98, 0]}}
    f = sync_odk.flatten(sub)
    assert f["camp_site"] == "TST" and f["gps"]["coordinates"][1] == 9.98 and f["_instance_id"] == "uuid:1"
    assert sync_odk.ingest(None, "obs_water_sample", sub) is False


def test_statistics_helpers():
    assert analytics.odds_ratio(10, 10, 5, 20)["or"] == 4.0
    assert analytics.kappa([(True, True), (False, False)]) == 1.0
    assert 40 <= analytics.heat_index_c(33, 75) <= 46


def test_stickers(tmp_path):
    from tools import stickers
    path, n = stickers.make("household", 1, 30, site="CVB", out_dir=str(tmp_path))
    assert n == 30 and os.path.getsize(path) > 5000


def test_custom_advisory_without_translation_key(client, monkeypatch):
    monkeypatch.delenv("OBS_SARVAM_API_KEY", raising=False)
    h = login(client, "coordinator")
    r = client.post("/api/advisories/custom", json={"site": "DC2", "text_en": "Boil water before drinking."}, headers=h)
    assert r.status_code == 200 and r.json()["translated"] is False
    a = client.get("/api/advisories", headers=h).json()[0]
    assert a["kind"] == "custom" and "Malayalam not available" in a["text_ml"]


def test_custom_advisory_translated_by_sarvam(client, monkeypatch):
    from app import translate
    calls = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"translated_text": "വെള്ളം തിളപ്പിച്ച് കുടിക്കുക."}

    def fake_post(url, **kw):
        calls.append(kw["json"])
        assert kw["headers"]["api-subscription-key"] == "test-key"
        return Resp()

    monkeypatch.setenv("OBS_SARVAM_API_KEY", "test-key")
    monkeypatch.setattr(translate.requests, "post", fake_post)
    h = login(client, "doctor")
    body = {"site": "DMA", "text_en": "Please boil drinking water this week."}
    assert client.post("/api/advisories/custom", json=body, headers=h).json()["translated"] is True
    client.post("/api/advisories/custom", json=body, headers=h)          # same text again: cached
    assert len(calls) == 1 and calls[0]["target_language_code"] == "ml-IN"
    assert client.get("/api/advisories", headers=h).json()[0]["text_ml"] == "വെള്ളം തിളപ്പിച്ച് കുടിക്കുക."


def test_scientist_cannot_write_advisory(client):
    r = client.post("/api/advisories/custom", json={"site": "DC2", "text_en": "Hello there."}, headers=login(client, "scientist"))
    assert r.status_code == 403


def test_kobo_submission_ingests_like_odk(client):
    from app import sync_kobo
    from app.db import SessionLocal
    from app.models import WaterSample
    rec = {"_uuid": "abc-1", "_submission_time": "2026-11-14T10:00:00", "camp/camp_site": "DMA", "camp/role": "nio",
           "today": "2026-11-14", "point_type": "household", "hh_id": "DMA-002", "sample/sample_id": "WS-900001",
           "sample/source": "own_well", "sample/taken_at": "source", "sample/gps": "9.9681 76.2431 2.0 4.5",
           "field/tds": "820", "field/rain_48h": "yes", "field/flooded_7d": "no", "aq/aquadip": "pos", "aq/to_lab": "yes"}
    db = SessionLocal()
    assert sync_kobo.ingest_kobo(db, "obs_water_sample", rec)
    db.commit()
    s = db.get(WaterSample, "WS-900001")
    assert s.hh_id == "DMA-002" and s.tds == 820 and abs(s.lat - 9.9681) < 1e-6 and abs(s.lon - 76.2431) < 1e-6
    rejected = dict(rec, **{"_validation_status": {"uid": "validation_status_not_approved"}})
    assert sync_kobo.ingest_kobo(db, "obs_water_sample", rejected) is False
    db.close()
