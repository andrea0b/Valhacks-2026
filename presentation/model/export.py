"""Export the real cancellation model and the July-2016 replay for the live console.

Writes two files read by ``presentation/model/model.js``:

* ``presentation/build/model.json``: the cancellation model (stack of logistic regression,
  LightGBM and CatBoost) with everything model.js needs to rebuild the feature vector of ONE
  request, every member's logit, the stack probability and the exact per-input contributions that
  ``src/explain.py`` computes (LR coefficient x value, path-dependent TreeSHAP for LightGBM and
  CatBoost, weighted by the stack weights).
* ``presentation/build/live.json``: the replay shown on the live slides. The model is trained only
  on arrivals before 1 July 2016 (honest out-of-sample), the policy is ``BidPricePolicy`` with
  ``logit_shift=0``, and the requests booked from 1 July to 11 August 2016 are replayed in the
  simulator's order (same-day requests in random order, default shuffle seed). It holds the replayed
  requests, the policy state at the start (enough to rebuild every later state exactly), the demand
  forecast parameters, start-of-day snapshots and a worked bid-price example.

Large numeric arrays are stored as little-endian typed arrays in base64 strings
``"~<kind>:<base64>"`` with kind in f64, f32, i32, u32, i16, u16, u8 (exact and compact);
model.js decodes them on load. Nothing here reads data from the 2017 test year.

Run: python presentation/model/export.py      (about 6 minutes the first time; the fitted model is
cached in the system temp directory, see ``CACHE``; ``--refit`` ignores the cache)
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "train-template-kit").exists())   # repository root, wherever this folder sits
BUILD = HERE.parent / "build"
sys.path.insert(0, str(ROOT))

from src.explain import LABELS, THEMES, decompose, label, outcome, reason, theme  # noqa: E402
from src.features import LEAD_BINS, LEAD_LABELS, stream_features  # noqa: E402
from src.policy import LEAD_EDGES, BidPricePolicy, _clean, _lead_bucket, _room_nights, shift_logit  # noqa: E402
from src.simulator import build_holdout, load_train  # noqa: E402
from src.stream_model import StreamCancelModel  # noqa: E402

START, RECORD_UNTIL = "2016-07-01", "2016-08-12"
MEMBERS = ["lr", "lgb", "cb"]
CACHE = Path(tempfile.gettempdir()) / "valhacks-presentation"
EXAMPLE = {"hotel": "Downtown Hotel", "night": "2016-09-15", "day": "2016-07-20"}   # methodology 6.3

_DT = {"f64": "<f8", "f32": "<f4", "i32": "<i4", "u32": "<u4", "i16": "<i2", "u16": "<u2", "u8": "u1"}


def enc(a, kind: str) -> str:
    """Typed array -> '~kind:base64' (exact: integer kinds check that nothing is lost)."""
    a = np.asarray(a)
    b = a.astype(_DT[kind])
    if kind not in ("f64", "f32") and not np.array_equal(b.astype(np.float64), a.astype(np.float64)):
        raise ValueError(f"values do not fit {kind}")
    return f"~{kind}:" + base64.b64encode(np.ascontiguousarray(b).tobytes()).decode("ascii")


def r(x, nd=2):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def fnum(x):
    """Full-precision float for plain JSON (None for NaN / inf)."""
    return None if x is None or not np.isfinite(x) else float(x)


# ---------------------------------------------------------------------------------------------
# Data and model (shared with parity.py)
# ---------------------------------------------------------------------------------------------

def holdout():
    return build_holdout(load_train(), start=START)


def fitted_model(ho, refit: bool = False) -> StreamCancelModel:
    """The demo model: stack of three, trained on arrivals before START. Cached (joblib) so that
    export.py and parity.py use the very same fitted object."""
    path = CACHE / f"stack3_{START}.joblib"
    if path.exists() and not refit:
        return joblib.load(path)
    model = StreamCancelModel(MEMBERS, stack=True).fit(ho.history, as_of=ho.days[0])
    CACHE.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return model


def replay(model, ho, on_day=None, on_request=None) -> BidPricePolicy:
    """Replay of the live slides. `on_day(t, day, pol)` runs at the start of every day
    (before its requests), `on_request(b, accepted, pol, stream_features)` after each decision."""
    model.start_session(ho.commitments)
    pol = BidPricePolicy(ho.commitments.copy(), {h: c.copy() for h, c in ho.capacity.items()},
                         history=ho.history, model=model, logit_shift=0.0)
    seen = {}
    observe = model.stream.observe

    def spy(b):                         # records the stream features the model really used
        s = observe(b)
        seen["s"] = s
        return s

    model.stream.observe = spy
    reqs = ho.requests[ho.requests.booking_date < RECORD_UNTIL]
    days = pd.date_range(START, pd.Timestamp(RECORD_UNTIL) - pd.Timedelta(days=1))
    for t, day in enumerate(days):
        if on_day:
            on_day(t, day, pol)
        for b in reqs[reqs.booking_date == day].to_dict("records"):
            seen.clear()
            ok = bool(pol.decide(b))
            if on_request:
                on_request(b, ok, pol, dict(seen.get("s") or {}))
    model.stream.observe = observe
    return pol


# ---------------------------------------------------------------------------------------------
# model.json
# ---------------------------------------------------------------------------------------------

def export_features(model) -> dict:
    fb = model.fb
    cfg = fb.config
    months = list(range(1, 13))
    return {
        "columns": fb.columns_,
        "cat_cols": fb.cat_cols_,
        "num_cols": fb.num_cols_,
        "vocab": fb.vocab_,
        "raw_num": list(cfg.raw_num),
        "raw_cat": list(cfg.raw_cat),
        "groups": list(cfg.groups),
        "agent_te": {str(k): float(v) for k, v in fb.te_.items()},
        "prior": float(fb.prior_),
        "lead_bins": [[hi, lab] for hi, lab in zip(LEAD_BINS[1:], LEAD_LABELS)],
        # numpy's sin/cos of 2*pi*month/12, exactly as transform_record computes them
        "month_sin": [float(np.sin(2 * np.pi * mo / 12)) for mo in months],
        "month_cos": [float(np.cos(2 * np.pi * mo / 12)) for mo in months],
        "labels": {c: label(c) for c in fb.columns_},
        "themes": {c: theme(c) for c in fb.columns_},
        "label_names": LABELS,
        "theme_names": list(THEMES) + ["other"],
    }


def export_lr(e) -> dict:
    return {"intercept": float(e.m.intercept_[0]), "coef": enc(e.m.coef_[0], "f64"),
            "mu": enc(e.mu, "f64"), "sd": enc(e.sd, "f64"),
            "num_idx": e.num_idx, "cat_idx": e.cat_idx, "sizes": e.sizes}


def export_lgb(e, n_features: int) -> dict:
    """LightGBM trees in LightGBM's own node numbering (internal nodes >= 0, leaves ~index)."""
    d = e.b.dump_model()
    assert d["num_tree_per_iteration"] == 1 and not d["average_output"]
    feat, thr, kind, left, right, icount = [], [], [], [], [], []
    lval, lcount = [], []
    int_off, leaf_off, n_leaves, cat_sets = [], [], [], []
    miss = {"None": 0, "Zero": 1, "NaN": 2}
    for t in d["tree_info"]:
        root = t["tree_structure"]
        int_off.append(len(feat))
        leaf_off.append(len(lval))
        n_leaves.append(t["num_leaves"])
        n_int = t["num_leaves"] - 1
        nodes = [None] * n_int
        leaves = [None] * t["num_leaves"]

        def walk(n):
            if "leaf_index" in n or "leaf_value" in n and "split_index" not in n:
                leaves[n.get("leaf_index", 0)] = n
                return ~n.get("leaf_index", 0)
            nodes[n["split_index"]] = n
            n["_l"], n["_r"] = walk(n["left_child"]), walk(n["right_child"])
            return n["split_index"]

        walk(root)
        for n in nodes:
            cat = n["decision_type"] == "=="
            if cat:
                thr.append(len(cat_sets))
                cat_sets.append(sorted(int(v) for v in str(n["threshold"]).split("||")))
            else:
                assert n["decision_type"] == "<="
                thr.append(float(n["threshold"]))
            feat.append(n["split_feature"])
            kind.append(int(cat) | (int(bool(n["default_left"])) << 1) | (miss[n["missing_type"]] << 2))
            left.append(n["_l"])
            right.append(n["_r"])
            icount.append(n["internal_count"])
        for lf in leaves:
            lval.append(float(lf["leaf_value"]))
            lcount.append(int(lf.get("leaf_count", 0)))
    return {"n_features": n_features, "n_trees": len(d["tree_info"]),
            "int_off": enc(int_off, "i32"), "leaf_off": enc(leaf_off, "i32"), "n_leaves": enc(n_leaves, "i32"),
            "feat": enc(feat, "u8"), "thr": enc(thr, "f64"), "kind": enc(kind, "u8"),
            "left": enc(left, "i16"), "right": enc(right, "i16"), "count": enc(icount, "i32"),
            "leaf_value": enc(lval, "f64"), "leaf_count": enc(lcount, "i32"), "cat_sets": cat_sets}


