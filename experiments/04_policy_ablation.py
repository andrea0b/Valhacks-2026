"""Policy variants on the 2016 replay (H1, H2, FY; 3 within-day orders), with the LR model at shift 0.

base           the bid-price rule as delivered
displaceK      on a night full in expectation, price the walk at K x P(full) x cheapest seated rate
               instead of refusing
z0.5           safety margin: expected shows + 0.5 standard deviations must fit
bidX           bid price multiplied by X
Run: python experiments/04_policy_ablation.py      (writes results/04_policy_ablation.csv)
"""
from joblib import Parallel, delayed
import pandas as pd

from common import RESULTS, WINDOWS, run_config, StreamCancelModel

VARIANTS = {
    "base": {},
    "displace3.5": {"displace_k": 3.5},
    "displace2.5": {"displace_k": 2.5},
    "displace5": {"displace_k": 5.0},
    "z0.5": {"z": 0.5},
    "bid0.9": {"bid_scale": 0.9},
    "bid1.1": {"bid_scale": 1.1},
    "bid0.9+displace3.5": {"bid_scale": 0.9, "displace_k": 3.5},
}


def job(name, window):
    return run_config(name, lambda: StreamCancelModel("lr"), window, seeds=(0, 1, 2), shifts=(0.0,),
                      policy_kw=VARIANTS[name])


if __name__ == "__main__":
    res = Parallel(n_jobs=8)(delayed(job)(n, w) for n in VARIANTS for w in WINDOWS)
    pd.DataFrame([r for rs in res for r in rs]).to_csv(RESULTS / "04_policy_ablation.csv", index=False)
