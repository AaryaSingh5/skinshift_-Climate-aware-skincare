import os, sqlite3, hashlib, hmac, secrets, time, datetime as dt
import httpx, jwt, numpy as np
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DEV = os.getenv("DEV") == "1"
SECRET = os.getenv("SECRET_KEY") or ("dev-only-secret" if DEV else None)
if not SECRET:
    raise SystemExit("SECRET_KEY must be set (or DEV=1 for local use)")
DB = os.getenv("DB_PATH", "skinshift.db")
NOTICE_VERSION, K_MIN = "2026-3", 5
NOTICES = {
 "consumer": "SKINSHIFT uses your skin check-ins, the city you choose and local environmental data (UV, PM2.5, humidity) to build your personal Skin Resilience Twin. Your data is stored securely and used to give you guidance. Only if you switch on research sharing, de-identified check-ins may be combined with other participants’ data and analysed by L’Oréal researchers; groups under 5 people are hidden and photos are never shared. If you use the photo check, the photo is analysed on our server and then discarded; only three numbers (light, sharpness, a redness reading) are saved, and any photos you choose to keep stay on your own device. If you use the Ask assistant, your question (and your product list only if you allow it) is sent to an AI service hosted by NVIDIA, so never include your name or contact details. You can withdraw sharing, export or delete your data at any time. SKINSHIFT gives cosmetic guidance, not medical advice.",
 "researcher": "You are accessing data from participants who opted in to research. Data is de-identified and shown only as aggregates; groups under 5 are suppressed. Every query you make is logged. Do not attempt to re-identify people, extract raw records or use outputs outside the approved study. Findings are hypotheses for testing, not proof that an ingredient works.",
}
CITIES = {"Mumbai": (19.08, 72.88), "Delhi": (28.61, 77.21), "Bengaluru": (12.97, 77.59), "Jaipur": (26.91, 75.79)}
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

def q(sql, args=(), one=False, commit=False):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    try:
        cur = c.execute(sql, args)
        if commit: c.commit(); return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()
    finally: c.close()

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def audit(actor, action, detail=""): q("insert into audit(ts,actor,action,detail) values(?,?,?,?)", (now(), actor, action, detail), commit=True)
def hash_pw(p):
    s = secrets.token_bytes(16); return s.hex() + "$" + hashlib.scrypt(p.encode(), salt=s, n=2**14, r=8, p=1).hex()
def check_pw(p, stored):
    s, h = stored.split("$"); return hmac.compare_digest(hashlib.scrypt(p.encode(), salt=bytes.fromhex(s), n=2**14, r=8, p=1).hex(), h)

def init():
    for s in ["create table if not exists users(id integer primary key, email text unique, pw text, role text, research_consent int default 0, created text)",
      "create table if not exists consents(id integer primary key, user_id int, kind text, version text, granted int, ts text)",
      "create table if not exists checkins(id integer primary key, user_id int references users(id) on delete cascade, day text, city text, comfort real, uv real, pm25 real, humidity real, source text)",
      "create table if not exists audit(id integer primary key, ts text, actor text, action text, detail text)"]:
        q(s, commit=True)
    e, p = os.getenv("RESEARCHER_EMAIL"), os.getenv("RESEARCHER_PASSWORD")
    if e and p and not q("select 1 from users where email=?", (e.lower(),), one=True):
        q("insert into users(email,pw,role,created) values(?,?,?,?)", (e.lower(), hash_pw(p), "researcher", now()), commit=True)

app = FastAPI(title="SKINSHIFT", docs_url=None, redoc_url=None)
init()

