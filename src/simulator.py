"""Local replay of the evaluation rules on a holdout window taken from train.csv.

It reproduces what the organisers' evaluator does on the competition year, using 2016 (or part of
it) as the test window:
1. build `commitments` (window arrivals booked before the window starts, without `cancelled`) and
   `capacity` (rooms minus guests who arrived earlier and are still in house, per night);
2. create the policy with (commitments, capacity) and call decide() once per request, in
   booking-date order (random order within a day, see `build_holdout`);
3. at check-in, seat the guests who show up day by day; when the hotel is full the cheapest
   arriving guests are walked (no revenue, penalty 2.5 x stay value).

Note on "full at check-in": guests are seated in arrival order, so when a guest arrives every
occupied room on the following nights is also occupied tonight. Checking the arrival night alone
or the whole stay therefore gives the same result; we check the whole stay to be safe.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TRAIN_CSV = ROOT / "train-template-kit" / "train.csv"
ROOMS = {"Downtown Hotel": 124, "Seaside Hotel": 103}
WALK_PENALTY = 2.5


DROPPED_COLUMNS = ["deposit"]   # organisers' rule: the deposit column must not be used


def load_train(path: Path = TRAIN_CSV) -> pd.DataFrame:
    """train.csv with parsed dates, without `deposit`, plus `value` = nightly_rate x nights."""
    df = pd.read_csv(path, parse_dates=["arrival_date", "booking_date"]).drop(columns=DROPPED_COLUMNS)
    df["value"] = df.nightly_rate * df.nights
    return df


@dataclass
class Holdout:
    year: int
    days: pd.DatetimeIndex                # every night of the holdout year
    history: pd.DataFrame                 # arrivals before the holdout year (with outcomes)
    commitments: pd.DataFrame             # what the policy receives (no `cancelled`)
    capacity: dict[str, pd.Series]        # what the policy receives
    requests: pd.DataFrame                # in-year requests, in decide() order (no `cancelled`)
    truth: pd.DataFrame                   # holdout-year arrivals with outcomes, indexed by booking_id

    def day_index(self, dates) -> np.ndarray:
        return (pd.DatetimeIndex(dates) - self.days[0]).days.to_numpy()


def build_holdout(df: pd.DataFrame, year: int = 2016, start: str | None = None,
                  end: str | None = None, shuffle_seed: int = 0) -> Holdout:
    """Holdout = arrivals in [start, end]. Default: the whole `year`.

    With start="2016-07-01" (end defaults to Dec 31 of that year) the policy is "created" on
    July 1st: history = arrivals before July 1st, commitments = window arrivals booked before
    July 1st, capacity = rooms minus guests arrived before July 1st still in house.
    """
    start = pd.Timestamp(start or f"{year}-01-01")
    end = pd.Timestamp(end or f"{start.year}-12-31")
    year = start.year
    days = pd.date_range(start, end)
    in_year = df[(df.arrival_date >= start) & (df.arrival_date <= end)]
    drop = ["cancelled", "value"]

    capacity = {}
    for h, rooms in ROOMS.items():
        prev = df[(df.hotel == h) & (df.arrival_date < start) & (df.cancelled == 0)]
        dep = prev.arrival_date + pd.to_timedelta(prev.nights, "D")
        occ = np.zeros(len(days), dtype=int)
        for d in (dep[dep > start] - start).dt.days:
            occ[: min(d, len(days))] += 1
        capacity[h] = pd.Series(np.clip(rooms - occ, 0, None), index=days, name=h)

    commit = in_year[in_year.booking_date < start]
    # Within a booking day the order is random (fixed seed), NOT by booking_id: booking_id follows
    # the original file order, which is sorted by outcome in long runs, so replaying by id would
    # leak the label to any stateful/online feature. Never use booking_id as a feature either.
    req = in_year[in_year.booking_date >= start]
    tie = np.random.default_rng(shuffle_seed).permutation(len(req))
    req = req.assign(_tie=tie).sort_values(["booking_date", "_tie"], kind="stable").drop(columns="_tie")
    return Holdout(
        year=year,
        days=days,
        history=df[df.arrival_date < start].copy(),
        commitments=commit.drop(columns=drop).reset_index(drop=True),
        capacity=capacity,
        requests=req.drop(columns=drop).reset_index(drop=True),
        truth=in_year.set_index("booking_id"),
    )


def run_policy(factory: Callable, ho: Holdout) -> tuple[np.ndarray, float]:
    """Instantiate the policy like evaluate() does and collect decide() answers.

    `factory(commitments, capacity)` is a Solution class (or a functools.partial of one).
    Returns the boolean accept mask aligned with ho.requests and the seconds spent.
    """
    t0 = time.perf_counter()
    policy = factory(ho.commitments.copy(), {h: s.copy() for h, s in ho.capacity.items()})
    accepted = np.fromiter((bool(policy.decide(b)) for b in ho.requests.to_dict("records")),
                           dtype=bool, count=len(ho.requests))
    return accepted, time.perf_counter() - t0


def check_in(ho: Holdout, accepted: np.ndarray) -> pd.DataFrame:
    """Seat or walk every guest who shows up. Returns one row per guest who showed up."""
    ids = np.concatenate([ho.commitments.booking_id.values, ho.requests.booking_id.values[accepted]])
    g = ho.truth.loc[ids]
    g = g[g.cancelled == 0].reset_index()
    g["start"] = ho.day_index(g.arrival_date)
    g["end"] = np.minimum(g.start + g.nights, len(ho.days))
    g = g.sort_values(["start", "value", "booking_id"], ascending=[True, False, True], kind="stable")

    seated = np.zeros(len(g), dtype=bool)
    for h in ROOMS:
        free = ho.capacity[h].to_numpy().copy()
        rows = np.flatnonzero(g.hotel.values == h)
        for r, s, e in zip(rows, g.start.values[rows], g.end.values[rows]):
            if (free[s:e] > 0).all():
                free[s:e] -= 1
                seated[r] = True
    g["seated"] = seated
    g["revenue"] = np.where(seated, g.value, 0.0)
    g["penalty"] = np.where(seated, 0.0, WALK_PENALTY * g.value)
    return g


def score(ho: Holdout, accepted: np.ndarray) -> pd.DataFrame:
    """Per-hotel summary: accepted requests, revenue, walks, penalties, net, empty room-nights."""
    g = check_in(ho, accepted)
    req_hotel = ho.requests.hotel.values
    rows = []
    for h in ROOMS:
        x = g[g.hotel == h]
        used = np.zeros(len(ho.days))
        for s, e in zip(x.start[x.seated], x.end[x.seated]):
            used[s:e] += 1
        rows.append({
            "hotel": h,
            "accepted": int(accepted[req_hotel == h].sum()),
            "requests": int((req_hotel == h).sum()),
            "revenue": x.revenue.sum(),
            "walk": int((~x.seated).sum()),
            "penalties": x.penalty.sum(),
            "net": x.revenue.sum() - x.penalty.sum(),
            "empty_room_nights": int((ho.capacity[h].to_numpy() - used).clip(0).sum()),
        })
    return pd.DataFrame(rows)


def evaluate_local(factory: Callable, ho: Holdout) -> pd.DataFrame:
    """Replay + scoring in one call: per-hotel summary with the decide() time in seconds."""
    accepted, secs = run_policy(factory, ho)
    out = score(ho, accepted)
    out["seconds"] = secs
    return out
