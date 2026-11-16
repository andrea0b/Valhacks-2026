"""Compute every number the presentation draws.

Everything comes from the training data (`train-template-kit/train.csv`, arrivals July 2015 -
December 2016) and from the versioned experiment results in `experiments/results/`. Nothing here
reads data from the 2017 test year.

Run: python presentation/data.py        (about a minute; writes presentation/build/data.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "train-template-kit").exists())   # repository root, wherever this folder sits
sys.path.insert(0, str(ROOT))

from src.customers import (PERSONA_ORDER, add_block_size, booking_frame, explode_nights,  # noqa: E402
                           fit_personas)
from src.simulator import ROOMS, load_train  # noqa: E402

RES = ROOT / "experiments" / "results"
OUT = HERE / "build" / "data.json"
HOTELS = list(ROOMS)
SHORT = {"Downtown Hotel": "Downtown", "Seaside Hotel": "Seaside"}
BANDS = ([-1, 7, 30, 90, 180, 10_000], ["0-7", "8-30", "31-90", "91-180", "181+"])


def rnd(x, nd=3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def hotels(df):
    return {SHORT[h]: {"rooms": ROOMS[h], "bookings": int((df.hotel == h).sum()),
                       "cancel": rnd(df[df.hotel == h].cancelled.mean()),
                       "median_rate": rnd(df[df.hotel == h].nightly_rate.median(), 1),
                       "mean_nights": rnd(df[df.hotel == h].nights.mean(), 2)} for h in HOTELS}


def nightly(df):
    """Guests who showed up / rooms, every night 15 Jul 2015 - 31 Dec 2016 (notebook 02)."""
    n = explode_nights(df, ["hotel"])
    occ = n.groupby(["hotel", "night"]).show.sum().rename("shown").reset_index()
    days = pd.date_range("2015-07-15", "2016-12-31")
    out = {"start": "2015-07-15", "ratio": {}}
    for h in HOTELS:
        s = occ[occ.hotel == h].set_index("night").shown.reindex(days).fillna(0)
        out["ratio"][SHORT[h]] = [rnd(v / ROOMS[h], 2) for v in s]
    return out


def seasons(df):
    """Nightly rate by arrival month in 2016: median and interquartile range (notebook 02)."""
    d = df[df.arrival_date.dt.year == 2016]
    out = {}
    for h in HOTELS:
        g = d[d.hotel == h].groupby(d.arrival_date.dt.month).nightly_rate
        out[SHORT[h]] = {"median": [rnd(v, 1) for v in g.median()], "q25": [rnd(v, 1) for v in g.quantile(.25)],
                         "q75": [rnd(v, 1) for v in g.quantile(.75)]}
    return out


def lead(df):
    df = df.assign(band=pd.cut(df.days_ahead, bins=BANDS[0], labels=BANDS[1]))
    out = {}
    for key, d in [("all", df)] + [(SHORT[h], df[df.hotel == h]) for h in HOTELS]:
        shown = d[d.cancelled == 0]
        out[key] = {b: {"cancel": rnd(d[d.band == b].cancelled.mean()),
                        "share": rnd((shown.band == b).sum() / len(shown)),
                        "rate": rnd(d[d.band == b].nightly_rate.median(), 1),
                        "n": int((d.band == b).sum())} for b in BANDS[1]}
    return out


def booking_curve(df):
    """Share of the guests who showed up in 2016 that had booked at least L days ahead."""
    d = df[(df.arrival_date.dt.year == 2016) & (df.cancelled == 0)]
    out = {}
    for h in HOTELS:
        lead_days = np.sort(d[d.hotel == h].days_ahead.to_numpy())
        out[SHORT[h]] = [rnd(1 - np.searchsorted(lead_days, L, side="left") / len(lead_days)) for L in range(0, 366)]
    return out


def id_leak(df):
    """Cancellation rate by position of booking_id within its booking day (notebook 01)."""
    d = df.assign(pos=df.groupby("booking_date").booking_id.rank(pct=True))
    d = d[df.groupby("booking_date").booking_id.transform("size") >= 10]
    t = d.groupby([pd.cut(d.pos, np.linspace(0, 1, 11), labels=range(10)), "hotel"], observed=True).cancelled.mean().unstack()
    return {SHORT[h]: [rnd(v) for v in t[h]] for h in HOTELS}


def drift(df):
    """Share of cancellations recorded as Portugal, by arrival quarter (notebook 03)."""
    d = df.assign(q=df.arrival_date.dt.to_period("Q").astype(str))
    c = d[d.cancelled == 1]
    prt = c.groupby("q").apply(lambda x: (x.country == "PRT").mean(), include_groups=False)
    ab = pd.read_csv(RES / "01_ablations.csv")
    ab = ab[ab.variant.isin(["final features", "+ country and guest history"])]
    calib = [{"cut": r.cut, "algo": r.algo, "variant": r.variant, "pred": rnd(r.mean_pred), "true": rnd(r.mean_true),
              "logloss": rnd(r.logloss)} for r in ab.itertuples()]
    return {"quarters": list(prt.index), "prt_share": [rnd(v) for v in prt], "calib": calib}


def groups(full):
    raw = [c for c in full.columns if c not in ("booking_id", "cancelled", "value", "block")]
    g = full.groupby(raw, dropna=False).cancelled.agg(["size", "mean"])
    multi = g[g["size"] > 1]
    return {"rows_in_groups": rnd(multi["size"].sum() / len(full)), "n_groups": int(len(multi)),
            "all_cancel": rnd((multi["mean"] == 1).mean()), "all_show": rnd((multi["mean"] == 0).mean()),
            "mixed": rnd(((multi["mean"] > 0) & (multi["mean"] < 1)).mean())}


def customers(full):
    """Personas per hotel (notebooks 04-05) and agencies with 100+ bookings clustered into partner types."""
    k = {"Downtown Hotel": 7, "Seaside Hotel": 8}
    data, personas = {}, {}
    for h in HOTELS:
        d = booking_frame(full, h)
        d["persona"], _ = fit_personas(d, k[h])
        data[h] = d
        rows = []
        for p in PERSONA_ORDER:
            g = d[d.persona == p]
            if g.empty:
                continue
            rows.append({"persona": p, "cancel": rnd(g.cancelled.mean()), "rate": rnd(g.nightly_rate.mean(), 1),
                         "share": rnd(g.nights.sum() / d.nights.sum()), "yield": rnd(g.realized.sum() / g.nights.sum(), 1),
                         "late": rnd((g.days_ahead <= 30).mean())})
        personas[SHORT[h]] = rows
    both = pd.concat([data[h].assign(hotel=h) for h in HOTELS])
    both["hotel_yield"] = both.hotel.map({h: data[h].realized.sum() / data[h].nights.sum() for h in HOTELS})
    sc = both[both.agent_id != "none"].groupby(["hotel", "agent_id"]).agg(
        bookings=("booking_id", "size"), cancel_rate=("cancelled", "mean"), median_lead=("days_ahead", "median"),
        mean_block=("block", "mean"), nights=("nights", "sum"), revenue=("realized", "sum"),
        hotel_yield=("hotel_yield", "first"))
    sc["yield_index"] = sc.revenue / sc.nights / sc.hotel_yield
    big = sc[sc.bookings >= 100].copy()
    z = StandardScaler().fit_transform(np.column_stack([np.log(big.bookings), big.cancel_rate, np.log1p(big.median_lead),
                                                        np.log(big.mean_block), big.yield_index]))
    big["cluster"] = KMeans(4, n_init=20, random_state=0).fit_predict(z)
    names = {0: "Reliable niche agencies", 1: "Block wholesalers", 2: "High-volume online partners", 3: "Mixed tour operators"}
    big["type"] = big.cluster.map(names)
    total = sum(data[h].realized.sum() for h in HOTELS)
    agencies = [{"hotel": SHORT[h], "agent": a, "bookings": int(r.bookings), "cancel": rnd(r.cancel_rate),
                 "yield": rnd(r.yield_index), "share": rnd(r.revenue / total, 4), "type": r.type}
                for (h, a), r in big.iterrows()]
    types = big.groupby("type").agg(agencies=("bookings", "size"), bookings=("bookings", "sum"),
                                    cancel=("cancel_rate", "median"), yield_index=("yield_index", "median"),
                                    share=("revenue", lambda r: r.sum() / total))
    return personas, agencies, {t: {k: rnd(v) for k, v in row.items()} for t, row in types.iterrows()}


SHOWN = ('lr', 'lgb', 'cb', 'avg3', 'stack3')     # recipes drawn on the model slides


def model_results():
    rvt = pd.read_csv(RES / "01_random_vs_time.csv")
    alg = pd.read_csv(RES / "01_algorithms.csv")
    cal = pd.read_csv(RES / "01_calibration.csv")
    sw = pd.read_csv(RES / "01_stack_weights.csv")
    ab = pd.read_csv(RES / "01_ablations.csv")
    fi = pd.read_csv(RES / "06_feature_importance.csv")
    mi = pd.read_csv(RES / "06_member_importance.csv")
    return {
        "random_vs_time": [{"validation": r.validation, "features": r.features, "auc": rnd(r.auc), "logloss": rnd(r.logloss)}
                           for r in rvt.itertuples()],
        "algorithms": [{"cut": r.cut, "recipe": r.recipe, "logloss": rnd(r.logloss, 4), "auc": rnd(r.auc, 4),
                        "ece": rnd(r.ece, 4), "pred": rnd(r.mean_pred), "true": rnd(r.mean_true)}
                       for r in alg[alg.recipe.isin(SHOWN)].itertuples()],
        "calibration": {k: [[rnd(r.pred), rnd(r.obs)] for r in g.itertuples()]
                        for k, g in cal[cal.recipe.isin(SHOWN)].groupby("recipe")},
        "stack_weights": [{"cut": r.cut, "lr": rnd(r.lr), "lgb": rnd(r.lgb), "cb": rnd(r.cb)}
                          for r in sw[sw.recipe == "stack3"].itertuples()],
        "ablations": [{"cut": r.cut, "algo": r.algo, "variant": r.variant, "logloss": rnd(r.logloss, 4), "auc": rnd(r.auc, 4)}
                      for r in ab.itertuples()],
        "themes": {t: rnd(v) for t, v in fi.groupby("theme").share.sum().sort_values(ascending=False).items()},
        "columns": [{"label": r.label, "theme": r.theme, "share": rnd(r.share, 4)}
                    for r in fi.groupby(["label", "theme"], as_index=False).share.sum().sort_values("share", ascending=False).itertuples()],
        "members": {m: {"weight": rnd(g.weight.iloc[0], 3),
                        "top": [[r.label, rnd(r.mean_abs_weighted, 4)] for r in g.sort_values("mean_abs_weighted", ascending=False).head(6).itertuples()]}
                    for m, g in mi.groupby("member")},
    }


def policy_results():
    pa = pd.read_csv(RES / "04_policy_ablation.csv")
    m = pa.groupby(["config", "window"]).net_M.mean().unstack()
    halves = (m["H1"] + m["H2"])
    ablation = {c: rnd(halves[c] - halves["base"], 4) for c in m.index if c != "base"}
    fin = pd.read_csv(RES / "03_finalists.csv")
    fin = fin[fin.config.isin(["lr", "lgb", "stack_lr_lgb_cb"])]      # the recipes drawn on the robustness slide
    g = fin.groupby(["config", "shift", "window"]).net_M.agg(["mean", "min", "max"]).reset_index()
    finalists = [{"config": r.config, "shift": rnd(r.shift, 1), "window": r.window, "mean": rnd(r.mean, 4),
                  "min": rnd(r.min, 4), "max": rnd(r.max, 4)} for r in g.itertuples()]
    return {"ablation": ablation, "finalists": finalists}


def replay_results():
    """Shipped system on the 2016 replay: net revenue table (docs/methodology.md §7, notebooks 06-08),
    every night of the year, and the decisions of the second half."""
    table = {"windows": ["H1", "H2", "FY"],
             "rows": [["No overbooking", [1.638, 1.101, 3.790]], ["Classic overbooking", [2.246, 1.420, 5.257]],
                      ["This system", [2.683, 1.694, 6.328]], ["Perfect foresight", [3.068, 1.933, 7.761]]]}
    nights = pd.read_csv(RES / "05_nights_FY.csv", parse_dates=["night"])
    year = {}
    for h in HOTELS:
        g = nights[nights.hotel == h].sort_values("night")
        year[SHORT[h]] = {"occ": [rnd(s / c if c > 0 else 0, 3) for s, c in zip(g.seated, g.capacity)],
                          "walk": [int(w) for w in g.walked_arrivals], "start": str(g.night.iloc[0].date())}
    summary = json.loads((RES / "05_summary.json").read_text())
    dec = pd.read_csv(RES / "05_decisions_H2.csv", parse_dates=["booking_date", "arrival_date"])
    flow = {o: {"n": int(len(g)), "cancelled": int(g.cancelled.sum())} for o, g in dec.groupby("outcome")}
    night = pd.Timestamp("2016-09-15")
    cover = dec[(dec.hotel == "Downtown Hotel") & dec.accepted & (dec.arrival_date <= night)
                & (dec.arrival_date + pd.to_timedelta(dec.nights, "D") > night)].sort_values("booking_date")
    examples = dec[dec.booking_id.isin([56105, 99175])]
    ex = [{"id": int(r.booking_id), "booked": str(r.booking_date.date()), "arrival": str(r.arrival_date.date()),
           "nights": int(r.nights), "rate": rnd(r.rate, 2), "segment": r.segment, "p": rnd(r.p_cancel),
           "bid": rnd(r.bid, 2), "free": rnd(r.free_min, 1), "to_come": rnd(r.demand_to_come, 1),
           "booked_share": rnd(r.booked_share), "growth": rnd(r.growth, 3), "level": rnd(r.price_level, 1),
           "outcome": r.outcome, "cancelled": int(r.cancelled),
           "drivers": [[r.driver1, rnd(r.driver1_logit)], [r.driver2, rnd(r.driver2_logit)], [r.driver3, rnd(r.driver3_logit)]]}
          for r in examples.itertuples()]
    return {"table": table, "year": year, "fy": {k: summary["FY"][k] for k in ("net", "revenue", "walk", "penalty", "occupancy")},
            "flow": flow, "night": {"date": "2016-09-15", "q": [rnd(1 - p) for p in cover.p_cancel]}, "examples": ex}


def evaluator_results():
    """Organisers' evaluator on the submitted solution (evaluation/results.csv). Report only."""
    res = pd.read_csv(ROOT / "evaluation" / "results.csv")
    rows = [{"key": r.solution, "label": r.description, "net": int(r.net_revenue_eur)}
            for r in res.itertuples()]
    by = {r["key"]: r["net"] for r in rows}
    return {"rows": rows, "vs_classic": rnd(by["model"] / by["average_rate"] - 1, 4),
            "vs_none": rnd(by["model"] / by["no_overbooking"] - 1, 4),
            "decide_calls": 26439, "accepted": 12069, "commitments": 14104, "ms_per_decision": 2.1}


def main():
    df = load_train()
    full = add_block_size(df)
    personas, agencies, types = customers(full)
    out = {"hotels": hotels(df), "nightly": nightly(df), "seasons": seasons(df), "lead": lead(df),
           "booking_curve": booking_curve(df), "id_leak": id_leak(df), "drift": drift(df), "groups": groups(full),
           "personas": personas, "agencies": agencies, "partner_types": types,
           "model": model_results(), "policy": policy_results(), "replay": replay_results(),
           "evaluator": evaluator_results()}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf8")
    print(f"{OUT} · {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
