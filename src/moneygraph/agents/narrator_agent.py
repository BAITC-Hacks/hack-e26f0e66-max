"""Narrator agent — rewrites rule traces into readable English.

It is given the *trace*, never the graph: the gate that fired, the metrics it
compared, the thresholds, and the deterministic template as a reference. It may
improve the phrasing. It may not introduce a fact.

Every returned string goes through `evidence.validate`, which enforces the
length cap, the forbidden-word list, and — the important one — that every
number in the text appears in the rule trace. A rejected string is silently
replaced by its template, so a bad narration costs a little money and nothing
else. The rejection is counted and reported in the run trace.
"""

from __future__ import annotations

import json

import pandas as pd

from ..evidence import allowed_number_tokens, validate
from ..roles import RuleTrace
from .llm import LLMClient

SYSTEM = """You rewrite AML analyst notes so they read naturally. You are a copy-editor, not an analyst.

Absolute rules:
- Use ONLY the numbers given to you in `metrics` and `thresholds`. Never compute, round differently, or introduce a number. If a figure is not supplied, do not mention it.
- Never state or imply guilt, criminality or certainty. These are hypotheses an analyst will verify. Write "signs of", "pattern consistent with", "candidate for review".
- Never use: criminal, guilty, launderer, "organizer is", confirmed.
- Stay under the character limit you are given, including spaces.
- No names, ages, genders, incomes, organizations — the data has none, and inventing one is a disqualification.
- Keep the account identifier (gid) if the reference text has one.

Answer with JSON only: {"texts": {"<gid>": "<rewritten sentence>", ...}}
Return one entry per input item, in the same order."""


