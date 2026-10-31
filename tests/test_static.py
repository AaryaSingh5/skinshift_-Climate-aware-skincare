import re, pathlib
from fastapi.testclient import TestClient
from app.main import app
S = pathlib.Path("static")

def test_every_element_id_used_in_js_exists_in_html():
    html = (S / "consumer.html").read_text(); ids = set(re.findall(r'id="([^"]+)"', html))
    for f in ("consumer.js", "care.js", "photos.js"):
        used = set(re.findall(r'\$\("#([\w-]+)"\)', (S / f).read_text()))
        assert not used - ids, f"{f} uses ids missing from consumer.html: {used - ids}"
    r = (S / "researcher.html").read_text(); rid = set(re.findall(r'id="([^"]+)"', r))
    assert not set(re.findall(r'\$\("#([\w-]+)"\)', (S / "researcher.js").read_text())) - rid

def test_csp_allows_local_blob_images_only():
    h = TestClient(app).get("/").headers["content-security-policy"]
    assert "img-src 'self' blob:" in h and "unsafe-inline" not in h

def test_no_inline_scripts_or_styles():
    for p in S.glob("*.html"): t = p.read_text(); assert "<script>" not in t and " style=" not in t

def test_every_html_page_loads_only_existing_local_assets():
    for p in S.glob("*.html"):
        for ref in re.findall(r'(?:src|href)="/static/([^"]+)"', p.read_text()): assert (S / ref).exists(), f"{p.name} references missing {ref}"

def test_photo_history_never_uploads_the_kept_photo():
    js = (S / "photos.js").read_text()
    calls = re.findall(r'api\("([^"]+)"', js)
    assert set(calls) <= {"/api/consumer/me", "/api/consumer/photo", "/api/consumer/photo/summary"}, calls
    assert "fetch(" not in js and "sendBeacon" not in js and "localStorage" not in js
    assert js.count('api("/api/consumer/photo"') == 1, "only the optional, opt-in quality check may send a photo"
    assert "if ($(\"#pcn\").checked)" in js, "the quality check must be guarded by its own checkbox"
    html = (S / "consumer.html").read_text()
    assert re.search(r'<input id="pcn"|<input type="checkbox" id="pcn"', html) and 'id="pcn" checked' not in html

def test_photo_history_lists_what_photos_cannot_measure():
    html = (S / "consumer.html").read_text().lower()
    for claim in ("skin-barrier integrity", "tewl", "hydration levels", "cellular aging", "oxidative stress", "biological skin age"):
        assert claim in html
    assert "lighting" in html and "angle" in html and "make-up" in html

def test_photo_history_has_the_four_user_facing_views():
    html = (S / "consumer.html").read_text()
    for needle in ('id="gal"', 'id="tl"', 'id="cmp"', 'Before &amp; after', 'Capture a photo every two weeks'): assert needle in html
