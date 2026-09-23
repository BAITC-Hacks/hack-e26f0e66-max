"""Loading and schema validation for the organizers' parquet files.

The three files under ``data/`` are read-only inputs. This module is the only
place that touches them, so a change in the organizers' schema has exactly one
landing site.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

# Column contracts taken from data/README.md. Validation is by presence and
# coercible dtype, not by exact dtype string: pyarrow versions differ on
# whether `depth` arrives as int8 or int64, and that difference is harmless.
EDGE_COLUMNS = ["src", "dst", "sum_kzt", "n_tx", "depth"]
NODE_COLUMNS = ["gid", "depth", "is_seed"]
TX_COLUMNS = ["src", "dst", "date", "sum_kzt"]


@dataclass(frozen=True)
class Dataset:
    """The three organizer tables, validated and normalized."""

    nodes: pd.DataFrame
    edges: pd.DataFrame
    tx: pd.DataFrame

    @property
    def max_depth(self) -> int:
        """Traversal depth read from the data, never hardcoded (guideline §6)."""
        return int(self.nodes["depth"].max())

    @property
    def seeds(self) -> pd.Index:
        return pd.Index(self.nodes.loc[self.nodes["is_seed"], "gid"], name="gid")


def _require_columns(df: pd.DataFrame, expected: list[str], name: str) -> None:
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(
            f"{name}.parquet is missing required column(s) {missing}; "
            f"found {list(df.columns)}"
        )


def load_dataset(data_dir: str | Path) -> Dataset:
    """Read the three parquet files and normalize types.

    Normalization is deliberately minimal: gids stay integers, amounts become
    float, dates become datetime64. Nothing is filtered or deduplicated here —
    duplicates and self-loops are findings for the profile, not something to
    silently clean away.
    """
    data_dir = Path(data_dir)
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    edges = pd.read_parquet(data_dir / "edges.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")

    _require_columns(nodes, NODE_COLUMNS, "nodes")
    _require_columns(edges, EDGE_COLUMNS, "edges")
    _require_columns(tx, TX_COLUMNS, "transactions")

    nodes = nodes.copy()
    nodes["gid"] = nodes["gid"].astype("int64")
    nodes["depth"] = nodes["depth"].astype("int64")
    nodes["is_seed"] = nodes["is_seed"].astype(bool)
    # Deterministic row order everywhere downstream.
    nodes = nodes.sort_values("gid", kind="mergesort").reset_index(drop=True)

    edges = edges.copy()
    edges["src"] = edges["src"].astype("int64")
    edges["dst"] = edges["dst"].astype("int64")
    edges["sum_kzt"] = edges["sum_kzt"].astype("float64")
    edges["n_tx"] = edges["n_tx"].astype("int64")
    edges["depth"] = edges["depth"].astype("int64")
    edges = edges.sort_values(["src", "dst"], kind="mergesort").reset_index(drop=True)

    tx = tx.copy()
    tx["src"] = tx["src"].astype("int64")
    tx["dst"] = tx["dst"].astype("int64")
    tx["sum_kzt"] = tx["sum_kzt"].astype("float64")
    tx["date"] = pd.to_datetime(tx["date"])
    tx = tx.sort_values(["date", "src", "dst", "sum_kzt"], kind="mergesort").reset_index(
        drop=True
    )

    return Dataset(nodes=nodes, edges=edges, tx=tx)


def load_config(path: str | Path = "config.yaml") -> dict:
    """Load every threshold and weight. No magic numbers live in the code."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
