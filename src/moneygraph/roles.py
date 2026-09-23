"""The rule engine (guideline §8, brief must-have 3).

This module is the only thing in the repository that decides a role. It is
deliberately boring: a fixed list of gates, each a comparison between one
metric and one threshold from `config.yaml`, applied in a fixed precedence
order. No model, no fitting, no learned weights.

Every decision emits a `RuleTrace` recording the gate that fired, the exact
metric values it compared, the thresholds it compared them against, and every
penalty applied to the score. Two things depend on that trace:

* `evidence.py` may only quote numbers that appear in it, so the explanation
  can never contradict the logic that produced the role;
* the viewer shows it verbatim, which is how the jury's "name three gids and
  explain them" check is answered in seconds rather than minutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

ROLE_PRECEDENCE = ["coordinator", "consolidator", "distributor",
                   "transit", "terminal", "cutoff", "peripheral"]
BASE_ROLES = ["consolidator", "distributor", "transit", "terminal"]
KEY_ROLES = {"consolidator", "distributor", "transit"}


@dataclass
class RuleTrace:
    """Why one node got one role. Serialized into node_features.parquet."""

    gid: int
    role: str = "peripheral"
    role_score: float = 0.0
    gate: str = ""                                   # the rule that fired
    metrics: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    penalties: list[str] = field(default_factory=list)
    secondary_roles: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gid": int(self.gid), "role": self.role,
            "role_score": round(float(self.role_score), 4),
            "gate": self.gate,
            "metrics": {k: _clean(v) for k, v in self.metrics.items()},
            "thresholds": {k: _clean(v) for k, v in self.thresholds.items()},
            "penalties": self.penalties,
            "secondary_roles": self.secondary_roles,
            "notes": self.notes,
        }


def _clean(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if np.isnan(f) else round(f, 4)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    return v


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def _gate_consolidator(row, rc) -> tuple[bool, dict, dict]:
    """Collection is visible from the inflow side alone, so this gate is allowed
    at any depth — including MAX_DEPTH, where the onward flow is unknown."""
    t = rc["consolidator"]
    m = {"in_deg": row.in_deg, "seed_in_deg": row.seed_in_deg, "in_sum": row.in_sum}
    th = {"min_payers": t["min_payers"], "strong_payers": t["strong_payers"]}
    return bool(row.in_deg >= t["min_payers"]), m, th


def _gate_distributor(row, rc) -> tuple[bool, dict, dict]:
    """Fan-out must dominate fan-in, otherwise a busy hub that both collects and
    pays out would be filed as a distributor."""
    t = rc["distributor"]
    m = {"out_deg": row.out_deg, "in_deg": row.in_deg, "out_sum": row.out_sum}
    th = {"min_recipients": t["min_recipients"], "fan_ratio": t["fan_ratio"],
          "strong_recipients": t["strong_recipients"]}
    ok = (row.out_deg >= t["min_recipients"]
          and row.out_deg >= t["fan_ratio"] * max(row.in_deg, 1))
    return bool(ok), m, th


def _gate_transit(row, rc) -> tuple[bool, dict, dict]:
    """Money in ~= money out, on a node that is neither a collection point nor a
    fan-out. Requires both sides of the ratio to be trustworthy."""
    t = rc["transit"]
    cons_min = rc["consolidator"]["min_payers"]
    dist_min = rc["distributor"]["min_recipients"]
    m = {"pass_ratio": row.pass_ratio, "in_sum": row.in_sum, "out_sum": row.out_sum,
         "in_deg": row.in_deg, "out_deg": row.out_deg,
         "fast_pass_share": getattr(row, "fast_pass_share", np.nan),
         "median_lag_days": getattr(row, "median_lag_days", np.nan)}
    th = {"ratio_low": t["ratio_low"], "ratio_high": t["ratio_high"],
          "max_lag_days": t["max_lag_days"],
          "below_consolidator_payers": cons_min, "below_distributor_recipients": dist_min}
    ratio = row.pass_ratio
    ok = (row.inflow_reliable and row.outflow_observed
          and ratio is not None and not (isinstance(ratio, float) and np.isnan(ratio))
          and t["ratio_low"] <= ratio <= t["ratio_high"]
          and row.in_deg < cons_min and row.out_deg < dist_min)
    return bool(ok), m, th


def _gate_terminal(row, rc) -> tuple[bool, dict, dict]:
    """Money arrives and stays — but only claimable where the onward flow was
    actually traced. Never fires at MAX_DEPTH; that is the 444-false-sinks fix."""
    t = rc["terminal"]
    m = {"in_sum": row.in_sum, "out_sum": row.out_sum, "in_deg": row.in_deg,
         "pass_ratio": row.pass_ratio, "depth": row.depth}
    th = {"max_pass": t["max_pass"]}
    ok = (row.outflow_observed and row.in_sum > 0
          and row.out_sum <= t["max_pass"] * row.in_sum)
    return bool(ok), m, th


GATES = {
    "consolidator": _gate_consolidator,
    "distributor": _gate_distributor,
    "transit": _gate_transit,
    "terminal": _gate_terminal,
}


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _strength(metric: float, threshold: float, strong: float, cfg: dict) -> float:
    """0.5 for passing the gate, up to 1.0 as the metric approaches `strong`."""
    s = cfg["scoring"]
    if strong <= threshold:
        return float(s["base"] + s["span"])
    frac = (metric - threshold) / (strong - threshold)
    return float(s["base"] + s["span"] * float(np.clip(frac, 0.0, 1.0)))


def _score_for(role: str, row, cfg: dict) -> float:
    rc, s = cfg["roles"], cfg["scoring"]
    if role == "consolidator":
        t = rc["consolidator"]
        return _strength(row.in_deg, t["min_payers"], t["strong_payers"], cfg)
    if role == "distributor":
        t = rc["distributor"]
        return _strength(row.out_deg, t["min_recipients"], t["strong_recipients"], cfg)
    if role == "transit":
        t = rc["transit"]
        # Strength is how close the ratio sits to 1.0 — perfectly balanced is
        # the clearest signal — boosted when the money also moves fast.
        centre = 1.0
        half = max(t["ratio_high"] - centre, centre - t["ratio_low"]) or 1.0
        closeness = 1.0 - min(abs(float(row.pass_ratio) - centre) / half, 1.0)
        score = s["base"] + s["span"] * closeness
        fast = getattr(row, "fast_pass_share", np.nan)
        if fast is not None and not (isinstance(fast, float) and np.isnan(fast)) \
                and fast >= t["fast_pass_boost_share"]:
            score = min(score + s["span"] / 2, 1.0)
        return float(score)
    if role == "terminal":
        t = rc["terminal"]
        # The less that leaves, the more confident "the money stayed here" is.
        kept = 1.0 - (row.out_sum / row.in_sum if row.in_sum > 0 else 0.0)
        floor = 1.0 - t["max_pass"]
        return _strength(kept, floor, 1.0, cfg)
    if role == "coordinator":
        t = rc["coordinator"]
        return _strength(row.seed_reach, t["min_seed_reach"],
                         max(t["min_seed_reach"] * 3, t["min_seed_reach"] + 1), cfg)
    return float(s["base"])


def _apply_penalties(score: float, role: str, row, cfg: dict,
                     trace: RuleTrace) -> float:
    s = cfg["scoring"]
    if not row.outflow_observed:
        score *= s["penalty_max_depth"]
        trace.penalties.append(
            f"x{s['penalty_max_depth']}: at max traversal depth, onward flow unknown")
    if role in ("transit", "terminal", "coordinator") and not row.inflow_reliable:
        score *= s["penalty_unreliable_inflow"]
        trace.penalties.append(
            f"x{s['penalty_unreliable_inflow']}: inflow side is not reliable")
    return float(np.clip(score, 0.0, 1.0))


# ---------------------------------------------------------------------------
# pass 1 — base roles
# ---------------------------------------------------------------------------

def assign_base_roles(df: pd.DataFrame, cfg: dict, max_depth: int) -> pd.DataFrame:
    """Everything except `coordinator`, which needs the roles of a node's payers."""
    rc = cfg["roles"]
    use_cutoff = bool(rc.get("use_extended_roles", True))
    s = cfg["scoring"]
    traces: list[RuleTrace] = []

    for row in df.itertuples(index=False):
        trace = RuleTrace(gid=int(row.gid))
        passed: list[str] = []
        all_metrics: dict[str, Any] = {}
        all_thresholds: dict[str, Any] = {}

        for role in BASE_ROLES:
            # Seeds are barred from the two roles their pass ratio cannot
            # support: the export never captured what they received.
            if row.is_seed and role in ("transit", "terminal"):
                continue
            ok, m, th = GATES[role](row, rc)
            if ok:
                passed.append(role)
                all_metrics.update(m)
                all_thresholds.update(th)

        if passed:
            winner = min(passed, key=ROLE_PRECEDENCE.index)
            trace.role = winner
            trace.gate = _gate_description(winner, row, rc)
            trace.metrics = all_metrics
            trace.thresholds = all_thresholds
            trace.secondary_roles = [r for r in passed if r != winner]
            trace.role_score = _apply_penalties(_score_for(winner, row, cfg),
                                                winner, row, cfg, trace)
        elif use_cutoff and row.depth == max_depth:
            trace.role = "cutoff"
            trace.role_score = float(s["cutoff_fixed"])
            trace.gate = (f"depth == MAX_DEPTH ({max_depth}) and no inflow-based "
                          f"gate passed")
            trace.metrics = {"depth": row.depth, "in_deg": row.in_deg,
                             "in_sum": row.in_sum, "out_deg": row.out_deg}
            trace.notes.append(
                "Traversal artifact: onward transfers were never requested, so "
                "this node is not evidence of money settling.")
        else:
            trace.role = "peripheral"
            n_edges = int(row.in_deg) + int(row.out_deg)
            trace.role_score = float(s["peripheral_quiet"] if n_edges <= 1
                                     else s["peripheral_noisy"])
            trace.gate = "no role gate passed"
            trace.metrics = {"in_deg": row.in_deg, "out_deg": row.out_deg,
                             "in_sum": row.in_sum, "out_sum": row.out_sum}
            if row.is_seed and n_edges == 0:
                trace.notes.append(
                    "Known seed with no transfers above the export threshold in "
                    "the covered period.")
            elif row.depth == max_depth:
                trace.notes.append(
                    "At max traversal depth: onward transfers were never traced.")
        traces.append(trace)

    out = df.copy()
    out["role"] = [t.role for t in traces]
    out["role_score"] = [t.role_score for t in traces]
    out["secondary_roles"] = [";".join(t.secondary_roles) for t in traces]
    # No leading underscore: pandas `itertuples` renames such columns to
    # positional placeholders, which would break the coordinator pass below.
    out["trace_obj"] = traces
    return out