def narrate_evidence(
    df: pd.DataFrame,
    traces: dict[int, RuleTrace],
    client: LLMClient,
    cfg: dict,
    tracer,
    scope_gids: list[int] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Rewrite the `evidence` column for the selected nodes.

    Returns the frame and a stats dict: how many were narrated, how many
    narrations were rejected by validation and fell back to the template.
    """
    acfg = (cfg.get("agents", {}) or {}).get("narrator", {}) or {}
    stats = {"attempted": 0, "accepted": 0, "rejected": 0, "reasons": {}}
    if not acfg.get("enabled", True) or not client.available:
        stats["skipped"] = client.disabled_reason or "narrator disabled"
        return df, stats

    scope = acfg.get("scope", "top_and_clusters")
    if scope == "none":
        stats["skipped"] = "scope: none"
        return df, stats

    gids = scope_gids if scope_gids is not None else _default_scope(df, cfg, scope)
    if not gids:
        stats["skipped"] = "no nodes in scope"
        return df, stats

    limit = int(cfg["evidence"]["max_chars"])
    batch_size = int(acfg.get("batch_size", 40))
    by_gid = df.set_index("gid")
    updates: dict[int, str] = {}

    for start in range(0, len(gids), batch_size):
        if not client.available:          # budget may have run out mid-way
            break
        batch = gids[start:start + batch_size]
        items = []
        for gid in batch:
            trace = traces.get(int(gid))
            if trace is None:
                continue
            items.append({
                "gid": int(gid),
                "role": trace.role,
                "rule_that_fired": trace.gate,
                "metrics": trace.metrics,
                "thresholds": trace.thresholds,
                "reference_text": by_gid.at[gid, "evidence"],
            })
        if not items:
            continue
        stats["attempted"] += len(items)

        answer = client.complete_json(
            agent="narrator",
            purpose=f"evidence batch {start // batch_size + 1}",
            system=SYSTEM,
            user=json.dumps({"character_limit": limit, "items": items},
                            ensure_ascii=False, default=str),
        )
        texts = (answer or {}).get("texts", {}) if isinstance(answer, dict) else {}
        for item in items:
            gid = item["gid"]
            candidate = texts.get(str(gid)) or texts.get(gid)
            if not candidate:
                stats["rejected"] += 1
                stats["reasons"]["no text returned"] = \
                    stats["reasons"].get("no text returned", 0) + 1
                continue
            trace = traces[gid]
            row = by_gid.loc[gid]
            ok, reason = validate(
                candidate, cfg, limit=limit,
                allowed_numbers=allowed_number_tokens(trace, row))
            if ok:
                updates[gid] = " ".join(candidate.split())
                stats["accepted"] += 1
            else:
                stats["rejected"] += 1
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

    if updates:
        df = df.copy()
        mask = df["gid"].isin(updates)
        df.loc[mask, "evidence"] = df.loc[mask, "gid"].map(updates)
    if stats["rejected"]:
        tracer.note_warning(
            f"narrator: {stats['rejected']} of {stats['attempted']} rewrites failed "
            f"validation and kept the deterministic template "
            f"({', '.join(f'{k} x{v}' for k, v in stats['reasons'].items())})")
    return df, stats


def _default_scope(df: pd.DataFrame, cfg: dict, scope: str) -> list[int]:
    """Narration is a readability upgrade, so it is spent where it is read.

    Templates are always correct, so narrating all 2,248 nodes buys very little
    and costs real money. By default: the priority shortlist, plus the top node
    of every cluster — exactly the rows a jury or analyst will actually open.
    """
    if scope == "all":
        return df["gid"].astype(int).tolist()
    top_n = int(cfg["priority"]["top_n"])
    gids = set(df.nlargest(top_n, "priority_score")["gid"].astype(int))
    if "cluster_id" in df:
        leaders = df.sort_values(["cluster_id", "priority_score"],
                                 ascending=[True, False]).groupby("cluster_id").head(1)
        gids |= set(leaders["gid"].astype(int))
    return sorted(gids)


def narrate_hypotheses(
    clusters: pd.DataFrame, members_by_cluster: dict, client: LLMClient,
    cfg: dict, tracer,
) -> tuple[pd.DataFrame, dict]:
    """Same contract for cluster hypotheses: rephrase, validate, fall back."""
    acfg = (cfg.get("agents", {}) or {}).get("narrator", {}) or {}
    stats = {"attempted": 0, "accepted": 0, "rejected": 0, "reasons": {}}
    if not acfg.get("enabled", True) or not client.available \
            or acfg.get("scope") == "none":
        return clusters, stats

    limit = int(cfg["clustering"]["max_hypothesis_chars"])
    items = []
    for row in clusters.itertuples(index=False):
        members = members_by_cluster.get(int(row.cluster_id))
        if members is None or len(members) < 2:
            continue
        items.append({
            "cluster_id": int(row.cluster_id),
            "n_nodes": int(row.n_nodes),
            "n_seed": int(row.n_seed),
            "internal_turnover_kzt": float(row.sum_kzt_internal),
            "role_counts": members["role"].value_counts().to_dict(),
            "top_gids": row.top_gids,
            "reference_text": row.hypothesis,
        })
    if not items:
        return clusters, stats
    stats["attempted"] = len(items)

    answer = client.complete_json(
        agent="narrator", purpose="cluster hypotheses", system=SYSTEM,
        user=json.dumps({"character_limit": limit,
                         "note": "key is cluster_id, not gid", "items": items},
                        ensure_ascii=False, default=str),
    )
    texts = (answer or {}).get("texts", {}) if isinstance(answer, dict) else {}
    updates: dict[int, str] = {}
    for item in items:
        cid = item["cluster_id"]
        candidate = texts.get(str(cid)) or texts.get(cid)
        if not candidate:
            stats["rejected"] += 1
            continue
        # Cluster text has no single rule trace, so numbers are checked against
        # the cluster's own aggregates.
        allowed = set()
        for value in (item["n_nodes"], item["n_seed"], item["internal_turnover_kzt"],
                      *item["role_counts"].values()):
            allowed |= {str(int(value)), f"{float(value):.0f}",
                        f"{float(value) / 1e6:.1f}", f"{float(value) / 1e6:.1f}M",
                        f"{float(value) / 1e3:.0f}", f"{float(value) / 1e3:.0f}k"}
        allowed |= set(str(g) for g in str(item["top_gids"]).split(";") if g)
        allowed.add(str(cid))
        ok, reason = validate(candidate, cfg, limit=limit, allowed_numbers=allowed)
        if ok:
            updates[cid] = " ".join(candidate.split())
            stats["accepted"] += 1
        else:
            stats["rejected"] += 1
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

    if updates:
        clusters = clusters.copy()
        mask = clusters["cluster_id"].isin(updates)
        clusters.loc[mask, "hypothesis"] = clusters.loc[mask, "cluster_id"].map(updates)
    return clusters, stats
