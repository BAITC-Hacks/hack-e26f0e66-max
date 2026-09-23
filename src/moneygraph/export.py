"""Write the deliverables (brief §5, guideline §5).

Column order and dtypes are fixed because the jury checks them mechanically.
Extra columns are allowed and useful, so `node_features.parquet` carries every
metric and the full rule trace for the viewer — but the three CSVs lead with
exactly the required columns, in exactly the required order.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

NODES_ROLES_COLUMNS = ["gid", "role", "role_score", "cluster_id",
                       "priority_score", "evidence"]
CLUSTERS_COLUMNS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal",
                    "top_gids", "hypothesis"]
TOP_COLUMNS = ["rank", "gid", "role", "priority_score", "why"]

# Carried into nodes_roles.csv after the required six, so the file is useful on
# its own without breaking the fixed schema.
CONTEXT_COLUMNS = ["depth", "is_seed", "in_deg", "out_deg", "in_sum", "out_sum",
                   "pass_ratio", "seed_reach", "seed_kzt_attributed",
                   "secondary_roles", "outflow_observed", "inflow_reliable"]


def write_nodes_roles(df: pd.DataFrame, out_dir: Path) -> Path:
    cols = NODES_ROLES_COLUMNS + [c for c in CONTEXT_COLUMNS if c in df.columns]
    out = df[cols].copy()
    out["gid"] = out["gid"].astype("int64")
    out["cluster_id"] = out["cluster_id"].astype("int64")
    out["role_score"] = out["role_score"].astype("float64").round(4)
    out["priority_score"] = out["priority_score"].astype("float64").round(6)
    out["evidence"] = out["evidence"].astype(str)
    out = out.sort_values("gid", kind="mergesort").reset_index(drop=True)
    path = out_dir / "nodes_roles.csv"
    out.to_csv(path, index=False)
    return path


def write_clusters(df: pd.DataFrame, out_dir: Path) -> Path:
    out = df[CLUSTERS_COLUMNS].copy()
    out["cluster_id"] = out["cluster_id"].astype("int64")
    out["n_nodes"] = out["n_nodes"].astype("int64")
    out["n_seed"] = out["n_seed"].astype("int64")
    out["sum_kzt_internal"] = out["sum_kzt_internal"].astype("float64").round(2)
    out = out.sort_values("cluster_id", kind="mergesort").reset_index(drop=True)
    path = out_dir / "clusters.csv"
    out.to_csv(path, index=False)
    return path


def write_top_nodes(df: pd.DataFrame, out_dir: Path) -> Path:
    out = df[TOP_COLUMNS].copy()
    out["rank"] = out["rank"].astype("int64")
    out["gid"] = out["gid"].astype("int64")
    out["priority_score"] = out["priority_score"].astype("float64").round(6)
    path = out_dir / "top_nodes.csv"
    out.to_csv(path, index=False)
    return path


def write_features(df: pd.DataFrame, traces: dict, out_dir: Path) -> Path:
    """Every metric plus the serialized rule trace — this is what the viewer reads."""
    out = df.drop(columns=[c for c in ("trace_obj",) if c in df.columns]).copy()
    out["rule_trace"] = out["gid"].map(
        lambda g: json.dumps(traces[int(g)].to_dict(), ensure_ascii=False)
        if int(g) in traces else "{}")
    out = out.sort_values("gid", kind="mergesort").reset_index(drop=True)
    path = out_dir / "node_features.parquet"
    out.to_parquet(path, index=False)
    return path


def write_edges(edges: pd.DataFrame, out_dir: Path) -> Path:
    """The viewer needs the edges too, and must never re-read `data/`."""
    path = out_dir / "graph_edges.parquet"
    edges.to_parquet(path, index=False)
    return path


def write_text(name: str, text: str, out_dir: Path) -> Path:
    path = out_dir / name
    path.write_text(text, encoding="utf-8")
    return path
