"""Write freeze_manifest.json: SHA-256 of the files that make up the shipped solution.

    python evaluation/freeze.py

The manifest records what the evaluator ran on (solution.py, the trained model, src/, requirements.txt), the
package versions and the time it was written. It is a fingerprint of the solution, not a proof of when it was made.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ["pandas", "numpy", "scikit-learn", "lightgbm", "catboost", "joblib"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    files = ["solution.py", "models/final.joblib", "requirements.txt"] + sorted(
        p.relative_to(ROOT).as_posix() for p in (ROOT / "src").glob("*.py"))
    manifest = {
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "python": sys.version.split()[0],
        "packages": {p: metadata.version(p) for p in PACKAGES},
        "files": {f: sha256(ROOT / f) for f in files},
    }
    (Path(__file__).resolve().parent / "freeze_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
