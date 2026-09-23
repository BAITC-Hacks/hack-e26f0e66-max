"""Evidence, `why` and cluster hypotheses (guideline §11, brief §9 wording).

Two layers, in this order:

1. **Templates.** One per role, filled from the node's `RuleTrace`. The metrics
   quoted are exactly the ones the rule compared, so the explanation can never
   contradict the logic. This layer always runs and is always sufficient.
2. **Narration** (optional, `agents.narrator`). The LLM may rewrite a template
   into more natural English — and its output is then checked by `validate`
   below. Any number it introduces that is not in the rule trace, any forbidden
   word, any overlong string: rejected, template kept.

That ordering is what keeps the tool inside the brief's ban on black boxes.
The agent is a copy-editor with no authority over the facts.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from .roles import RuleTrace


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def fmt_kzt(x: float | None) -> str:
    """Readable money: 8.4M KZT, 412k KZT, 7,300 KZT."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    x = float(x)
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f}M KZT"
    if abs(x) >= 1e3:
        return f"{x / 1e3:.0f}k KZT"
    return f"{x:,.0f} KZT"


def fmt_pct(x: float | None) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{100 * float(x):.0f}%"


def truncate(text: str, limit: int) -> str:
    """Hard cap at a word boundary, with an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]).rstrip(" ,;.") + "…"


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------

def evidence_for(row, trace: RuleTrace, cfg: dict) -> str:
    """The `evidence` column: why this node got this role, with real numbers."""
    limit = int(cfg["evidence"]["max_chars"])
    role = trace.role
    seeds = f" ({int(row.seed_in_deg)} seed{'s' if row.seed_in_deg != 1 else ''})" \
        if getattr(row, "seed_in_deg", 0) else ""

    if role == "consolidator":
        text = (f"Receives from {int(row.in_deg)} distinct payers{seeds}, "
                f"{fmt_kzt(row.in_sum)}")
        if row.outflow_observed and row.in_sum > 0:
            text += f"; forwards {fmt_pct(min(row.out_sum / row.in_sum, 9.99))}"
        else:
            text += "; onward flow not traced (export depth limit)"
        text += " — signs of consolidation."

    elif role == "distributor":
        text = (f"Fans out to {int(row.out_deg)} recipients "
                f"({fmt_kzt(row.out_sum)}) against {int(row.in_deg)} payer"
                f"{'s' if row.in_deg != 1 else ''} — pattern consistent with "
                f"a distribution layer.")

    elif role == "transit":
        text = (f"In {fmt_kzt(row.in_sum)} / out {fmt_kzt(row.out_sum)} "
                f"(ratio {float(row.pass_ratio):.2f})")
        fast = getattr(row, "fast_pass_share", np.nan)
        lag = cfg["roles"]["transit"]["max_lag_days"]
        if fast is not None and not (isinstance(fast, float) and np.isnan(fast)):
            text += f", {fmt_pct(fast)} forwarded within {int(lag)} days"
        text += " — pattern consistent with transit."

    elif role == "terminal":
        text = (f"Receives {fmt_kzt(row.in_sum)} from {int(row.in_deg)} payer"
                f"{'s' if row.in_deg != 1 else ''}, forwards "
                f"{fmt_pct(row.out_sum / row.in_sum if row.in_sum else 0)}; "
                f"outflow was traced (hop {int(row.depth)}) — possible final recipient.")

    elif role == "coordinator":
        text = (f"Money from {int(row.seed_reach)} seeds converges here via "
                f"{int(getattr(row, 'n_key_payers', 0))} collector/transit account"
                f"{'s' if getattr(row, 'n_key_payers', 0) != 1 else ''} across "
                f"{int(getattr(row, 'n_payer_clusters', 0))} clusters — candidate "
                f"upper-level node for review.")

    elif role == "cutoff":
        text = (f"Hop-{int(row.depth)} node: onward transfers were not traced "
                f"(export limit). Receives {fmt_kzt(row.in_sum)} from "
                f"{int(row.in_deg)} payer{'s' if row.in_deg != 1 else ''}.")

    else:  # peripheral
        if row.is_seed and (row.in_deg + row.out_deg) == 0:
            text = ("Known seed; no transfers above the export threshold observed "
                    "in the covered period.")
        else:
            text = (f"No role indicators: {int(row.in_deg)} payer"
                    f"{'s' if row.in_deg != 1 else ''}, {int(row.out_deg)} recipient"
                    f"{'s' if row.out_deg != 1 else ''}, {fmt_kzt(row.in_sum)} in / "
                    f"{fmt_kzt(row.out_sum)} out.")

    if trace.secondary_roles and len(text) < limit - 40:
        text += f" Also matches: {', '.join(trace.secondary_roles)}."
    return truncate(text, limit)


def why_for(row, cfg: dict, contributors: list[str]) -> str:
    """The `why` column in top_nodes.csv: plain language, no jargon.

    Names the components that actually drove this node's rank, so the analyst
    can see whether they are looking at a wide collector, a big exposure, or a
    node that simply sits in a seed-dense cluster.
    """
    limit = int(cfg["evidence"]["max_why_chars"])
    phrases: list[str] = []
    for name in contributors:
        if name == "payers" and row.in_deg > 0:
            seeds = (f" incl. {int(row.seed_in_deg)} seed"
                     f"{'s' if row.seed_in_deg != 1 else ''}") if row.seed_in_deg else ""
            phrases.append(f"receives from {int(row.in_deg)} different payers{seeds}")
        elif name == "seed_reach" and row.seed_reach > 0:
            phrases.append(f"money from {int(row.seed_reach)} seeds can reach it")
        elif name == "seed_money" and row.seed_kzt_attributed > 0:
            phrases.append(f"estimated {fmt_kzt(row.seed_kzt_attributed)} of "
                           f"seed-originated flow passes through")
        elif name == "role":
            phrases.append(f"classified {row.role}")
        elif name == "cluster":
            phrases.append(f"sits in cluster {int(row.cluster_id)}")
    if row.outflow_observed and row.in_sum > 0:
        phrases.append(f"forwards {fmt_pct(min(row.out_sum / row.in_sum, 9.99))} of inflow")
    elif not row.outflow_observed:
        phrases.append("onward flow not traced — candidate for a follow-up request")

    # Upper-case the first letter only: `str.capitalize()` would lower-case the
    # rest and turn "8.4M KZT" into "8.4m kzt".
    joined = "; ".join(phrases[:4])
    text = (joined[:1].upper() + joined[1:] + ".") if joined else "No signals detected."
    adj = getattr(row, "priority_adjustments", "")
    if adj and len(text) < limit - len(adj) - 3:
        text += f" [{adj}]"
    return truncate(text, limit)


def hypothesis_for(cluster_row, members: pd.DataFrame, cfg: dict) -> str:
    """A template-generated sentence driven by the cluster's role mix and flows."""
    limit = int(cfg["clustering"]["max_hypothesis_chars"])
    n, n_seed = int(cluster_row.n_nodes), int(cluster_row.n_seed)
    internal = float(cluster_row.sum_kzt_internal)
    counts = members["role"].value_counts().to_dict()

    if n == 1:
        only = members.iloc[0]
        if bool(only["is_seed"]):
            return truncate("Isolated known seed; no transfers observed in the "
                            "export window.", limit)
        return truncate(f"Single disconnected node, {fmt_kzt(float(only['in_sum']))} "
                        f"received.", limit)

    top = members.nlargest(1, "priority_score").iloc[0] if "priority_score" in members else members.iloc[0]
    gid = int(top["gid"])
    share = (float(top["in_sum"]) / internal) if internal > 0 else 0.0

    if counts.get("coordinator"):
        text = (f"Possible control layer: {counts['coordinator']} candidate "
                f"upper-level node(s), money from {n_seed} seed(s) converging; "
                f"{gid} ranks highest.")
    elif counts.get("consolidator"):
        text = (f"Signs of a collection hub: money from {n_seed} seed(s) "
                f"converges on consolidator {gid}")
        if share > 0:
            text += f" ({fmt_pct(min(share, 1.0))} of internal turnover)"
        text += "."
    elif counts.get("distributor"):
        out_deg = int(top["out_deg"])
        text = (f"Pattern consistent with a distribution layer: {gid} fans out "
                f"to {out_deg} recipients across a {n}-node group.")
    elif counts.get("transit", 0) >= 2:
        lag = cfg["roles"]["transit"]["max_lag_days"]
        text = (f"Transit chain: {counts['transit']} pass-through accounts "
                f"forward funds within {int(lag)} days.")
    elif counts.get("cutoff", 0) > n / 2:
        text = (f"Group sits on the traversal frontier: {counts['cutoff']} of {n} "
                f"nodes were never expanded — onward flow unknown.")
    else:
        text = (f"{n}-node group, {n_seed} seed(s), {fmt_kzt(internal)} internal "
                f"turnover; no dominant role pattern detected.")
    return truncate(text, limit)


