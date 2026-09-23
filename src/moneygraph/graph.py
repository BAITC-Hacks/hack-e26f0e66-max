"""Graph construction (task guidelines §6)."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from .io import Dataset


def build_graph(ds: Dataset) -> nx.DiGraph:
    """Directed, weighted graph over **every** gid in the node list.

    Isolated nodes matter: the 19 seeds with no transfers must still appear in
    `nodes_roles.csv`, so they are added as nodes with no edges rather than
    being lost by building the graph from the edge list alone.
    """
    g = nx.DiGraph()
    g.add_nodes_from(ds.nodes["gid"].astype(int).tolist())
    for r in ds.edges.itertuples(index=False):
        g.add_edge(int(r.src), int(r.dst),
                   sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    assert g.number_of_nodes() == len(ds.nodes), (
        f"graph has {g.number_of_nodes()} nodes but the node list has {len(ds.nodes)}"
    )
    return g


def component_table(g: nx.DiGraph, ds: Dataset) -> pd.DataFrame:
    """Weakly connected components, numbered by size descending.

    Ties break on the smallest gid so the numbering is stable across runs.
    """
    seeds = set(ds.seeds)
    comps = sorted((sorted(c) for c in nx.weakly_connected_components(g)),
                   key=lambda c: (-len(c), c[0]))
    rows = []
    for cid, members in enumerate(comps):
        for gid in members:
            rows.append({"gid": gid, "component_id": cid,
                         "component_size": len(members),
                         "component_n_seed": len(seeds.intersection(members))})
    return pd.DataFrame(rows).sort_values("gid", kind="mergesort").reset_index(drop=True)


def annotate(g: nx.DiGraph, ds: Dataset) -> pd.DataFrame:
    """Per-node graph attributes: depth, seed flag, component, observability.

    The two observability flags encode the announced data flaws as data, so no
    downstream rule has to remember them:

    * `outflow_observed` — False at MAX_DEPTH, where the crawl stopped. Those
      nodes' onward transfers are *unknown*, not zero. This is the fix for the
      444 false sinks.
    * `inflow_reliable` — False for seeds, whose inflow from outside the sample
      is missing by construction, and for anything with no traced inflow.
    """
    max_depth = ds.max_depth
    df = ds.nodes.copy()
    df = df.merge(component_table(g, ds), on="gid", how="left")
    df["outflow_observed"] = df["depth"] < max_depth
    in_sum = dict(g.in_degree(weight="sum_kzt"))
    df["_in_sum"] = df["gid"].map(in_sum).fillna(0.0)
    df["inflow_reliable"] = (~df["is_seed"]) & (df["_in_sum"] > 0)
    return df.drop(columns=["_in_sum"])
