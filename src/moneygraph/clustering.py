"""Clustering (guideline §9).

Louvain runs on the **undirected** projection, which is a real concession: the
starter README warns that dropping direction erases the point of the case. It
is stated openly rather than hidden — community detection needs an undirected
graph, so direction is dropped *for grouping only*. Every role, every metric
and every flow shown to the analyst still uses the directed graph.

Small components are never absorbed into large clusters. A two-node fragment
with one seed is its own finding, not noise to be filed under cluster 0.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from .io import Dataset


def cluster_nodes(g: nx.DiGraph, ds: Dataset, df: pd.DataFrame,
                  cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Assign every node a `cluster_id`. Returns (df, diagnostics)."""
    ccfg = cfg["clustering"]
    seed = int(cfg.get("seed", 42))
    min_size = int(ccfg["min_cluster_size"])

    ug = nx.Graph()
    ug.add_nodes_from(g.nodes)
    for u, v, data in g.edges(data=True):
        w = float(np.log1p(data.get("sum_kzt", 0.0)))
        if ug.has_edge(u, v):
            ug[u][v]["weight"] += w
        else:
            ug.add_edge(u, v, weight=w)

    # Components below `min_cluster_size`, and isolated nodes, keep their own
    # identity; Louvain only runs inside the components big enough to have
    # structure worth detecting.
    assignment: dict[int, tuple] = {}
    for comp in nx.connected_components(ug):
        members = sorted(comp)
        if len(members) < min_size:
            assignment.update({n: ("small", members[0]) for n in members})
            continue
        sub = ug.subgraph(members)
        communities = nx.community.louvain_communities(
            sub, weight="weight", resolution=float(ccfg["resolution"]), seed=seed)
        for community in communities:
            key = min(community)
            assignment.update({n: ("louvain", key) for n in community})

    # Renumber by size descending, ties broken by smallest gid, for determinism.
    groups: dict[tuple, list[int]] = {}
    for node, key in assignment.items():
        groups.setdefault(key, []).append(int(node))
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), min(kv[1])))
    cluster_of = {node: cid for cid, (_k, members) in enumerate(ordered) for node in members}

    df = df.copy()
    df["cluster_id"] = df["gid"].map(cluster_of).astype("int64")
    assert df["cluster_id"].notna().all(), "every node must land in a cluster"

    diagnostics = {
        "n_clusters": len(ordered),
        "n_singletons": sum(1 for _k, m in ordered if len(m) == 1),
        "largest": len(ordered[0][1]) if ordered else 0,
        "stability": _stability(ug, cfg, cluster_of, min_size),
    }
    return df, diagnostics


def _stability(ug: nx.Graph, cfg: dict, baseline: dict[int, int],
               min_size: int) -> dict:
    """Re-run Louvain under several seeds and measure how often node pairs stay
    together. Supports the organizers' "8 stable communities" claim with a
    number instead of a hope."""
    ccfg = cfg["clustering"]
    seeds = list(ccfg.get("stability_seeds", []) or [])
    if len(seeds) < 2:
        return {"checked": False}

    runs: list[dict[int, int]] = []
    for s in seeds:
        run: dict[int, int] = {}
        for comp in nx.connected_components(ug):
            members = sorted(comp)
            if len(members) < min_size:
                run.update({n: hash(("small", members[0])) for n in members})
                continue
            communities = nx.community.louvain_communities(
                ug.subgraph(members), weight="weight",
                resolution=float(ccfg["resolution"]), seed=int(s))
            for community in communities:
                key = hash(("louvain", min(community)))
                run.update({n: key for n in community})
        runs.append(run)

    by_cluster: dict[int, list[int]] = {}
    for node, cid in baseline.items():
        by_cluster.setdefault(cid, []).append(node)

    scores: dict[int, float] = {}
    rng = np.random.default_rng(int(cfg.get("seed", 42)))
    for cid, members in by_cluster.items():
        if len(members) < 2:
            scores[cid] = 1.0
            continue
        # Sample pairs in large clusters: exact is O(n^2) and adds nothing.
        pairs = _sample_pairs(members, rng, cap=2000)
        togethers = [
            np.mean([1.0 if run.get(a) == run.get(b) else 0.0 for run in runs])
            for a, b in pairs
        ]
        scores[cid] = float(np.mean(togethers)) if togethers else 1.0

    stable = [c for c, s in scores.items() if s >= 0.8]
    return {"checked": True, "n_seeds": len(seeds), "per_cluster": scores,
            "n_stable_clusters": len(stable),
            "mean_stability": float(np.mean(list(scores.values()))) if scores else 1.0}


def _sample_pairs(members: list[int], rng, cap: int) -> list[tuple[int, int]]:
    n = len(members)
    total = n * (n - 1) // 2
    if total <= cap:
        return [(members[i], members[j]) for i in range(n) for j in range(i + 1, n)]
    out = set()
    while len(out) < cap:
        i, j = rng.integers(0, n, 2)
        if i != j:
            out.add((members[min(i, j)], members[max(i, j)]))
    return sorted(out)


def cluster_table(df: pd.DataFrame, ds: Dataset, cfg: dict) -> pd.DataFrame:
    """One row per cluster: size, seeds, internal turnover, top gids."""
    edges = ds.edges
    cluster_of = dict(zip(df["gid"], df["cluster_id"]))
    src_c = edges["src"].map(cluster_of)
    dst_c = edges["dst"].map(cluster_of)
    internal = (edges.assign(c=src_c.where(src_c == dst_c))
                     .dropna(subset=["c"]).groupby("c")["sum_kzt"].sum())

    top_n = 5
    rows = []
    for cid, grp in df.groupby("cluster_id"):
        top = grp.nlargest(top_n, "priority_score") if "priority_score" in grp else grp.head(top_n)
        rows.append({
            "cluster_id": int(cid),
            "n_nodes": int(len(grp)),
            "n_seed": int(grp["is_seed"].sum()),
            "sum_kzt_internal": float(internal.get(cid, 0.0)),
            "top_gids": ";".join(str(int(g)) for g in top["gid"]),
        })
    return pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)
