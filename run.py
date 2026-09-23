#!/usr/bin/env python3
"""Single entry point for the whole pipeline (guideline.md §2, §5).

    python run.py                                  # uses the defaults below
    python run.py --data data --out outputs --config config.yaml

No manual steps, no notebooks, no network access.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make src/ importable without an install step, so `python run.py` works on a
# clean checkout after nothing more than `pip install -r requirements.txt`.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from moneygraph.pipeline import run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Money Graph — full pipeline")
    ap.add_argument("--data", default="data", help="folder with the parquet files")
    ap.add_argument("--out", default="outputs", help="where to write the CSVs")
    ap.add_argument("--config", default="config.yaml", help="thresholds and weights")
    a = ap.parse_args()
    return run(a.data, a.out, a.config)


if __name__ == "__main__":
    raise SystemExit(main())
