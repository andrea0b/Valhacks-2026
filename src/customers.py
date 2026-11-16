"""Customer segmentation helpers shared by notebooks 04 and 05.

The dataset has no customer id: one row is one room booking, and a group booking of n rooms is n
identical rows. Personas therefore describe *bookings*. They are built only from information
available when the request arrives (no outcome, no post-booking columns, no `country`, which is
partly leakage), so a persona could be assigned live. They explain the customer base; the decision
itself is made by the cancellation model and the bid-price policy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

PARTY = ["Single", "Couple", "Family", "Adult group"]
TRIP = ["Short weekday (1-3, no weekend)", "Short weekend (1-3)", "Holiday (4-6 nights)",
        "Long holiday (7+ nights)"]
PERSONA_ORDER = ["Online leisure couples", "Families", "Tour-operator holidays", "Contracts / allotments",
                 "Last-minute direct guests", "Business / corporate", "Groups and agency blocks"]

def add_block_size(full: pd.DataFrame) -> pd.DataFrame:
    """`block` = number of identical rows (same value in every column but booking_id / outcome)."""
    raw = [c for c in full.columns if c not in ("booking_id", "cancelled", "value")]
    return full.assign(block=full.groupby(raw, dropna=False).booking_id.transform("size"))


def booking_frame(full: pd.DataFrame, hotel: str) -> pd.DataFrame:
    """Rows of one hotel with the derived columns used in the customer analysis."""
    df = full[full.hotel == hotel].reset_index(drop=True).copy()
    df["children"] = df.children.fillna(0)
    df["kids"] = df.children + df.babies
    df["realized"] = df.value * (1 - df.cancelled)                 # revenue actually earned
    df["repeat"] = ((df.returning_guest == 1) | (df.past_stays > 0)).astype(int)
    # price relative to the median of the same arrival month: removes seasonality
    df["rate_idx"] = df.nightly_rate / df.groupby(df.arrival_date.dt.to_period("M")).nightly_rate.transform("median")
    df["period"] = df.arrival_date.dt.year.astype(str) + "-H" + np.where(df.arrival_date.dt.month <= 6, "1", "2")
    df["agent_id"] = df.agent.fillna(-1).astype(int).astype(str).replace("-1", "none")
    df["party"] = np.select([df.kids > 0, df.adults >= 3, df.adults == 2, df.adults == 1],
                            ["Family", "Adult group", "Couple", "Single"], "No adults")
    df["trip"] = np.select([df.nights >= 7, df.nights >= 4, df.weekend_nights == 0],
                           [TRIP[3], TRIP[2], TRIP[0]], TRIP[1])
    return df


def segment_features(df: pd.DataFrame) -> pd.DataFrame:
    """17 features known when the request arrives: trip shape, party, price, how they buy."""
    return pd.DataFrame({
        "lead days (log)": np.log1p(df.days_ahead),
        "nights (log)": np.log1p(df.nights),
        "weekend share": df.weekend_nights / df.nights,
        "adults": df.adults.clip(0, 4),
        "with kids": (df.kids > 0).astype(int),
        "price vs month": df.rate_idx.clip(0, 3),
        "non-standard room": (df.room_type != "A").astype(int),
        "half/full board": df.meal.isin(["HB", "FB"]).astype(int),
        "repeat guest": df.repeat,
        "block size (log)": np.log(df.block),
        "online TA": (df.sales_segment == "Online TA").astype(int),
        "offline TA/TO": (df.sales_segment == "Offline TA/TO").astype(int),
        "Groups segment": (df.sales_segment == "Groups").astype(int),
        "direct": (df.sales_segment == "Direct").astype(int),
        "corporate": df.sales_segment.isin(["Corporate", "Aviation"]).astype(int),
        "transient-party": (df.guest_type == "Transient-Party").astype(int),
        "contract/group": df.guest_type.isin(["Contract", "Group"]).astype(int),
    }, index=df.index)


def standardize(F: pd.DataFrame) -> np.ndarray:
    return StandardScaler().fit_transform(F)


def name_cluster(p: pd.Series) -> str:
    """Readable persona name from a cluster centroid (raw feature means; rule order matters)."""
    if p["with kids"] > .5:
        return "Families"
    if p["corporate"] > .5:
        return "Business / corporate"
    if p["direct"] > .5:
        return "Last-minute direct guests"
    if p["Groups segment"] > .5:
        return "Groups and agency blocks"
    if p["contract/group"] > .5:
        return "Contracts / allotments"
    if p["offline TA/TO"] > .5:
        return "Tour-operator holidays"
    if p["online TA"] > .5:
        return "Online leisure couples"
    return "Other"


def fit_personas(df: pd.DataFrame, k: int, seed: int = 0) -> tuple[pd.Series, KMeans]:
    """k-means on the standardised segment features; returns the persona of every row."""
    F = segment_features(df)
    km = KMeans(k, n_init=10, random_state=seed).fit(standardize(F))
    prof = F.groupby(km.labels_).mean()
    names = {c: name_cluster(prof.loc[c]) for c in prof.index}
    return pd.Series(km.labels_, index=df.index).map(names).rename("persona"), km


def kpi(g: pd.DataFrame, ref: pd.DataFrame) -> pd.Series:
    """Business KPIs of a set of bookings. yield = realised revenue per requested room-night."""
    rn = g.nights.sum()
    return pd.Series({
        "bookings": len(g), "cancel_rate": g.cancelled.mean(),
        "median_rate": g.nightly_rate.median(), "avg_nights": g.nights.mean(),
        "median_lead_days": g.days_ahead.median(),
        "yield_per_requested_night": g.realized.sum() / rn,
        "share_requested_room_nights": rn / ref.nights.sum(),
        "revenue_share": g.realized.sum() / ref.realized.sum()})


def explode_nights(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """One row per (booking, night) with the requested columns and `show` (1 = guest showed up)."""
    idx = np.repeat(df.index.values, df.nights.values)
    off = np.concatenate([np.arange(n) for n in df.nights.values])
    out = pd.DataFrame({"night": df.arrival_date.values[idx] + pd.to_timedelta(off, "D"),
                        "show": 1 - df.cancelled.values[idx]})
    for c in cols:
        out[c] = df[c].values[idx]
    return out
