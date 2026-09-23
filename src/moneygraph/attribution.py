"""Seed-money attribution (task guidelines §7) — our original contribution.

Two questions the raw degrees cannot answer:

* `seed_reach` — how many of the known seeds can reach this node at all? A node
  fed by one courier is a different proposition from one where eleven separate
  courier chains converge, even at identical in-degree.
* `seed_kzt_attributed` — how much seed-originated money plausibly reached it?

Attribution is a documented **heuristic, not an accounting fact**. Money is
fungible; once two inflows mix, no export can say which tenge went where. The
propagation below splits a node's attributed inflow across its outgoing edges
in proportion to edge size, scaled by how much of its inflow it actually
forwards. Read the result as an upper-bound-style estimate of exposure, and
never as "this node received X tenge of drug money".
"""

from __future__ import annotations

from collections import deque

import networkx as nx
import numpy as np
import pandas as pd

from .io import Dataset


def seed_reach(g: nx.DiGraph, ds: Dataset) -> pd.Series:
    """Distinct seeds with a directed path to each node. BFS per seed."""
    counts: dict[int, int] = {int(n): 0 for n in g.nodes}
    for seed in ds.seeds:
        seed = int(seed)
        if seed not in g:
            continue
        seen = {seed}
        q = deque([seed])
        while q:
            cur = q.popleft()
            for nxt in g.successors(cur):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        # A seed reaches itself trivially; that is not evidence about the seed.
        for node in seen - {seed}:
            counts[node] += 1
    return pd.Series(counts, name="seed_reach")


def attribute_seed_money(g: nx.DiGraph, ds: Dataset, features: pd.DataFrame) -> pd.Series:
    """Propagate seed-originated money forward, `MAX_DEPTH + 1` rounds.

    A fixed round count rather than a convergence loop: the graph contains
    cycles, and a bounded number of rounds terminates on any input while still
    covering every path the export could have traced.
    """
    pass_ratio = dict(zip(features["gid"], features["pass_ratio"]))
    out_sum = dict(zip(features["gid"], features["out_sum"]))
    seeds = set(int(s) for s in ds.seeds)

    attributed: dict[int, float] = {int(n): 0.0 for n in g.nodes}
    # Round 0: every seed pushes the full value of its outgoing edges.
    frontier: dict[int, float] = {}
    for seed in seeds:
        if seed not in g:
            continue
        for _u, v, data in g.out_edges(seed, data=True):
            amount = float(data.get("sum_kzt", 0.0))
            attributed[v] += amount
            frontier[v] = frontier.get(v, 0.0) + amount

    for _round in range(ds.max_depth + 1):
        if not frontier:
            break
        nxt: dict[int, float] = {}
        for node, incoming in frontier.items():
            total_out = float(out_sum.get(node, 0.0) or 0.0)
            if total_out <= 0:
                continue        # money stops here, or its onward flow is untraced
            ratio = pass_ratio.get(node, np.nan)
            # An unknown pass ratio means we cannot say how much was forwarded.
            # Forwarding the full attributed amount would inflate everything
            # downstream, so cap at 1 and treat unknown as "forwards all of it"
            # only for the split, never for the node's own attributed total.
            share = 1.0 if (ratio is None or np.isnan(ratio)) else min(float(ratio), 1.0)
            movable = incoming * share
            if movable <= 0:
                continue
            for _u, v, data in g.out_edges(node, data=True):
                edge_share = float(data.get("sum_kzt", 0.0)) / total_out
                passed = movable * edge_share
                if passed <= 0:
                    continue
                attributed[v] += passed
                nxt[v] = nxt.get(v, 0.0) + passed
        frontier = nxt

    # A seed's own attributed inflow is meaningless: the export starts there.
    for seed in seeds:
        attributed[seed] = 0.0
    return pd.Series(attributed, name="seed_kzt_attributed")


def attribution_features(g: nx.DiGraph, ds: Dataset, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    reach = seed_reach(g, ds)
    df["seed_reach"] = df["gid"].map(reach).fillna(0).astype("int64")
    attributed = attribute_seed_money(g, ds, df)
    df["seed_kzt_attributed"] = df["gid"].map(attributed).fillna(0.0)
    return df
