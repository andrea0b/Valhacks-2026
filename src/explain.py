"""Human-readable reasons for every decision.

:func:`reason` is called right after ``policy.decide(booking)``. It only reads what the decision
already computed (``policy.last`` and ``model.last_array``) and never touches the online state.

The cancellation model is a stack of three members, and its final logit is a weighted sum of the
members' logits. Each member splits additively into per-feature contributions (logistic regression:
coefficient x value; LightGBM and CatBoost: TreeSHAP), so the final logit is
*exactly* the sum of per-feature contributions (:func:`decompose`, verified by
:func:`check_additivity`). The reason lists the inputs that really moved the forecast.
"""
from __future__ import annotations

import numpy as np

# Readable names for the model columns.
LABELS = {
    "days_ahead": "booking lead time", "log_lead": "booking lead time",
    "lead_bin": "lead-time band", "nightly_rate": "nightly rate", "agent": "booking agent",
    "agent_te": "agent's historical cancel rate", "agent_none": "booking without an agent",
    "sales_segment": "sales segment", "sales_channel": "channel", "guest_type": "guest type",
    "hotel": "hotel", "meal": "meal plan", "room_type": "room type", "nights": "number of nights",
    "adults": "adults", "children": "children", "babies": "babies", "weekday_nights": "weekday nights",
    "weekend_nights": "weekend nights", "weekend_share": "share of weekend nights",
    "arrival_month": "arrival month", "arrival_week": "arrival week", "arrival_day": "arrival day",
    "arrival_dow": "arrival weekday", "booking_dow": "request weekday",
    "season": "season", "month_sin": "seasonality", "month_cos": "seasonality",
    "block_rank": "identical requests already seen (group)",
    "log_block_rank": "identical requests already seen (group)",
    "in_block": "part of a group", "log_loose_rank": "similar requests the same day",
    "log_day_agent": "requests from the same agent that day",
    "log_demand_date": "requests already seen for the night",
    "log_demand_week": "requests already seen for the week", "company_flag": "company booking",
    "company": "company", "country": "country", "returning_guest": "returning guest",
    "past_stays": "past stays", "past_cancellations": "past cancellations",
    "has_special": "special requests", "has_amend": "amendments", "waitlisted": "waiting list",
    "special_requests": "special requests", "amendments": "amendments", "waitlist_days": "waitlist days",
}

# Columns grouped into business themes (used for global importance).
THEMES = {
    "agent": ("agent", "agent_te", "agent_none"),
    "group of identical requests": ("block_rank", "log_block_rank", "in_block", "log_loose_rank",
                                    "log_day_agent"),
    "lead time": ("days_ahead", "log_lead", "lead_bin"),
    "rate and stay": ("nightly_rate", "nights", "weekday_nights", "weekend_nights", "weekend_share"),
    "calendar": ("arrival_month", "arrival_week", "arrival_day", "arrival_dow", "booking_dow", "season",
                 "month_sin", "month_cos"),
    "demand already seen": ("log_demand_date", "log_demand_week"),
    "guest profile": ("sales_segment", "sales_channel", "guest_type", "company_flag", "company", "meal",
                      "room_type", "adults", "children", "babies"),
    "hotel": ("hotel",),
}


def label(col: str) -> str:
    return LABELS.get(col, col)


def theme(col: str) -> str:
    for t, cols in THEMES.items():
        if col in cols:
            return t
    return "other"


def member_contributions(e, A, fb) -> tuple[np.ndarray, float]:
    """Additive decomposition of ONE member's logit for the row A (1 x d).

    Returns (per-column contribution aligned with ``fb.columns_``, bias); their sum is the member's
    logit. LR: coefficient x design value; LightGBM / CatBoost: TreeSHAP; EBM: term scores.
    """
    c = np.zeros(len(fb.columns_))
    name = type(e).__name__
    if name == "_LR":
        x = e._design(A)[0]
        w = e.m.coef_[0]
        k = len(e.num_idx)
        for n, j in enumerate(e.num_idx):
            c[j] += x[n] * w[n]
        for j, size in zip(e.cat_idx, e.sizes):
            c[j] += float((x[k:k + size] * w[k:k + size]).sum())
            k += size
        return c, float(e.m.intercept_[0])
    if name == "_LGB":
        v = e.b.predict(A, pred_contrib=True)[0]
        return np.asarray(v[:-1]), float(v[-1])
    if name == "_CB":
        from catboost import Pool
        v = e.m.get_feature_importance(Pool(e._obj(A), cat_features=e.cat_idx), type="ShapValues")[0]
        return np.asarray(v[:-1]), float(v[-1])
    if name == "_EBM":
        t = e.m.eval_terms(A)[0]
        for ti, feats in enumerate(e.m.term_features_):
            for f in feats:
                c[f] += t[ti] / len(feats)
        return c, float(np.ravel(e.m.intercept_)[0])
    raise TypeError(name)