def export_cb(e, fb) -> tuple[dict, dict]:
    """CatBoost oblivious trees with the CTR features pre-resolved.

    CatBoost turns the categorical inputs into CTR features (target statistics of combinations of
    categories, sometimes combined with binarised float features) through hashed lookup tables.
    The tables are resolved here for every combination of category codes the model can see, and
    each CTR is stored as its bucket (number of its borders it exceeds), which is all the trees
    need. The CTR arithmetic is float32, as in CatBoost. Returns (export, check) where check holds
    what export_check needs to compare a numpy re-implementation with CatBoost itself.
    """
    from catboost import Pool
    est = e.m
    with tempfile.TemporaryDirectory() as tmp:
        jpath = Path(tmp) / "cb.json"
        est.save_model(str(jpath), format="json")
        J = json.loads(jpath.read_text(encoding="utf8"))
        # The python export carries the hash of every category code and the CTR tables in
        # executable form (calc_hash); a pool with every code makes it include all of them.
        K = max(len(v) for v in fb.vocab_.values())
        A = np.zeros((K, len(fb.columns_)))
        for c in fb.cat_cols_:
            j = fb.columns_.index(c)
            A[:, j] = np.minimum(np.arange(K), len(fb.vocab_[c]) - 1)
        ppath = Path(tmp) / "cb_model.py"
        est.save_model(str(ppath), format="python", pool=Pool(e._obj(A), cat_features=e.cat_idx))
        ns: dict = {}
        exec(compile(ppath.read_text(encoding="utf8"), "cb_model", "exec"), ns)   # our own model's export
    pm = ns["catboost_model"]
    hashes = {int(k): v for k, v in ns["cat_features_hashes"].items()}
    fi = J["features_info"]
    ffeat, cfeat, ctrs = fi["float_features"], fi["categorical_features"], fi["ctrs"]
    assert [f["feature_index"] for f in ffeat] == list(range(len(ffeat)))
    assert all(len(f["borders"]) for f in ffeat)            # bin_index i == float feature i
    float_flat = [f["flat_feature_index"] for f in ffeat]
    cat_flat = [c["flat_feature_index"] for c in cfeat]
    cat_size = [len(fb.vocab_[fb.columns_[j]]) for j in cat_flat]
    onehot = [c for c in cfeat if c.get("values")]
    assert len(onehot) == 1 and len(onehot[0]["values"]) == 1
    oh_cat = onehot[0]["feature_index"]
    oh_code = [k for k, v in hashes.items() if (v & 0xFFFFFFFF) == (onehot[0]["values"][0] & 0xFFFFFFFF)]
    assert len(oh_code) == 1
    oh_code = oh_code[0]
    n_float_bins = len(ffeat)

    # ---- CTR features, in the order of features_info.ctrs == python export order
    flat_ctrs = [(cm.projection, ctr) for cm in pm.model_ctrs.compressed_model_ctrs for ctr in cm.model_ctrs]
    assert len(flat_ctrs) == len(ctrs)
    learn = pm.model_ctrs.ctr_data.learn_ctrs
    f32 = np.float32
    MASK = (1 << 64) - 1
    MAGIC = 0x4906BA494954CB65
    projections, proj_key = [], {}
    ctr_proj = []                                   # ctr index -> (projection index, slot)
    for i, (proj, ctr) in enumerate(flat_ctrs):
        jc = ctrs[i]
        assert jc["ctr_type"] == ctr.base_ctr_type and float(jc["prior_numerator"]) == float(ctr.prior_num)
        cats = list(proj.transposed_cat_feature_indexes)
        bins = []
        for bi in proj.binarized_indexes:
            if bi.bin_index < n_float_bins:
                assert not bi.check_value_equal
                bins.append({"float": bi.bin_index, "border": float(ffeat[bi.bin_index]["borders"][bi.value - 1])})
            else:
                assert bi.bin_index == n_float_bins and bi.check_value_equal and bi.value == 1
                bins.append({"onehot": oh_cat, "code": oh_code})
        key = json.dumps([cats, bins])
        if key not in proj_key:
            proj_key[key] = len(projections)
            projections.append({"cats": cats, "bins": bins, "ctrs": [], "_proj": proj})
        p = proj_key[key]
        ctr_proj.append((p, len(projections[p]["ctrs"])))
        projections[p]["ctrs"].append(i)

    def calc_hash_vec(a, b):
        return (np.uint64(MAGIC) * (a + np.uint64(MAGIC) * b))

    def ctr_value(ctr, tab, bucket):
        if bucket is None:
            cin, tot = 0, 0
        elif ctr.base_ctr_type == "Counter":
            cin, tot = tab.ctr_total[bucket], tab.counter_denominator
        else:
            assert ctr.base_ctr_type == "Borders" and tab.target_classes_count == 2
            cin, tot = tab.ctr_total[2 * bucket + 1], tab.ctr_total[2 * bucket] + tab.ctr_total[2 * bucket + 1]
        v = (f32(cin) + f32(ctr.prior_num)) / (f32(tot) + f32(ctr.prior_denom))
        return (v + f32(ctr.shift)) * f32(ctr.scale)

    def ctr_bucket(i, v):
        return int((np.float32(v) > np.asarray(ctrs[i]["borders"], dtype=np.float32)).sum())

    n_entries = 0
    with np.errstate(over="ignore"):
        for p in projections:
            radix = [cat_size[c] for c in p["cats"]] + [2] * len(p["bins"])
            grids = np.meshgrid(*[np.arange(k) for k in radix], indexing="ij")
            digits = [g.ravel().astype(np.int64) for g in grids]
            keyv = np.zeros(digits[0].size, dtype=np.int64)
            for dgt, k in zip(digits, radix):
                keyv = keyv * k + dgt
            h = np.zeros(keyv.size, dtype=np.uint64)
            for c, dgt in zip(p["cats"], digits):
                hv = np.array([hashes[int(x)] & MASK for x in range(cat_size[c])], dtype=np.uint64)
                h = calc_hash_vec(h, hv[dgt])
            for dgt in digits[len(p["cats"]):]:
                h = calc_hash_vec(h, dgt.astype(np.uint64))
            hl = h.tolist()
            default = [ctr_bucket(i, ctr_value(flat_ctrs[i][1], learn[flat_ctrs[i][1].base_hash], None))
                       for i in p["ctrs"]]
            rows = {}
            for slot, i in enumerate(p["ctrs"]):
                ctr = flat_ctrs[i][1]
                tab = learn[ctr.base_hash]
                for kk, hh in zip(keyv.tolist(), hl):
                    bucket = tab.resolve_hash_index(hh)
                    if bucket is None:
                        continue
                    b = ctr_bucket(i, ctr_value(ctr, tab, bucket))
                    if b != default[slot]:
                        rows.setdefault(kk, list(default))[slot] = b
            keys = sorted(rows)
            n_entries += len(keys)
            p["radix"] = radix
            p["default"] = default
            p["keys"] = keys
            p["buckets"] = [[rows[k][s] for k in keys] for s in range(len(p["ctrs"]))]

    # ---- trees
    base_ctr = sum(len(f["borders"]) for f in ffeat) + 1        # float borders, then the one-hot
    ctr_start = np.cumsum([0] + [len(c["borders"]) for c in ctrs])
    classes, class_key = [], {}

    def class_of(cols):
        k = tuple(sorted(set(cols)))
        if k not in class_key:
            class_key[k] = len(classes)
            classes.append(list(k))
        return class_key[k]

    depth, s_kind, s_a, s_b, s_class, leaf_v, leaf_w = [], [], [], [], [], [], []
    for tr in J["oblivious_trees"]:
        depth.append(len(tr["splits"]))
        for sp in tr["splits"]:
            if sp["split_type"] == "FloatFeature":
                f = sp["float_feature_index"]
                s_kind.append(0); s_a.append(f); s_b.append(float(sp["border"]))
                s_class.append(class_of([float_flat[f]]))
            elif sp["split_type"] == "OneHotFeature":
                c = sp["cat_feature_index"]
                assert c == oh_cat and sp["value"] == onehot[0]["values"][0]
                s_kind.append(1); s_a.append(c); s_b.append(float(oh_code))
                s_class.append(class_of([cat_flat[c]]))
            else:
                assert sp["split_type"] == "OnlineCtr"
                i = int(np.searchsorted(ctr_start, sp["split_index"] - base_ctr, side="right") - 1)
                k = sp["split_index"] - base_ctr - int(ctr_start[i])
                assert abs(ctrs[i]["borders"][k] - sp["border"]) < 1e-9
                s_kind.append(2); s_a.append(i); s_b.append(float(k))
                p = projections[ctr_proj[i][0]]
                cols = [cat_flat[c] for c in p["cats"]]
                cols += [float_flat[b["float"]] if "float" in b else cat_flat[b["onehot"]] for b in p["bins"]]
                s_class.append(class_of(cols))
        assert len(tr["leaf_values"]) == 1 << len(tr["splits"])
        leaf_v += tr["leaf_values"]
        leaf_w += tr["leaf_weights"]
    scale, bias = J["scale_and_bias"]
    out = {
        "n_trees": len(depth), "scale": float(scale), "bias": float(bias[0]),
        "float_flat": float_flat, "cat_flat": cat_flat,
        "ctr_proj": [list(x) for x in ctr_proj],
        "projections": [{"cats": p["cats"], "bins": p["bins"], "radix": p["radix"], "ctrs": p["ctrs"],
                         "default": p["default"], "keys": enc(p["keys"], "u32"),
                         "buckets": [enc(b, "u8") for b in p["buckets"]]} for p in projections],
        "depth": enc(depth, "u8"), "split_kind": enc(s_kind, "u8"), "split_a": enc(s_a, "u16"),
        "split_b": enc(s_b, "f64"), "split_class": enc(s_class, "u16"),
        "leaf_value": enc(leaf_v, "f64"), "leaf_weight": enc(leaf_w, "f64"),
        "classes": classes,
    }
    check = {"projections": projections, "ctr_proj": ctr_proj, "depth": depth, "s_kind": s_kind, "s_a": s_a,
             "s_b": s_b, "leaf_v": np.array(leaf_v), "float_flat": float_flat, "cat_flat": cat_flat,
             "n_entries": n_entries, "scale": float(scale), "bias": float(bias[0])}
    return out, check


