"""Full trace of the final recipe (stack of LR + LightGBM + CatBoost, shift 0) on the 2016 replay, for the policy notebook.

H2  model trained on arrivals before 2016-07-01, replay of every H2 request. For each request it
    records the model's probability, the bid price, the free rooms, which check decided and the
    three inputs that moved the cancellation forecast most (exact decomposition, src/explain.py).
FY  model trained on arrivals before 2016-01-01, replay of the whole of 2016; per-night occupancy
    after check-in (seated guests, walks, revenue).

Outputs: results/05_decisions_H2.csv, results/05_nights_FY.csv, results/05_summary.json
Run: python experiments/05_decision_trace.py      (~10 minutes)
"""
import json

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from common import RESULTS, WINDOWS
from src.explain import drivers, outcome
from src.policy import BidPricePolicy
from src.simulator import ROOMS, build_holdout, check_in, load_train, score
from src.stream_model import StreamCancelModel

MEMBERS = ["lr", "lgb", "cb"]


def job(window):
    df = load_train()
    ho = build_holdout(df, **WINDOWS[window])
    model = StreamCancelModel(MEMBERS, stack=True).fit(ho.history, as_of=ho.days[0])
    model.start_session(ho.commitments)
    pol = BidPricePolicy(ho.commitments.copy(), {h: c.copy() for h, c in ho.capacity.items()},
                         history=ho.history, model=model, logit_shift=0.0)
    acc, rec = [], []
    for b in ho.requests.to_dict("records"):
        ok = bool(pol.decide(b))
        acc.append(ok)
        if window == "H2":
            L = pol.last
            n0 = L["nights"][0] if L.get("nights") else {}
            drv = drivers(model) if not L.get("invalid") else []
            rec.append({"booking_id": b["booking_id"], "hotel": b["hotel"], "booking_date": b["booking_date"],
                        "arrival_date": b["arrival_date"], "nights": b["nights"], "rate": b["nightly_rate"],
                        "segment": b["sales_segment"], "p_cancel": L["p_cancel"], "bid": L["bid"],
                        "free_min": min((c["free"] for c in L.get("nights", [])), default=np.nan),
                        "demand_to_come": n0.get("N", np.nan), "booked_share": n0.get("F", np.nan),
                        "growth": n0.get("growth", np.nan), "price_level": n0.get("P", np.nan),
                        "outcome": outcome(L, ok), "accepted": ok,
                        **{f"driver{i + 1}": n for i, (n, _) in enumerate(drv)},
                        **{f"driver{i + 1}_logit": v for i, (_, v) in enumerate(drv)}})
    acc = np.array(acc)
    s = score(ho, acc)
    cap_nights = sum(float(c.sum()) for c in ho.capacity.values())
    occupied = cap_nights - float(s.empty_room_nights.sum())
    summary = {"window": window, "net": float(s.net.sum()), "revenue": float(s.revenue.sum()),
               "walk": int(s.walk.sum()), "penalty": float(s.penalties.sum()), "accepted": int(s.accepted.sum()),
               "requests": int(s.requests.sum()), "occupancy": occupied / cap_nights,
               "revenue_per_occupied_room_night": float(s.revenue.sum()) / occupied,
               "net_per_hotel": {r.hotel: float(r.net) for r in s.itertuples()},
               "stack_weights": dict(zip(MEMBERS, model.stack_["coef"])), "stack_intercept": model.stack_["intercept"]}
    if window == "H2":
        t = pd.DataFrame(rec)
        t["cancelled"] = ho.truth.loc[t.booking_id, "cancelled"].to_numpy()
        t.to_csv(RESULTS / "05_decisions_H2.csv", index=False)
    else:
        g = check_in(ho, acc)
        rows = []
        for h in ROOMS:
            x = g[g.hotel == h]
            seated, walked, rev = (np.zeros(len(ho.days)) for _ in range(3))
            for st, en, ok_, v in zip(x.start, x.end, x.seated, x.value):
                if ok_:
                    seated[st:en] += 1
                    rev[st:en] += v / max(en - st, 1)
                else:
                    walked[st] += 1
            rows.append(pd.DataFrame({"hotel": h, "night": ho.days, "capacity": ho.capacity[h].to_numpy(),
                                      "seated": seated, "walked_arrivals": walked, "revenue": rev}))
        pd.concat(rows).to_csv(RESULTS / "05_nights_FY.csv", index=False)
    return summary


if __name__ == "__main__":
    out = Parallel(n_jobs=2)(delayed(job)(w) for w in ("H2", "FY"))
    json.dump({s["window"]: s for s in out}, open(RESULTS / "05_summary.json", "w"), indent=1)
    print(out)
