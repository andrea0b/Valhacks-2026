"""Finalist recipes on H1, H2 and the full year 2016, with temporal stacking and a fine shift grid.

7 recipes x 3 windows x 3 within-day orders x 5 logit shifts.
Run: python experiments/03_finalists.py      (writes results/03_finalists.csv, ~1 hour on 9 cores)
"""
from joblib import Parallel, delayed
import pandas as pd

from common import RESULTS, WINDOWS, run_config, StreamCancelModel

RECIPES = {
    "lr": lambda: StreamCancelModel("lr"),
    "lgb": lambda: StreamCancelModel("lgb"),
    "avg4": lambda: StreamCancelModel(["lr", "lgb", "cb", "ebm"]),
    "stack4": lambda: StreamCancelModel(["lr", "lgb", "cb", "ebm"], stack=True),
    "stack_lr_lgb": lambda: StreamCancelModel(["lr", "lgb"], stack=True),
    "stack_lr_ebm_cb": lambda: StreamCancelModel(["lr", "ebm", "cb"], stack=True),
    "stack_lr_lgb_cb": lambda: StreamCancelModel(["lr", "lgb", "cb"], stack=True),
}
SHIFTS = (-0.2, -0.1, 0.0, 0.1, 0.2)


def job(name, window):
    return run_config(name, RECIPES[name], window, seeds=(0, 1, 2), shifts=SHIFTS)


if __name__ == "__main__":
    order = sorted(((n, w) for n in RECIPES for w in WINDOWS), key=lambda t: t[1] != "FY")  # long jobs first
    res = Parallel(n_jobs=9)(delayed(job)(n, w) for n, w in order)
    pd.DataFrame([r for rs in res for r in rs]).to_csv(RESULTS / "03_finalists.csv", index=False)