def cb_reference_raw(chk, A: np.ndarray) -> np.ndarray:
    """numpy re-implementation of the exported CatBoost format (self-check against CatBoost)."""
    n = len(A)
    X32 = A.astype(np.float32)
    codes = {c: A[:, j].astype(np.int64) for c, j in enumerate(chk["cat_flat"])}
    n_ctr = len(chk["ctr_proj"])
    cb = np.zeros((n, n_ctr), dtype=np.int64)
    for p in chk["projections"]:
        key = np.zeros(n, dtype=np.int64)
        digs = [codes[c] for c in p["cats"]]
        for b in p["bins"]:
            if "float" in b:
                digs.append((X32[:, chk["float_flat"][b["float"]]] > np.float32(b["border"])).astype(np.int64))
            else:
                digs.append((codes[b["onehot"]] == b["code"]).astype(np.int64))
        for dgt, k in zip(digs, p["radix"]):
            key = key * k + dgt
        keys = np.asarray(p["keys"], dtype=np.int64)
        idx = np.searchsorted(keys, key)
        idx_c = np.minimum(idx, max(len(keys) - 1, 0))
        found = (idx < len(keys)) & (keys[idx_c] == key) if len(keys) else np.zeros(n, bool)
        for slot, i in enumerate(p["ctrs"]):
            bk = np.asarray(p["buckets"][slot], dtype=np.int64)
            cb[:, i] = np.where(found, bk[idx_c] if len(bk) else 0, p["default"][slot])
    raw = np.zeros(n)
    pos = leaf = 0
    for d in chk["depth"]:
        li = np.zeros(n, dtype=np.int64)
        for k in range(d):
            kind, a, b = chk["s_kind"][pos + k], chk["s_a"][pos + k], chk["s_b"][pos + k]
            if kind == 0:
                bit = X32[:, chk["float_flat"][a]] > np.float32(b)
            elif kind == 1:
                bit = codes[a] == int(b)
            else:
                bit = cb[:, a] > int(b)
            li |= bit.astype(np.int64) << k
        raw += chk["leaf_v"][leaf + li]
        pos += d
        leaf += 1 << d
    return raw * chk["scale"] + chk["bias"]


