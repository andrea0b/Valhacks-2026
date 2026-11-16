"""What the final model uses: global importance from the exact additive decomposition.

For 1,500 random requests booked in 2016 the final logit of models/final.joblib is split into
per-column contributions (src.explain.decompose). Importance = mean |contribution|; share = its
fraction of the total. The same rows are also decomposed member by member, to show how the stack
weights turn into per-input weights. The model was trained on all of train.csv, so these rows are
in-sample: this describes what the model relies on, not how well it predicts.

Outputs: results/06_feature_importance.csv, results/06_member_importance.csv,
         results/06_additivity.json
Run: python experiments/06_feature_importance.py      (~3 minutes)
"""
import json

import joblib
import numpy as np
import pandas as pd

from common import RESULTS, ROOT
from src.explain import check_additivity, decompose, label, member_contributions, theme
from src.features import stream_features
from src.simulator import load_train

N, SEED = 1500, 0
MEMBERS = ["lr", "lgb", "cb"]

if __name__ == "__main__":
    model = joblib.load(ROOT / "models" / "final.joblib")["model"]
    df = load_train()
    st = stream_features(df.drop(columns=["cancelled", "value"]))
    idx = df[df.booking_date.dt.year == 2016].sample(N, random_state=SEED).index
    A = model.fb.to_array(model.fb.transform(df.loc[idx], st.loc[idx]))
    cols = model.fb.columns_
    w = np.array(model.stack_["coef"])
    total = np.zeros((N, len(cols)))
    per_member = np.zeros((len(MEMBERS), N, len(cols)))
    errors = []
    for i in range(N):
        row = A[i:i + 1]
        total[i], _ = decompose(model, row)
        for k, e in enumerate(model.sets_[-1]):
            per_member[k, i], _ = member_contributions(e, row, model.fb)
        if i < 50:
            errors.append(check_additivity(model, row))
    imp = pd.DataFrame({"column": cols, "label": [label(c) for c in cols], "theme": [theme(c) for c in cols],
                        "mean_abs": np.abs(total).mean(0)})
    imp["share"] = imp.mean_abs / imp.mean_abs.sum()
    imp.sort_values("mean_abs", ascending=False).to_csv(RESULTS / "06_feature_importance.csv", index=False)
    rows = [{"member": m, "weight": w[k], "column": c, "label": label(c),
             "mean_abs": np.abs(per_member[k, :, j]).mean(),
             "mean_abs_weighted": np.abs(w[k] * per_member[k, :, j]).mean()}
            for k, m in enumerate(MEMBERS) for j, c in enumerate(cols)]
    pd.DataFrame(rows).to_csv(RESULTS / "06_member_importance.csv", index=False)
    json.dump({"rows_checked": len(errors), "max_abs_error": float(max(errors)),
               "stack_weights": dict(zip(MEMBERS, w.tolist())), "stack_intercept": model.stack_["intercept"]},
              open(RESULTS / "06_additivity.json", "w"), indent=1)
    print(imp.groupby("theme").share.sum().sort_values(ascending=False).round(3))
