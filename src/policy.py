"""Economic accept / reject rule: the bid-price policy.

For every request the policy answers two questions:

1. **Is the rate worth the room?** Each night has a *bid price* (reserve price): the nightly rate
   of the marginal guest we still expect to seat on that night if we keep the room. The request
   passes when its nightly rate is at least the average bid price of the nights of its stay.
2. **Does it fit?** The *expected shows* (each booking counts ``q = 1 - p_cancel`` rooms) already
   accepted on every night of the stay, plus this one, must stay within the free rooms.

``p_cancel`` decides *how much* capacity a booking uses (overbooking comes from counting expected
shows, not bookings); the bid price decides *who* gets it.

Pieces
------
* :class:`ShowLoad`: expected shows (and their variance) per hotel and night.
* :class:`DemandForecast`: demand still to come for a night and the rates it will pay, built from
  the training history only and updated online with every request seen -> bid prices.
* :class:`BidPricePolicy`: the decision rule, with the ``Solution`` interface
  (``__init__(commitments, capacity, ...)`` and ``decide(booking) -> bool``). After each call
  ``policy.last`` holds every number behind the decision, used by :mod:`src.explain`.

``deposit`` is never used (organisers' rule) and is dropped if present.
"""
from __future__ import annotations

import math
from typing import Protocol

import numpy as np
import pandas as pd

FORBIDDEN = ("deposit",)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(columns=[c for c in FORBIDDEN if c in df.columns])


def random_day_order(df: pd.DataFrame, seed: int = 12345) -> pd.DataFrame:
    """Sort by booking_date with a random order inside each day (never by booking_id, which leaks
    the outcome)."""
    tie = np.random.default_rng(seed).permutation(len(df))
    return df.assign(_tie=tie).sort_values(["booking_date", "_tie"], kind="stable").drop(columns="_tie")


class CancelModel(Protocol):
    def predict_one(self, booking: dict) -> float: ...
    def predict_frame(self, df: pd.DataFrame) -> np.ndarray: ...


# --------------------------------------------------------------------------------------------
# Expected shows per night
# --------------------------------------------------------------------------------------------

class ShowLoad:
    """Expected shows E and their variance V per hotel and night of everything accepted so far.

    A booking with show probability q adds q to E and q(1-q) to V on every night of its stay.
    """

    def __init__(self, capacity: dict[str, pd.Series]):
        first = next(iter(capacity.values()))
        self.start, self.n_days = first.index[0], len(first)
        self.cap = {h: s.to_numpy(dtype=float) for h, s in capacity.items()}
        self.E = {h: np.zeros(self.n_days) for h in capacity}
        self.V = {h: np.zeros(self.n_days) for h in capacity}

    def span(self, b: dict) -> tuple[str, int, int]:
        """Hotel and [first, last+1) night indices of the stay, clipped to the planning window."""
        s = (b["arrival_date"] - self.start).days
        return b["hotel"], max(s, 0), min(s + int(b["nights"]), self.n_days)

    def add(self, b: dict, q: float) -> None:
        h, s, e = self.span(b)
        self.E[h][s:e] += q
        self.V[h][s:e] += q * (1 - q)

    def fits(self, b: dict, q: float, z: float = 0.0) -> bool:
        """Expected shows + z standard deviations stay within capacity on every night."""
        h, s, e = self.span(b)
        if e <= s:
            return True
        need = self.E[h][s:e] + q + z * np.sqrt(self.V[h][s:e] + q * (1 - q))
        return bool((need <= self.cap[h][s:e] + 1e-9).all())


# --------------------------------------------------------------------------------------------
# Demand forecast -> bid prices
# --------------------------------------------------------------------------------------------

LEAD_EDGES = np.array([0, 4, 8, 15, 22, 31, 46, 61, 91, 121, 151, 181, 241, 301, 366, 100_000])


