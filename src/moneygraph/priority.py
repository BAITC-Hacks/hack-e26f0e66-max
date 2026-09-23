"""Priority score (guideline §10).

A weighted sum of percentile ranks, not of raw values. Percentiles matter: raw
turnover spans four orders of magnitude, so a single large transfer would
otherwise dominate every other signal. Ranking first makes the weights mean
what they say.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _pct(series: pd.Series) -> pd.Series:
    """Percentile rank in [0, 1]; NaN and all-equal inputs degrade to 0."""
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if s.nunique() <= 1:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return s.rank(pct=True, method="average")


def priority_score(df: pd.DataFrame, cfg: dict, max_depth: int) -> pd.DataFrame:
    p = cfg["priority"]
    w = p["weights"]
    df = df.copy()

    role_w = df["role"].map(p["role_weight"]).fillna(0.05)
    cluster_density = (df.groupby("cluster_id")["is_seed"]
                         .transform("mean").fillna(0.0))

    components = {
        "role": role_w,
        "seed_money": _pct(df["seed_kzt_attributed"]),
        "seed_reach": _pct(df["seed_reach"]),
        "payers": _pct(df["in_deg"]),
        "cluster": _pct(cluster_density),
    }
    score = sum(float(w[k]) * v for k, v in components.items())

    # Keep each component so the viewer can show what drove a node's rank, and
    # so `why` text quotes the real top contributors rather than a guess.
    for name, values in components.items():
        df[f"prio_{name}"] = np.round(np.asarray(values, dtype=float), 4)
        df[f"prio_{name}_w"] = float(w[name]) * np.asarray(values, dtype=float)

    adjustments = pd.Series([""] * len(df), index=df.index, dtype=object)

    # Law enforcement already knows the 81 seeds; the analyst's value is above them.
    discount = float(p["seed_discount"])
    score = np.where(df["is_seed"], score * discount, score)
    adjustments = np.where(df["is_seed"],
                           f"x{discount} known seed (already identified)", adjustments)

    # A collector or controller on the traversal frontier is the best candidate
    # for a hop-5 data request, because the chain probably continues past it.
    boost = float(p["cutoff_boost"])
    frontier = (df["depth"] == max_depth) & df["role"].isin(["consolidator", "coordinator"])
    score = np.where(frontier, np.minimum(score * boost, 1.0), score)
    adjustments = np.where(
        frontier,
        np.where(adjustments == "", f"x{boost} at traversal frontier",
                 adjustments + f"; x{boost} at traversal frontier"),
        adjustments)

    df["priority_score"] = np.clip(np.round(score.astype(float), 6), 0.0, 1.0)
    df["priority_adjustments"] = adjustments
    return df


def top_contributors(row, cfg: dict, k: int = 3) -> list[str]:
    """The k largest weighted components of this node's score, by name."""
    w = cfg["priority"]["weights"]
    pairs = [(name, float(getattr(row, f"prio_{name}_w", 0.0))) for name in w]
    pairs.sort(key=lambda kv: -kv[1])
    return [name for name, value in pairs[:k] if value > 0]


def rank_top_nodes(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The ranked shortlist. Ties break on gid so two runs agree exactly."""
    n = int(cfg["priority"]["top_n"])
    ranked = df.sort_values(["priority_score", "gid"], ascending=[False, True],
                            kind="mergesort").head(n).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    return ranked