def _gate_description(role: str, row, rc: dict) -> str:
    """One line, quoting the comparison that actually fired."""
    if role == "consolidator":
        return f"in_deg {row.in_deg} >= min_payers {rc['consolidator']['min_payers']}"
    if role == "distributor":
        t = rc["distributor"]
        return (f"out_deg {row.out_deg} >= min_recipients {t['min_recipients']} "
                f"and >= {t['fan_ratio']}x in_deg {row.in_deg}")
    if role == "transit":
        t = rc["transit"]
        return (f"pass_ratio {row.pass_ratio:.2f} in "
                f"[{t['ratio_low']}, {t['ratio_high']}], both flow sides observed")
    if role == "terminal":
        t = rc["terminal"]
        return (f"out_sum <= {t['max_pass']} x in_sum, outflow traced "
                f"(depth {row.depth} < MAX_DEPTH)")
    return role


# ---------------------------------------------------------------------------
# pass 2 — coordinator
# ---------------------------------------------------------------------------

def assign_coordinators(df: pd.DataFrame, edges: pd.DataFrame,
                        cfg: dict) -> pd.DataFrame:
    """A node where money from several collectors, or from many separate courier
    chains, converges is a candidate upper-level controller.

    This runs after pass 1 and after clustering because both inputs are
    role-dependent: `n_key_payers` needs the payers' roles, `n_payer_clusters`
    needs their clusters.
    """
    t = cfg["roles"]["coordinator"]
    df = df.copy()

    role_by_gid = dict(zip(df["gid"], df["role"]))
    cluster_by_gid = dict(zip(df["gid"], df.get("cluster_id", pd.Series(dtype=int))))

    payers = edges.groupby("dst")["src"].apply(list)
    df["n_key_payers"] = df["gid"].map(
        lambda g: sum(1 for p in payers.get(g, []) if role_by_gid.get(p) in KEY_ROLES)
    ).fillna(0).astype("int64")
    df["n_payer_clusters"] = df["gid"].map(
        lambda g: len({cluster_by_gid.get(p) for p in payers.get(g, [])
                       if cluster_by_gid.get(p) is not None})
    ).fillna(0).astype("int64")

    reach_cut = float(df["seed_reach"].quantile(t["seed_reach_percentile"]))

    for i, row in enumerate(df.itertuples(index=False)):
        route_a = (row.n_key_payers >= t["min_key_payers"]
                   and row.seed_reach >= t["min_seed_reach"])
        route_b = (row.seed_reach >= reach_cut
                   and row.n_payer_clusters >= t["min_payer_clusters"])
        if not (route_a or route_b):
            continue
        trace: RuleTrace = row.trace_obj
        if trace.role != "peripheral":
            trace.secondary_roles = sorted(set(trace.secondary_roles + [trace.role]))
        trace.role = "coordinator"
        trace.gate = (
            f"n_key_payers {row.n_key_payers} >= {t['min_key_payers']} and "
            f"seed_reach {row.seed_reach} >= {t['min_seed_reach']}" if route_a else
            f"seed_reach {row.seed_reach} >= p{int(t['seed_reach_percentile'] * 100)} "
            f"({reach_cut:.0f}) and payers span {row.n_payer_clusters} clusters"
        )
        trace.metrics.update({
            "seed_reach": row.seed_reach, "n_key_payers": row.n_key_payers,
            "n_payer_clusters": row.n_payer_clusters, "in_deg": row.in_deg,
            "in_sum": row.in_sum,
        })
        trace.thresholds.update({
            "min_key_payers": t["min_key_payers"],
            "min_seed_reach": t["min_seed_reach"],
            "seed_reach_p99": round(reach_cut, 2),
        })
        trace.penalties = []
        trace.role_score = _apply_penalties(_score_for("coordinator", row, cfg),
                                            "coordinator", row, cfg, trace)
        df.iat[i, df.columns.get_loc("role")] = trace.role
        df.iat[i, df.columns.get_loc("role_score")] = trace.role_score
        df.iat[i, df.columns.get_loc("secondary_roles")] = ";".join(trace.secondary_roles)

    return df


def role_counts(df: pd.DataFrame) -> dict[str, int]:
    counts = df["role"].value_counts().to_dict()
    return {r: int(counts.get(r, 0)) for r in ROLE_PRECEDENCE}
