"""Revenue grid of model recipes on the 2016 replay (windows H1 and H2).

14 recipes x 2 windows x 3 within-day orders x 4 logit shifts. Besides the candidate algorithms and
ensembles, it measures two ablations (one model per hotel, per-hotel intercept calibration) and what
the post-booking columns would be worth (FULL_CFG, WITH_SPECIAL_REQUESTS_CFG: references only).

Run: python experiments/02_recipe_grid.py      (writes results/02_recipe_grid.csv, ~1 hour on 6 cores)
"""
from joblib import Parallel, delayed
import pandas as pd

from common import RESULTS, run_config, StreamCancelModel
from src.stream_model import FULL_CFG, WITH_SPECIAL_REQUESTS_CFG

RECIPES = {
    "lr": lambda: StreamCancelModel("lr"),
    "lgb": lambda: StreamCancelModel("lgb"),
    "cb": lambda: StreamCancelModel("cb"),
    "ebm": lambda: StreamCancelModel("ebm"),
    "lr+lgb": lambda: StreamCancelModel(["lr", "lgb"]),
    "lr+lgb+cb+ebm": lambda: StreamCancelModel(["lr", "lgb", "cb", "ebm"]),
    "lgb_perhotel": lambda: StreamCancelModel("lgb", per_hotel=True),
    "lr_perhotel": lambda: StreamCancelModel("lr", per_hotel=True),
    "lr_cal": lambda: StreamCancelModel("lr", calibrate="intercept"),
    "lgb_cal": lambda: StreamCancelModel("lgb", calibrate="intercept"),
    "ref_full_lr": lambda: StreamCancelModel("lr", cfg=FULL_CFG),
    "ref_full_lgb": lambda: StreamCancelModel("lgb", cfg=FULL_CFG),
    "ref_sr_lr": lambda: StreamCancelModel("lr", cfg=WITH_SPECIAL_REQUESTS_CFG),
    "ref_sr_lgb": lambda: StreamCancelModel("lgb", cfg=WITH_SPECIAL_REQUESTS_CFG),
}
SHIFTS = (-0.3, 0.0, 0.3, 0.6)


def job(name, window):
    return run_config(name, RECIPES[name], window, seeds=(0, 1, 2), shifts=SHIFTS)


if __name__ == "__main__":
    res = Parallel(n_jobs=6)(delayed(job)(n, w) for n in RECIPES for w in ("H1", "H2"))
    pd.DataFrame([r for rs in res for r in rs]).to_csv(RESULTS / "02_recipe_grid.csv", index=False)