# ---------------------------------------------------------------------------
# validation — the gate every narrated string must pass
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(r"\d[\d,._]*(?:\.\d+)?[MkK%]?")


def allowed_number_tokens(trace: RuleTrace, row) -> set[str]:
    """Every numeric string a narration is permitted to contain.

    Built from the rule trace plus the node's own metrics, in each of the
    formats the templates use. A narration quoting anything else is inventing a
    fact and is rejected.
    """
    allowed: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        try:
            f = float(value)
        except (TypeError, ValueError):
            return
        if np.isnan(f):
            return
        allowed.update({
            f"{int(f)}" if f.is_integer() else "",
            f"{f:.0f}", f"{f:.1f}", f"{f:.2f}",
            f"{f:,.0f}".replace(",", ""), f"{f:,.0f}",
            f"{f / 1e6:.1f}", f"{f / 1e6:.1f}M", f"{f / 1e3:.0f}", f"{f / 1e3:.0f}k",
            f"{100 * f:.0f}", f"{100 * f:.0f}%",
        })
        allowed.discard("")

    for value in trace.metrics.values():
        add(value)
    for value in trace.thresholds.values():
        add(value)
    for field in ("in_deg", "out_deg", "in_sum", "out_sum", "depth", "seed_reach",
                  "seed_in_deg", "seed_kzt_attributed", "pass_ratio", "cluster_id",
                  "n_key_payers", "n_payer_clusters", "fast_pass_share",
                  "median_lag_days", "max_payers_same_day", "gid"):
        add(getattr(row, field, None))
    # Ratios expressed as percentages of inflow.
    in_sum = float(getattr(row, "in_sum", 0) or 0)
    if in_sum > 0:
        add(float(getattr(row, "out_sum", 0) or 0) / in_sum)
    return allowed


def validate(text: str, cfg: dict, *, limit: int,
             allowed_numbers: set[str] | None = None) -> tuple[bool, str]:
    """Returns (ok, reason). Used for every narrated string before it is kept."""
    if not text or not text.strip():
        return False, "empty"
    stripped = " ".join(text.split())
    if len(stripped) > limit:
        return False, f"too long ({len(stripped)} > {limit})"

    lowered = stripped.lower()
    for word in cfg["evidence"]["forbidden_words"]:
        if word.lower() in lowered:
            return False, f"forbidden wording: '{word}'"

    if allowed_numbers is not None:
        for token in NUMBER_RE.findall(stripped):
            norm = token.rstrip(".,;").replace(",", "")
            if norm and norm not in allowed_numbers and token not in allowed_numbers:
                return False, f"number '{token}' is not in the rule trace"
    return True, "ok"
