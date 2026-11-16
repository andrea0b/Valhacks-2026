"""Hotel overbooking: the `Solution` class passed to the organisers' `evaluate(Solution)`.

Rules of the challenge: Downtown Hotel has 124 rooms, Seaside Hotel 103. A guest who shows up
earns `nightly_rate x nights`; a guest who cancels earns nothing. When a hotel is full at check-in
the cheapest arriving guests are walked: no revenue and a penalty of 2.5 x their stay value.
Score = revenue of seated guests - walk penalties. Requests arrive one at a time, in booking-date
order, and must be accepted or rejected immediately.

How a request is decided (details in README.md and docs/methodology.md):
  1. p_cancel(booking): a stack of three models (LR, LightGBM, CatBoost) trained on 2015-2016 (models/final.joblib), using only
     what a hotel knows when the request arrives;
  2. bid price per night: the rate of the marginal guest we still expect to seat on that night;
  3. accept when rate >= average bid price of the stay and the expected shows fit the free rooms.
After every decide(), `explain()` returns the reason in plain English.
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.explain import reason  # noqa: E402
from src.policy import BidPricePolicy  # noqa: E402


class Solution:
    def __init__(self, commitments: pd.DataFrame, capacity: dict[str, pd.Series]) -> None:
        """Called once, before the planning year starts.

        commitments  arrivals of the planning year booked before 1 January (already confirmed,
                     no `cancelled` column)
        capacity     hotel -> free rooms on each night of the year (indexed by date)
        """
        bundle = joblib.load(ROOT / "models" / "final.joblib")
        self.model = bundle["model"]
        self.model.start_session(commitments)
        self.policy = BidPricePolicy(commitments.copy(), {h: c.copy() for h, c in capacity.items()},
                                     history=self.model._hist, model=self.model, **bundle["policy_kw"])
        self._last: tuple[dict, bool] | None = None

    def decide(self, booking: dict) -> bool:
        """True = confirm the booking, False = reject it."""
        try:
            ok = bool(self.policy.decide(booking))
        except Exception:                      # never crash the replay: reject instead
            ok = False
            self.policy.last = {}
        self._last = (booking, ok)
        return ok

    def explain(self) -> str:
        """Reason for the last decide() call."""
        if self._last is None:
            return ""
        booking, ok = self._last
        return reason(self.policy, self.model, booking, ok)
