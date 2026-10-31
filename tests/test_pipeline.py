import numpy as np, pandas as pd
from pipeline import ingest, train

def synthetic(n_p=30, days=120, seed=0):  # smoke-test fixture only: proves the code runs, says nothing about real skin
    r = np.random.default_rng(seed); d = pd.date_range("2025-01-01", periods=days); cities = list(ingest.CITIES); rows = []
    env = pd.concat([pd.DataFrame({"date": d, "city": c, "pm25": 60 + 40 * np.sin(np.arange(days) / 9) + r.normal(0, 10, days), "pm10": 90 + r.normal(0, 15, days), "ozone": 50 + r.normal(0, 8, days),
        "uv": 7 + 2 * np.sin(np.arange(days) / 20) + r.normal(0, .5, days), "humidity": 55 + 15 * np.sin(np.arange(days) / 13) + r.normal(0, 4, days), "temp": 28 + r.normal(0, 2, days)}) for c in cities])
    for i in range(n_p):
        c = cities[i % 4]; e = env[env.city == c]; b = r.uniform(5, 8)
        y = np.clip(b - .02 * (e.pm25.values - 60) + .15 * (e.humidity.values - 55) / 15 + r.normal(0, .5, days), 1, 10)
        rows.append(pd.DataFrame({"pid": f"p{i}", "date": e.date.values, "city": c, "comfort": y}))
    return env, pd.concat(rows)

def test_pipeline_runs_and_reports_baselines():
    rep = train.run(*synthetic())
    assert {"time_split", "held_out_participants_cv", "best_model_cv"} <= rep.keys()
    assert "baseline_persistence" in rep["time_split"] and rep["beats_global_mean_baseline"]

def test_refuses_tiny_data():
    env, ck = synthetic(3, 30)
    try: train.run(env, ck); assert False
    except SystemExit as e: assert "Not enough data" in str(e)

def test_open_meteo_parsing(monkeypatch):
    def fake(url, params=None, headers=None):
        if "archive" in url: return {"daily": {"time": ["2025-01-01"], "temperature_2m_mean": [25], "relative_humidity_2m_mean": [60]}}
        return {"hourly": {"time": ["2025-01-01T00:00", "2025-01-01T12:00"], "pm2_5": [40, 60], "pm10": [80, 100], "ozone": [30, 50], "uv_index": [0, 9]}}
    monkeypatch.setattr(ingest, "_get", fake); d = ingest.open_meteo("Delhi", "2025-01-01", "2025-01-01")
    assert d.pm25[0] == 50 and d.uv[0] == 9 and d.humidity[0] == 60
