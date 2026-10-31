import numpy as np
from pipeline import synthetic as s, train

def test_synthetic_data_matches_training_columns_and_is_trainable():
    rng = np.random.default_rng(0); env = s.make_env("2025-01-01", 200, rng); ck = s.make_checkins(env, 24, 60, .9, rng)
    assert {"date", "city", *train.ENV[:6]} <= set(env.columns) and list(ck.columns) == ["pid", "date", "city", "comfort"]
    assert ck.comfort.between(1, 10).all()
    r = train.run(env, ck, min_participants=20, min_rows=500); assert r["participants"] == 24 and "baseline_persistence" in r["time_split"]
