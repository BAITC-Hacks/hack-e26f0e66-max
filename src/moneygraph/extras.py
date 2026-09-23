"""Optional analyses (brief §8). Deterministic, cheap, and each one switchable.

Four items from the optional list, all computed from structure, amounts and
dates alone:

* **recurring routes and return flows** — cycles where money comes back to a
  sender, and A→B→C chains that repeat over time;
* **network resilience** — what breaks when the top-N accounts are removed,
  measured against removing N random accounts, because "the network fragments"
  means nothing without that baseline;
* **anomaly flags** — amounts just above the reporting floor, round-number
  amounts, and accounts whose profile is extreme *for their own hop*;
* (the cut-off artifact and temporal patterns are handled in the core, in
  `roles.py` and `temporal.py` respectively.)

Nothing here changes a role, a score or a rank. These are **flags** presented
next to a node, exactly as the brief requires: "shown as flags, not roles".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import networkx as nx

from .io import Dataset


# ---------------------------------------------------------------------------
# recurring routes and return flows
# ---------------------------------------------------------------------------

def find_cycles(g: nx.DiGraph, length_bound: int = 5, limit: int = 200) -> list[dict]:
    """Directed cycles: money that comes back to someone who sent it.

    A cycle is not proof of anything on its own — mutual trade between two
    businesses is a two-cycle — but a longer one, carrying real amounts, is a
    pattern worth an analyst's attention.
    """
    out: list[dict] = []
    capped = False
    for cycle in nx.simple_cycles(g, length_bound=length_bound):
        if len(cycle) < 2:
            continue
        pairs = list(zip(cycle, cycle[1:] + cycle[:1]))
        amounts = [float(g[a][b].get("sum_kzt", 0.0)) for a, b in pairs]
        out.append({
            "length": len(cycle),
            "gids": [int(x) for x in cycle],
            "min_kzt": min(amounts) if amounts else 0.0,
            "total_kzt": sum(amounts),
        })
        if len(out) >= limit:
            capped = True
            break
    # The narrowest hop bounds how much could actually have gone round.
    ranked = sorted(out, key=lambda c: -c["min_kzt"])
    if capped and ranked:
        # Enumeration stopped at the cap. Saying "200 cycles" would state a
        # total we did not compute.
        ranked[0] = {**ranked[0], "_capped_at": limit}
    return ranked


def recurring_routes(ds: Dataset, min_repeats: int = 2, limit: int = 50) -> list[dict]:
    """A→B→C chains where B forwards on shortly after receiving, repeatedly.

    Requires transaction dates; without them the concept does not exist and an
    empty list is returned rather than a guess.
    """
    if not ds.has_transactions:
        return []
    tx = ds.tx
    joined = tx.merge(tx, left_on="dst", right_on="src", suffixes=("_in", "_out"))
    joined = joined[joined["dst_out"] != joined["src_in"]]          # not a bounce-back
    lag = (joined["date_out"] - joined["date_in"]).dt.days
    joined = joined[(lag >= 0) & (lag <= 3)]
    if joined.empty:
        return []
    grouped = (joined.groupby(["src_in", "src_out", "dst_out"])
                     .agg(times=("sum_kzt_in", "size"),
                          kzt_in=("sum_kzt_in", "sum"),
                          kzt_out=("sum_kzt_out", "sum"))
                     .reset_index())
    grouped = grouped[grouped["times"] >= min_repeats]
    grouped = grouped.sort_values(["times", "kzt_in"], ascending=False).head(limit)
    return [{"a": int(r.src_in), "b": int(r.src_out), "c": int(r.dst_out),
             "times": int(r.times), "kzt": float(r.kzt_in)}
            for r in grouped.itertuples(index=False)]


# ---------------------------------------------------------------------------
# network resilience
# ---------------------------------------------------------------------------

def resilience(g: nx.DiGraph, df: pd.DataFrame, ds: Dataset,
               remove_counts: list[int], seed: int = 42) -> dict:
    """Remove the top-N by priority, and N random accounts, and compare.

    The random baseline is the whole point. Any graph fragments if you delete
    enough of it; the question is whether removing *these* accounts does more
    damage than removing any N, and by how much.
    """
    rng = np.random.default_rng(seed)
    ranked = df.sort_values(["priority_score", "gid"],
                            ascending=[False, True])["gid"].astype(int).tolist()
    candidates = [gid for gid in ranked if gid in g]

    def measure(removed: list[int]) -> dict:
        h = g.copy()
        h.remove_nodes_from(removed)
        comps = list(nx.weakly_connected_components(h)) or [set()]
        largest = max((len(c) for c in comps), default=0)
        reachable = _seed_reachable_depth(h, ds, min_depth=3)
        return {"largest_component": largest,
                "n_components": len(comps),
                "accounts_reached_beyond_hop_2": reachable}

    base = measure([])
    rows = []
    for n in remove_counts:
        top = candidates[:n]
        after_top = measure(top)
        # Average of several random draws: one draw is noise.
        draws = []
        for _ in range(5):
            pick = rng.choice(candidates, size=min(n, len(candidates)),
                              replace=False).tolist()
            draws.append(measure([int(x) for x in pick]))
        after_rand = {k: float(np.mean([d[k] for d in draws])) for k in base}
        rows.append({
            "n_removed": n,
            "targeted": after_top,
            "random_baseline": after_rand,
            "largest_component_drop_pct": round(
                100 * (base["largest_component"] - after_top["largest_component"])
                / max(base["largest_component"], 1), 1),
            "random_drop_pct": round(
                100 * (base["largest_component"] - after_rand["largest_component"])
                / max(base["largest_component"], 1), 1),
        })
    return {"baseline": base, "removals": rows}


def _seed_reachable_depth(h: nx.DiGraph, ds: Dataset, min_depth: int) -> int:
    """How many accounts seed money can still reach at `min_depth` hops or more."""
    from collections import deque

    seeds = [int(s) for s in ds.seeds if s in h]
    seen: dict[int, int] = {}
    q = deque((s, 0) for s in seeds)
    for s in seeds:
        seen[s] = 0
    while q:
        node, d = q.popleft()
        for nxt in h.successors(node):
            if nxt not in seen:
                seen[nxt] = d + 1
                q.append((nxt, d + 1))
    return sum(1 for d in seen.values() if d >= min_depth)


# ---------------------------------------------------------------------------
# anomaly flags
# ---------------------------------------------------------------------------

def anomaly_flags(df: pd.DataFrame, ds: Dataset, cfg: dict) -> pd.DataFrame:
    """Per-account flags. Flags, never roles (brief §8).

    Three signals, all interpretable:

    * `flag_near_threshold` — a large share of this account's transfers sit just
      above the reporting floor, which is what structuring looks like from the
      side that *is* visible;
    * `flag_round_amounts` — a large share are round numbers, unusual for
      genuine commerce;
    * `flag_extreme_for_hop` — the account's inflow is extreme compared with
       other accounts *at the same hop*, which is the only fair comparison when
       depth drives so much of the distribution.
    """
    acfg = (cfg.get("extras", {}) or {}).get("anomalies", {}) or {}
    floor = (cfg.get("expected", {}) or {}).get("min_amount_kzt") or 0
    near_ceiling = float(acfg.get("near_threshold_kzt", floor * 1.1 or 5500))
    modulo = float(acfg.get("round_amount_modulo", 100000))
    z_cut = float(acfg.get("z_score", 3.0))

    out = df[["gid"]].copy()

    # Built by mapping rather than merging: merging a Series whose name already
    # exists on the frame silently produces _x/_y columns, and the flags then
    # read from whichever one survives.
    near_share = pd.Series(dtype="float64")
    round_share = pd.Series(dtype="float64")
    if ds.has_transactions and floor:
        tx = ds.tx
        per = tx.groupby("src").agg(
            n=("sum_kzt", "size"),
            near=("sum_kzt", lambda s: int(((s >= floor) & (s <= near_ceiling)).sum())),
            round_=("sum_kzt", lambda s: int((s % modulo == 0).sum())))
        per = per[per["n"] >= 3]          # a share out of two transfers is noise
        near_share = per["near"] / per["n"]
        round_share = per["round_"] / per["n"]

    out["near_threshold_share"] = out["gid"].map(near_share).round(3)
    out["round_amount_share"] = out["gid"].map(round_share).round(3)
    out["flag_near_threshold"] = out["near_threshold_share"].fillna(0) >= 0.5
    out["flag_round_amounts"] = out["round_amount_share"].fillna(0) >= 0.8

    # Extreme for its own hop: depth drives the distribution, so comparing an
    # account at hop 1 with one at hop 4 would flag the hop, not the account.
    z = (df.groupby("depth")["in_sum"]
           .transform(lambda s: (s - s.mean()) / (s.std(ddof=0) or np.nan)))
    out["inflow_z_for_hop"] = np.round(z.fillna(0.0), 2)
    out["flag_extreme_for_hop"] = out["inflow_z_for_hop"].abs() >= z_cut
    out["n_flags"] = out[["flag_near_threshold", "flag_round_amounts",
                          "flag_extreme_for_hop"]].sum(axis=1).astype("int64")
    return out


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def run_extras(g: nx.DiGraph, ds: Dataset, df: pd.DataFrame,
               cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Run whichever optional analyses are enabled. Returns (df, report)."""
    ex = cfg.get("extras", {}) or {}
    report: dict = {}

    if (ex.get("anomalies") or {}).get("enabled"):
        flags = anomaly_flags(df, ds, cfg)
        df = df.drop(columns=[c for c in flags.columns if c != "gid"
                              and c in df.columns])
        df = df.merge(flags, on="gid", how="left")
        report["anomalies"] = {
            "near_threshold": int(df["flag_near_threshold"].fillna(False).sum()),
            "round_amounts": int(df["flag_round_amounts"].fillna(False).sum()),
            "extreme_for_hop": int(df["flag_extreme_for_hop"].fillna(False).sum()),
            "any_flag": int((df["n_flags"].fillna(0) > 0).sum()),
        }

    cy = ex.get("cycles") or {}
    if cy.get("enabled"):
        limit = int(cy.get("limit", 200))
        cycles = find_cycles(g, int(cy.get("length_bound", 5)), limit=limit)
        routes = recurring_routes(ds)
        report["cycles"] = {"n_cycles": len(cycles), "capped": len(cycles) >= limit,
                            "limit": limit, "top": cycles[:10]}
        report["recurring_routes"] = {"n_routes": len(routes),
                                      "capped": len(routes) >= 50,
                                      "top": routes[:10]}

    rs = ex.get("resilience") or {}
    if rs.get("enabled"):
        report["resilience"] = resilience(
            g, df, ds, [int(x) for x in rs.get("remove_top_n", [5, 10, 20])],
            seed=int(cfg.get("seed", 42)))

    return df, report


