"""Fetch real environmental data for the four study cities and merge it into data/env.csv.
Sources: Open-Meteo (modelled weather + air quality), NASA POWER (satellite/reanalysis), OpenAQ v3 (ground monitors, needs OPENAQ_API_KEY),
CPCB (manual CSV download from the CPCB portal, loaded with load_csv). Each value keeps its source so modelled and measured data are never mixed silently."""
import argparse, os
import httpx, pandas as pd

CITIES = {"Mumbai": (19.08, 72.88), "Delhi": (28.61, 77.21), "Bengaluru": (12.97, 77.59), "Jaipur": (26.91, 75.79)}

def _get(url, params=None, headers=None):
    r = httpx.get(url, params=params, headers=headers, timeout=60); r.raise_for_status(); return r.json()

def open_meteo(city, start, end):
    lat, lon = CITIES[city]
    w = _get("https://archive-api.open-meteo.com/v1/archive", dict(latitude=lat, longitude=lon, start_date=start, end_date=end, daily="temperature_2m_mean,relative_humidity_2m_mean", timezone="auto"))["daily"]
    a = _get("https://air-quality-api.open-meteo.com/v1/air-quality", dict(latitude=lat, longitude=lon, start_date=start, end_date=end, hourly="pm2_5,pm10,ozone,uv_index", timezone="auto"))["hourly"]
    wd = pd.DataFrame({"date": pd.to_datetime(w["time"]), "temp": w["temperature_2m_mean"], "humidity": w["relative_humidity_2m_mean"]})
    ah = pd.DataFrame(a); ah["date"] = pd.to_datetime(ah["time"]).dt.normalize()
    ad = ah.groupby("date").agg(pm25=("pm2_5", "mean"), pm10=("pm10", "mean"), ozone=("ozone", "mean"), uv=("uv_index", "max")).reset_index()
    d = wd.merge(ad, on="date", how="outer"); d["city"] = city; return d

def nasa_power(city, start, end):
    lat, lon = CITIES[city]
    j = _get("https://power.larc.nasa.gov/api/temporal/daily/point", dict(parameters="T2M,RH2M,ALLSKY_SFC_UV_INDEX", community="SB", longitude=lon, latitude=lat, start=start.replace("-", ""), end=end.replace("-", ""), format="JSON"))
    p = j["properties"]["parameter"]
    d = pd.DataFrame({"date": pd.to_datetime(list(p["T2M"]), format="%Y%m%d"), "nasa_temp": list(p["T2M"].values()), "nasa_humidity": list(p["RH2M"].values()), "nasa_uv": list(p["ALLSKY_SFC_UV_INDEX"].values())})
    d = d.replace(-999, float("nan")); d["city"] = city; return d

def openaq(city, start, end, key=None):
    """Ground-monitor PM2.5 (daily mean) from the nearest OpenAQ stations within 25 km."""
    key = key or os.getenv("OPENAQ_API_KEY")
    if not key: return pd.DataFrame(columns=["date", "city", "pm25_ground"])
    lat, lon = CITIES[city]; h = {"X-API-Key": key}; rows = []
    locs = _get("https://api.openaq.org/v3/locations", dict(coordinates=f"{lat},{lon}", radius=25000, parameters_id=2, limit=5), h)["results"]
    for loc in locs:
        for s in loc.get("sensors", []):
            if s.get("parameter", {}).get("name") != "pm25": continue
            for r in _get(f"https://api.openaq.org/v3/sensors/{s['id']}/days", dict(datetime_from=start, datetime_to=end, limit=1000), h)["results"]:
                rows.append({"date": pd.to_datetime(r["period"]["datetimeFrom"]["utc"]).tz_localize(None).normalize(), "v": r["value"]})
    if not rows: return pd.DataFrame(columns=["date", "city", "pm25_ground"])
    d = pd.DataFrame(rows).groupby("date").v.mean().rename("pm25_ground").reset_index(); d["city"] = city; return d

def load_csv(path, city, date_col, pm25_col):
    """Load a manually downloaded CPCB station export (daily) as ground PM2.5 for one city."""
    d = pd.read_csv(path); d = d.rename(columns={date_col: "date", pm25_col: "pm25_cpcb"}); d["date"] = pd.to_datetime(d["date"], dayfirst=True)
    d = d.groupby("date").pm25_cpcb.mean().reset_index(); d["city"] = city; return d

def build(start, end, cities=CITIES):
    parts = []
    for c in cities:
        base = open_meteo(c, start, end)
        for f in (nasa_power, openaq):
            try: base = base.merge(f(c, start, end), on=["date", "city"], how="left")
            except Exception as e: print(f"warning: {f.__name__} failed for {c}: {e}")
        parts.append(base)
    env = pd.concat(parts, ignore_index=True)
    if "pm25_ground" not in env: env["pm25_ground"] = float("nan")
    env["pm25_is_measured"] = env["pm25_ground"].notna()
    return env

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--start", required=True); ap.add_argument("--end", required=True); ap.add_argument("--out", default="data/env.csv")
    a = ap.parse_args(); env = build(a.start, a.end); env.to_csv(a.out, index=False); print(f"wrote {len(env)} rows to {a.out}")
