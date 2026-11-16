"""Feature engineering for the cancellation model.

Every feature is computable at the moment a booking request arrives, from three sources:

* the request itself;
* statistics learned on the training history (rows whose outcome is already known);
* the stream of requests seen so far (history, commitments and earlier requests).

The module has two layers.

1. **Stream features** (stateful, causal). They depend on the order in which requests arrive:

   ==================  ========================================================================
   ``block_rank``      identical requests seen so far, this one included (1 = first of its kind)
   ``loose_rank``      same, on a looser key (booking day, hotel, arrival, nights, agent)
   ``day_agent_count`` requests from the same agent to the same hotel on the same booking day
   ``demand_date``     requests seen *before* this one for the same hotel and arrival night
   ``demand_week``     same, for the same hotel and arrival week
   ==================  ========================================================================

   :func:`stream_features` computes them for a whole frame; :class:`OnlineStream` computes them
   one request at a time inside ``decide()``. Both give identical values for the same sequence.

2. :class:`FeatureBuilder` (fit / transform). It learns category vocabularies and the agent's
   historical cancellation rate on the training history and turns rows (plus their stream
   features) into a model matrix. Which features are built is controlled by
   :class:`FeatureConfig`.

Ordering rule
-------------
Within a booking day the order of requests is **random**. ``booking_id`` follows the row order of
the original file, which is sorted by outcome in long runs: replaying requests by id would leak the
label into any order-dependent feature. ``booking_id`` is never used, neither as a feature nor as
an ordering key. ``deposit`` is never used either (organisers' rule).

Typical use::

    stream = stream_features(df)                         # once, on the whole known stream
    fb = FeatureBuilder(FeatureConfig(...)).fit(train)   # rows with a known outcome
    A_train = fb.to_array(fb.transform(train, stream.loc[train.index], oof=True))

    # inside decide()
    s = online_stream.observe(booking)                   # updates the state, returns a dict
    x = fb.transform_record(booking, s)                  # 1 x n float array, ~0.05 ms
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

# ----------------------------------------------------------------------------------------------
# Column lists
# ----------------------------------------------------------------------------------------------

# Every input column of train.csv except booking_id, cancelled (the target) and deposit (excluded).
RAW_COLUMNS = [
    "hotel", "days_ahead", "arrival_year", "arrival_month", "arrival_week", "arrival_day",
    "weekend_nights", "weekday_nights", "adults", "children", "babies", "meal", "country",
    "sales_segment", "sales_channel", "returning_guest", "past_cancellations", "past_stays",
    "room_type", "amendments", "agent", "company", "waitlist_days", "guest_type", "nightly_rate",
    "special_requests", "arrival_date", "booking_date", "nights",
]
BLOCK_KEY = RAW_COLUMNS                      # identical requests = same value in every column
LOOSE_KEY = ["booking_date", "hotel", "arrival_date", "nights", "agent"]
STREAM_COLUMNS = ["block_rank", "loose_rank", "day_agent_count", "demand_date", "demand_week"]

# Raw numeric columns (arrival_year is excluded on purpose: the deployment year is never in training).
RAW_NUM = ["days_ahead", "arrival_week", "arrival_day", "weekend_nights", "weekday_nights", "adults",
           "children", "babies", "amendments", "waitlist_days", "nightly_rate", "special_requests",
           "nights"]
# Guest-history counters: their meaning drifts over time (see notebooks/03_cancellation_drivers).
HIST_NUM = ["returning_guest", "past_cancellations", "past_stays"]
RAW_CAT = ["hotel", "arrival_month", "meal", "sales_segment", "sales_channel", "room_type",
           "guest_type"]
_CAT_INPUTS = ("hotel", "arrival_month", "meal", "country", "sales_segment", "sales_channel",
               "room_type", "guest_type")

LEAD_BINS = [-1, 0, 7, 30, 90, 180, 365, 10_000]
LEAD_LABELS = ["0", "1-7", "8-30", "31-90", "91-180", "181-365", ">365"]


def _missing_str(s: pd.Series, missing: str = "NA") -> pd.Series:
    return s.astype(object).where(s.notna(), missing).astype(str)


def _agent_str(s: pd.Series) -> pd.Series:
    """`agent` / `company` ids are floats with NaN: map them to 'none' or the integer id as text."""
    return pd.Series(np.where(s.isna(), "none", s.fillna(-1).astype(int).astype(str)), index=s.index)


# ----------------------------------------------------------------------------------------------
# Stream (causal, order-dependent) features
# ----------------------------------------------------------------------------------------------

def _norm_frame(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Normalise key columns so that the batch groupby and the online tuples agree (NaN -> sentinel)."""
    out = {}
    for c in cols:
        s = df[c]
        if c in ("arrival_date", "booking_date"):
            out[c] = pd.to_datetime(s).dt.normalize().astype("int64")
        elif s.dtype.kind in "fiub":
            out[c] = s.astype(float).fillna(-1.0)
        else:
            out[c] = _missing_str(s)
    return pd.DataFrame(out, index=df.index)