def export_model(model, A_check: np.ndarray) -> dict:
    lr, lgb, cb = model.sets_[-1]
    assert model.stack_["members"] == MEMBERS and not model.per_hotel and not model.offset_
    cbx, chk = export_cb(cb, model.fb)
    raw_ref = cb_reference_raw(chk, A_check)
    raw_cb = cb.m.predict(cb._obj(A_check), prediction_type="RawFormulaVal")
    err = float(np.abs(raw_ref - raw_cb).max())
    print(f"  CatBoost: {chk['n_entries']} CTR entries; re-implementation vs CatBoost on "
          f"{len(A_check)} rows: max |raw diff| = {err:.2e}")
    assert err < 1e-9, "CatBoost export does not reproduce CatBoost"
    return {
        "format": "hotel-overbooking-model/1",
        "trained_on": f"arrivals before {START} (train.csv)",
        "members": MEMBERS,
        "stack": {"intercept": float(model.stack_["intercept"]),
                  "coef": dict(zip(MEMBERS, map(float, model.stack_["coef"])))},
        "features": export_features(model),
        "lr": export_lr(lr),
        "lgb": export_lgb(lgb, len(model.fb.columns_)),
        "cb": cbx,
    }


# ---------------------------------------------------------------------------------------------
# live.json
# ---------------------------------------------------------------------------------------------