def _lead_bucket(lead) -> np.ndarray | int:
    return np.minimum(np.searchsorted(LEAD_EDGES, np.maximum(lead, 0), side="right") - 1,
                      len(LEAD_EDGES) - 2)


def _room_nights(df: pd.DataFrame, q: np.ndarray, origin: pd.Timestamp) -> dict[str, np.ndarray]:
    """Explode bookings into room-nights: night index from `origin`, lead of that night, rate, q."""
    s = (df.arrival_date - origin).dt.days.to_numpy()
    n = df.nights.to_numpy().astype(int)
    bk = (df.booking_date - origin).dt.days.to_numpy()
    rep = np.repeat(np.arange(len(df)), n)
    off = np.arange(rep.size) - np.repeat(np.cumsum(n) - n, n)
    night = s[rep] + off
    return dict(night=night, lead=night - bk[rep], rate=df.nightly_rate.to_numpy()[rep],
                q=q[rep], hotel=df.hotel.to_numpy()[rep])


def shift_logit(p: np.ndarray, shift) -> np.ndarray:
    if np.isscalar(shift) and not shift:
        return p
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return 1 / (1 + np.exp(-(np.log(p / (1 - p)) + shift)))


class DemandForecast:
    """Demand still to come for a night, and the bid price it implies.

    Unit of demand: expected shows ``q = 1 - p_cancel`` (the same unit as the capacity check). For
    night ``d`` of hotel ``h``, decided ``L`` days before ``d``:

    * **booking curve** ``F_h(L)``: share of a night's demand booked at least ``L`` days ahead
      (training history, recency-weighted, per hotel);
    * **total demand** ``T(d) = g * mu(d)``: ``mu(d)`` is the demand of the same weekday one year
      earlier (mean of nights d-371, d-364, d-357; the hotel average when history does not cover
      them), ``g`` the live growth factor (:meth:`growth`);
    * **demand still to come** ``N = T * (1 - F(L))``;
    * **its rates** = price level ``P(d)`` x relative rates of bookings made less than ``L`` days
      ahead (relative rate = rate / mean rate of the same hotel on nights +-3, from history).
      ``P(d)`` blends the level of the requests already seen for nights near ``d`` (corrected for
      their lead-time mix) with last year's level;
    * **bid price**: the rate ``x`` such that the future demand paying more than ``x`` just fills
      the free rooms, ``x = P(d) * Q_rel(1 - free / N)``; 0 when ``N <= free`` (the night will not
      fill) and infinite when ``free <= 0`` (already full in expectation).
    """

    def __init__(self, policy: "BidPricePolicy", history: pd.DataFrame, price_weight: float = 30.0,
                 halflife_days: float = 365.0, half_window: int = 3, growth_horizon: int = 90,
                 growth_min_f: float = 0.3, growth_k: float = 500.0,
                 growth_clip: tuple[float, float] = (0.6, 1.8)):
        self.start = start = policy.start
        self.n_days = policy.load.n_days
        self.hw, self.price_weight = half_window, price_weight
        self.g_h, self.g_minf, self.g_k, self.g_clip = growth_horizon, growth_min_f, growth_k, growth_clip
        self._g_cache: dict[tuple[str, int], float] = {}
        hist = _clean(history)
        shifts = hist.hotel.map(lambda h: policy.shift_for(h)).to_numpy(dtype=float)
        q = 1 - shift_logit(policy.model.predict_frame(hist), shifts)
        h0 = hist.arrival_date.min()
        rn = _room_nights(hist, q, h0)
        n_hist = (start - h0).days
        w_rec = 0.5 ** ((n_hist - rn["night"]) / halflife_days) if halflife_days else np.ones(rn["night"].size)
        lead_cap = int(LEAD_EDGES[-2]) + 1
        kern = np.ones(2 * half_window + 1)
        nb = len(LEAD_EDGES) - 1
        self.hotels = list(policy.load.cap)
        self.F, self.rel_q, self.rel_cdf, self.rel_mean, self.mu, self.P0 = {}, {}, {}, {}, {}, {}
        for h in self.hotels:
            m = (rn["hotel"] == h) & (rn["night"] >= 0) & (rn["night"] < n_hist) & (rn["rate"] > 0)
            night, lead, rate, qq = rn["night"][m], rn["lead"][m], rn["rate"][m], rn["q"][m]
            wq = qq * w_rec[m]
            T = np.bincount(night, weights=qq, minlength=n_hist)          # expected shows per night
            R = np.bincount(night, weights=qq * rate, minlength=n_hist)   # expected revenue per night
            Ts, Rs = np.convolve(T, kern, "same"), np.convolve(R, kern, "same")
            P_hist = np.where(Ts > 0, Rs / np.maximum(Ts, 1e-9), np.nan)  # price level, nights +-3
            rel = rate / P_hist[night]
            ok = np.isfinite(rel)
            # booking curve: F[L] = share of demand with lead >= L
            per_lead = np.bincount(np.clip(lead, 0, lead_cap), weights=wq, minlength=lead_cap + 1)
            tail = np.cumsum(per_lead[::-1])[::-1]
            self.F[h] = tail / tail[0]
            # relative rates: mean per lead bucket, and the distribution of bookings made later
            # than the start of each bucket (what is still to come)
            bucket = _lead_bucket(lead)
            self.rel_mean[h] = np.array([np.average(rel[ok & (bucket == j)], weights=wq[ok & (bucket == j)])
                                         if (ok & (bucket == j)).any() else 1.0 for j in range(nb)])
            rq, rc = [], []
            for j in range(nb):
                sel = ok & (bucket <= j)
                o = np.argsort(rel[sel])
                c = np.cumsum(wq[sel][o])
                rq.append(rel[sel][o])
                rc.append(c / c[-1] if c.size else c)
            self.rel_q[h], self.rel_cdf[h] = rq, rc
            # prior per planning night: same weekday one year earlier when available
            mu = np.full(self.n_days, T[T > 0].mean() if (T > 0).any() else 0.0)
            P0 = np.full(self.n_days, R.sum() / max(T.sum(), 1e-9))
            for d in range(self.n_days):
                an = [a for a in (d + n_hist - lag for lag in (371, 364, 357)) if 0 <= a < n_hist and T[a] > 0]
                if len(an) >= 2:
                    mu[d], P0[d] = np.mean(T[an]), np.nanmean(P_hist[an])
            self.mu[h], self.P0[h] = mu, P0
        self.O = {h: np.zeros(self.n_days) for h in self.hotels}    # q seen per night
        self.OR = {h: np.zeros(self.n_days) for h in self.hotels}   # q x rate seen
        self.OL = {h: np.zeros(self.n_days) for h in self.hotels}   # q x expected relative rate of its lead
        for b, qb in policy.committed:
            self.observe(b, qb)

    def observe(self, b: dict, q: float) -> None:
        """Record a request (accepted or not): it is evidence about demand and prices."""
        if b["nightly_rate"] <= 0:
            return
        h = b["hotel"]
        s = (b["arrival_date"] - self.start).days
        e = min(s + int(b["nights"]), self.n_days)
        s = max(s, 0)
        if e <= s:
            return
        self.O[h][s:e] += q
        self.OR[h][s:e] += q * b["nightly_rate"]
        self.OL[h][s:e] += q * self.rel_mean[h][_lead_bucket(b["days_ahead"])]

    def components(self, h: str, d: int, t: int, free: float) -> dict:
        """Every quantity of the forecast for night d decided on day t (indices from the start)."""
        L = d - t
        F = self.F[h]
        f = min(F[min(max(L, 0), F.size - 1)], 1 - 1e-6)
        lo, hi = max(d - self.hw, 0), min(d + self.hw + 1, self.n_days)
        g = self.growth(h, t)
        T = g * self.mu[h][d]
        N = T * (1 - f)
        qs = self.O[h][lo:hi].sum()
        P_seen = self.OR[h][lo:hi].sum() / self.OL[h][lo:hi].sum() if qs > 0 else self.P0[h][d]
        P = (qs * P_seen + self.price_weight * self.P0[h][d]) / (qs + self.price_weight)
        bid, pct = 0.0, None
        if free <= 0:
            bid = np.inf
        elif N > free:
            j = _lead_bucket(L)
            rq, rc = self.rel_q[h][j], self.rel_cdf[h][j]
            if rq.size:
                pct = 1.0 - free / N
                bid = P * rq[min(np.searchsorted(rc, pct), rq.size - 1)]
        return dict(lead=L, F=f, T=T, N=N, free=free, P=P, bid=bid, growth=g, quantile=pct)

    def growth(self, h: str, t: int) -> float:
        """Demand this year vs the prior. Over the next `growth_horizon` nights that the booking curve
        says are at least `growth_min_f` booked: (q seen + k) / (q the prior expected by now + k),
        clipped. The constant k keeps a few early bookings from driving it. Cached per day."""
        if not self.g_h:
            return 1.0
        key = (h, t)
        g = self._g_cache.get(key)
        if g is None:
            lo, hi = max(t, 0), min(max(t, 0) + self.g_h, self.n_days)
            F = self.F[h]
            f = F[np.clip(np.arange(lo, hi) - t, 0, F.size - 1)]
            m = f >= self.g_minf
            exp = float((self.mu[h][lo:hi][m] * f[m]).sum())
            seen = float(self.O[h][lo:hi][m].sum())
            g = min(max((seen + self.g_k) / (exp + self.g_k), self.g_clip[0]), self.g_clip[1])
            self._g_cache = {key: g} | {k: v for k, v in self._g_cache.items() if k[0] != h}
        return g

    def night_details(self, b: dict, h: str, s: int, e: int, free: np.ndarray) -> list[dict]:
        t = (b["booking_date"] - self.start).days
        return [self.components(h, d, t, free[k]) for k, d in enumerate(range(s, e))]

    def bid_prices(self, b: dict, h: str, s: int, e: int, free: np.ndarray) -> np.ndarray:
        return np.array([c["bid"] for c in self.night_details(b, h, s, e, free)])


