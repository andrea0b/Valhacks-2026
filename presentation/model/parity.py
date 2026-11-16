"""Dump Python's numbers for the replay, so parity.mjs can check model.js against them.

Re-runs the replay of export.py with the same cached model and records, for every replayed
request: the feature vector the model really used, each member's logit, the stack probability, the
per-column contributions and constant of src.explain.decompose, each member's own contributions,
and the decision (outcome, bid, bid and free rooms per night, reason). It also records the
start-of-day price list (bid and free rooms per night, full precision) of every replay day.

Run after export.py:  python presentation/model/parity.py   (about 3 minutes)
Output: <temp>/valhacks-presentation/parity.json (not part of the presentation)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(next(p for p in HERE.parents if (p / "train-template-kit").exists())))

import export as X  # noqa: E402
from src.explain import decompose, member_contributions, outcome, reason  # noqa: E402
from src.stream_model import logit  # noqa: E402

OUT = X.CACHE / "parity.json"


def f(x):
    return None if x is None or not np.isfinite(x) else float(x)


def main() -> None:
    t0 = time.perf_counter()
    ho = X.holdout()
    model = X.fitted_model(ho)
    mj = json.loads((X.BUILD / "model.json").read_text(encoding="utf8"))
    assert mj["stack"]["intercept"] == float(model.stack_["intercept"]), "model.json is from another fit"
    ests = model.sets_[-1]
    reqs, days = [], []

    def on_day(t, day, pol):
        hs = []
        for h in ho.capacity:
            qs = X.quotes(pol, h, t, range(t, len(ho.days)))
            hs.append({"growth": X.growth_free(pol.forecast, h, t), "bid": [f(c["bid"]) for c in qs],
                       "free": [f(c["free"]) for c in qs], "N": [f(c["N"]) for c in qs], "P": [f(c["P"]) for c in qs]})
        days.append({"t": t, "day": day.strftime("%Y-%m-%d"), "hotels": hs})

    def on_request(b, ok, pol, s):
        A = model.last_array
        L = pol.last
        contrib, const = decompose(model, A)
        rec = {
            "id": int(b["booking_id"]), "features": A[0].tolist(),
            "members": {m: float(logit(e.predict(A))[0]) for m, e in zip(X.MEMBERS, ests)},
            "p": float(L["p_cancel"]), "contrib": contrib.tolist(), "constant": float(const),
            "outcome": outcome(L, ok), "bid": f(L["bid"]), "reason": reason(pol, model, b, ok),
            "bids": [f(c["bid"]) for c in L.get("nights", [])], "free": [f(c["free"]) for c in L.get("nights", [])],
        }
        if len(reqs) < 400:                       # members' own decompositions, for debugging
            rec["member_contrib"] = {}
            for m, e in zip(X.MEMBERS, ests):
                c, bias = member_contributions(e, A, model.fb)
                rec["member_contrib"][m] = {"c": c.tolist(), "bias": float(bias)}
        reqs.append(rec)

    X.replay(model, ho, on_day, on_request)
    OUT.write_text(json.dumps({"columns": model.fb.columns_, "requests": reqs, "days": days}, allow_nan=False),
                   encoding="utf8")
    print(f"{len(reqs)} requests, {len(days)} days -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, "
          f"{time.perf_counter() - t0:.0f} s)")


if __name__ == "__main__":
    main()