def week_index(day_idx: int, dow0: int) -> int:
    """Index of the Monday-start week of night `day_idx` (week 0 holds the first replay night)."""
    return (day_idx + dow0) // 7


def export_policy(pol, model, ho) -> dict:
    """Demand forecast parameters (fit on the history at policy creation) + the state at the start
    of the replay. The per-booking history arrays rebuild the relative-rate quantile tables."""
    fc = pol.forecast
    hist = _clean(ho.history)
    shifts = hist.hotel.map(lambda h: pol.shift_for(h)).to_numpy(dtype=float)
    q = 1 - shift_logit(model.predict_frame(hist), shifts)          # exactly as DemandForecast
    h0 = hist.arrival_date.min()
    n_hist = (pol.start - h0).days
    rn = _room_nights(hist, q, h0)
    w_tab = 0.5 ** ((n_hist - np.arange(n_hist)) / 365.0)
    kern = np.ones(2 * fc.hw + 1)
    s = (hist.arrival_date - h0).dt.days.to_numpy()
    n = hist.nights.to_numpy().astype(int)
    bk = (hist.booking_date - h0).dt.days.to_numpy()
    rate = hist.nightly_rate.to_numpy()
    hotels = []
    for h in fc.hotels:
        m = (rn["hotel"] == h) & (rn["night"] >= 0) & (rn["night"] < n_hist) & (rn["rate"] > 0)
        night, qq = rn["night"][m], rn["q"][m]
        T = np.bincount(night, weights=qq, minlength=n_hist)
        R = np.bincount(night, weights=qq * rn["rate"][m], minlength=n_hist)
        Ts, Rs = np.convolve(T, kern, "same"), np.convolve(R, kern, "same")
        P_hist = np.where(Ts > 0, Rs / np.maximum(Ts, 1e-9), np.nan)
        # bookings of this hotel that put at least one priced room-night inside the history
        sel = (hist.hotel.to_numpy() == h) & (rate > 0) & (n > 0) & (s < n_hist)
        lead0 = s[sel] - bk[sel]
        assert (s[sel] >= 0).all() and (lead0 >= 0).all() and (lead0 < 1024).all() and (n[sel] < 64).all()
        cents = np.round(rate[sel] * 100)
        assert np.array_equal(cents / 100, rate[sel])
        pack = s[sel] | (n[sel] << 9) | (lead0 << 15)
        _check_quantiles(fc, h, s[sel], n[sel], lead0, cents / 100, q[sel], P_hist, w_tab, n_hist)
        hotels.append({
            "name": h,
            "cap": enc(pol.load.cap[h], "f64"),
            "F": enc(fc.F[h], "f64"), "rel_mean": [float(x) for x in fc.rel_mean[h]],
            "mu": enc(fc.mu[h], "f64"), "P0": enc(fc.P0[h], "f64"),
            "E0": enc(pol.load.E[h], "f64"), "O0": enc(fc.O[h], "f64"),
            "OR0": enc(fc.OR[h], "f64"), "OL0": enc(fc.OL[h], "f64"),
            "P_hist": enc(P_hist, "f64"),
            "book_pack": enc(pack, "u32"), "book_cents": enc(cents, "u32"), "book_q": enc(q[sel], "f64"),
        })
    return {
        "start": str(pol.start.date()), "n_days": int(pol.load.n_days), "n_hist": int(n_hist),
        "params": {"half_window": fc.hw, "price_weight": fc.price_weight, "growth_horizon": fc.g_h,
                   "growth_min_f": fc.g_minf, "growth_k": fc.g_k, "growth_clip": list(fc.g_clip),
                   "z": pol.z, "bid_scale": pol.bid_scale, "logit_shift": 0.0, "halflife_days": 365.0},
        "lead_edges": [int(x) for x in LEAD_EDGES],
        "w_rec": enc(w_tab, "f64"),
        "hotels": hotels,
    }