# --------------------------------------------------------------------------------------------
# The policy
# --------------------------------------------------------------------------------------------

class BidPricePolicy:
    """Accept a request when

    1. its nightly rate >= the average bid price of the nights it occupies. A booking that shows up
       with probability q uses q expected room-nights per night and earns q x rate; every expected
       room-night given away is worth the bid price to the demand we would otherwise seat. q is on
       both sides and cancels out, so the comparison is simply rate vs bid price;
    2. the expected shows on every night of the stay, this booking included, fit the free rooms
       (plus z standard deviations, z = 0 in the final configuration).

    Parameters (final configuration in brackets): ``logit_shift`` added to the model's logit [0];
    ``z`` safety margin [0]; ``bid_scale`` multiplier of the bid price [1]; ``displace_k``: instead
    of refusing on a night that is full in expectation, price the walk it would cause at
    ``k x P(full) x rate of the cheapest seated guest`` [off]. Only the first is model-related, the
    others are the policy ablations reported in notebooks/08_bid_price_policy.
    """

    def __init__(self, commitments: pd.DataFrame, capacity: dict[str, pd.Series], history: pd.DataFrame,
                 model: CancelModel, forecast_kw: dict | None = None, logit_shift: float | dict = 0.0,
                 z: float = 0.0, bid_scale: float = 1.0, displace_k: float | None = None):
        commitments = _clean(commitments)
        self.model = model
        self.logit_shift = logit_shift
        self.z, self.bid_scale, self.displace_k = z, bid_scale, displace_k
        self.load = ShowLoad(capacity)
        self.start = self.load.start
        self.committed: list[tuple[dict, float]] = []        # (booking, q) of the commitments
        for b in random_day_order(commitments).to_dict("records"):
            q = 1.0 - self.p_cancel(b)
            self.load.add(b, q)
            self.committed.append((b, q))
        self.forecast = DemandForecast(self, history, **(forecast_kw or {}))
        if displace_k:
            self._nb = {h: [[] for _ in range(self.load.n_days)] for h in self.load.cap}
            for b, q in self.committed:
                self._register(b, q)
        self.last: dict = {}

    # ---- cancellation probability --------------------------------------------------------
    def shift_for(self, hotel: str) -> float:
        """Logit shift of a hotel (`logit_shift` is a number or a {hotel: number} dict)."""
        ls = self.logit_shift
        return ls.get(hotel, 0.0) if isinstance(ls, dict) else ls

    def p_cancel(self, b: dict) -> float:
        p = self.model.predict_one(b)
        shift = self.shift_for(b["hotel"])
        if shift:
            p = min(max(p, 1e-6), 1 - 1e-6)
            p = 1.0 / (1.0 + math.exp(-(math.log(p / (1 - p)) + shift)))
        return p

    # ---- displacement rule (ablation) ----------------------------------------------------
    def _register(self, b: dict, q: float) -> None:
        h, s, e = self.load.span(b)
        for d in range(s, e):
            self._nb[h][d].append((float(b["nightly_rate"]), q))

    def _displacement_cost(self, h: str, d: int, q: float) -> float | None:
        """Cost per room-night of adding a booking to a night that would end up over capacity, or
        None if the night still fits. When the hotel is full the cheapest arriving guest is walked:
        we lose their stay (v) and pay 2.5 v, i.e. 3.5 v, with probability P(full) (normal
        approximation of the shows already accepted)."""
        E, V, cap = self.load.E[h][d], self.load.V[h][d], self.load.cap[h][d]
        if E + q <= cap + 1e-9:
            return None
        lst = sorted(self._nb[h][d])
        pos, cum, v = max(E - cap, 0.0), 0.0, lst[-1][0] if lst else 0.0
        for rate, qq in lst:
            cum += qq
            if cum > pos:
                v = rate
                break
        pf = 0.5 * math.erfc((cap - 0.5 - E) / (math.sqrt(V + 1e-6) * math.sqrt(2.0)))
        return self.displace_k * pf * v

    # ---- decision ------------------------------------------------------------------------
    def decide(self, booking: dict) -> bool:
        b = {k: v for k, v in booking.items() if k not in FORBIDDEN}
        p = self.p_cancel(b)
        q = 1.0 - p
        h, s, e = self.load.span(b)
        self.forecast.observe(b, q)
        if b["nightly_rate"] <= 0 or e <= s:
            self.last = dict(p_cancel=p, bid=np.nan, rate=b["nightly_rate"], ok_value=False, ok_risk=False,
                             priced_walk=False, invalid=True, nights=[])
            return False
        free = self.load.cap[h][s:e] - self.load.E[h][s:e]
        nights = self.forecast.night_details(b, h, s, e, free)
        bids = np.array([c["bid"] for c in nights], dtype=float)
        priced_walk = False
        if self.displace_k:
            for k, d in enumerate(range(s, e)):
                c = self._displacement_cost(h, d, q)
                if c is not None:
                    bids[k], priced_walk = c, True
        bid = self.bid_scale * float(np.mean(bids))
        ok_value = b["nightly_rate"] >= bid
        ok_risk = ok_value and (priced_walk or self.load.fits(b, q, self.z))
        self.last = dict(p_cancel=p, bid=bid, rate=b["nightly_rate"], ok_value=ok_value, ok_risk=ok_risk,
                         priced_walk=priced_walk, invalid=False, nights=nights,
                         expected_shows=self.load.E[h][s:e].copy(), capacity=self.load.cap[h][s:e].copy())
        if ok_risk:
            self.load.add(b, q)
            if self.displace_k:
                self._register(b, q)
            return True
        return False
