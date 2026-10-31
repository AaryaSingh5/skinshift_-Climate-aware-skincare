import os, tempfile
os.environ.update(DEV="1", DB_PATH=tempfile.mktemp(suffix=".db"))
import app.main as m
P = lambda: dict(id=1, name="MySecretCream", category="moisturiser", ingredients="glycerin", slot="both")

def test_blocked_claims_fall_back(monkeypatch):
    monkeypatch.setattr(m, "llm_call", lambda msgs: "This serum will reverse aging and cure acne.")
    assert m.ai_answer("tell me about serums", [], m.Profile()) is None
    monkeypatch.setattr(m, "llm_call", lambda msgs: "Use sunscreen daily. I’m fairly sure.")
    assert "not medical advice" in m.ai_answer("should I wear sunscreen daily", [], m.Profile())

def test_products_only_sent_with_permission(monkeypatch):
    seen = []; monkeypatch.setattr(m, "llm_call", lambda msgs: seen.append(str(msgs)) or "ok")
    m.ai_answer("dry skin", [P()], m.Profile(ai_personalisation=False)); m.ai_answer("dry skin", [P()], m.Profile(ai_personalisation=True))
    assert "MySecretCream" not in seen[0] and "MySecretCream" in seen[1]

def test_alerts_dedupe_and_quiet_mode(monkeypatch):
    monkeypatch.setattr(m, "fetch_env", lambda c: dict(uv=9, humidity=50, pm25=30, source="open-meteo (modelled)"))
    ids = []
    for em, quiet in (("loud@x.org", False), ("quiet@x.org", True)):
        uid = m.q("insert into users(email,pw,role,created) values(?,?,?,?)", (em, "x$y", "consumer", m.now()), commit=True); ids.append(uid)
        m.q("insert into checkins(user_id,day,city,comfort) values(?,?,?,?)", (uid, "2026-01-01", "Mumbai", 6), commit=True)
        m.q("insert into profiles(user_id,data) values(?,?)", (uid, m.Profile(quiet_mode=quiet).model_dump_json()), commit=True)
    m.run_alerts(); m.run_alerts()
    n = lambda i: m.q("select count(*) n from alerts where user_id=?", (i,), one=True)["n"]
    assert n(ids[0]) == 1 and n(ids[1]) == 0