def _check_quantiles(fc, h, s, n, lead0, rate, q, P_hist, w_tab, n_hist):
    """Rebuild the relative-rate quantile tables from the exported per-booking arrays (the way
    model.js does it, with a stable sort) and compare with the live DemandForecast."""
    rep = np.repeat(np.arange(len(s)), n)
    off = np.arange(rep.size) - np.repeat(np.cumsum(n) - n, n)
    night = s[rep] + off
    keep = night < n_hist
    night, lead, rt, qq = night[keep], (lead0[rep] + off)[keep], rate[rep][keep], q[rep][keep]
    rel = rt / P_hist[night]
    wq = qq * w_tab[night]
    ok = np.isfinite(rel)
    bucket = _lead_bucket(lead)
    worst = 0.0
    for j in range(len(LEAD_EDGES) - 1):
        sel = ok & (bucket <= j)
        o = np.argsort(rel[sel], kind="stable")
        c = np.cumsum(wq[sel][o])
        rq, rc = rel[sel][o], c / c[-1]
        assert np.array_equal(rq, fc.rel_q[h][j]), "relative rates differ"
        worst = max(worst, float(np.abs(rc - fc.rel_cdf[h][j]).max()))
    print(f"  {h}: quantile tables rebuilt from {len(s)} bookings; max |cdf diff| (tie order) = {worst:.1e}")


def growth_free(fc, h, t):
    """Growth factor at the start of day t without touching the per-day cache of the forecast."""
    saved = fc._g_cache
    fc._g_cache = {}
    g = fc.growth(h, t)
    fc._g_cache = saved
    return g