def render_report(report: dict) -> str:
    """`extras_report.md` — the optional findings, in words."""
    md = ["# Optional analyses", "",
          "Computed from structure, amounts and dates only. **None of this "
          "changes a role, a score or a rank** — these are flags and context "
          "shown next to an account, as the brief requires.", ""]

    a = report.get("anomalies")
    if a:
        md += ["## Anomaly flags", "",
               f"- **{a['near_threshold']}** accounts send mostly amounts just "
               f"above the reporting floor. That is what structuring looks like "
               f"from the side that is visible; below the floor nothing is.",
               f"- **{a['round_amounts']}** accounts send almost entirely "
               f"round-number amounts.",
               f"- **{a['extreme_for_hop']}** accounts have an inflow that is "
               f"extreme *for their own hop* — the only fair comparison, since "
               f"hop drives most of the distribution.",
               f"- **{a['any_flag']}** accounts carry at least one flag.", ""]

    c = report.get("cycles")
    if c:
        count = (f"**At least {c['n_cycles']}**" if c.get("capped")
                 else f"**{c['n_cycles']}**")
        md += ["## Return flows (cycles)", "",
               f"{count} directed cycles within the length bound — money "
               f"returning to someone who sent it. A two-cycle is ordinary "
               f"mutual settlement; longer ones carrying real amounts are worth "
               f"a look.", ""]
        if c.get("capped"):
            md += [f"> Enumeration stopped at {c['limit']} cycles, so this is a "
                   f"lower bound, not a total. The ones listed are the ones "
                   f"whose narrowest hop carries the most money.", ""]
        if c["top"]:
            md += ["| Length | Accounts | Narrowest hop |", "|---:|---|---:|"]
            for cy in c["top"][:5]:
                md.append(f"| {cy['length']} | {' → '.join(str(g) for g in cy['gids'])} "
                          f"| {cy['min_kzt']:,.0f} KZT |")
            md.append("")

    r = report.get("recurring_routes")
    if r:
        count = (f"**At least {r['n_routes']}**" if r.get("capped")
                 else f"**{r['n_routes']}**")
        md += ["## Recurring routes", "",
               f"{count} A→B→C chains where B forwarded within three days of "
               f"receiving, more than once."
               + (" Listing is capped; this is a lower bound."
                  if r.get("capped") else ""), ""]
        if r["top"]:
            md += ["| Route | Times | Amount |", "|---|---:|---:|"]
            for rt in r["top"][:5]:
                md.append(f"| {rt['a']} → {rt['b']} → {rt['c']} | {rt['times']} "
                          f"| {rt['kzt']:,.0f} KZT |")
            md.append("")

    res = report.get("resilience")
    if res:
        base = res["baseline"]
        md += ["## Network resilience", "",
               f"Baseline: largest connected component **{base['largest_component']}** "
               f"accounts, **{base['n_components']}** components, "
               f"**{base['accounts_reached_beyond_hop_2']}** accounts still "
               f"reachable from a seed at three hops or more.", "",
               "Removing the top-N by priority, against removing N accounts at "
               "random. The baseline is the point: any graph fragments if enough "
               "of it is deleted, so the question is whether removing *these* "
               "accounts does more damage than removing any N.", "",
               "| Removed | Largest component | Drop | Random drop | Advantage |",
               "|---:|---:|---:|---:|---:|"]
            
        for row in res["removals"]:
            adv = row["largest_component_drop_pct"] - row["random_drop_pct"]
            md.append(f"| {row['n_removed']} | {row['targeted']['largest_component']} "
                      f"| {row['largest_component_drop_pct']}% "
                      f"| {row['random_drop_pct']}% | {adv:+.1f} pp |")
        md.append("")
        md.append("A positive advantage means the priority ranking is finding "
                  "accounts that actually hold the network together.")
    return "\n".join(md) + "\n"
