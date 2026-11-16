"""Train the final cancellation model on ALL of train.csv and save the bundle `solution.py` loads.

The recipe (algorithms, features, recency half-life, stacking, policy parameters) was chosen with
the temporal walk-forward and the 2016 replay (experiments/, notebooks/07 and 08). Once chosen, it is
retrained on the whole history (July 2015 - December 2016) with the same rules on data and weights.

Run:  python -m src.build_final            (writes models/final.joblib, ~5 minutes)
"""
from __future__ import annotations

from pathlib import Path

import joblib

from src.simulator import load_train
from src.stream_model import StreamCancelModel

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

RECIPE = {
    "members": ["lr", "lgb", "cb"],          # logistic regression, LightGBM, CatBoost
    "stack": True,                           # logistic meta-model on out-of-time predictions
    "half_life": 6.0,                        # months: older arrivals weigh less
    "policy": {"logit_shift": 0.0},          # BidPricePolicy keyword arguments
}


def build(recipe: dict = RECIPE, out: Path = MODELS / "final.joblib") -> Path:
    df = load_train()
    model = StreamCancelModel(recipe["members"], half_life=recipe["half_life"], stack=recipe["stack"])
    model.fit(df)                            # goes live the day after the last training arrival
    out.parent.mkdir(exist_ok=True)
    joblib.dump({"model": model, "policy_kw": recipe["policy"], "recipe": recipe}, out, compress=3)
    return out


if __name__ == "__main__":
    print(build())
