# Evaluation

The organisers' evaluator and the 2017 test requests, with the result of the shipped solution (stack of
LR + LightGBM + CatBoost, `models/final.joblib`) and of the two baselines.

The 2017 data are used for reporting only. The model, the policy and the recipe were chosen on the 2016
replay and the temporal walk-forward (`experiments/`, `docs/methodology.md`); nothing was trained, chosen
or tuned on 2017, and the evaluator is run on the solution as it is. The figures below are what the
organisers' evaluator prints when run locally on this repository: they are not a score announced by the
organisers.

| File | What |
|---|---|
| `evaluate.py`, `test.csv` | The organisers' kit, unchanged. `evaluate(Solution)` replays the 2017 requests in booking-date order and prints the net revenue. |
| `run.py` | Runs the evaluator on the shipped `Solution` and on the two baselines, in a temporary folder holding copies of `train.csv` and `test.csv`, and compares each run with `results.csv`. |
| `results.csv` | Net revenue of the three runs, with the time of the run. |
| `freeze_manifest.json`, `freeze.py` | SHA-256 of the shipped solution (`solution.py`, `models/final.joblib`, `src/`, `requirements.txt`), the package versions and the time the manifest was written (`python evaluation/freeze.py` writes it). A fingerprint of the solution, not proof of when it was made. |

## Result

| Solution | Net revenue, 2017 |
|---|---|
| No overbooking (accept up to the free rooms) | 3,149,034 € |
| Classic overbooking (the hotel's average show rate) | 4,193,263 € |
| **Shipped system** (stack of three models + bid price per night) | **5,425,157 €** |

+29.4% over classic overbooking, +72.3% over no overbooking. The run handled 26,439 requests and
accepted 12,069 (14,104 confirmed commitments are not decided); initialisation took 7.2 s and a
decision about 2.1 ms.

## Reproduce

```bash
python evaluation/run.py            # model, no_overbooking, average_rate
python evaluation/run.py model      # only the shipped solution
```

Each line ends with "matches results.csv" when the net revenue equals the recorded one.
The shipped model is `models/final.joblib`; its hash is in `freeze_manifest.json`.

## What the evaluator does not tell

It prints only the net revenue: there is no figure for walked guests or occupancy, and a
"perfect foresight" bound would need the 2017 outcomes, which the kit does not contain. The 2016 replay in
`src/simulator.py` is the local stand-in; the two differ in the year and in the order of same-day requests
(the evaluator uses `booking_id`, which leaks the outcome, so no feature may rely on it).
