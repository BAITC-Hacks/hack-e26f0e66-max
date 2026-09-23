"""Calibrator agent — chooses the role thresholds and writes its reasoning.

This is where the agent layer earns its place. Picking "at least 5 distinct
payers" is a judgement call: it has to sit far enough into the tail to mean
something, be a round number an analyst can defend out loud, and not collapse
the role space. That is reasoning over a distribution, not arithmetic — and it
is exactly what the jury asks about when they say "explain why this gid got
this role".

Crucially, this stays inside the brief's ban on black boxes. The agent does not
touch a single node. It proposes numbers; `roles.py` still decides every role by
comparing a metric to a threshold, and the jury still sees a formal rule. What
the agent adds is a written rationale for the number, saved next to it.

Three guardrails:

1. **Simulation before acceptance.** Every proposal is applied to the real
   distribution and the resulting role counts are computed. A proposal that
   empties a role, or hands one role more than half the graph, is rejected.
2. **Bounds.** Each threshold has a legal range derived from the data's own
   percentiles; a proposal outside it never reaches the simulation.
3. **Persistence.** The accepted result is written to `config.calibrated.yaml`
   and reused on later runs, so the submitted artifact is reproducible. Pass
   `--recalibrate` to run the agent again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .base import WORDING_RULES, Agent

CALIBRATED_FILE = "config.calibrated.yaml"

# Every threshold the agent may set, with the legal range it must stay inside.
# Ranges are expressed against the data's own distribution, so they rescale
# with the input rather than encoding anything about this particular export.
TUNABLE = {
    "consolidator.min_payers": {"kind": "int", "metric": "in_deg",
                                "lo_pct": 0.90, "hi_pct": 0.995},
    "consolidator.strong_payers": {"kind": "int", "metric": "in_deg",
                                   "lo_pct": 0.98, "hi_pct": 1.0},
    "distributor.min_recipients": {"kind": "int", "metric": "out_deg",
                                   "lo_pct": 0.90, "hi_pct": 0.995},
    "distributor.strong_recipients": {"kind": "int", "metric": "out_deg",
                                      "lo_pct": 0.98, "hi_pct": 1.0},
    "distributor.fan_ratio": {"kind": "num", "lo": 1.5, "hi": 6},
    "transit.ratio_low": {"kind": "num", "lo": 0.5, "hi": 0.95},
    "transit.ratio_high": {"kind": "num", "lo": 1.05, "hi": 1.6},
    "terminal.max_pass": {"kind": "num", "lo": 0.01, "hi": 0.3},
    "coordinator.min_key_payers": {"kind": "int", "lo": 1, "hi": 6},
    "coordinator.min_seed_reach": {"kind": "int", "metric": "seed_reach",
                                   "lo_pct": 0.80, "hi_pct": 0.99},
}

SYSTEM = f"""You are a financial-crime data analyst calibrating the thresholds of a rule engine that assigns roles in a money-transfer network.

You are given the real distribution of every metric (percentiles, min, max) and the meaning of each role. Choose thresholds and justify each one.

What a good threshold looks like:
- It sits in the tail, so the role means "unusual", not "has more than one counterparty".
- It is a ROUND number a person can defend aloud: 5, 10, 25, 50. Never 4.7 or 11.3.
- It is justified by a percentile of the actual distribution, which you must name.
- It leaves every role populated but none dominant. A role with 0 nodes is a dead rule; a role with half the graph is not a finding.

You will be told the legal range for each threshold. Stay inside it.

Answer with JSON only:
{{"thresholds": {{"<dotted.key>": <number>, ...}},
  "rationale": {{"<dotted.key>": "<one sentence naming the percentile and the effect>", ...}},
  "expected_concerns": ["<anything you expect to look wrong, and why it is acceptable>"]}}

