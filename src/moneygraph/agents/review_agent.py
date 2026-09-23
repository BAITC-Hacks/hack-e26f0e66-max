"""Reviewer agent — completeness assessment (brief §8, optional item 8).

Answers "what data would close the blind spots, and what should the analyst
request next?". The gaps themselves are computed deterministically from the
graph — how many frontier nodes were never expanded, which seeds have no
traced inflow, where the 5,000 KZT floor most likely hides activity. The agent
only turns that list into a readable brief.

Output: `output_files/data_requests.md`, and a per-node line in the node card.
"""

from __future__ import annotations

import json

import pandas as pd

from .llm import LLMClient

SYSTEM = """You write a short data-request brief for an AML analyst.

You are given computed gaps in a transfer export. Turn them into a prioritized,
concrete list of requests the analyst can send.

Rules:
- Use ONLY the figures given. Never add a number.
- Each request states what to ask for, which accounts it concerns, and what it would resolve.
- Hypothesis wording; no accusations. Never use: criminal, guilty, launderer, "organizer is", confirmed.
- Markdown, at most 400 words, no preamble."""


def compute_gaps(nodes: pd.DataFrame, edges: pd.DataFrame, ds, cfg: dict) -> dict:
    """The deterministic part: what is provably missing from this export."""
    max_depth = ds.max_depth
    frontier = nodes[nodes["depth"] == max_depth]
    frontier_key = frontier[frontier["role"].isin(["consolidator", "coordinator", "cutoff"])]
    seeds_no_inflow = nodes[nodes["is_seed"] & (nodes["in_deg"] == 0)]
    seeds_isolated = nodes[nodes["is_seed"] & (nodes["in_deg"] == 0) & (nodes["out_deg"] == 0)]
    top = nodes.nlargest(int(cfg["priority"]["top_n"]), "priority_score")
    top_frontier = top[top["depth"] == max_depth]

    n_components = int(nodes["component_id"].nunique()) if "component_id" in nodes else None
    floor = (cfg.get("expected", {}) or {}).get("min_amount_kzt")

    return {
        "max_depth": int(max_depth),
        "frontier_nodes": int(len(frontier)),
        "frontier_collectors": sorted(int(g) for g in frontier_key["gid"].head(25)),
        "n_frontier_collectors": int(len(frontier_key)),
        "frontier_kzt_received": float(frontier["in_sum"].sum()),
        "seeds_without_traced_inflow": int(len(seeds_no_inflow)),
        "seeds_with_no_transfers_at_all": int(len(seeds_isolated)),
        "top_nodes_on_frontier": sorted(int(g) for g in top_frontier["gid"]),
        "n_components": n_components,
        "amount_floor_kzt": floor,
        "period": {
            "from": str(ds.tx["date"].min().date()) if ds.has_transactions else None,
            "to": str(ds.tx["date"].max().date()) if ds.has_transactions else None,
        },
        "transactions_available": bool(ds.has_transactions),
    }


def deterministic_brief(gaps: dict) -> str:
    """The fallback write-up, and the reference the agent is asked to improve."""
    md = ["# Data requests", "",
          "What this export cannot show, and what to ask for next. "
          "Every item below is computed from the graph, not assumed.", ""]

    md += ["## 1. The traversal frontier", "",
           f"The export stopped at hop {gaps['max_depth']}. "
           f"**{gaps['frontier_nodes']} accounts** sit on that frontier and their "
           f"onward transfers were never requested, so their outflow is *unknown*, "
           f"not zero. They received {gaps['frontier_kzt_received']:,.0f} KZT in total.", ""]
    if gaps["n_frontier_collectors"]:
        listed = ", ".join(str(g) for g in gaps["frontier_collectors"])
        md += [f"**Request:** outgoing transfers (hop {gaps['max_depth'] + 1}) for the "
               f"{gaps['n_frontier_collectors']} frontier accounts showing collection "
               f"behaviour — starting with {listed}.", "",
               "These are the highest-value requests: a collection point at the edge "
               "of the visible data is exactly where the chain is most likely to "
               "continue.", ""]

    md += ["## 2. Inflows to the seed accounts", "",
           f"The graph was built *from* the seeds by following outgoing transfers, so "
           f"money reaching them from outside the sample is absent. "
           f"**{gaps['seeds_without_traced_inflow']} seeds** have no traced inflow at "
           f"all, and **{gaps['seeds_with_no_transfers_at_all']}** have no transfers "
           f"in either direction.", "",
           "**Request:** incoming transfers to all seed accounts for the same period. "
           "Without them, no seed's pass-through ratio can be interpreted.", ""]

    if gaps.get("amount_floor_kzt"):
        md += ["## 3. Activity below the reporting threshold", "",
               f"Transfers under {gaps['amount_floor_kzt']:,} KZT were excluded. "
               f"Structuring just below that line is invisible by construction.", "",
               f"**Request:** all transfers regardless of amount for the priority "
               f"shortlist, to test whether any account's pattern changes once the "
               f"floor is removed.", ""]

    if gaps.get("n_components") and gaps["n_components"] > 1:
        md += ["## 4. Disconnected fragments", "",
               f"The export splits into **{gaps['n_components']} components**. Whether "
               f"they are genuinely separate networks or connected through accounts "
               f"outside the sample cannot be answered from this data.", "",
               "**Request:** transfers between the seed sets of the separate "
               "components, including through accounts not currently in the export.", ""]

    if not gaps.get("transactions_available"):
        md += ["## 5. Transaction-level detail", "",
               "Only aggregated pairs were supplied, so no timing analysis was "
               "possible: pass-through speed, same-day collection and activity "
               "bursts are all unavailable.", "",
               "**Request:** the individual dated transactions behind each pair.", ""]
    elif gaps["period"]["from"]:
        md += ["## 5. Period", "",
               f"The export covers {gaps['period']['from']} to {gaps['period']['to']}. "
               f"Patterns that repeat monthly cannot be distinguished from one-off "
               f"movements in a single month.", "",
               "**Request:** the same export for the preceding two months.", ""]

    return "\n".join(md)


def write_brief(gaps: dict, client: LLMClient, cfg: dict, tracer) -> str:
    """Deterministic brief, optionally rephrased by the agent and validated."""
    baseline = deterministic_brief(gaps)
    acfg = (cfg.get("agents", {}) or {}).get("reviewer", {}) or {}
    if not acfg.get("enabled", True) or not client.available:
        return baseline

    text = client.complete(
        agent="reviewer", purpose="data request brief", system=SYSTEM,
        user=json.dumps({"computed_gaps": gaps, "reference_brief": baseline},
                        ensure_ascii=False, default=str),
        max_output_tokens=1200,
    )
    if not text:
        return baseline

    lowered = text.lower()
    bad = [w for w in cfg["evidence"]["forbidden_words"] if w.lower() in lowered]
    if bad:
        tracer.note_warning(
            f"reviewer: brief contained forbidden wording {bad}; kept the "
            f"deterministic version")
        return baseline
    return text.strip() + "\n"
