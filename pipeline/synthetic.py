"""SYNTHETIC data to smoke-test the training pipeline. NOT real, proves nothing about skin.
Writes data/synthetic_env.csv and data/synthetic_checkins.csv in exactly the columns pipeline.train expects.
Effects are planted (PM2.5 and UV lower comfort, humidity raises it) so you can check the pipeline recovers them.
Real runs use pipeline.ingest (environment) + pipeline.export (opted-in check-ins) instead."""
import argparse, os
import numpy as np, pandas as pd

CITIES = ["Mumbai", "Delhi", "Bengaluru", "Jaipur"]
BASE = {"Mumbai": (45, 78, 7), "Delhi": (110, 55, 8), "Bengaluru": (30, 68, 7), "Jaipur": (75, 50, 9)}  # rough pm25, humidity, uv levels

def make_env(start, days, rng):
    d = pd.date_range(start, periods=days); rows = []
    for c in CITIES:
        pm, hu, uv = BASE[c]; t = np.arange(days); s = np.sin(2 * np.pi * t / 365)
        pm25 = np.clip(pm * (1 + .4 * s) + rng.gamma(2, 8, days) - 16, 3, None)
        rows.append(pd.DataFrame({"date": d, "city": c, "pm25": pm25, "pm10": pm25 * 1.7 + rng.normal(0, 10, days), "ozone": 40 + 15 * s + rng.normal(0, 8, days),
                                  "uv": np.clip(uv - 2 * s + rng.normal(0, 1.2, days), 0, 12), "humidity": np.clip(hu - 15 * s + rng.normal(0, 8, days), 15, 100), "temp": 27 + 6 * s + rng.normal(0, 2, days)}))
    return pd.concat(rows, ignore_index=True)

def make_checkins(env, n_people, n_days, adherence, rng):
    rows = []; dates = np.sort(env.date.unique())
    for i in range(n_people):
        city = CITIES[i % 4]; e = env[env.city == city].set_index("date"); start = rng.integers(0, len(dates) - n_days); base = rng.normal(6.8, .8); sens = rng.uniform(.5, 1.5); noise = 0.0
        for dd in dates[start:start + n_days]:
            if rng.random() > adherence: continue
            r = e.loc[dd]; noise = .6 * noise + rng.normal(0, .5)
            y = base - sens * (.012 * (r.pm25 - 60) + .10 * (r.uv - 7)) + .015 * (r.humidity - 60) + noise
            rows.append({"pid": f"s{i:03d}", "date": pd.Timestamp(dd).date().isoformat(), "city": city, "comfort": float(np.clip(np.round(y * 2) / 2, 1, 10))})
    return pd.DataFrame(rows)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--people", type=int, default=60); ap.add_argument("--days", type=int, default=90); ap.add_argument("--adherence", type=float, default=.85); ap.add_argument("--seed", type=int, default=0); ap.add_argument("--outdir", default="data")
    a = ap.parse_args(); rng = np.random.default_rng(a.seed); env = make_env("2025-01-01", 540, rng); ck = make_checkins(env, a.people, a.days, a.adherence, rng)
    os.makedirs(a.outdir, exist_ok=True); env.to_csv(f"{a.outdir}/synthetic_env.csv", index=False); ck.to_csv(f"{a.outdir}/synthetic_checkins.csv", index=False)
    print(f"SYNTHETIC: {len(env)} env rows, {len(ck)} check-ins, {ck.pid.nunique()} people")
