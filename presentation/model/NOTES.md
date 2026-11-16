# The model in the browser

`model.js` runs the shipped cancellation model (stack of logistic regression, LightGBM and CatBoost)
and the start-of-day bid-price check in plain JavaScript, so the presentation can score a request you type
without a server. This is the port, the checks that compare it with Python, and where it differs.

## Files

| File | Role |
|---|---|
| `export.py` | Writes `build/model.json` (the model) and `build/live.json` (the 1 Jul - 11 Aug 2016 replay with every decision, plus start-of-day bid prices and free rooms). The model is trained on arrivals before 1 July 2016 only. About 7 min the first time (the fitted model is cached in the temp folder). |
| `model.js` | Features, the three members, the stack, per-input contributions, and the decision from the snapshots. |
| `parity.py` | Re-runs the replay in Python and dumps its numbers (features, member logits, probability, contributions, outcome) to `<temp>/valhacks-presentation/parity.json`. About 7 min. |
| `parity.mjs` | Compares `model.js` with that dump. `node presentation/model/parity.mjs` (add `--n 200` for a quick run). |

## What matches Python

Checked on the 3,761 requests of the replay (`node presentation/model/parity.mjs`):

| Quantity | Max difference |
|---|---|
| The 36 model inputs of every request, built from the raw request | 9e-16 |
| Logit of each member (LR, LightGBM, CatBoost) | 7e-15 |
| P(cancel) of the stack | 2e-16 |
| Contributions of LR and LightGBM (TreeSHAP) | 4e-16 |
| Sum of contributions + constant against the logit | 1e-14 |
| Outcome of the first request of each of the 42 days (start-of-day state) | 42 of 42 agree |
| Bid prices of the snapshots | 0.05 EUR (stored to 0.1) |

Speed: about 0.2 ms to score a request, 6 ms to explain it.

## What differs

* **CatBoost contributions.** They are an exact additive split of CatBoost's output over the same feature
  classes (a split on a combination of inputs is one player, its share split equally between the inputs),
  but they are not the numbers CatBoost's own `ShapValues` returns. Per input they differ by up to 0.26 logit for
  CatBoost alone and 0.07 logit in the stack. The top driver has the same label as Python for 65% of the
  requests, and Python's top three are all among the JS top three for 94%. The replay console shows the Python
  drivers (exact); the request box shows the JS ones.
* **Decision of a typed request.** It uses the snapshot of the chosen day (bid price and free rooms of every
  night at the start of the day). Python also records the request itself in the demand forecast before pricing it,
  and earlier requests of the same day change the state; both effects are tiny for the first request of a day
  and are not modelled. Stream features of a typed request are the defaults of a new request (no identical request
  seen), with the demand counters of the snapshot.
* **Policy parameters.** The forecast is not ported: `live.json` carries its outputs (snapshots), not its
  internals. `export.py` also writes the forecast parameters under `policy`; the page does not embed them.
