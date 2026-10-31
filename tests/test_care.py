import os, tempfile
os.environ.update(DEV="1", DB_PATH=tempfile.mktemp(suffix=".db"))
from app.main import recommend, analyse, Profile
E = lambda uv=3, hu=60, pm=40, src="open-meteo (modelled)": dict(uv=uv, humidity=hu, pm25=pm, source=src)
P = lambda i, n, c, ing="": dict(id=i, name=n, category=c, ingredients=ing, slot="both")

def test_adds_sunscreen_only_when_needed():
    assert "Add a daily sunscreen" == recommend(E(uv=9), [], Profile())["title"]
    r = recommend(E(uv=9), [P(1, "SPF", "sunscreen")], Profile()); assert "no new product" in r["why"].lower() or "Apply" in r["why"]

def test_no_action_and_unavailable_data():
    assert recommend(E(), [], Profile())["action"] is False
    r = recommend(dict(uv=None, humidity=None, pm25=None, source="unavailable"), [], Profile()); assert not r["action"] and r["confidence"] == "low" and not r["notify"]

def test_quiet_mode_silences_notification():
    assert recommend(E(uv=9), [], Profile(quiet_mode=True))["notify"] is False

def test_flags_and_duplicates():
    a = analyse([P(1, "A", "moisturiser", "water, fragrance"), P(2, "B", "moisturiser", "glycerin"), P(3, "R", "serum", "retinol"), P(4, "X", "serum", "glycolic acid")], Profile(fragrance_free=True))
    assert a["products"][0]["flags"] and any("2 moisturisers" in n for n in a["notes"]) and any("different nights" in n for n in a["notes"])
