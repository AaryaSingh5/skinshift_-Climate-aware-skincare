import base64, io, numpy as np, pytest
from fastapi import HTTPException
from PIL import Image
import app.main as m

def img(a): return Image.fromarray(a.astype("uint8"), "RGB")
def noisy(v=130, size=300): r = np.random.default_rng(1); return img(np.clip(v + r.normal(0, 40, (size, size, 3)), 0, 255))

def test_photo_quality_gates():
    assert m.photo_metrics(noisy())["ok"]
    assert not m.photo_metrics(noisy(20))["ok"] and not m.photo_metrics(noisy(250))["ok"]
    assert any("Blurry" in i for i in m.photo_metrics(img(np.full((300, 300, 3), 130)))["issues"])
    assert not m.photo_metrics(noisy(size=100))["ok"]
    red = np.zeros((300, 300, 3)); red[...] = (180, 100, 90); assert m.photo_metrics(img(red + np.random.default_rng(2).normal(0, 30, red.shape)))["redness_index"] > 0.1

def test_image_needs_consent_and_valid_type():
    d = "data:image/png;base64," + base64.b64encode(b"x").decode()
    with pytest.raises(HTTPException) as e: m.decode_img(m.Img(image=d, consent_image=False)); assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e: m.decode_img(m.Img(image="hello", consent_image=True)); assert e.value.status_code == 422

def test_label_parsing_sanitises(monkeypatch):
    b = io.BytesIO(); noisy().save(b, "PNG"); i = m.Img(image="data:image/png;base64," + base64.b64encode(b.getvalue()).decode(), consent_image=True)
    uid = m.q("insert into users(email,pw,role,created) values(?,?,?,?)", ("lab@x.org", "x$y", "consumer", m.now()), commit=True)
    monkeypatch.setattr(m, "llm_call", lambda msgs, max_tokens=600: 'Here: {"name":"Cream","category":"weird","ingredients":"Aqua, Glycerin"}')
    r = m.scan_label(i, {"id": uid}); assert r["category"] == "other" and "Glycerin" in r["ingredients"]
    monkeypatch.setattr(m, "llm_call", lambda msgs, max_tokens=600: "I can't read it")
    with pytest.raises(HTTPException): m.scan_label(i, {"id": uid})

def test_barcode_lookup(monkeypatch):
    monkeypatch.setattr(m, "off_lookup", lambda c: {"status": 1, "product": {"brands": "Acme", "product_name": "Sun Fluid", "ingredients_text": "Aqua, Zinc Oxide", "categories_tags": ["en:sun-care"]}})
    r = m.barcode("8901234567890", {"id": 99}); assert r["category"] == "sunscreen" and "Zinc Oxide" in r["ingredients"]
    with pytest.raises(HTTPException): m.barcode("abc", {"id": 99})
    monkeypatch.setattr(m, "off_lookup", lambda c: {"status": 0})
    with pytest.raises(HTTPException) as e: m.barcode("8901234567891", {"id": 99}); assert e.value.status_code == 404

def test_delivery_is_opt_in_and_generic(monkeypatch):
    sent = []; monkeypatch.setattr(m, "send_email", lambda to, b: sent.append(("email", b))); monkeypatch.setattr(m, "send_push", lambda s, b: sent.append(("push", b)))
    a = m.q("insert into users(email,pw,role,created) values(?,?,?,?)", ("d1@x.org", "x$y", "consumer", m.now()), commit=True)
    m.deliver(a); assert sent == []
    m.q("insert into profiles(user_id,data) values(?,?)", (a, m.Profile(alert_email=True).model_dump_json()), commit=True)
    m.q("insert into push_subs(user_id,endpoint,sub) values(?,?,?)", (a, "https://p/1", "{}"), commit=True)
    m.deliver(a); assert {k for k, _ in sent} == {"email", "push"} and all("uv" not in b.lower() and "sunscreen" not in b.lower() for _, b in sent)
