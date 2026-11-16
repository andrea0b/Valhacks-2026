"""Shared helpers for the experiment scripts.

Every number produced here comes from the local replay of 2016 (src/simulator.py), built from
train.csv only. A model is trained once per window on `ho.history` (arrivals before the window),
then the replay is repeated for several within-day request orders (shuffle seeds) and logit shifts.
Results are written to experiments/results/.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from src.policy import BidPricePolicy  # noqa: E402
from src.simulator import build_holdout, load_train, score  # noqa: E402
from src.stream_model import StreamCancelModel  # noqa: E402,F401  (re-exported for the scripts)

RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)

# Replay windows: the policy goes live on the first day and decides every later request.
WINDOWS = {
    "H1": dict(start="2016-01-01", end="2016-06-30"),
    "H2": dict(start="2016-07-01"),
    "FY": dict(year=2016),
}


def replay(ho, model: StreamCancelModel, shift: float, policy_kw: dict | None = None) -> dict:
    """One replay of the window with a fitted model; returns net revenue (M EUR) and counters."""
    model.start_session(ho.commitments)
    t0 = time.perf_counter()
    pol = BidPricePolicy(ho.commitments.copy(), {h: c.copy() for h, c in ho.capacity.items()},
                         history=ho.history, model=model, logit_shift=shift, **(policy_kw or {}))
    acc = np.array([bool(pol.decide(b)) for b in ho.requests.to_dict("records")])
    out = score(ho, acc)
    return {"net_M": out.net.sum() / 1e6, "net_DT": out.net.iloc[0] / 1e6, "net_SS": out.net.iloc[1] / 1e6,
            "walk": int(out.walk.sum()), "accepted": int(out.accepted.sum()),
            "empty_nights": int(out.empty_room_nights.sum()), "sec": time.perf_counter() - t0}


def run_config(name: str, factory, window: str, seeds=(0, 1, 2), shifts=(0.0,),
               policy_kw: dict | None = None) -> list[dict]:
    """Fit `factory()` on the window's history once, then replay for every seed x shift."""
    df = load_train()
    ho0 = build_holdout(df, **WINDOWS[window])
    t0 = time.perf_counter()
    model = factory().fit(ho0.history, as_of=ho0.days[0])
    fit_s = time.perf_counter() - t0
    rows = []
    for seed in seeds:
        ho = build_holdout(df, shuffle_seed=seed, **WINDOWS[window])
        for sh in shifts:
            r = replay(ho, model, sh, policy_kw)
            rows.append({"config": name, "window": window, "seed": seed, "shift": sh, "fit_s": fit_s, **r})
    return rows