def quotes(pol, h, t, nights):
    """What the forecast quotes on day t for each night with zero-weight request (the request
    itself is not observed): list of components dicts. The growth cache is left untouched."""
    fc = pol.forecast
    saved = fc._g_cache
    fc._g_cache = {}
    out = [fc.components(h, d, t, pol.load.cap[h][d] - pol.load.E[h][d]) for d in nights]
    fc._g_cache = saved
    return out


def bid_example(pol, ho) -> dict:
    """Methodology 6.3: the bid price of one night on one day, with every quantity behind it."""
    fc = pol.forecast
    h = EXAMPLE["hotel"]
    d = int((pd.Timestamp(EXAMPLE["night"]) - pol.start).days)
    t = int((pd.Timestamp(EXAMPLE["day"]) - pol.start).days)
    free = float(pol.load.cap[h][d] - pol.load.E[h][d])
    c = quotes(pol, h, t, [d])[0]
    j = int(_lead_bucket(c["lead"]))
    rq, rc = fc.rel_q[h][j], fc.rel_cdf[h][j]
    probs = np.linspace(0, 1, 201)
    Q = [float(rq[min(int(np.searchsorted(rc, p)), rq.size - 1)]) for p in probs]
    N = c["N"]
    curve = []
    saved = fc._g_cache
    fc._g_cache = {}
    for f in range(0, int(math.ceil(N)) + 1):
        curve.append(fnum(fc.components(h, d, t, float(f))["bid"]))
    fc._g_cache = saved
    lo, hi = int(LEAD_EDGES[j]), int(LEAD_EDGES[j + 1]) - 1
    return {
        "hotel": h, "night": EXAMPLE["night"], "decided_on": EXAMPLE["day"], "night_index": d, "day_index": t,
        "capacity": float(pol.load.cap[h][d]), "expected_guests": float(pol.load.E[h][d]), "free": free,
        "lead": int(c["lead"]), "F": float(c["F"]), "growth": float(c["growth"]), "mu": float(fc.mu[h][d]),
        "T": float(c["T"]), "N": float(N), "P": float(c["P"]), "P0": float(fc.P0[h][d]),
        "quantile": fnum(c["quantile"]), "bid": fnum(c["bid"]),
        "lead_bucket": j, "lead_bucket_days": [lo, hi],
        "Q": {"probs": [float(p) for p in probs], "rel": Q,
              "note": "Q(p) = rel_q[searchsorted(rel_cdf, p)], the relative rate of the bookings made "
                      "less than `lead` days ahead; bid = P * Q(1 - free / N) when 0 < free < N, "
                      "0 when free >= N, infinite (null) when free <= 0"},
        "bid_by_free": {"free": list(range(0, int(math.ceil(N)) + 1)), "bid": curve},
        "note": "start of the day, before that day's requests; the request itself is not observed",
    }


