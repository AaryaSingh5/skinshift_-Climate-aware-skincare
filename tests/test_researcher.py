import os, tempfile, datetime as dt
os.environ.update(DEV="1", DB_PATH=tempfile.mktemp(suffix=".db"), RESEARCHER_EMAIL="r@x.org", RESEARCHER_PASSWORD="research-pass-1")
from fastapi.testclient import TestClient
from app.main import app, q, hash_pw, now

def seed(city, n, consent=1, day="2026-01-01"):
    for i in range(n):
        uid = q("insert into users(email,pw,role,research_consent,created) values(?,?,?,?,?)", (f"{city}{i}{consent}@x.org", hash_pw("x" * 12), "consumer", consent, now()), commit=True)
        q("insert into checkins(user_id,day,city,comfort,uv,pm25,humidity,source) values(?,?,?,?,?,?,?,?)", (uid, day, city, 6.0, 7.0, 50.0, 55.0, "open-meteo (modelled)"), commit=True)

def client():
    c = TestClient(app); assert c.post("/api/researcher/auth/login", json={"email": "r@x.org", "password": "research-pass-1", "ack": True}).status_code == 200; return c

def test_export_suppresses_small_cells_and_ignores_non_consenting():
    seed("Mumbai", 6); seed("Delhi", 4); seed("Jaipur", 8, consent=0)
    c = client(); rows = c.get("/api/researcher/export").text.strip().splitlines()
    assert len(rows) == 2 and "Mumbai" in rows[1] and "Delhi" not in rows[1] and "Jaipur" not in rows[1]

def test_quality_hides_small_cities_and_warns():
    d = client().get("/api/researcher/quality").json()
    assert {c["city"]: c["participants"] for c in d["cities"]}["Delhi"] == "<5" and any("Skin-tone" in w for w in d["warnings"])

def test_researcher_actions_are_audited_and_consumers_blocked():
    from app.main import q as Q
    assert Q("select count(*) n from audit where action='dataset_export'", one=True)["n"] >= 1
    assert TestClient(app).get("/api/researcher/quality").status_code in (401, 403)