@app.middleware("http")
async def headers(req, call):
    r = await call(req)
    r.headers.update({"Content-Security-Policy": "default-src 'self'; img-src 'self' blob:; frame-ancestors 'none'", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store" if req.url.path.startswith("/api") else "public, max-age=300"})
    return r

def need(role):
    def dep(req: Request):
        try: p = jwt.decode(req.cookies.get("ss_" + role, ""), SECRET, algorithms=["HS256"])
        except Exception: raise HTTPException(401, "Please sign in")
        u = q("select * from users where id=? and role=?", (int(p.get("sub")), role), one=True)
        if not u or p.get("role") != role: raise HTTPException(403, "Wrong account type")
        return u
    return dep

TRIES = {}
def throttle(key, limit=6):
    t = [x for x in TRIES.get(key, []) if time.time() - x < 300]
    if len(t) >= limit: raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    TRIES[key] = t + [time.time()]

class Cred(BaseModel):
    email: str = Field(pattern=EMAIL, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    ack: bool
    research_consent: bool = False

def session(resp: Response, u):
    tok = jwt.encode({"sub": str(u["id"]), "role": u["role"], "exp": int(time.time()) + 8 * 3600}, SECRET, "HS256")
    resp.set_cookie("ss_" + u["role"], tok, httponly=True, samesite="strict", secure=not DEV, max_age=8 * 3600, path="/")

def log_ack(role, uid): q("insert into consents(user_id,kind,version,granted,ts) values(?,?,?,?,?)", (uid, "notice:" + role, NOTICE_VERSION, 1, now()), commit=True)

@app.get("/api/notice/{role}")
def notice(role: str):
    if role not in NOTICES: raise HTTPException(404)
    return {"version": NOTICE_VERSION, "text": NOTICES[role]}

@app.post("/api/consumer/auth/register")
def register(c: Cred, resp: Response):
    if not c.ack: raise HTTPException(400, "Please confirm you have read the data-use notice.")
    try: uid = q("insert into users(email,pw,role,research_consent,created) values(?,?,?,?,?)", (c.email.lower(), hash_pw(c.password), "consumer", int(c.research_consent), now()), commit=True)
    except sqlite3.IntegrityError: raise HTTPException(409, "That email is already registered.")
    log_ack("consumer", uid)
    q("insert into consents(user_id,kind,version,granted,ts) values(?,?,?,?,?)", (uid, "research", NOTICE_VERSION, int(c.research_consent), now()), commit=True)
    session(resp, {"id": uid, "role": "consumer"}); return {"ok": True}

def login(c: Cred, req: Request, resp: Response, role):
    if not c.ack: raise HTTPException(400, "Please confirm you have read the data-use notice.")
    throttle(f"{role}:{c.email.lower()}:{req.client.host}")
    u = q("select * from users where email=? and role=?", (c.email.lower(), role), one=True)
    if not u or not check_pw(c.password, u["pw"]): raise HTTPException(401, "Email or password is incorrect.")
    log_ack(role, u["id"]); session(resp, u)
    if role == "researcher": audit(u["email"], "login")
    return {"ok": True}

@app.post("/api/consumer/auth/login")
def consumer_login(c: Cred, req: Request, resp: Response): return login(c, req, resp, "consumer")
@app.post("/api/researcher/auth/login")
def researcher_login(c: Cred, req: Request, resp: Response): return login(c, req, resp, "researcher")
@app.post("/api/{role}/auth/logout")
def logout(role: str, resp: Response): resp.delete_cookie("ss_" + role, path="/"); return {"ok": True}

def fetch_env(city):
    lat, lon = CITIES[city]
    try:
        with httpx.Client(timeout=6) as c:
            w = c.get("https://api.open-meteo.com/v1/forecast", params=dict(latitude=lat, longitude=lon, current="relative_humidity_2m", daily="uv_index_max", timezone="auto", forecast_days=1)).json()
            a = c.get("https://air-quality-api.open-meteo.com/v1/air-quality", params=dict(latitude=lat, longitude=lon, current="pm2_5")).json()
        return dict(uv=w["daily"]["uv_index_max"][0], humidity=w["current"]["relative_humidity_2m"], pm25=a["current"]["pm2_5"], source="open-meteo (modelled)")
    except Exception: return dict(uv=None, humidity=None, pm25=None, source="unavailable")

def fit(rows):
    rows = [r for r in rows if None not in (r["uv"], r["pm25"], r["humidity"])]
    if len(rows) < 8: return None
    X = np.array([[1, (r["pm25"] - 60) / 40, (r["uv"] - 7) / 2, (r["humidity"] - 55) / 15] for r in rows]); y = np.array([r["comfort"] for r in rows])
    P = np.eye(4) * .5; P[0, 0] = 0
    w = np.linalg.solve(X.T @ X + P, X.T @ y); res = y - X @ w
    return w, float(np.sqrt(res @ res / max(1, len(y) - 4))), float(y.mean()), len(y)

class Checkin(BaseModel):
    city: str; comfort: float = Field(ge=1, le=10)

consumer = need("consumer")
@app.get("/api/consumer/me")
def me(u=Depends(consumer)):
    n = q("select count(*) n from checkins where user_id=?", (u["id"],), one=True)["n"]
    return {"email": u["email"], "research_consent": bool(u["research_consent"]), "checkins": n, "cities": list(CITIES)}

@app.post("/api/consumer/checkin")
def checkin(c: Checkin, u=Depends(consumer)):
    if c.city not in CITIES: raise HTTPException(422, "Choose one of the listed cities.")
    e, d = fetch_env(c.city), dt.date.today().isoformat()
    q("delete from checkins where user_id=? and day=?", (u["id"], d), commit=True)
    q("insert into checkins(user_id,day,city,comfort,uv,pm25,humidity,source) values(?,?,?,?,?,?,?,?)", (u["id"], d, c.city, c.comfort, e["uv"], e["pm25"], e["humidity"], e["source"]), commit=True)
    return {"environment": e}

@app.get("/api/consumer/twin")
def twin(u=Depends(consumer)):
    rows = q("select * from checkins where user_id=? order by day", (u["id"],))
    f = fit(rows)
    if not f: return {"ready": False, "have": len(rows), "need": 8, "message": "Keep checking in. The twin needs 8 days with environment data before it shows any pattern."}
    w, sd, base, n = f
    return {"ready": True, "n": n, "baseline": round(base, 2), "confidence": "low" if n < 14 else "moderate" if n < 30 else "better",
            "effects": {k: round(float(v), 2) for k, v in zip(["PM2.5", "UV", "Humidity"], w[1:])}, "typical_error": round(sd, 2),
            "note": "These are associations in your own reported comfort, not a diagnosis or a measure of skin aging."}

@app.put("/api/consumer/consent/research")
def set_consent(body: dict, u=Depends(consumer)):
    g = int(bool(body.get("granted")))
    q("update users set research_consent=? where id=?", (g, u["id"]), commit=True)
    q("insert into consents(user_id,kind,version,granted,ts) values(?,?,?,?,?)", (u["id"], "research", NOTICE_VERSION, g, now()), commit=True)
    return {"research_consent": bool(g)}

@app.get("/api/consumer/export")
def export(u=Depends(consumer)):
    d = {"email": u["email"], "checkins": [dict(r) for r in q("select day,city,comfort,uv,pm25,humidity,source from checkins where user_id=?", (u["id"],))],
         "consents": [dict(r) for r in q("select kind,version,granted,ts from consents where user_id=?", (u["id"],))]}
    return JSONResponse(d, headers={"Content-Disposition": "attachment; filename=skinshift-my-data.json"})

@app.delete("/api/consumer/account")
def delete(resp: Response, u=Depends(consumer)):
    q("delete from consents where user_id=?", (u["id"],), commit=True); q("delete from users where id=?", (u["id"],), commit=True)
    audit(f"user:{u['id']}", "account_deleted"); resp.delete_cookie("ss_consumer", path="/"); return {"ok": True}

@app.get("/api/researcher/cohort")
def cohort(u=Depends(need("researcher"))):
    out = []
    for city in CITIES:
        users = q("select distinct u.id from users u join checkins c on c.user_id=u.id where u.role='consumer' and u.research_consent=1 and c.city=?", (city,))
        if len(users) < K_MIN: out.append({"city": city, "participants": f"<{K_MIN}"}); continue
        rows = q("select c.* from checkins c join users u on u.id=c.user_id where u.research_consent=1 and c.city=?", (city,))
        mean = lambda k: round(float(np.mean([r[k] for r in rows if r[k] is not None])), 1) if any(r[k] is not None for r in rows) else None
        eff = [f[0][1:] for f in (fit([r for r in rows if r["user_id"] == x["id"]]) for x in users) if f]
        out.append({"city": city, "participants": len(users), "checkins": len(rows), "mean_comfort": mean("comfort"), "mean_pm25": mean("pm25"), "mean_uv": mean("uv"), "mean_humidity": mean("humidity"),
                    "mean_effects": dict(zip(["PM2.5", "UV", "Humidity"], [round(float(v), 2) for v in np.mean(eff, 0)])) if len(eff) >= K_MIN else f"<{K_MIN} usable models"})
    audit(u["email"], "cohort_query"); return {"k_min": K_MIN, "cities": out}

@app.get("/sw.js")
def sw(): return FileResponse("static/sw.js", media_type="application/javascript")
@app.get("/")
def home(): return FileResponse("static/index.html")
@app.get("/app")
def consumer_page(): return FileResponse("static/consumer.html")
@app.get("/research")
def researcher_page(): return FileResponse("static/researcher.html")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- Phase 2: profile, products, home recommendation, ask ----------
import json, re
from typing import Literal, Optional
for _s in ["create table if not exists profiles(user_id integer primary key references users(id) on delete cascade, data text)",
           "create table if not exists products(id integer primary key, user_id int references users(id) on delete cascade, name text, category text, ingredients text, slot text, added text)"]:
    q(_s, commit=True)

ING = {  # name: (function, evidence, limits)
 "glycerin": ("humectant (draws water into skin)", "strong", "Rarely an issue."),
 "hyaluronic acid": ("humectant", "moderate", "Works best on damp skin, with a moisturiser on top."),
 "ceramide": ("barrier lipid", "moderate", "Supports the skin barrier; not a treatment for skin disease."),
 "niacinamide": ("barrier and oil-balance support", "moderate", "Usually well tolerated; high strengths can irritate some people."),
 "panthenol": ("soothing humectant", "moderate", "Generally gentle."),
 "zinc oxide": ("mineral UV filter", "strong", "Protection depends on the full product's tested SPF and enough application."),
 "titanium dioxide": ("mineral UV filter", "strong", "Same as above."),
 "avobenzone": ("UVA filter", "strong", "Needs a stable formula; reapply when outdoors."),
 "vitamin c": ("antioxidant", "moderate", "Can sting and is unstable; does not replace sunscreen."),
 "ascorbic": ("antioxidant (vitamin C)", "moderate", "Can sting and is unstable; does not replace sunscreen."),
 "tocopherol": ("antioxidant (vitamin E)", "moderate", "Supports formulas; not a standalone protection."),
 "retinol": ("retinoid", "strong for texture and photoageing", "Can irritate; use sunscreen; avoid in pregnancy unless a doctor advises."),
 "salicylic acid": ("BHA exfoliant", "moderate", "Can dry or irritate; start slowly."),
 "glycolic acid": ("AHA exfoliant", "moderate", "Increases irritation risk; use sunscreen."),
 "lactic acid": ("AHA exfoliant", "moderate", "Increases irritation risk; use sunscreen."),
 "fragrance": ("scent", "none for skin benefit", "A common trigger for sensitive skin."),
 "parfum": ("scent", "none for skin benefit", "A common trigger for sensitive skin."),
 "alcohol denat": ("solvent", "none for skin benefit", "Can feel drying for some people."),
}
UVF = {"zinc oxide", "titanium dioxide", "avobenzone"}; HUM = {"glycerin", "hyaluronic acid", "ceramide", "panthenol"}
EXF = {"salicylic acid", "glycolic acid", "lactic acid"}
CATS = ["cleanser", "moisturiser", "sunscreen", "serum", "other"]
ESCALATE = re.compile(r"bleed|swell|infect|pus|blister|severe|spreading|fever|painful|mole|rash|eye|allerg", re.I)

class Profile(BaseModel):
    skin_type: Optional[Literal["oily", "dry", "combination", "sensitive", "normal"]] = None
    concerns: list[str] = Field(default_factory=list, max_length=10); goals: list[str] = Field(default_factory=list, max_length=10)
    sensitivities: list[str] = Field(default_factory=list, max_length=15); avoid: list[str] = Field(default_factory=list, max_length=15)
    fragrance_free: bool = False; ai_personalisation: bool = False; alert_email: bool = False; budget: Optional[Literal["low", "mid", "high"]] = None; quiet_mode: bool = False

class Product(BaseModel):
    name: str = Field(min_length=1, max_length=80); category: Literal["cleanser", "moisturiser", "sunscreen", "serum", "other"]
    ingredients: str = Field(default="", max_length=3000); slot: Literal["am", "pm", "both"] = "both"

def get_profile(uid):
    r = q("select data from profiles where user_id=?", (uid,), one=True); return Profile(**json.loads(r["data"])) if r else Profile()
def feats(text): t = text.lower(); return {k for k in ING if k in t}

@app.get("/api/consumer/profile")
def read_profile(u=Depends(consumer)): return get_profile(u["id"])
@app.put("/api/consumer/profile")
def save_profile(p: Profile, u=Depends(consumer)):
    q("insert into profiles(user_id,data) values(?,?) on conflict(user_id) do update set data=excluded.data", (u["id"], p.model_dump_json()), commit=True); return p

@app.post("/api/consumer/products")
def add_product(p: Product, u=Depends(consumer)):
    if q("select count(*) n from products where user_id=?", (u["id"],), one=True)["n"] >= 40: raise HTTPException(400, "Product limit reached.")
    pid = q("insert into products(user_id,name,category,ingredients,slot,added) values(?,?,?,?,?,?)", (u["id"], p.name, p.category, p.ingredients, p.slot, now()), commit=True); return {"id": pid}
@app.delete("/api/consumer/products/{pid}")
def del_product(pid: int, u=Depends(consumer)): q("delete from products where id=? and user_id=?", (pid, u["id"]), commit=True); return {"ok": True}

def analyse(prods, prof):
    out = []
    for p in prods:
        f = feats(p["ingredients"]); t = p["ingredients"].lower(); flags = []
        for a in prof.avoid + prof.sensitivities:
            if a.strip() and a.strip().lower() in t: flags.append(f"Contains {a.strip()}, which you asked to avoid.")
        if prof.fragrance_free and ({"fragrance", "parfum"} & f): flags.append("Contains fragrance, and you prefer fragrance-free.")
        out.append({"id": p["id"], "name": p["name"], "category": p["category"], "slot": p["slot"], "functions": sorted({ING[k][0] for k in f}), "flags": flags, "no_ingredients": not t.strip()})
    notes = []
    for c in ("moisturiser", "sunscreen", "cleanser"):
        n = [p["name"] for p in prods if p["category"] == c]
        if len(n) > 1: notes.append(f"You have {len(n)} {c}s ({', '.join(n)}). One is usually enough; check whether you need all of them.")
    for p in prods:
        for q2 in prods:
            if p["id"] < q2["id"]:
                a, b = feats(p["ingredients"]), feats(q2["ingredients"])
                if ("retinol" in a and (b & EXF)) or ("retinol" in b and (a & EXF)): notes.append(f"{p['name']} and {q2['name']} are both strong actives; using them together can irritate. Consider different nights.")
    return {"products": out, "notes": notes}

def recommend(env, prods, prof):
    allf = set().union(*[feats(p["ingredients"]) for p in prods]) if prods else set()
    sun = any(p["category"] == "sunscreen" for p in prods) or bool(allf & UVF); moist = any(p["category"] == "moisturiser" for p in prods) or bool(allf & HUM)
    conf = {"unavailable": "low"}.get(env["source"], "moderate"); ev = "Based on modelled local data (" + env["source"] + "); not a personal measurement."
    def r(action, title, why): return {"action": action, "title": title, "why": why, "confidence": conf, "evidence": ev, "notify": action and not prof.quiet_mode and conf != "low", "env": env}
    if env["uv"] is None: return r(False, "No change needed today", "Today’s local data isn’t available, so I won’t suggest a change.")
    if env["uv"] >= 6 and not sun: return r(True, "Add a daily sunscreen", f"UV is high today ({env['uv']:.0f}) and you haven’t listed a sunscreen. This is the one product worth adding.")
    if env["uv"] >= 6: return r(True, "Use your sunscreen this morning", f"UV is high today ({env['uv']:.0f}). Apply enough and reapply if you’re outdoors. No new product is needed.")
    if env["humidity"] is not None and env["humidity"] < 35 and moist: return r(True, "Use your moisturiser on slightly damp skin", f"Air is dry today ({env['humidity']:.0f}% humidity). Your current moisturiser is enough; no new product is needed.")
    if env["pm25"] is not None and env["pm25"] >= 100: return r(True, "Cleanse gently this evening", f"PM2.5 is high ({env['pm25']:.0f}). A gentle cleanse with what you already own is enough. No anti-pollution product is needed.")
    return r(False, "No change needed today", "Conditions are ordinary for your skin, so keep your current routine.")

@app.get("/api/consumer/home")
def home_rec(city: str = "Mumbai", u=Depends(consumer)):
    if city not in CITIES: raise HTTPException(422, "Choose one of the listed cities.")
    return recommend(fetch_env(city), q("select * from products where user_id=?", (u["id"],)), get_profile(u["id"]))

@app.get("/api/consumer/products")
def list_products(u=Depends(consumer)): return analyse(q("select * from products where user_id=? order by id", (u["id"],)), get_profile(u["id"]))

@app.get("/api/consumer/ingredient")
def ingredient(name: str):
    k = name.strip().lower()
    for key, v in ING.items():
        if key in k or k in key: return {"name": key, "function": v[0], "evidence": v[1], "limits": v[2]}
    raise HTTPException(404, "I don’t have notes on that ingredient yet.")

class Ask(BaseModel): q: str = Field(min_length=2, max_length=300)
@app.post("/api/consumer/ask")
def ask(a: Ask, u=Depends(consumer)):
    throttle(f"ask:{u['id']}", 20); t = a.q.lower(); prods = q("select * from products where user_id=?", (u["id"],))
    if ESCALATE.search(t): return {"answer": "That sounds like something a dermatologist or doctor should look at, especially if it is severe, painful, spreading or not settling. I can’t assess it from here."}
    if re.search(r"need|buy|another|new|purchase", t):
        for c in CATS[:3]:
            if c in t or (c == "moisturiser" and "moisturizer" in t):
                have = [p["name"] for p in prods if p["category"] == c]
                return {"answer": f"You already have {', '.join(have)} for this. Use that first; a new {c} is unlikely to be needed." if have else f"You haven’t listed a {c}. If you use one regularly, add it under My Products and I’ll check again."}
    found = [k for k in ING if k in t]
    if len(found) >= 2 and re.search(r"together|with|combine|mix", t):
        return {"answer": "Strong actives (retinol with exfoliating acids) can irritate together; use them on different nights." if "retinol" in found and (set(found) & EXF) else "I don’t have a specific caution for that pair. Introduce one new product at a time and watch how your skin feels."}
    if found: k = found[0]; return {"answer": f"{k.title()}: {ING[k][0]}. Evidence: {ING[k][1]}. {ING[k][2]}"}
    ai = ai_answer(a.q, prods, get_profile(u["id"]))
    if ai: return {"answer": ai, "source": "ai"}
    return {"answer": "I can answer questions about ingredients, whether two actives suit together, whether you need another product, and when to see a doctor. I’m a rule-based helper, not a medical service."}

# ---------- Phase 3: researcher tools ----------
import csv, io, statistics
from collections import Counter
researcher = need("researcher")

def consented_rows(): return q("select u.id uid, c.* from checkins c join users u on u.id=c.user_id where u.research_consent=1 and u.role='consumer'")

@app.get("/api/researcher/quality")
def quality(u=Depends(researcher)):
    rows, out, warn = consented_rows(), [], []
    total_people = len({r["uid"] for r in rows}); week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    for city in CITIES:
        cr = [r for r in rows if r["city"] == city]; people = {r["uid"] for r in cr}
        if len(people) < K_MIN: out.append({"city": city, "participants": f"<{K_MIN}"}); continue
        per = Counter(r["uid"] for r in cr); src = Counter(r["source"] for r in cr)
        comp = sum(None not in (r["uv"], r["pm25"], r["humidity"]) for r in cr) / len(cr)
        ret = len({r["uid"] for r in cr if r["day"] >= week_ago}) / len(people)
        out.append({"city": city, "participants": len(people), "checkins": len(cr), "median_checkins_per_person": statistics.median(per.values()),
                    "environment_complete": round(comp, 2), "active_last_7_days": round(ret, 2), "sources": dict(src)})
        if comp < .8: warn.append(f"{city}: environment data is incomplete ({comp:.0%}). Treat exposure results with caution.")
        if ret < .5: warn.append(f"{city}: fewer than half of participants checked in this week, so dropout bias is possible.")
        if len(people) / total_people > .5: warn.append(f"{city}: more than half of the sample comes from one city.")
    if len([c for c in out if isinstance(c["participants"], int)]) < len(CITIES): warn.append("Some cities have too few participants to report or compare.")
    warn.append("Skin-tone and demographic balance are not collected yet, so fairness cannot be assessed.")
    audit(u["email"], "quality_query"); return {"cities": out, "warnings": warn}

@app.get("/api/researcher/export")
def research_export(u=Depends(researcher)):
    """City-day aggregates only; a cell is released only if 5+ opted-in participants contributed."""
    cells = {}
    for r in consented_rows(): cells.setdefault((r["city"], r["day"]), []).append(r)
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(["date", "city", "participants", "mean_comfort", "mean_pm25", "mean_uv", "mean_humidity"]); n = 0
    avg = lambda rs, k: round(statistics.mean(x[k] for x in rs if x[k] is not None), 2) if any(x[k] is not None for x in rs) else ""
    for (city, day), rs in sorted(cells.items()):
        if len({x["uid"] for x in rs}) >= K_MIN: w.writerow([day, city, len({x["uid"] for x in rs}), avg(rs, "comfort"), avg(rs, "pm25"), avg(rs, "uv"), avg(rs, "humidity")]); n += 1
    audit(u["email"], "dataset_export", f"{n} city-day cells")
    from fastapi.responses import Response as R
    return R(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=skinshift-city-day.csv"})

@app.get("/api/researcher/hypotheses")
def hypotheses(u=Depends(researcher)):
    out = []
    for c in cohort(u)["cities"]:
        e = c.get("mean_effects")
        if not isinstance(e, dict): continue
        if e["PM2.5"] < -.15: out.append({"city": c["city"], "observation": f"Comfort tends to fall as PM2.5 rises (mean effect {e['PM2.5']}).", "research_question": "Does a barrier-supporting formulation change TEWL or comfort on high-PM2.5 days?"})
        if e["Humidity"] > .15: out.append({"city": c["city"], "observation": f"Comfort tends to be lower when air is drier (humidity effect {e['Humidity']}).", "research_question": "Do lighter and richer moisturising formats perform differently in dry conditions?"})
        if e["UV"] < -.15: out.append({"city": c["city"], "observation": f"Comfort tends to fall as UV rises (effect {e['UV']}).", "research_question": "How do photoprotective formats differ in comfort and adherence on high-UV days?"})
    return {"hypotheses": out, "caveat": "Associations in self-reported comfort. They are hypotheses to test, not proof that any ingredient works."}

@app.get("/api/researcher/model-report")
def model_report(u=Depends(researcher)):
    p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "metrics.json")
    return json.load(open(p)) if os.path.exists(p) else {"message": "No model report yet. Run the training pipeline once enough data exists."}

# ---------- Phase 4: AI assistant (NVIDIA-hosted) and alerts ----------
KB = json.load(open(os.path.join(os.path.dirname(__file__), "knowledge.json")))["entries"]
BLOCKED = re.compile(r"reverse (your )?(skin )?(aging|ageing)|cellular repair|cure|diagnos|pollution-proof|detox(ify)? your skin|guarantee", re.I)
SYSTEM = ("You are SKINSHIFT’s skincare helper giving cosmetic guidance for people in India. Use ONLY the notes provided. If the notes do not cover the question, say you are not sure and suggest a dermatologist or pharmacist. "
          "Never diagnose, never promise to reverse ageing or repair cells, and never suggest buying a new product if the user’s own products already cover the need. Reply in plain language under 120 words and end with one short line on how certain you are.")

def llm_call(messages, max_tokens=600):
    key = os.getenv("NVIDIA_API_KEY")
    if not key: return None
    try:
        r = httpx.post(os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1") + "/chat/completions", headers={"Authorization": "Bearer " + key},
                       json={"model": os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"), "messages": messages, "temperature": .2, "max_tokens": max_tokens}, timeout=40)
        r.raise_for_status(); t = r.json()["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip() or None
    except Exception: return None

def retrieve(question, k=3):
    w = set(re.findall(r"[a-z0-9.]+", question.lower()))
    return [e for s, e in sorted(((len(w & set(e["keywords"])), e) for e in KB), key=lambda x: -x[0])[:k] if s > 0]

def ai_answer(question, prods, prof):
    notes = retrieve(question)
    ctx = "Notes:\n" + "\n".join(f"- {e['topic']}: {e['text']}" for e in notes) if notes else "Notes: none matched."
    if prof.ai_personalisation and prods: ctx += "\nThe user’s products: " + "; ".join(f"{p['name']} ({p['category']}): {p['ingredients'][:200]}" for p in prods)
    out = llm_call([{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{ctx}\n\nQuestion: {question}"}])
    if not out or BLOCKED.search(out): return None
    return out + "\n\n(AI-generated cosmetic guidance, not medical advice.)"

for _s in ["create table if not exists alerts(id integer primary key, user_id int references users(id) on delete cascade, day text, title text, body text, created text, read int default 0)"]: q(_s, commit=True)

def run_alerts():
    """Run daily (cron). One alert per user per day, never in quiet mode or on low-confidence data, never the same message twice within 3 days."""
    cache, sent, today = {}, 0, dt.date.today().isoformat(); since = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    for u in q("select id from users where role='consumer'"):
        last = q("select city from checkins where user_id=? order by day desc limit 1", (u["id"],), one=True)
        if not last: continue
        city = last["city"]; cache.setdefault(city, fetch_env(city))
        rec = recommend(cache[city], q("select * from products where user_id=?", (u["id"],)), get_profile(u["id"]))
        if not rec["notify"] or q("select 1 from alerts where user_id=? and day=?", (u["id"], today), one=True) or q("select 1 from alerts where user_id=? and title=? and day>=?", (u["id"], rec["title"], since), one=True): continue
        q("insert into alerts(user_id,day,title,body,created) values(?,?,?,?,?)", (u["id"], today, rec["title"], rec["why"], now()), commit=True); deliver(u["id"]); sent += 1
    return sent

@app.get("/api/consumer/alerts")
def alerts(u=Depends(consumer)): return [dict(r) for r in q("select id,day,title,body from alerts where user_id=? and read=0 order by id desc limit 5", (u["id"],))]
@app.post("/api/consumer/alerts/{aid}/read")
def alert_read(aid: int, u=Depends(consumer)): q("update alerts set read=1 where id=? and user_id=?", (aid, u["id"]), commit=True); return {"ok": True}

# ---------- Phase 5: barcode, label scan, photo check, push/email delivery ----------
import base64, io, smtplib
from email.message import EmailMessage
from PIL import Image
for _s in ["create table if not exists photo_metrics(id integer primary key, user_id int references users(id) on delete cascade, day text, redness real, brightness real, sharpness real)",
           "create table if not exists push_subs(id integer primary key, user_id int references users(id) on delete cascade, endpoint text unique, sub text)"]: q(_s, commit=True)

def off_lookup(code):
    r = httpx.get(f"https://world.openbeautyfacts.org/api/v2/product/{code}.json", params={"fields": "product_name,brands,ingredients_text,categories_tags"}, headers={"User-Agent": "SKINSHIFT/1.0"}, timeout=10)
    return r.json() if r.status_code == 200 else {"status": 0}

def guess_category(tags):
    t = " ".join(tags or [])
    for k, c in (("sun", "sunscreen"), ("moistur", "moisturiser"), ("cleans", "cleanser"), ("serum", "serum")):
        if k in t: return c
    return "other"

@app.get("/api/consumer/barcode/{code}")
def barcode(code: str, u=Depends(consumer)):
    if not re.fullmatch(r"\d{8,14}", code): raise HTTPException(422, "Barcodes are 8 to 14 digits.")
    throttle(f"bar:{u['id']}", 30)
    try: d = off_lookup(code)
    except Exception: raise HTTPException(502, "The product database is unreachable right now. Enter the product by hand.")
    p = d.get("product") if d.get("status") == 1 else None
    if not p: raise HTTPException(404, "Not found in Open Beauty Facts. Add it by hand or photograph the label.")
    return {"name": " ".join(x for x in (p.get("brands"), p.get("product_name")) if x)[:80], "category": guess_category(p.get("categories_tags")), "ingredients": (p.get("ingredients_text") or "")[:3000], "source": "Open Beauty Facts (community data; check against the pack)"}

class Img(BaseModel): image: str = Field(max_length=6_000_000); consent_image: bool = False
def decode_img(i: Img):
    if not i.consent_image: raise HTTPException(400, "Please agree to the photo being processed first.")
    m = re.match(r"data:image/(jpeg|png|webp);base64,(.+)$", i.image, re.S)
    if not m: raise HTTPException(422, "Send a JPEG, PNG or WebP image.")
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > 4_500_000: raise HTTPException(413, "Image is too large.")
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try: im = Image.open(io.BytesIO(raw)); im.load(); return im.convert("RGB")
    except Exception: raise HTTPException(422, "That image could not be read.")

@app.post("/api/consumer/label")
def scan_label(i: Img, u=Depends(consumer)):
    decode_img(i); throttle(f"label:{u['id']}", 10)
    prompt = ("Read this skincare product label. Reply with ONLY JSON: {\"name\": string|null, \"category\": \"cleanser\"|\"moisturiser\"|\"sunscreen\"|\"serum\"|\"other\", \"ingredients\": string|null}. "
              "Copy the ingredient list exactly as printed, comma-separated. Use null for anything not clearly legible. Do not guess.")
    out = llm_call([{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": i.image}}]}], max_tokens=1500)
    m = re.search(r"\{.*\}", out or "", re.S)
    try: d = json.loads(m.group(0))
    except Exception: raise HTTPException(422, "I couldn’t read that label. Try brighter light and a flatter angle, or type the ingredients.")
    cat = d.get("category") if d.get("category") in CATS else "other"
    return {"name": str(d.get("name") or "")[:80], "category": cat, "ingredients": str(d.get("ingredients") or "")[:3000], "note": "Check this against the packaging before adding. Nothing was saved."}

def photo_metrics(im):
    if min(im.size) < 200: return {"ok": False, "issues": ["The photo is too small. Use a closer, higher-resolution photo."]}
    import numpy as np
    a = np.asarray(im.resize((256, 256)), dtype=float); lum = a.mean(axis=2)
    sharp = float((-4 * lum[1:-1, 1:-1] + lum[:-2, 1:-1] + lum[2:, 1:-1] + lum[1:-1, :-2] + lum[1:-1, 2:]).var()); bright = float(lum.mean())
    c = a[64:192, 64:192]; red = float(((c[..., 0] - c[..., 1]) / (c.sum(axis=2) + 1)).mean()); issues = []
    if bright < 70: issues.append("Too dark. Face a window in daylight.")
    if bright > 190: issues.append("Too bright or washed out. Move out of direct sun.")
    if sharp < 30: issues.append("Blurry. Hold steady and tap to focus.")
    return {"ok": not issues, "issues": issues, "brightness": round(bright), "sharpness": round(sharp), "redness_index": round(red, 3)}

@app.post("/api/consumer/photo")
def photo(i: Img, u=Depends(consumer)):
    throttle(f"photo:{u['id']}", 20); m = photo_metrics(decode_img(i))
    if m["ok"]: q("insert into photo_metrics(user_id,day,redness,brightness,sharpness) values(?,?,?,?,?)", (u["id"], dt.date.today().isoformat(), m["redness_index"], m["brightness"], m["sharpness"]), commit=True)
    return {**m, "stored": "Only these numbers were saved. The photo was discarded." if m["ok"] else "Nothing saved."}

@app.get("/api/consumer/photo/summary")
def photo_summary(u=Depends(consumer)):
    rows = [dict(r) for r in q("select day,redness from photo_metrics where user_id=? order by day,id", (u["id"],))]
    note = "A relative redness reading, not a skin score or diagnosis. It depends on lighting and has not been validated across Indian skin tones; treat it as a rough personal trend."
    if len(rows) < 2: return {"readings": rows, "summary": "Take at least two good-quality photos in similar light to see a trend.", "note": note}
    ch = rows[-1]["redness"] - rows[0]["redness"]
    return {"readings": rows, "note": note, "summary": f"{len(rows)} readings. Change from first to latest: {ch:+.3f}. " + ("Changes under 0.02 are likely photo-to-photo variation (a rough guess, not validated)." if abs(ch) < .02 else "This is larger than typical photo-to-photo variation, but lighting and make-up can still explain it.")}

# delivery: alerts are generic on purpose so nothing sensitive shows on a lock screen or in an inbox preview
GENERIC = "You have a new suggestion in SKINSHIFT. Open the app to see it."
def send_email(to, body):
    if not os.getenv("SMTP_HOST"): return False
    try:
        m = EmailMessage(); m["Subject"] = "SKINSHIFT"; m["From"] = os.getenv("SMTP_FROM", "no-reply@skinshift.local"); m["To"] = to; m.set_content(body + "\n\nTurn off emails in My Skin > profile.")
        with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            if os.getenv("SMTP_USER"): s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            s.send_message(m)
        return True
    except Exception as e: audit("system", "email_failed", type(e).__name__); return False

def send_push(sub, body):
    key = os.getenv("VAPID_PRIVATE_KEY")
    if not key: return False
    try:
        from pywebpush import webpush, WebPushException
        webpush(subscription_info=json.loads(sub["sub"]), data=json.dumps({"title": "SKINSHIFT", "body": body}), vapid_private_key=key, vapid_claims={"sub": os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")}); return True
    except Exception as e:
        if getattr(getattr(e, "response", None), "status_code", 0) in (404, 410): q("delete from push_subs where id=?", (sub["id"],), commit=True)
        audit("system", "push_failed", type(e).__name__); return False

def deliver(uid):
    u = q("select email from users where id=?", (uid,), one=True)
    if get_profile(uid).alert_email: send_email(u["email"], GENERIC)
    for s in q("select * from push_subs where user_id=?", (uid,)): send_push(s, GENERIC)

@app.get("/api/consumer/push/key")
def push_key(u=Depends(consumer)): return {"key": os.getenv("VAPID_PUBLIC_KEY")}
@app.post("/api/consumer/push/subscribe")
def push_sub(body: dict, u=Depends(consumer)):
    ep, k = str(body.get("endpoint", "")), body.get("keys") or {}
    if not ep.startswith("https://") or not k.get("p256dh") or not k.get("auth"): raise HTTPException(422, "Invalid subscription.")
    q("insert into push_subs(user_id,endpoint,sub) values(?,?,?) on conflict(endpoint) do update set user_id=excluded.user_id, sub=excluded.sub", (u["id"], ep, json.dumps({"endpoint": ep, "keys": {"p256dh": k["p256dh"], "auth": k["auth"]}})), commit=True); return {"ok": True}