def _norm_value(c: str, v):
    """Online twin of `_norm_frame` for a single value."""
    if c in ("arrival_date", "booking_date"):
        return pd.Timestamp(v).normalize().value
    if isinstance(v, str):
        return v
    if v is None:
        return "NA" if c in _CAT_INPUTS else -1.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return -1.0 if np.isnan(f) else f


def _week_start(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates).dt.normalize()
    return d - pd.to_timedelta(d.dt.day_of_week, unit="D")


def stream_order(df: pd.DataFrame, seed: int = 0) -> np.ndarray:
    """Row positions in arrival order of the requests: by booking_date, random within a day."""
    key = np.random.default_rng(seed).permutation(len(df))
    return np.lexsort((key, pd.to_datetime(df.booking_date).to_numpy()))


def stream_features(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Batch version of :class:`OnlineStream`: causal stream features for every row of `df`.

    `df` must be the whole stream the model would have seen (e.g. all of train.csv). The result
    is aligned to ``df.index``.
    """
    d = df.iloc[stream_order(df, seed)]
    out = pd.DataFrame(index=d.index)
    blk = _norm_frame(d, BLOCK_KEY)
    out["block_rank"] = blk.groupby(BLOCK_KEY, sort=False).cumcount() + 1
    loose = _norm_frame(d, LOOSE_KEY)
    out["loose_rank"] = loose.groupby(LOOSE_KEY, sort=False).cumcount() + 1
    out["day_agent_count"] = loose.groupby(["booking_date", "hotel", "agent"], sort=False).cumcount() + 1
    arr = pd.to_datetime(d.arrival_date).dt.normalize()
    out["demand_date"] = d.groupby([d.hotel, arr], sort=False).cumcount()
    out["demand_week"] = d.groupby([d.hotel, _week_start(arr)], sort=False).cumcount()
    return out.loc[df.index].astype(float)


class OnlineStream:
    """Online twin of :func:`stream_features`. Call :meth:`observe` once per request, in order.

    `observe` returns the stream features of the request *and* records it, so later requests see
    it. Feed the history and the commitments first with :meth:`observe_frame`. The state is a few
    dict counters, so each call is O(1).
    """

    def __init__(self) -> None:
        self.block = defaultdict(int)
        self.loose = defaultdict(int)
        self.day_agent = defaultdict(int)
        self.demand_date = defaultdict(int)
        self.demand_week = defaultdict(int)

    def observe(self, b: dict) -> dict:
        kb = tuple(_norm_value(c, b.get(c)) for c in BLOCK_KEY)
        kl = tuple(_norm_value(c, b.get(c)) for c in LOOSE_KEY)
        kd = (kl[0], kl[1], kl[4])                      # booking day, hotel, agent
        arr = pd.Timestamp(b["arrival_date"]).normalize()
        kdate = (b["hotel"], arr)
        kweek = (b["hotel"], arr - pd.Timedelta(days=arr.dayofweek))

        self.block[kb] += 1
        self.loose[kl] += 1
        self.day_agent[kd] += 1
        feats = {
            "block_rank": float(self.block[kb]),
            "loose_rank": float(self.loose[kl]),
            "day_agent_count": float(self.day_agent[kd]),
            "demand_date": float(self.demand_date[kdate]),
            "demand_week": float(self.demand_week[kweek]),
        }
        self.demand_date[kdate] += 1
        self.demand_week[kweek] += 1
        return feats

    def observe_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Observe a whole frame in arrival order; returns its stream features (aligned to df.index)."""
        order = stream_order(df)
        feats = [self.observe(r) for r in df.iloc[order].to_dict("records")]
        return pd.DataFrame(feats, index=df.index[order]).loc[df.index]


# ----------------------------------------------------------------------------------------------
# Configurable feature builder
# ----------------------------------------------------------------------------------------------

FEATURE_GROUPS = ("lead", "calendar", "engage", "block", "demand")


@dataclass
class FeatureConfig:
    """Which features to build.

    groups   : engineered groups added to the raw columns (subset of FEATURE_GROUPS)
               lead     log lead time and lead-time band
               calendar arrival weekday, request weekday, season, cyclic month, weekend share
               engage   flags for special requests / amendments / waitlist (post-booking info)
               block    stream features about identical and similar requests (groups)
               demand   stream features about requests already seen for the night and week
    country  : 'raw' (levels with >= min_count rows) | 'drop'
    agent    : 'raw' (levels with >= min_count rows) | 'drop'
    agent_te : add the smoothed historical cancel rate of the agent (out-of-fold on training rows)
    company  : 'raw' | 'flag' (company present) | 'drop'
    history  : past_stays / past_cancellations / returning_guest as 'raw' | 'drop'
    raw_num  : raw numeric columns to keep
    """
    groups: tuple = ()
    country: str = "raw"
    agent: str = "raw"
    agent_te: bool = False
    company: str = "raw"
    history: str = "raw"
    raw_num: tuple = tuple(RAW_NUM)
    raw_cat: tuple = tuple(RAW_CAT)
    min_count: int = 20
    te_smoothing: float = 30.0
    te_folds: int = 5


@dataclass
class FeatureBuilder:
    config: FeatureConfig = field(default_factory=FeatureConfig)

    # ---- fit ---------------------------------------------------------------------------------
    def fit(self, hist: pd.DataFrame) -> "FeatureBuilder":
        """Learn category vocabularies and the agent encoding from rows with a known outcome."""
        cfg = self.config
        self.__dict__.pop("_code", None)
        self.prior_ = float(hist.cancelled.mean()) if "cancelled" in hist else 0.35
        base = self._base(hist)
        self.vocab_ = {}
        for c in self._cat_columns():
            vc = base[c].value_counts()
            keep = vc[vc >= cfg.min_count].index.tolist()
            self.vocab_[c] = sorted(set(keep) | {"other"})
        if cfg.agent_te:
            a = _agent_str(hist.agent)
            self.te_ = self._te_table(a, hist.cancelled)
            self.te_oof_ = self._te_oof(hist, a)
        return self

    def _te_table(self, key: pd.Series, y: pd.Series) -> dict:
        """Smoothed cancel rate per key: (cancellations + m * prior) / (rows + m)."""
        g = pd.DataFrame({"k": key.values, "y": y.values}).groupby("k").y.agg(["sum", "count"])
        m = self.config.te_smoothing
        return ((g["sum"] + m * self.prior_) / (g["count"] + m)).to_dict()

    def _te_oof(self, hist: pd.DataFrame, a: pd.Series) -> pd.Series:
        """Out-of-fold encoding for the training rows. Folds are grouped by (booking day, hotel,
        agent) so that rows of the same group booking never encode each other."""
        groups = _norm_frame(hist, ["booking_date", "hotel", "agent"]).astype(str).agg("|".join, axis=1)
        out = pd.Series(self.prior_, index=hist.index, dtype=float)
        for tr, te in GroupKFold(self.config.te_folds).split(hist, groups=groups):
            tab = self._te_table(a.iloc[tr], hist.cancelled.iloc[tr])
            out.iloc[te] = a.iloc[te].map(tab).fillna(self.prior_).to_numpy()
        return out

    # ---- transform ---------------------------------------------------------------------------
    def _cat_columns(self) -> list[str]:
        cfg = self.config
        cols = list(cfg.raw_cat)
        if cfg.country != "drop":
            cols.append("country")
        if cfg.agent == "raw":
            cols.append("agent")
        if cfg.company == "raw":
            cols.append("company")
        if "lead" in cfg.groups:
            cols.append("lead_bin")
        if "calendar" in cfg.groups:
            cols += ["arrival_dow", "season"]
        return cols

    def _base(self, df: pd.DataFrame, stream: pd.DataFrame | None = None) -> pd.DataFrame:
        """All feature columns, before categories are mapped to the fitted vocabularies."""
        cfg, g = self.config, self.config.groups
        X = pd.DataFrame(index=df.index)
        for c in cfg.raw_num:
            X[c] = df[c].astype(float)
        if "children" in X:
            X["children"] = X["children"].fillna(0.0)
        for c in cfg.raw_cat:
            X[c] = _missing_str(df[c])
        if cfg.country == "raw":
            X["country"] = _missing_str(df.country)
        if cfg.agent == "raw":
            X["agent"] = _agent_str(df.agent)
        X["agent_none"] = df.agent.isna().astype(float)
        if cfg.company == "raw":
            X["company"] = _agent_str(df.company)
        if cfg.company in ("raw", "flag"):
            X["company_flag"] = df.company.notna().astype(float)
        if cfg.history == "raw":
            for c in HIST_NUM:
                X[c] = df[c].astype(float)
        if "lead" in g:
            lead = df.days_ahead.astype(float)
            X["log_lead"] = np.log1p(lead)
            X["lead_bin"] = pd.cut(lead, LEAD_BINS, labels=LEAD_LABELS).astype(str)
        if "calendar" in g:
            arr = pd.to_datetime(df.arrival_date)
            X["arrival_dow"] = arr.dt.day_of_week.astype(str)
            X["booking_dow"] = pd.to_datetime(df.booking_date).dt.day_of_week.astype(float)
            X["weekend_share"] = df.weekend_nights / df.nights.clip(lower=1)
            mo = arr.dt.month
            X["season"] = np.select([mo.isin([6, 7, 8]), mo.isin([12, 1, 2]), mo.isin([3, 4, 5])],
                                    ["summer", "winter", "spring"], default="autumn")
            X["month_sin"] = np.sin(2 * np.pi * mo / 12)
            X["month_cos"] = np.cos(2 * np.pi * mo / 12)
        if "engage" in g:
            X["has_special"] = (df.special_requests > 0).astype(float)
            X["has_amend"] = (df.amendments > 0).astype(float)
            X["waitlisted"] = (df.waitlist_days > 0).astype(float)
        if "block" in g and stream is not None:
            X["block_rank"] = stream.block_rank.to_numpy()
            X["log_block_rank"] = np.log(stream.block_rank.to_numpy())
            X["in_block"] = (stream.block_rank.to_numpy() > 1).astype(float)
            X["log_loose_rank"] = np.log(stream.loose_rank.to_numpy())
            X["log_day_agent"] = np.log(stream.day_agent_count.to_numpy())
        if "demand" in g and stream is not None:
            X["log_demand_date"] = np.log1p(stream.demand_date.to_numpy())
            X["log_demand_week"] = np.log1p(stream.demand_week.to_numpy())
        return X

    def transform(self, df: pd.DataFrame, stream: pd.DataFrame | None = None,
                  oof: bool = False) -> pd.DataFrame:
        """Model matrix: float numeric columns + pandas Categorical columns (fixed categories).

        stream : stream features aligned to df (needed by the 'block' and 'demand' groups)
        oof    : True only for the exact rows passed to fit(): uses the out-of-fold agent encoding
        """
        cfg = self.config
        X = self._base(df, stream)
        for c in self._cat_columns():
            if c in X.columns:
                v = X[c].where(X[c].isin(self.vocab_[c]), "other")
                X[c] = pd.Categorical(v, categories=self.vocab_[c])
        if cfg.agent_te:
            if oof:
                X["agent_te"] = self.te_oof_.loc[df.index].to_numpy()
            else:
                X["agent_te"] = _agent_str(df.agent).map(self.te_).fillna(self.prior_).to_numpy()
        self.cat_cols_ = [c for c in X.columns if isinstance(X[c].dtype, pd.CategoricalDtype)]
        self.num_cols_ = [c for c in X.columns if c not in self.cat_cols_]
        self.columns_ = list(X.columns)
        return X

    # ---- fast numeric path (used inside decide()) -------------------------------------------
    @staticmethod
    def to_array(X: pd.DataFrame) -> np.ndarray:
        """Model matrix -> float array in the same column order, categoricals as integer codes
        (position in the fitted vocabulary). All estimators are trained on this layout."""
        A = np.empty(X.shape, dtype=float)
        for j, c in enumerate(X.columns):
            col = X[c]
            A[:, j] = (col.cat.codes.to_numpy() if isinstance(col.dtype, pd.CategoricalDtype)
                       else col.to_numpy(dtype=float))
        return A

    def transform_record(self, b: dict, s: dict | None = None) -> np.ndarray:
        """One request dict (+ its OnlineStream features) -> 1 x n float array.

        Identical to ``to_array(transform(...))`` but about 100x faster (plain Python, no pandas).
        Requires a previous call to transform() (fit + transform on the training rows does it).
        """
        cfg, g = self.config, self.config.groups
        if not hasattr(self, "_code"):
            self._code = {c: {v: i for i, v in enumerate(self.vocab_[c])} for c in self.vocab_}

        def num(v, default=0.0):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return default
            return default if f != f else f

        def miss(v):
            return "NA" if v is None or (isinstance(v, float) and v != v) else str(v)

        def ag(v):
            f = num(v, float("nan"))
            return "none" if f != f else str(int(f))

        arr = pd.Timestamp(b["arrival_date"])
        nights = num(b["nights"])
        r = {}
        for c in cfg.raw_num:
            r[c] = num(b.get(c))
        for c in cfg.raw_cat:
            r[c] = miss(b.get(c))
        if cfg.country == "raw":
            r["country"] = miss(b.get("country"))
        if cfg.agent == "raw":
            r["agent"] = ag(b.get("agent"))
        r["agent_none"] = float(ag(b.get("agent")) == "none")
        if cfg.company == "raw":
            r["company"] = ag(b.get("company"))
        if cfg.company in ("raw", "flag"):
            r["company_flag"] = float(ag(b.get("company")) != "none")
        if cfg.history == "raw":
            for c in HIST_NUM:
                r[c] = num(b.get(c))
        if "lead" in g:
            lead = num(b.get("days_ahead"))
            r["log_lead"] = float(np.log1p(lead))
            r["lead_bin"] = next(lab for hi, lab in zip(LEAD_BINS[1:], LEAD_LABELS) if lead <= hi)
        if "calendar" in g:
            mo = arr.month
            r["arrival_dow"] = str(arr.dayofweek)
            r["booking_dow"] = float(pd.Timestamp(b["booking_date"]).dayofweek)
            r["weekend_share"] = num(b.get("weekend_nights")) / max(nights, 1)
            r["season"] = ("summer" if mo in (6, 7, 8) else "winter" if mo in (12, 1, 2)
                           else "spring" if mo in (3, 4, 5) else "autumn")
            r["month_sin"] = float(np.sin(2 * np.pi * mo / 12))
            r["month_cos"] = float(np.cos(2 * np.pi * mo / 12))
        if "engage" in g:
            r["has_special"] = float(num(b.get("special_requests")) > 0)
            r["has_amend"] = float(num(b.get("amendments")) > 0)
            r["waitlisted"] = float(num(b.get("waitlist_days")) > 0)
        if "block" in g and s is not None:
            r["block_rank"] = s["block_rank"]
            r["log_block_rank"] = float(np.log(s["block_rank"]))
            r["in_block"] = float(s["block_rank"] > 1)
            r["log_loose_rank"] = float(np.log(s["loose_rank"]))
            r["log_day_agent"] = float(np.log(s["day_agent_count"]))
        if "demand" in g and s is not None:
            r["log_demand_date"] = float(np.log1p(s["demand_date"]))
            r["log_demand_week"] = float(np.log1p(s["demand_week"]))
        if cfg.agent_te:
            r["agent_te"] = self.te_.get(ag(b.get("agent")), self.prior_)
        out = np.empty((1, len(self.columns_)))
        for j, c in enumerate(self.columns_):
            v = r[c]
            if c in self._code:
                code = self._code[c]
                v = code.get(v, code["other"])
            out[0, j] = v
        return out
