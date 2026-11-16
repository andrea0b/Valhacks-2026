"""Classification quality of the cancellation models under temporal walk-forward validation.

Three cuts T = 1 Jan, 1 Apr, 1 Jul 2016. For each cut the model is trained on arrivals before T
(outcomes known at T) and scored on every request booked on or after T (arrivals up to the end of
2016). The test runs to the end of the data, not just a few months, because in deployment the
model stays frozen for a whole year.

Outputs (experiments/results/):
  01_algorithms.csv     log-loss / AUC / Brier / ECE per cut for LR, LightGBM, CatBoost, EBM, and the
                        combinations: plain logit average of LR + LightGBM + CatBoost (avg3) and the
                        temporal stack of the same three (stack3, the shipped recipe); the same two
                        combinations with EBM added (avg4, stack4) are kept as a comparison
  01_calibration.csv    reliability bins (deciles of the prediction) per recipe at the July cut
  01_stack_weights.csv  meta-model weights of each stack per cut
  01_ablations.csv      feature-set and recency-weight ablations (LR and LightGBM)
  01_random_vs_time.csv the same LightGBM scored with random 5-fold CV vs the temporal cuts

Run: python experiments/01_walk_forward_metrics.py      (~15 minutes)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import KFold

from common import RESULTS
from src.features import stream_features
from src.simulator import load_train
from src.stream_model import (FULL_CFG, MODEL_CFG, WITH_DRIFTING_CFG, WITH_SPECIAL_REQUESTS_CFG,
                              StreamCancelModel, logit, sigmoid)

CUTS = ("2016-01-01", "2016-04-01", "2016-07-01")
MEMBERS = ["lr", "lgb", "cb", "ebm"]       # every member compared
SHIPPED = ["lr", "lgb", "cb"]                # members of the shipped stack


def ece(y, p, bins=10):
    """Expected calibration error with equal-width bins, weighted by bin size."""
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return sum((idx == b).sum() * abs(p[idx == b].mean() - y[idx == b].mean())
               for b in range(bins) if (idx == b).any()) / len(y)


def metrics(y, p, hotel) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    out = {"logloss": log_loss(y, p), "auc": roc_auc_score(y, p), "brier": brier_score_loss(y, p),
           "ece": ece(y, p), "mean_pred": p.mean(), "mean_true": y.mean(), "n": len(y)}
    for h, k in (("Downtown Hotel", "dt"), ("Seaside Hotel", "ss")):
        m = hotel == h
        out[f"logloss_{k}"] = log_loss(y[m], p[m], labels=[0, 1])
        out[f"auc_{k}"] = roc_auc_score(y[m], p[m])
    return out


def split(df, cut):
    """Training rows (arrival < cut) and test rows (booked >= cut) with their stream features."""
    T = pd.Timestamp(cut)
    stream = stream_features(df.drop(columns=["cancelled", "value"]))   # causal: past rows only
    return df[df.arrival_date < T], df[df.booking_date >= T], stream


def score(model, test, stream):
    A = model.fb.to_array(model.fb.transform(test, stream.loc[test.index]))
    return A, model._p_from_array(A)


def algorithms_job(df, cut):
    train, test, stream = split(df, cut)
    model = StreamCancelModel(MEMBERS, stack=True).fit(train, as_of=cut)
    shipped = StreamCancelModel(SHIPPED, stack=True).fit(train, as_of=cut)
    A, p_stack4 = score(model, test, stream)
    _, p_stack3 = score(shipped, test, stream)
    member_logits = {n: logit(e.predict(A)) for n, e in zip(MEMBERS, model.sets_[-1])}
    avg3 = np.mean([member_logits[n] for n in SHIPPED], axis=0)
    preds = {**{n: sigmoid(z) for n, z in member_logits.items()},
             "avg3": sigmoid(avg3), "stack3": p_stack3,
             "avg4": sigmoid(np.mean(list(member_logits.values()), axis=0)), "stack4": p_stack4}
    y, hotel = test.cancelled.to_numpy(), test.hotel.to_numpy()
    rows = [{"cut": cut, "recipe": r, **metrics(y, p, hotel)} for r, p in preds.items()]
    calib = []
    if cut == CUTS[-1]:
        for r, p in preds.items():
            q = pd.qcut(p, 10, labels=False, duplicates="drop")
            g = pd.DataFrame({"p": p, "y": y, "bin": q}).groupby("bin").agg(pred=("p", "mean"), obs=("y", "mean"),
                                                                          n=("y", "size"))
            calib.append(g.reset_index().assign(recipe=r))
    weights = [{"recipe": r, "cut": cut, "intercept": m.stack_["intercept"], **dict(zip(m.members, m.stack_["coef"]))}
               for r, m in (("stack3", shipped), ("stack4", model))]
    return rows, calib, weights


ABLATIONS = {
    "final features": dict(cfg=MODEL_CFG),
    "+ country and guest history": dict(cfg=WITH_DRIFTING_CFG),
    "+ special requests": dict(cfg=WITH_SPECIAL_REQUESTS_CFG),
    "+ all post-booking columns": dict(cfg=FULL_CFG),
    "no recency weights": dict(cfg=MODEL_CFG, half_life=None),
    "half-life 3 months": dict(cfg=MODEL_CFG, half_life=3.0),
    "half-life 12 months": dict(cfg=MODEL_CFG, half_life=12.0),
}


def ablation_job(df, cut, algo, name):
    train, test, stream = split(df, cut)
    model = StreamCancelModel(algo, **ABLATIONS[name]).fit(train, as_of=cut)
    _, p = score(model, test, stream)
    return {"cut": cut, "algo": algo, "variant": name,
            **metrics(test.cancelled.to_numpy(), p, test.hotel.to_numpy())}


def random_cv_job(df, cfg_name, cfg):
    """Random 5-fold CV on all rows: what a non-temporal validation would have told us."""
    stream = stream_features(df.drop(columns=["cancelled", "value"]))
    y, p = df.cancelled.to_numpy(), np.zeros(len(df))
    for tr, te in KFold(5, shuffle=True, random_state=0).split(df):
        model = StreamCancelModel("lgb", cfg=cfg).fit(df.iloc[tr], as_of=df.arrival_date.max() + pd.Timedelta(days=1))
        p[te] = score(model, df.iloc[te], stream)[1]
    return {"validation": "random 5-fold", "features": cfg_name, **metrics(y, p, df.hotel.to_numpy())}


def temporal_job(df, cfg_name, cfg, cut):
    train, test, stream = split(df, cut)
    model = StreamCancelModel("lgb", cfg=cfg).fit(train, as_of=cut)
    return {"validation": f"temporal cut {cut}", "features": cfg_name,
            **metrics(test.cancelled.to_numpy(), score(model, test, stream)[1], test.hotel.to_numpy())}


if __name__ == "__main__":
    df = load_train()
    res = Parallel(n_jobs=3)(delayed(algorithms_job)(df, c) for c in CUTS)
    pd.DataFrame([r for rows, _, _ in res for r in rows]).to_csv(RESULTS / "01_algorithms.csv", index=False)
    pd.concat([c for _, cal, _ in res for c in cal]).to_csv(RESULTS / "01_calibration.csv", index=False)
    pd.DataFrame([w for _, _, ws in res for w in ws]).to_csv(RESULTS / "01_stack_weights.csv", index=False)

    jobs = [(c, a, n) for c in CUTS for a in ("lr", "lgb") for n in ABLATIONS]
    rows = Parallel(n_jobs=6)(delayed(ablation_job)(df, *j) for j in jobs)
    pd.DataFrame(rows).to_csv(RESULTS / "01_ablations.csv", index=False)

    cfgs = {"final features": MODEL_CFG, "+ post-booking columns": FULL_CFG}
    rows = Parallel(n_jobs=6)([delayed(random_cv_job)(df, n, c) for n, c in cfgs.items()]
                              + [delayed(temporal_job)(df, n, c, cut) for n, c in cfgs.items() for cut in CUTS])
    pd.DataFrame(rows).to_csv(RESULTS / "01_random_vs_time.csv", index=False)
    print(pd.read_csv(RESULTS / "01_algorithms.csv").round(4).to_string())