def decompose(model, A: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Per-column contribution to the FINAL logit of row `A` (default: the last prediction), and
    the constant part: final logit = constant + sum(contributions). Works for single models,
    averages and stacks, because the final logit is a weighted sum of additive members."""
    A = model.last_array if A is None else A
    hc = int(A[0, model._hcol])
    ests = model.sets_[hc] if model.per_hotel else model.sets_[-1]
    if model.stack_ is not None and len(model.stack_["coef"]) == len(ests):
        w, const = np.array(model.stack_["coef"]), model.stack_["intercept"]
    else:
        w, const = np.full(len(ests), 1.0 / len(ests)), 0.0
    total = np.zeros(len(model.fb.columns_))
    for wi, e in zip(w, ests):
        c, bias = member_contributions(e, A, model.fb)
        total += wi * c
        const += wi * bias
    return total, float(const)


def _aggregate(model, contrib: np.ndarray, key) -> list[tuple[str, float]]:
    agg: dict[str, float] = {}
    for col, v in zip(model.fb.columns_, contrib):
        agg[key(col)] = agg.get(key(col), 0.0) + float(v)
    return sorted(agg.items(), key=lambda kv: -abs(kv[1]))


def drivers(model, k: int = 3, A: np.ndarray | None = None) -> list[tuple[str, float]]:
    """Top-k inputs that moved the prediction, in logit units (positive = more cancellation)."""
    if A is None and getattr(model, "last_array", None) is None:
        return []
    contrib, _ = decompose(model, A)
    return _aggregate(model, contrib, label)[:k]


def themes(model, A: np.ndarray | None = None) -> list[tuple[str, float]]:
    """Contribution of each business theme to the logit, largest first."""
    contrib, _ = decompose(model, A)
    return _aggregate(model, contrib, theme)


def check_additivity(model, A: np.ndarray | None = None) -> float:
    """|constant + sum(contributions) - logit(p_cancel)| for a row (should be ~1e-15)."""
    A = model.last_array if A is None else A
    contrib, const = decompose(model, A)
    p = float(model._p_from_array(A)[0])
    return abs(const + contrib.sum() - float(np.log(p / (1 - p))))


def outcome(last: dict, accepted: bool) -> str:
    """Which check decided: accepted | invalid | full | price | capacity."""
    if accepted:
        return "accepted"
    if not last or last.get("invalid"):
        return "invalid"
    if not last.get("ok_value"):
        return "full" if np.isinf(last["bid"]) else "price"
    return "capacity"


def reason(policy, model, booking: dict, accepted: bool) -> str:
    """One-sentence explanation of the last decision."""
    L = getattr(policy, "last", None) or {}
    kind = outcome(L, accepted)
    if kind == "invalid":
        return "rejected: zero rate or stay outside the planning year"
    p, bid, rate = L["p_cancel"], L["bid"], L["rate"]
    show = 1.0 - p
    nights = int(booking["nights"])
    drv = drivers(model)                     # model.last_array = this request (set by predict_one)
    why = "; main factors: " + ", ".join(
        f"{n} ({'more' if v > 0 else 'less'} cancellation)" for n, v in drv) if drv else ""
    head = (f"{booking['hotel']}, {nights} nights at {rate:.0f} EUR: show-up probability {show:.2f}, "
            f"expected value {show * rate * nights:.0f} EUR")
    if kind == "accepted":
        if L.get("priced_walk"):
            return (f"accepted: {head}; night nearly full but the rate exceeds the expected walk cost "
                    f"({bid:.0f} EUR per night){why}")
        return (f"accepted: {head}; rate {rate:.0f} EUR >= reserve price {bid:.0f} EUR "
                f"and the expected guests fit the free rooms{why}")
    if kind == "full":
        return f"rejected: {head}; the requested nights are already full of expected guests{why}"
    if kind == "price":
        return (f"rejected: {head}; rate {rate:.0f} EUR < reserve price {bid:.0f} EUR "
                f"(we still expect demand that pays more for these nights){why}")
    return f"rejected: {head}; the expected guests would exceed capacity on at least one night{why}"
