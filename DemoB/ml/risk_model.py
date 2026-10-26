"""Load the trained Demo B classifier; fallback is for dashboard previews only."""
from pathlib import Path
import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier

FEATURES = ["result_count", "hour", "target_table_count", "query_frequency",
            "query_duration_ms", "is_department_query"]


def _model():
    rng = np.random.default_rng(401)
    normal = np.column_stack((rng.poisson(4, 600), rng.integers(8, 19, 600),
                              np.ones(600), rng.poisson(3, 600),
                              rng.normal(30, 12, 600).clip(1), rng.integers(0, 2, 600)))
    suspicious = np.column_stack((rng.integers(30, 300, 300), rng.choice([0,1,2,3,22,23], 300),
                                  rng.integers(2, 5, 300), rng.integers(30, 300, 300),
                                  rng.normal(200, 80, 300).clip(1), rng.integers(0, 2, 300)))
    x = np.vstack((normal, suspicious))
    y = np.r_[np.zeros(len(normal), dtype=int), np.ones(len(suspicious), dtype=int)]
    model = RandomForestClassifier(n_estimators=120, max_depth=7, class_weight="balanced",
                                   random_state=401)
    model.fit(x, y)
    return model


MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
LIVE_MODEL_PATH = MODEL_DIR / "random_forest_live_sim.joblib"
LIVE_METADATA_PATH = MODEL_DIR / "live_sim_model_metadata.json"
SYNTHETIC_MODEL_PATH = MODEL_DIR / "random_forest_synthetic.joblib"
if LIVE_MODEL_PATH.exists():
    import joblib
    MODEL = joblib.load(LIVE_MODEL_PATH)
elif SYNTHETIC_MODEL_PATH.exists():
    import joblib
    MODEL = joblib.load(SYNTHETIC_MODEL_PATH)
else:
    MODEL = _model()

try:
    LIVE_THRESHOLD = float(json.loads(LIVE_METADATA_PATH.read_text(encoding="utf-8")).get("threshold", 0.65))
except (OSError, ValueError, TypeError):
    LIVE_THRESHOLD = 0.65


def score_behavior(features):
    row = np.array([[float(features[name]) for name in FEATURES]])
    score = float(MODEL.predict_proba(row)[0, 1])
    return {"score": score, "label": "HIGH" if score >= LIVE_THRESHOLD else "NORMAL",
            "threshold": LIVE_THRESHOLD}
