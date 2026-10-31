"""Next-day comfort forecasting with honest evaluation: time split + held-out-participant CV, against simple baselines.
Refuses to train on too little data. Reports MAE/RMSE/R2, never 'accuracy'."""
import argparse, json, os
import numpy as np, pandas as pd
import statsmodels.formula.api as smf
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

ENV = ["pm25", "pm10", "ozone", "uv", "humidity", "temp", "pm25_lag1", "pm25_roll3", "uv_roll3", "hum_lag1", "month"]

def build(env, ck):
    env = env.copy(); env["date"] = pd.to_datetime(env["date"]); env = env.sort_values(["city", "date"])
    g = env.groupby("city")
    env["pm25_lag1"] = g.pm25.shift(1); env["hum_lag1"] = g.humidity.shift(1)
    env["pm25_roll3"] = g.pm25.transform(lambda s: s.rolling(3, min_periods=1).mean()); env["uv_roll3"] = g.uv.transform(lambda s: s.rolling(3, min_periods=1).mean())
    env["month"] = env.date.dt.month
    ck = ck.copy(); ck["date"] = pd.to_datetime(ck["date"]); ck = ck.sort_values(["pid", "date"])
    ck["comfort_prev"] = ck.groupby("pid").comfort.shift(1)
    ck["y"] = ck.groupby("pid").comfort.shift(-1); gap = (ck.groupby("pid").date.shift(-1) - ck.date).dt.days
    ck.loc[gap != 1, "y"] = np.nan  # only true next-day targets
    df = ck.merge(env[["city", "date"] + ENV], on=["city", "date"], how="left")
    return df.dropna(subset=["y"]).reset_index(drop=True)

def metrics(y, p): return {"mae": round(float(mean_absolute_error(y, p)), 3), "rmse": round(float(np.sqrt(mean_squared_error(y, p))), 3), "r2": round(float(r2_score(y, p)), 3)}

def models(tr):
    m = {"ridge_env": (ENV, make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(1.0))),
         "xgb_env": (ENV, XGBRegressor(n_estimators=300, max_depth=3, learning_rate=.05, subsample=.8, colsample_bytree=.8, random_state=0)),
         "xgb_env_plus_history": (ENV + ["comfort_prev"], XGBRegressor(n_estimators=300, max_depth=3, learning_rate=.05, subsample=.8, colsample_bytree=.8, random_state=0))}
    return m

def mixed_predict(tr, te):
    f = "y ~ pm25 + uv + humidity + temp + pm25_roll3"; cols = ["y", "pm25", "uv", "humidity", "temp", "pm25_roll3", "pid"]
    fit = smf.mixedlm(f, tr[cols].dropna(), groups="pid").fit(reml=False)
    fe = fit.predict(te.fillna(tr[cols].median(numeric_only=True)))
    re = te.pid.map(lambda p: float(fit.random_effects[p].iloc[0]) if p in fit.random_effects else 0.0)
    return (fe + re).to_numpy()

def predict_all(tr, te):
    out = {"baseline_global_mean": np.full(len(te), tr.y.mean()),
           "baseline_person_mean": te.pid.map(tr.groupby("pid").y.mean()).fillna(tr.y.mean()).to_numpy(),
           "baseline_persistence": te.comfort_prev.fillna(tr.y.mean()).to_numpy(),
           "mixed_effects_env": mixed_predict(tr, te)}
    for name, (cols, mdl) in models(tr).items(): out[name] = mdl.fit(tr[cols], tr.y).predict(te[cols])
    return out

def run(env, ck, min_participants=20, min_rows=500):
    df = build(env, ck)
    if df.pid.nunique() < min_participants or len(df) < min_rows:
        raise SystemExit(f"Not enough data to train responsibly: {df.pid.nunique()} participants, {len(df)} rows (need {min_participants}+ and {min_rows}+).")
    cut = df.date.quantile(.8); tr, te = df[df.date <= cut], df[df.date > cut]
    rep = {"rows": len(df), "participants": int(df.pid.nunique()), "time_split": {k: metrics(te.y, p) for k, p in predict_all(tr, te).items()}}
    oof = {}; 
    for a, b in GroupKFold(5).split(df, groups=df.pid):
        for k, p in predict_all(df.iloc[a], df.iloc[b]).items(): oof.setdefault(k, pd.Series(np.nan, index=df.index)).iloc[b] = p
    rep["held_out_participants_cv"] = {k: metrics(df.y, v) for k, v in oof.items()}
    base = rep["held_out_participants_cv"]["baseline_global_mean"]["mae"]
    rep["note"] = "Models only add value if their MAE beats the baselines on both splits. Environment-only models test whether exposure adds information beyond a person's own history."
    rep["best_model_cv"] = min((k for k in oof if not k.startswith("baseline")), key=lambda k: rep["held_out_participants_cv"][k]["mae"]); rep["beats_global_mean_baseline"] = rep["held_out_participants_cv"][rep["best_model_cv"]]["mae"] < base
    return rep

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--env", default="data/env.csv"); ap.add_argument("--checkins", default="data/checkins.csv"); ap.add_argument("--out", default="reports/metrics.json")
    a = ap.parse_args(); r = run(pd.read_csv(a.env), pd.read_csv(a.checkins)); os.makedirs(os.path.dirname(a.out), exist_ok=True); json.dump(r, open(a.out, "w"), indent=2); print(json.dumps(r, indent=2))
