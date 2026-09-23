#!/usr/bin/env python3
"""Single entry point (brief must-have 1, guideline §2).

    python run.py                                        # defaults below
    python run.py --data data --out output_files --config config.yaml
    python run.py --only-profile                         # data profiling only
    python run.py --recalibrate                          # re-run the calibrator agent
    MONEYGRAPH_NO_LLM=1 python run.py                    # fully offline, no agents

One command, no manual steps, no notebook. The run must finish inside the
5-minute budget from the brief; `pipeline.run` asserts against it and the
timing of every stage lands in output_files/run_trace.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from moneygraph.io import load_config      # noqa: E402
from moneygraph.pipeline import run        # noqa: E402


def main() -> int:
    cfg_default = str(ROOT / "config.yaml")
    ap = argparse.ArgumentParser(description="Money Graph — full pipeline")
    ap.add_argument("--config", default=cfg_default, help="thresholds and weights")
    ap.add_argument("--data", default=None,
                    help="folder of input files (default: config paths.data)")
    ap.add_argument("--out", default=None,
                    help="where deliverables are written (default: config paths.outputs)")
    ap.add_argument("--only-profile", action="store_true",
                    help="stop after the data profile report")
    ap.add_argument("--recalibrate", action="store_true",
                    help="re-run the calibrator agent instead of reusing "
                         "config.calibrated.yaml")
    a = ap.parse_args()

    cfg = load_config(a.config)
    data = a.data or cfg["paths"]["data"]
    out = a.out or cfg["paths"]["outputs"]
    return run(data, out, a.config, only_profile=a.only_profile,
               recalibrate=a.recalibrate)


if __name__ == "__main__":
    raise SystemExit(main())
