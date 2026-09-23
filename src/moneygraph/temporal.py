"""Temporal features (task guidelines §7, brief §8 "temporal patterns").

Timing is what separates "balanced in and out" from "money did not stop here".
Two accounts can have an identical pass-through ratio while one forwards within
a day and the other sits on the funds for three weeks.

When no transaction-level file was supplied every column here is NaN, and the
evidence text says the timing is unknown rather than implying it was checked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .io import Dataset

COLUMNS = ["median_lag_days", "fast_pass_share", "max_payers_same_day",
           "active_days", "first_seen", "last_seen"]


def temporal_features(ds: Dataset, df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = df.copy()
    if not ds.has_transactions:
        for c in COLUMNS:
            df[c] = np.nan
        df["temporal_available"] = False
        return df

    max_lag = int((cfg["roles"]["transit"]["max_lag_days"]))
    tx = ds.tx
    df["temporal_available"] = True

    inflow = tx.rename(columns={"dst": "gid"})[["gid", "date", "sum_kzt"]]
    outflow = tx.rename(columns={"src": "gid"})[["gid", "date", "sum_kzt"]]

    # --- activity span -----------------------------------------------------
    both = pd.concat([inflow, outflow], ignore_index=True)
    span = both.groupby("gid").agg(active_days=("date", "nunique"),
                                   first_seen=("date", "min"),
                                   last_seen=("date", "max"))

    # --- synchronized collection -------------------------------------------
    # The most distinct payers that paid a node on one calendar day. Several
    # couriers depositing on the same day is a structural signal, not volume.
    same_day = (tx.groupby(["dst", "date"])["src"].nunique()
                  .groupby("dst").max().rename("max_payers_same_day"))

    # --- pass-through lag ---------------------------------------------------
    # For each outgoing transfer, how long since the most recent inflow. A
    # merge_asof on sorted dates does this in one pass per node.
    lag = _outflow_lag(inflow, outflow)
    if lag.empty:
        agg_lag = pd.DataFrame(columns=["median_lag_days", "fast_pass_share"])
    else:
        lag["fast"] = lag["lag_days"] <= max_lag
        agg_lag = lag.groupby("gid").apply(
            lambda x: pd.Series({
                "median_lag_days": x["lag_days"].median(),
                # Share by AMOUNT, not by count: forwarding 95% of the money
                # fast and 5% slowly is transit; the reverse is not.
                "fast_pass_share": (x.loc[x["fast"], "sum_kzt"].sum()
                                    / x["sum_kzt"].sum()) if x["sum_kzt"].sum() > 0 else np.nan,
            }),
            include_groups=False,
        )

    out = df.set_index("gid").join([span, same_day, agg_lag]).reset_index()
    out["active_days"] = out["active_days"].fillna(0).astype("int64")
    out["max_payers_same_day"] = out["max_payers_same_day"].fillna(0).astype("int64")
    return out


def _outflow_lag(inflow: pd.DataFrame, outflow: pd.DataFrame) -> pd.DataFrame:
    """Days between each outgoing transfer and the nearest preceding inflow."""
    if inflow.empty or outflow.empty:
        return pd.DataFrame(columns=["gid", "lag_days", "sum_kzt"])
    ins = (inflow.sort_values(["date", "gid"], kind="mergesort")
                 .rename(columns={"date": "in_date"})[["gid", "in_date"]])
    outs = outflow.sort_values(["date", "gid"], kind="mergesort")
    merged = pd.merge_asof(
        outs, ins, left_on="date", right_on="in_date", by="gid",
        direction="backward", allow_exact_matches=True,
    )
    merged = merged.dropna(subset=["in_date"])
    if merged.empty:
        return pd.DataFrame(columns=["gid", "lag_days", "sum_kzt"])
    merged["lag_days"] = (merged["date"] - merged["in_date"]).dt.days
    return merged[["gid", "lag_days", "sum_kzt"]]
