"""Score the shipped Solution and the two baselines with the organisers' evaluator on the 2017 hold-out.

    python evaluation/run.py                  # model, no_overbooking, average_rate
    python evaluation/run.py model            # only the shipped model

`evaluate.py` and `test.csv` are the organisers' files, unchanged. The evaluator reads `train.csv` and
`test.csv` from the current directory, so the run happens in a temporary folder holding copies of both.
This is an evaluation only: nothing here trains, chooses or tunes anything. The `model` row of `results.csv`
is the shipped solution (`models/final.joblib`, hashes in `freeze_manifest.json`). Each run is compared with `results.csv`.
"""
from __future__ import annotations

import contextlib
import csv
import io
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE)]

from evaluate import evaluate  # noqa: E402  (the organisers' function)
from solution import Solution  # noqa: E402
from src.baselines import ExpectedShows, LoadLimit  # noqa: E402
from src.simulator import TRAIN_CSV, load_train  # noqa: E402


class NoOverbooking(LoadLimit):
    """Accept only up to the free rooms."""

    def __init__(self, commitments, capacity):
        super().__init__(commitments, capacity, factor=1.0)


class AverageRate(ExpectedShows):
    """Classic overbooking: each booking counts as the hotel's average show rate."""

    def __init__(self, commitments, capacity):
        super().__init__(commitments, capacity, history=load_train())


SOLUTIONS = {"model": Solution, "no_overbooking": NoOverbooking, "average_rate": AverageRate}


def recorded() -> dict[str, float]:
    with open(HERE / "results.csv", newline="", encoding="utf-8") as f:
        return {r["solution"]: float(r["net_revenue_eur"]) for r in csv.DictReader(f)}


def main(names: list[str]) -> None:
    reference = recorded()
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(TRAIN_CSV, tmp)
        shutil.copy(HERE / "test.csv", tmp)
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            for name in names:
                out, t0 = io.StringIO(), time.perf_counter()
                with contextlib.redirect_stdout(out):
                    evaluate(SOLUTIONS[name])
                net = float(re.search(r"EUR ([\d,]+)", out.getvalue()).group(1).replace(",", ""))
                check = "matches results.csv" if round(net) == round(reference.get(name, -1)) else \
                    f"results.csv: EUR {reference.get(name, float('nan')):,.0f}"
                print(f"{name:16s} net revenue EUR {net:>11,.0f}   ({time.perf_counter() - t0:.0f} s, {check})")
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    main(sys.argv[1:] or list(SOLUTIONS))
