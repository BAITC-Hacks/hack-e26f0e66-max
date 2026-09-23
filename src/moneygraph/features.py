"""Structural and flow metrics per node (guideline §7).

Undefined is NaN, never a silent zero: a pass-through ratio that cannot be
computed must stay uncomputed, otherwise a node whose outflow was never traced
looks identical to one that genuinely kept the money.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import networkx as nx

from .io import Dataset


def flow_features(g: nx.DiGraph, ds: Dataset, base: pd.DataFrame) -> pd.DataFrame:
    """Degrees, turnover, pass ratio, fan metrics."""
    e = ds.edges
    seeds = set(ds.seeds)

    out = e.groupby("src").agg(out_deg=("dst", "nunique"),
                               out_sum=("sum_kzt", "sum"),
                               n_tx_out=("n_tx", "sum"))
    inn = e.groupby("dst").agg(in_deg=("src", "nunique"),
                               in_sum=("sum_kzt", "sum"),
                               n_tx_in=("n_tx", "sum"))
    seed_in = (e[e["src"].isin(seeds)].groupby("dst")
                .agg(seed_in_deg=("src", "nunique"), seed_in_sum=("sum_kzt", "sum")))

    df = base.set_index("gid").join([out, inn, seed_in]).reset_index()
    for col, fill in [("out_deg", 0), ("in_deg", 0), ("n_tx_out", 0), ("n_tx_in", 0),
                      ("seed_in_deg", 0), ("out_sum", 0.0), ("in_sum", 0.0),
                      ("seed_in_sum", 0.0)]:
        df[col] = df[col].fillna(fill)
    for col in ("out_deg", "in_deg", "n_tx_out", "n_tx_in", "seed_in_deg"):
        df[col] = df[col].astype("int64")

    # pass_ratio is defined only where BOTH sides are trustworthy.
    computable = df["inflow_reliable"] & df["outflow_observed"] & (df["in_sum"] > 0)
    df["pass_ratio"] = np.where(computable, df["out_sum"] / df["in_sum"].replace(0, np.nan), np.nan)
    df["pass_ratio_undefined_reason"] = np.select(
        [
            df["is_seed"],
            ~df["outflow_observed"],
            df["in_sum"] <= 0,
        ],
        [
            "seed: inflow understated by the outgoing-only export",
            "at max traversal depth: onward transfers were never traced",
            "no traced inflow",
        ],
        default="",
    )

    df["fan_in_share"] = np.where(
        (df["in_deg"] + df["out_deg"]) > 0,
        df["in_deg"] / (df["in_deg"] + df["out_deg"]).replace(0, np.nan), np.nan)
    df["retention"] = 1 - np.minimum(df["pass_ratio"], 1)
    df["avg_tx_in"] = np.where(df["n_tx_in"] > 0,
                               df["in_sum"] / df["n_tx_in"].replace(0, np.nan), np.nan)
    df["avg_tx_out"] = np.where(df["n_tx_out"] > 0,
                                df["out_sum"] / df["n_tx_out"].replace(0, np.nan), np.nan)
    return df


def centrality_features(g: nx.DiGraph, df: pd.DataFrame) -> pd.DataFrame:
    """PageRank and betweenness.

    PageRank is weighted by `log1p(sum_kzt)` rather than the raw amount: one
    4M transfer should not outrank forty 100k transfers by a factor of forty.
    Betweenness is exact — at ~2k nodes it costs under a second, and an
    approximation would be one more thing to defend.
    """
    h = g.copy()
    for _u, _v, data in h.edges(data=True):
        data["logw"] = float(np.log1p(data.get("sum_kzt", 0.0)))
    pr = nx.pagerank(h, weight="logw")
    # Betweenness wants distance, not affinity: a fatter pipe is a SHORTER hop.
    for _u, _v, data in h.edges(data=True):
        data["dist"] = 1.0 / (1.0 + data["logw"])
    bt = nx.betweenness_centrality(h, weight="dist", normalized=True)
    df = df.copy()
    df["pagerank"] = df["gid"].map(pr).fillna(0.0)
    df["betweenness"] = df["gid"].map(bt).fillna(0.0)
    return df