{WORDING_RULES}"""


class CalibratorAgent(Agent):
    name = "calibrator"
    role = "choose role thresholds from the observed distributions"
    system = SYSTEM

    def build_task(self, context: dict) -> str:
        return json.dumps({
            "n_nodes": context["n_nodes"],
            "max_depth": context["max_depth"],
            "distributions": context["distributions"],
            "role_definitions": {
                "consolidator": "receives from many distinct payers; min_payers is "
                                "the gate, strong_payers is where confidence reaches 1",
                "distributor": "pays many distinct recipients AND fans out far more "
                               "than it takes in (fan_ratio x in_deg)",
                "transit": "money in is close to money out; ratio_low..ratio_high "
                           "is the band around 1.0",
                "terminal": "money arrives and stays; max_pass is the largest share "
                            "that may leave. Never applied at max traversal depth.",
                "coordinator": "money from several collector accounts and many "
                               "separate seed chains converges here",
            },
            "current_thresholds": context["current"],
            "legal_ranges": context["ranges"],
            "counts_at_current_thresholds": context["current_counts"],
            "note": "Nodes at max traversal depth had their onward flow truncated, "
                    "so most leaves trivially satisfy a low terminal threshold. "
                    "Account for that.",
        }, ensure_ascii=False, indent=2, default=str)

    def validate(self, output: Any, context: dict) -> tuple[bool, str]:
        if not isinstance(output, dict) or not isinstance(output.get("thresholds"), dict):
            return False, "no thresholds object"
        proposed, ranges = output["thresholds"], context["ranges"]

        for key, value in proposed.items():
            if key not in TUNABLE:
                return False, f"'{key}' is not a tunable threshold"
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False, f"'{key}' is not a number"
            lo, hi = ranges[key]["lo"], ranges[key]["hi"]
            if not (lo <= value <= hi):
                return False, f"'{key}'={value} outside the legal range [{lo}, {hi}]"
            if TUNABLE[key]["kind"] == "int" and float(value) != int(value):
                return False, f"'{key}'={value} must be a whole number"

        rationale = output.get("rationale") or {}
        missing = [k for k in proposed if not str(rationale.get(k, "")).strip()]
        if missing:
            return False, f"no rationale given for {missing}"

        merged = _merge(context["current"], proposed)
        if merged["consolidator"]["strong_payers"] <= merged["consolidator"]["min_payers"]:
            return False, "strong_payers must exceed min_payers"
        if merged["distributor"]["strong_recipients"] <= merged["distributor"]["min_recipients"]:
            return False, "strong_recipients must exceed min_recipients"
        if merged["transit"]["ratio_low"] >= merged["transit"]["ratio_high"]:
            return False, "ratio_low must be below ratio_high"

        # The decisive check: what do these thresholds actually do to the graph?
        counts = simulate_counts(context["features"], merged, context["max_depth"])
        n = context["n_nodes"]
        for role in ("consolidator", "distributor", "transit"):
            if counts.get(role, 0) == 0:
                return False, f"thresholds leave `{role}` empty ({counts})"
        for role, count in counts.items():
            if role not in ("peripheral", "cutoff", "terminal") and count > 0.5 * n:
                return False, f"`{role}` would claim {count}/{n} nodes ({counts})"
        output["simulated_counts"] = counts
        return True, "ok"

    def fallback(self, context: dict) -> Any:
        """The hand-set thresholds from config.yaml, which are themselves derived
        from the percentiles in the profile report."""
        return {
            "thresholds": {},
            "rationale": {},
            "source": "config.yaml defaults (percentile-derived, no agent involved)",
            "simulated_counts": context["current_counts"],
        }


# ---------------------------------------------------------------------------
# simulation — the same gates roles.py uses, counted without assigning anything
# ---------------------------------------------------------------------------

def simulate_counts(f: pd.DataFrame, rc: dict, max_depth: int) -> dict[str, int]:
    """Role counts under a candidate threshold set, in precedence order.

    Deliberately reuses the same comparisons as `roles.py` so a proposal is
    judged by what it would really do, not by an approximation of it.
    """
    cons = f["in_deg"] >= rc["consolidator"]["min_payers"]
    dist = ((f["out_deg"] >= rc["distributor"]["min_recipients"])
            & (f["out_deg"] >= rc["distributor"]["fan_ratio"] * f["in_deg"].clip(lower=1)))
    ratio = f["pass_ratio"]
    transit = (f["inflow_reliable"] & f["outflow_observed"] & ratio.notna()
               & ratio.between(rc["transit"]["ratio_low"], rc["transit"]["ratio_high"])
               & (f["in_deg"] < rc["consolidator"]["min_payers"])
               & (f["out_deg"] < rc["distributor"]["min_recipients"]))
    terminal = (f["outflow_observed"] & (f["in_sum"] > 0)
                & (f["out_sum"] <= rc["terminal"]["max_pass"] * f["in_sum"]))

    seed = f["is_seed"]
    transit &= ~seed
    terminal &= ~seed

    role = np.select(
        [cons, dist, transit, terminal, f["depth"] == max_depth],
        ["consolidator", "distributor", "transit", "terminal", "cutoff"],
        default="peripheral")
    counts = pd.Series(role).value_counts().to_dict()
    return {k: int(v) for k, v in counts.items()}


def build_context(features: pd.DataFrame, cfg: dict, max_depth: int) -> dict:
    """Distributions, current thresholds and the legal range for each."""
    pcts = [0.5, 0.75, 0.9, 0.95, 0.99]
    metrics = ["in_deg", "out_deg", "in_sum", "out_sum", "pass_ratio", "seed_reach"]
    distributions = {}
    for m in metrics:
        s = pd.to_numeric(features[m], errors="coerce")
        distributions[m] = {
            "n_nonzero": int((s.fillna(0) > 0).sum()),
            "min": _num(s.min()), "max": _num(s.max()),
            **{f"p{int(p * 100)}": _num(s.quantile(p)) for p in pcts},
        }

    current = {k: dict(v) for k, v in cfg["roles"].items() if isinstance(v, dict)}
    ranges = {}
    for key, spec in TUNABLE.items():
        if "metric" in spec:
            s = pd.to_numeric(features[spec["metric"]], errors="coerce")
            lo = float(s.quantile(spec["lo_pct"]))
            hi = float(s.quantile(spec["hi_pct"]))
            lo, hi = max(1, int(np.floor(lo))), max(2, int(np.ceil(hi)))
            if hi <= lo:
                hi = lo + 1
        else:
            lo, hi = spec["lo"], spec["hi"]
        ranges[key] = {"lo": lo, "hi": hi}

    return {
        "n_nodes": int(len(features)),
        "max_depth": int(max_depth),
        "features": features,
        "distributions": distributions,
        "current": current,
        "ranges": ranges,
        "current_counts": simulate_counts(features, current, max_depth),
    }


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else round(f, 4)


def _merge(current: dict, proposed: dict) -> dict:
    out = {k: dict(v) for k, v in current.items()}
    for dotted, value in proposed.items():
        section, key = dotted.split(".", 1)
        out.setdefault(section, {})[key] = value
    return out


# ---------------------------------------------------------------------------
# persistence — what makes an agent-calibrated pipeline reproducible
# ---------------------------------------------------------------------------

def load_calibration(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if data.get("thresholds") else None


def save_calibration(result: dict, path: str | Path, model: str) -> None:
    """Written next to config.yaml and committed with the submission, so the
    jury's run reproduces the numbers the agent chose."""
    path = Path(path)
    payload = {
        "_comment": (
            "Generated by the calibrator agent from the observed distributions. "
            "Committed so that `python run.py` reproduces exactly these thresholds. "
            "Delete this file, or pass --recalibrate, to run the agent again. "
            "Each threshold's rationale is below and is reproduced in the README."),
        "_model": model,
        "thresholds": result.get("thresholds", {}),
        "rationale": result.get("rationale", {}),
        "simulated_counts": result.get("simulated_counts", {}),
        "expected_concerns": result.get("expected_concerns", []),
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")


def apply_calibration(cfg: dict, calibration: dict) -> dict:
    """Overlay the agent's thresholds onto the config for this run."""
    cfg = json.loads(json.dumps(cfg))          # deep copy, config is plain data
    for dotted, value in (calibration.get("thresholds") or {}).items():
        section, key = dotted.split(".", 1)
        if section in cfg["roles"] and isinstance(cfg["roles"][section], dict):
            cfg["roles"][section][key] = value
    cfg["_calibration"] = calibration
    return cfg
