import os, tempfile
os.environ.update(DEV="1", DB_PATH=tempfile.mktemp(suffix=".db"), RESEARCHER_EMAIL="r@x.org", RESEARCHER_PASSWORD="research-pass-1")
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
C = {"email": "a@x.org", "password": "long-password-1", "ack": True}

def test_notice_must_be_acknowledged():
    assert c.post("/api/consumer/auth/register", json={**C, "ack": False}).status_code == 400
    assert c.post("/api/consumer/auth/register", json=C).status_code == 200

def test_roles_are_separate():
    assert c.get("/api/consumer/me").status_code == 200
    assert c.get("/api/researcher/cohort").status_code in (401, 403)
    assert c.post("/api/researcher/auth/login", json=C).status_code == 401
    r = TestClient(app)
    assert r.post("/api/consumer/auth/login", json={**C, "email": "r@x.org", "password": "research-pass-1"}).status_code == 401

def test_researcher_sees_only_suppressed_aggregates():
    r = TestClient(app)
    assert r.post("/api/researcher/auth/login", json={"email": "r@x.org", "password": "research-pass-1", "ack": True}).status_code == 200
    assert r.get("/api/consumer/me").status_code == 401
    assert all(x["participants"] == "<5" for x in r.get("/api/researcher/cohort").json()["cities"])
