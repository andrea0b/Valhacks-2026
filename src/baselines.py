"""Reference policies to compare the model against (all with the Solution interface).

Every policy has the Solution interface: __init__(commitments, capacity, ...) and decide(booking).
Extra arguments (history, factor) are bound with functools.partial before the replay.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.simulator import Holdout


class AcceptAll:
    def __init__(self, commitments, capacity):
        pass

    def decide(self, booking: dict) -> bool:
        return True


class RejectAll:
    def __init__(self, commitments, capacity):
        pass

    def decide(self, booking: dict) -> bool:
        return False


class LoadLimit:
    """First come, first served: accept while the weighted booked load stays within
    `factor` x capacity on every night of the stay.

    weight 1 and factor 1    -> no overbooking (booked rooms <= free rooms)
    weight 1 and factor k    -> fixed overbooking (booked rooms <= k x free rooms)
    weight = P(show)         -> expected guests who show <= free rooms
    """

    def __init__(self, commitments: pd.DataFrame, capacity: dict[str, pd.Series], factor: float = 1.0):
        self.factor = factor
        self.start = next(iter(capacity.values())).index[0]
        self.cap = {h: s.to_numpy(dtype=float) * factor for h, s in capacity.items()}
        self.load = {h: np.zeros(len(s)) for h, s in capacity.items()}
        for b in commitments.to_dict("records"):
            self._add(b)

    def weight(self, booking: dict) -> float:
        return 1.0

    def _span(self, b: dict) -> tuple[str, slice]:
        s = (b["arrival_date"] - self.start).days
        return b["hotel"], slice(s, min(s + b["nights"], len(self.load[b["hotel"]])))

    def _add(self, b: dict) -> None:
        h, sl = self._span(b)
        self.load[h][sl] += self.weight(b)

    def decide(self, booking: dict) -> bool:
        h, sl = self._span(booking)
        if (self.load[h][sl] + self.weight(booking) <= self.cap[h][sl] + 1e-9).all():
            self.load[h][sl] += self.weight(booking)
            return True
        return False


class ExpectedShows(LoadLimit):
    """Overbook using historical show rates: weight = 1 - cancel rate of the booking's group
    (by hotel, or by hotel x `by` column), estimated on `history` only."""

    def __init__(self, commitments, capacity, history: pd.DataFrame, by: str | None = None, factor: float = 1.0):
        keys = ["hotel"] + ([by] if by else [])
        self.by = by
        self.p_show = (1 - history.groupby(keys).cancelled.mean()).to_dict()
        self.p_show_hotel = (1 - history.groupby("hotel").cancelled.mean()).to_dict()
        super().__init__(commitments, capacity, factor)

    def weight(self, b: dict) -> float:
        if self.by is None:
            return self.p_show_hotel[b["hotel"]]
        return self.p_show.get((b["hotel"], b[self.by]), self.p_show_hotel[b["hotel"]])


def oracle_accept(ho: Holdout) -> np.ndarray:
    """Reference ceiling (cheats, not a valid policy): knows who will show up and picks them
    offline, highest nightly rate first, until the rooms are full. Not a hard upper bound
    (greedy, not optimal), but shows how much is left on the table."""
    req = ho.requests.merge(ho.truth[["cancelled"]], left_on="booking_id", right_index=True, how="left")
    order = req[req.cancelled == 0].sort_values("nightly_rate", ascending=False)
    shown_commit = ho.commitments[ho.truth.loc[ho.commitments.booking_id, "cancelled"].values == 0]
    pol = LoadLimit(shown_commit, ho.capacity)
    accepted = np.zeros(len(req), dtype=bool)
    for i, b in zip(order.index, order.drop(columns="cancelled").to_dict("records")):
        accepted[i] = pol.decide(b)
    return accepted
