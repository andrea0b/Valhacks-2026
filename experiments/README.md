# Experiments

Scripts behind every table and figure of notebooks 07–09. All of them use `train.csv` only: model
metrics on the temporal walk-forward cuts, revenue on the local replay of 2016
(`src/simulator.py`). Outputs are written to `results/` and versioned, so the notebooks run without
re-running the long grids.

| Script | What it measures | Output | Runtime |
|---|---|---|---|
| `01_walk_forward_metrics.py` | log-loss, AUC, Brier, calibration of LR / LightGBM / CatBoost / EBM / average / stack at three cuts; feature-set and recency ablations; random CV vs temporal | `01_*.csv` | ~15 min |
| `02_recipe_grid.py` | revenue of 14 model recipes on H1 and H2, 3 within-day orders × 4 logit shifts | `02_recipe_grid.csv` | ~1 h |
| `03_finalists.py` | finalists on H1, H2 and the full year, temporal stacking, fine shift grid | `03_finalists.csv` | ~1 h |
| `04_policy_ablation.py` | policy variants: safety margin, bid-price scale, walk pricing | `04_policy_ablation.csv` | ~30 min |
| `05_decision_trace.py` | every H2 decision of the shipped recipe (probability, bid price, outcome, top factors); per-night occupancy of the full year | `05_*.csv`, `05_summary.json` | ~10 min |
| `06_feature_importance.py` | global importance from the exact decomposition of `models/final.joblib` | `06_*.csv`, `06_additivity.json` | ~3 min |

`common.py` holds the shared replay runner. Run any script from the repository root, e.g.
`python experiments/01_walk_forward_metrics.py`.
