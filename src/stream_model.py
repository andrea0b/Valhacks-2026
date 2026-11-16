"""The cancellation model ``p_cancel(booking)`` used online by the policy.

:class:`StreamCancelModel` wraps :class:`~src.features.FeatureBuilder` +
:class:`~src.features.OnlineStream` and one or more estimators behind the two methods the policy
needs:

* ``predict_one(booking)``: probability for one request, inside ``decide()`` (~1-3 ms);
* ``predict_frame(df)``: probabilities for the training history (used by the demand forecast).

Online use (one session = one replay / one ``Solution``)::

    m = StreamCancelModel(["lr", "lgb", "cb"], stack=True).fit(history, as_of=start)
    m.start_session(commitments)          # stream sees history + commitments
    p = m.predict_one(booking)            # once per request, in arrival order

Design choices (see docs/methodology.md):

* recency weights ``0.5 ** (age_months / half_life)`` on the training arrivals;
* every estimator works on ``FeatureBuilder.to_array`` output, so one prediction needs no pandas;
* several ``members`` are combined either by averaging their logits or, with ``stack=True``, by a
  logistic meta-model fitted on *out-of-time* predictions (temporal stacking);
* ``per_hotel`` (one model per hotel) and ``calibrate`` (per-hotel intercept fitted on the most
  recent months) are ablations: both were tested and are off in the final recipe.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.features import RAW_NUM, FeatureBuilder, FeatureConfig, OnlineStream, stream_features

warnings.filterwarnings("ignore")

FORBIDDEN = ("deposit",)

LGB_PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=50,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                  cat_smooth=10, min_data_per_group=50, max_cat_to_onehot=4, verbose=-1, n_jobs=2)
CB_PARAMS = dict(iterations=400, learning_rate=0.08, depth=6, l2_leaf_reg=3, verbose=0, thread_count=2)
EBM_PARAMS = dict(interactions=0, outer_bags=4, learning_rate=0.02, max_rounds=3000,
                  min_samples_leaf=4, n_jobs=2)
LR_PARAMS = dict(C=1.0)

# ---------------------------------------------------------------------------------------------
# Feature sets
# ---------------------------------------------------------------------------------------------

# Columns that only exist AFTER the booking is created: amendments (changes made later),
# waitlist_days (time spent on the waiting list) and special_requests (often added later). The
# evaluator passes them to decide(), but a hotel that has just received a request would not have
# them, and they correlate with the outcome by construction. The final feature set ignores them.
POST_BOOKING_COLUMNS = ("amendments", "waitlist_days", "special_requests")
_AT_REQUEST_NUM = tuple(c for c in RAW_NUM if c not in POST_BOOKING_COLUMNS)
_GROUPS = ("lead", "calendar", "block", "demand")

# Final feature set: only what is known when the request arrives, no drifting columns.
MODEL_CFG = FeatureConfig(country="drop", history="drop", company="flag", agent="raw", agent_te=True,
                          raw_num=_AT_REQUEST_NUM, groups=_GROUPS)
# Ablation: the final set + country and guest-history counters (they drift over time).
WITH_DRIFTING_CFG = FeatureConfig(country="raw", history="raw", company="flag", agent="raw", agent_te=True,
                                  raw_num=_AT_REQUEST_NUM, groups=_GROUPS)
# Ablation: the final set + special_requests (some hotels collect them at booking time).
WITH_SPECIAL_REQUESTS_CFG = FeatureConfig(
    country="drop", history="drop", company="flag", agent="raw", agent_te=True,
    raw_num=tuple(c for c in RAW_NUM if c not in ("amendments", "waitlist_days")), groups=_GROUPS)
# Ablation: every post-booking column (what the shortcut would be worth, not a valid model).
FULL_CFG = FeatureConfig(country="drop", history="drop", company="flag", agent="raw", agent_te=True,
                         groups=("lead", "calendar", "engage", "block", "demand"))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def recency_weights(arrival: pd.Series, as_of: pd.Timestamp, half_life_months: float | None):
    """Sample weight that halves every `half_life_months` of age (None = uniform)."""
    if not half_life_months:
        return None
    age = (pd.Timestamp(as_of) - arrival).dt.days.to_numpy() / 30.44
    return 0.5 ** (np.maximum(age, 0) / half_life_months)


# ---------------------------------------------------------------------------------------------
# Estimators on the to_array() layout. Each exposes fit(A, y, w) and predict(A) -> P(cancel).
# ---------------------------------------------------------------------------------------------

class _LR:
    """Logistic regression with explicit standardisation + one-hot, so one row costs microseconds."""

    def __init__(self, fb: FeatureBuilder, **kw):
        self.fb, self.kw = fb, {**LR_PARAMS, **kw}
        self.cat_idx = [fb.columns_.index(c) for c in fb.cat_cols_]
        self.num_idx = [fb.columns_.index(c) for c in fb.num_cols_]
        self.sizes = [len(fb.vocab_[c]) for c in fb.cat_cols_]

    def _design(self, A):
        num = (A[:, self.num_idx] - self.mu) / self.sd
        cols = [num]
        for j, s in zip(self.cat_idx, self.sizes):
            oh = np.zeros((A.shape[0], s))
            oh[np.arange(A.shape[0]), np.clip(A[:, j].astype(int), 0, s - 1)] = 1.0
            cols.append(oh)
        return np.hstack(cols)

    def fit(self, A, y, w):
        num = A[:, self.num_idx]
        self.mu = np.average(num, axis=0, weights=w)
        self.sd = np.sqrt(np.average((num - self.mu) ** 2, axis=0, weights=w)) + 1e-9
        self.m = LogisticRegression(max_iter=3000, **self.kw).fit(self._design(A), y, sample_weight=w)
        return self

    def predict(self, A):
        return self.m.predict_proba(self._design(A))[:, 1]


class _LGB:
    """LightGBM with native categorical splits; prediction goes through the raw booster (fast)."""

    def __init__(self, fb, seed=0, **kw):
        self.fb, self.seed, self.params = fb, seed, {**LGB_PARAMS, **kw}
        self.cat_idx = [fb.columns_.index(c) for c in fb.cat_cols_]

    def fit(self, A, y, w):
        import lightgbm as lgb               # imported lazily: module objects cannot be pickled
        self.m = lgb.LGBMClassifier(**self.params, random_state=self.seed)
        self.m.fit(A, y, sample_weight=w, categorical_feature=self.cat_idx or "auto")
        self.b = self.m.booster_
        return self

    def predict(self, A):
        return self.b.predict(A)


class _CB:
    """CatBoost with ordered target statistics on the categorical columns."""

    def __init__(self, fb, seed=0, **kw):
        from catboost import CatBoostClassifier
        self.fb, self.seed, self.params = fb, seed, {**CB_PARAMS, **kw}
        self.cat_idx = [fb.columns_.index(c) for c in fb.cat_cols_]
        self.cls = CatBoostClassifier

    def _obj(self, A):
        O = A.astype(object)
        for j in self.cat_idx:
            O[:, j] = A[:, j].astype(int)
        return O

    def fit(self, A, y, w):
        self.m = self.cls(**self.params, random_seed=self.seed, cat_features=self.cat_idx)
        self.m.fit(self._obj(A), y, sample_weight=w)
        return self

    def predict(self, A):
        return self.m.predict_proba(self._obj(A))[:, 1]


class _EBM:
    """Explainable Boosting Machine (glass-box additive model, no interactions)."""

    def __init__(self, fb, seed=0, **kw):
        from interpret.glassbox import ExplainableBoostingClassifier
        self.fb, self.seed, self.params = fb, seed, {**EBM_PARAMS, **kw}
        self.types = ["nominal" if c in fb.cat_cols_ else "continuous" for c in fb.columns_]
        self.cls = ExplainableBoostingClassifier

    def fit(self, A, y, w):
        self.m = self.cls(feature_types=self.types, random_state=self.seed, **self.params)
        self.m.fit(A, y, sample_weight=w)
        return self

    def predict(self, A):
        return self.m.predict_proba(A)[:, 1]


ALGOS = {"lr": _LR, "lgb": _LGB, "cb": _CB, "ebm": _EBM}


# ---------------------------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------------------------

class StreamCancelModel:
    """Online cancellation model (see the module docstring).

    members      algorithm names from ALGOS; several = logit average (or stack, see below)
    cfg          FeatureConfig (default: MODEL_CFG)
    half_life    recency half-life in months (None = uniform weights)
    stack        combine several members with a logistic meta-model fitted on the out-of-time
                 predictions of the last `stack_months` of arrivals
    per_hotel    ablation: one set of estimators per hotel
    calibrate    ablation: "intercept" = per-hotel logit offset fitted on the last `calib_months`
    """

    def __init__(self, members="lgb", cfg: FeatureConfig | None = None, half_life: float | None = 6.0,
                 per_hotel: bool = False, calibrate: str | None = None, calib_months: int = 3,
                 params: dict | None = None, seed: int = 0, stack: bool = False, stack_months: int = 4,
                 stack_C: float = 1.0):
        self.members = [members] if isinstance(members, str) else list(members)
        self.cfg = cfg or MODEL_CFG
        self.half_life, self.per_hotel = half_life, per_hotel
        self.calibrate, self.calib_months = calibrate, calib_months
        self.params = params or {}
        self.seed = seed
        self.offset_: dict[int, float] = {}
        self.stack, self.stack_months, self.stack_C = stack, stack_months, stack_C
        self.stack_: dict | None = None
        if stack and per_hotel:
            raise ValueError("stack and per_hotel cannot be combined")

    # ---- training --------------------------------------------------------------------------
    def _fit_members(self, A, y, w, fb):
        out = []
        for name in self.members:
            seed = {"seed": self.seed} if name != "lr" else {}
            out.append(ALGOS[name](fb, **seed, **self.params.get(name, {})).fit(A, y, w))
        return out

    def _predict_members(self, ests, A):
        """Final logit: stack weights if fitted, otherwise the plain mean of the members' logits."""
        ls = np.stack([logit(e.predict(A)) for e in ests])
        if self.stack_ is not None and ls.shape[0] == len(self.stack_["coef"]):
            return self.stack_["intercept"] + (np.array(self.stack_["coef"])[:, None] * ls).sum(0)
        return ls.mean(0)

    def _fit_set(self, A, y, w, hotel_code):
        """Estimators keyed by hotel code (a single key -1 when not per hotel)."""
        if not self.per_hotel:
            return {-1: self._fit_members(A, y, w, self.fb)}
        out = {}
        for h in np.unique(hotel_code):
            m = hotel_code == h
            out[int(h)] = self._fit_members(A[m], y[m], None if w is None else w[m], self.fb)
        return out

    def _logit_array(self, sets, A, hotel_code):
        if not self.per_hotel:
            return self._predict_members(sets[-1], A)
        z = np.zeros(A.shape[0])
        for h, ests in sets.items():
            m = hotel_code == h
            if m.any():
                z[m] = self._predict_members(ests, A[m])
        return z

    def fit(self, history: pd.DataFrame, as_of: pd.Timestamp | None = None) -> "StreamCancelModel":
        """Train on `history` (rows with a known outcome). `as_of` = the day the model goes live."""
        hist = history.drop(columns=[c for c in FORBIDDEN if c in history.columns])
        self.as_of = pd.Timestamp(as_of) if as_of is not None else hist.arrival_date.max() + pd.Timedelta(days=1)
        self._hist = hist
        st = stream_features(hist)
        self.fb = FeatureBuilder(self.cfg).fit(hist)
        A = self.fb.to_array(self.fb.transform(hist, st, oof=True))
        self._hcol = self.fb.columns_.index("hotel")
        y = hist.cancelled.to_numpy()
        self.stack_ = None
        if self.stack and len(self.members) > 1:
            self._fit_stack(hist, A, y)
        w = recency_weights(hist.arrival_date, self.as_of, self.half_life)
        hc = A[:, self._hcol].astype(int)
        self.sets_ = self._fit_set(A, y, w, hc)
        self.insample_ = pd.Series(sigmoid(self._logit_array(self.sets_, A, hc)), index=hist.index)
        self.offset_ = {}
        if self.calibrate:
            self._fit_offsets(hist, A, y)
        return self

    def _fit_stack(self, hist, A, y):
        """Temporal stacking: members trained on arrivals before (as_of - stack_months) predict the
        later arrivals, whose outcomes are known; a logistic regression on the members' logits learns
        the weights and an intercept. The members are then refitted on everything."""
        cut = self.as_of - pd.DateOffset(months=self.stack_months)
        old = (hist.arrival_date < cut).to_numpy()
        w = recency_weights(hist.arrival_date, cut, self.half_life)
        ests = self._fit_members(A[old], y[old], None if w is None else w[old], self.fb)
        Z = np.stack([logit(e.predict(A[~old])) for e in ests], axis=1)
        meta = LogisticRegression(C=self.stack_C, max_iter=1000).fit(Z, y[~old])
        self.stack_ = {"coef": meta.coef_[0].tolist(), "intercept": float(meta.intercept_[0]),
                       "members": list(self.members)}

    def _fit_offsets(self, hist, A, y):
        """Per-hotel intercept so that the mean prediction on the most recent arrivals, scored by a
        model that did not see them, matches the observed rate (ablation, off in the final model)."""
        cut = self.as_of - pd.DateOffset(months=self.calib_months)
        old = (hist.arrival_date < cut).to_numpy()
        new = ~old
        hc = A[:, self._hcol].astype(int)
        w = recency_weights(hist.arrival_date, cut, self.half_life)
        sets = self._fit_set(A[old], y[old], None if w is None else w[old], hc[old])
        z = self._logit_array(sets, A[new], hc[new])
        for h in np.unique(hc[new]):
            m = hc[new] == h
            self.offset_[int(h)] = self._solve_offset(z[m], y[new][m])

    @staticmethod
    def _solve_offset(z, y, iters=30):
        """Newton steps for the intercept d such that mean(sigmoid(z + d)) = mean(y)."""
        d = 0.0
        for _ in range(iters):
            p = sigmoid(z + d)
            d -= (p - y).sum() / ((p * (1 - p)).sum() + 1e-9)
        return float(d)

    # ---- prediction ------------------------------------------------------------------------
    def _p_from_array(self, A):
        hc = A[:, self._hcol].astype(int)
        z = self._logit_array(self.sets_, A, hc)
        if self.offset_:
            z = z + np.array([self.offset_.get(int(h), 0.0) for h in hc])
        return sigmoid(z)

    def start_session(self, commitments: pd.DataFrame | None = None) -> None:
        """Fresh online state: the stream observes the history, then the commitments (in random
        within-day order), which are scored in one batch and cached by booking_id."""
        self.stream = OnlineStream()
        self.stream.observe_frame(self._hist.drop(columns=["cancelled", "value"], errors="ignore"))
        self._cache: dict[int, float] = {}
        self.last_array = None
        if commitments is not None and len(commitments):
            c = commitments.drop(columns=[x for x in FORBIDDEN if x in commitments.columns])
            rng = np.random.default_rng(12345)
            order = np.lexsort((rng.permutation(len(c)), c.booking_date.to_numpy()))
            recs = c.iloc[order].to_dict("records")
            feats = pd.DataFrame([self.stream.observe(r) for r in recs], index=c.index[order]).loc[c.index]
            p = self._p_from_array(self.fb.to_array(self.fb.transform(c, feats)))
            self._cache = dict(zip(c.booking_id.tolist(), p.tolist()))

    def predict_one(self, b: dict) -> float:
        """P(cancel) of one request. Updates the online stream, so call it once per request."""
        bid = b.get("booking_id")
        if bid in self._cache:
            return self._cache[bid]
        s = self.stream.observe(b)
        A = self.fb.transform_record(b, s)
        self.last_array = A                      # kept for src.explain (no second observe needed)
        p = float(self._p_from_array(A)[0])
        if bid is not None:
            self._cache[bid] = p
        return p

    def predict_frame(self, df: pd.DataFrame) -> np.ndarray:
        """P(cancel) for rows of the training history (in-sample), used by the demand forecast."""
        if df.index.isin(self.insample_.index).all():
            p = self.insample_.loc[df.index].to_numpy()
            if self.offset_:
                hc = df.hotel.map({v: i for i, v in enumerate(self.fb.vocab_["hotel"])}).to_numpy()
                p = sigmoid(logit(p) + np.array([self.offset_.get(int(h), 0.0) for h in hc]))
            return p
        A = self.fb.to_array(self.fb.transform(df, stream_features(df)))
        return self._p_from_array(A)

    def predict_requests(self, requests: pd.DataFrame, commitments: pd.DataFrame | None = None) -> pd.Series:
        """Batch P(cancel) for a frame of requests exactly as decide() would see them (frame order)."""
        self.start_session(commitments)
        return pd.Series([self.predict_one(r) for r in requests.to_dict("records")], index=requests.index)