def export_live(model, ho) -> tuple[dict, dict]:
    hotels = list(ho.capacity)
    n_days = len(ho.days)
    dow0 = int(ho.days[0].dayofweek)
    truth = ho.truth.cancelled
    out, snaps = [], []
    state = {}

    def on_day(t, day, pol):
        if t == 0:
            state["policy"] = export_policy(pol, model, ho)
            state["state0"] = {h: {"capacity": pol.load.cap[h].round(2).tolist(),
                                   "expected": pol.load.E[h].round(3).tolist(),
                                   "commitments": int((ho.commitments.hotel == h).sum())} for h in hotels}
        if day == pd.Timestamp(EXAMPLE["day"]):
            state["bid_example"] = bid_example(pol, ho)
        st = model.stream
        hs = []
        for h in hotels:
            nights = range(t, n_days)
            qs = quotes(pol, h, t, nights)
            w_lo, w_hi = week_index(t, dow0), week_index(n_days - 1, dow0)
            hs.append({
                "growth": r(growth_free(pol.forecast, h, t), 6),
                "bid": [r(c["bid"], 1) for c in qs],
                "free": [r(c["free"], 2) for c in qs],
                "dd": [int(st.demand_date.get((h, ho.days[d]), 0)) for d in nights],
                "w0": w_lo,
                "dw": [int(st.demand_week.get((h, ho.days[0] - pd.Timedelta(days=dow0) + pd.Timedelta(weeks=w)), 0))
                       for w in range(w_lo, w_hi + 1)],
            })
        snaps.append({"day": day.strftime("%Y-%m-%d"), "t": t, "hotels": hs})

    def on_request(b, ok, pol, s):
        L = pol.last
        kind = outcome(L, ok)
        h, s0, e0 = pol.load.span(b)
        rec = {
            "id": int(b["booking_id"]), "hotel": hotels.index(h), "booked": b["booking_date"].strftime("%Y-%m-%d"),
            "arrival": b["arrival_date"].strftime("%Y-%m-%d"), "s": int(s0), "e": int(e0), "nights": int(b["nights"]),
            "wkend": int(b["weekend_nights"]), "rate": r(b["nightly_rate"]), "lead": int(b["days_ahead"]),
            "adults": int(b["adults"]), "children": 0 if pd.isna(b["children"]) else int(b["children"]),
            "babies": int(b["babies"]),
            "kids": int((0 if pd.isna(b["children"]) else b["children"]) + b["babies"]),
            "segment": b["sales_segment"], "channel": b["sales_channel"], "guest": b["guest_type"],
            "meal": b["meal"], "room": b["room_type"], "agent": None if pd.isna(b["agent"]) else int(b["agent"]),
            "company": None if pd.isna(b["company"]) else int(b["company"]),
            "ctx": [int(s[k]) for k in ("block_rank", "loose_rank", "day_agent_count", "demand_date", "demand_week")],
            "p": r(L["p_cancel"], 4), "pe": float(L["p_cancel"]), "bid": r(L["bid"]), "outcome": kind,
            "accepted": ok, "cancelled": int(truth.loc[b["booking_id"]]), "reason": reason(pol, model, b, ok),
        }
        if not L.get("invalid"):
            rec["bids"] = [r(c["bid"], 1) for c in L["nights"]]
            rec["free"] = [r(c["free"], 2) for c in L["nights"]]
            contrib, _ = decompose(model)
            agg: dict[str, float] = {}
            for col, v in zip(model.fb.columns_, contrib):
                agg[label(col)] = agg.get(label(col), 0.0) + float(v)
            top = sorted(agg.items(), key=lambda kv: -abs(kv[1]))[:5]
            rec["drivers"] = [[name, r(v, 3)] for name, v in top]
        out.append(rec)

    pol = replay(model, ho, on_day, on_request)
    reqs = ho.requests[ho.requests.booking_date < RECORD_UNTIL]
    defaults = example_defaults(ho, reqs)
    live = {
        "format": "hotel-overbooking-live/1",
        "meta": {"start": START, "record_until": RECORD_UNTIL, "hotels": hotels,
                 "model": "stack of logistic regression, LightGBM and CatBoost, trained on arrivals before "
                          "1 July 2016",
                 "replay": "requests booked 1 July - 11 August 2016, same-day order random (shuffle_seed 0)"},
        "days": [d.strftime("%Y-%m-%d") for d in ho.days],
        "replay_days": [s_["day"] for s_ in snaps],
        "hotels": hotels,
        "dow0": dow0,
        "state0": state["state0"],
        "policy": state["policy"],
        "requests": out,
        "snapshots": snaps,
        "defaults": defaults,
        "bid_example": state["bid_example"],
    }
    return live, {"pol": pol}


def example_defaults(ho, reqs) -> dict:
    """Typical values per hotel for a default request: modes of the replayed requests, median
    lead time and nights, and last year's median rate per arrival month (history only)."""
    out = {}
    for h in ho.capacity:
        x = reqs[reqs.hotel == h]
        hist = ho.history[(ho.history.hotel == h) & (ho.history.nightly_rate > 0)]
        rate = hist.groupby(hist.arrival_date.dt.month).nightly_rate.median()
        out[h] = {
            "sales_segment": x.sales_segment.mode()[0], "sales_channel": x.sales_channel.mode()[0],
            "guest_type": x.guest_type.mode()[0], "meal": x.meal.mode()[0], "room_type": x.room_type.mode()[0],
            "agent": int(x.agent.mode()[0]), "adults": int(x.adults.median()),
            "nights": int(x.nights.median()), "days_ahead": int(x.days_ahead.median()),
            "rate_by_month": {int(k): round(float(v), 2) for k, v in rate.items()},
        }
    return out


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False), encoding="utf8")
    print(f"  {path.relative_to(ROOT)}: {path.stat().st_size / 1e6:.2f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refit", action="store_true", help="ignore the cached fitted model")
    args = ap.parse_args()
    t0 = time.perf_counter()
    ho = holdout()
    model = fitted_model(ho, refit=args.refit)
    print(f"model ready ({time.perf_counter() - t0:.0f} s)")
    BUILD.mkdir(parents=True, exist_ok=True)
    # every training row, to check the CatBoost re-implementation against CatBoost itself
    A_check = model.fb.to_array(model.fb.transform(model._hist, stream_features(model._hist), oof=True))
    write(BUILD / "model.json", export_model(model, A_check))
    print(f"model.json done ({time.perf_counter() - t0:.0f} s)")
    live, _ = export_live(model, ho)
    write(BUILD / "live.json", live)
    print(f"done in {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
