"""Deterministic graph tools — the only source of fact for the analyst agent.

Every function here answers a question directly from the exported artifacts.
The LLM's job is to pick the right function and phrase the result; it never
supplies a number of its own. That is what makes the natural-language answer
auditable: the viewer shows the tool calls and their raw output next to the
answer, so the analyst can check every claim.

The same functions back the no-key fallback form in the viewer, so the feature
works offline — only the phrasing is lost.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class GraphTools:
    """Bound to one run's outputs. Read-only."""

    def __init__(self, nodes: pd.DataFrame, edges: pd.DataFrame,
                 clusters: pd.DataFrame, tx: pd.DataFrame | None = None) -> None:
        self.nodes = nodes.set_index("gid", drop=False)
        self.edges = edges
        self.clusters = clusters
        self.tx = tx if tx is not None else pd.DataFrame()

    # ------------------------------------------------------------- lookups

    def node_card(self, gid: int) -> dict[str, Any]:
        """Everything known about one account."""
        gid = int(gid)
        if gid not in self.nodes.index:
            return {"error": f"gid {gid} is not in this dataset"}
        r = self.nodes.loc[gid]
        return {
            "gid": gid,
            "role": r["role"],
            "role_score": round(float(r["role_score"]), 3),
            "priority_score": round(float(r["priority_score"]), 4),
            "cluster_id": int(r["cluster_id"]),
            "depth": int(r["depth"]),
            "is_seed": bool(r["is_seed"]),
            "in_deg": int(r["in_deg"]), "out_deg": int(r["out_deg"]),
            "in_sum_kzt": float(r["in_sum"]), "out_sum_kzt": float(r["out_sum"]),
            "seed_reach": int(r.get("seed_reach", 0)),
            "seed_kzt_attributed": float(r.get("seed_kzt_attributed", 0.0)),
            "evidence": r["evidence"],
            "secondary_roles": r.get("secondary_roles", ""),
            "outflow_observed": bool(r.get("outflow_observed", True)),
        }

    def payers(self, gids: list[int]) -> list[dict]:
        """Who paid these accounts, with amounts."""
        gids = [int(g) for g in gids]
        sel = self.edges[self.edges["dst"].isin(gids)]
        return self._with_roles(sel, "src").to_dict("records")

    def recipients(self, gids: list[int]) -> list[dict]:
        """Who these accounts paid, with amounts."""
        gids = [int(g) for g in gids]
        sel = self.edges[self.edges["src"].isin(gids)]
        return self._with_roles(sel, "dst").to_dict("records")

    def common_downstream(self, gids: list[int], max_hops: int = 2) -> list[dict]:
        """Accounts reachable from ALL of the given gids — answers
        "who collects money from these five?"."""
        gids = [int(g) for g in gids]
        reach_sets = [self._reachable(g, max_hops) for g in gids]
        if not reach_sets:
            return []
        common = set.intersection(*reach_sets) - set(gids)
        rows = [self.node_card(g) for g in sorted(common)]
        return sorted(rows, key=lambda r: -r.get("priority_score", 0))[:25]

    def path(self, src: int, dst: int, max_hops: int = 6) -> dict:
        """The shortest directed money path between two accounts."""
        import networkx as nx

        g = nx.DiGraph()
        g.add_edges_from(zip(self.edges["src"], self.edges["dst"]))
        src, dst = int(src), int(dst)
        if src not in g or dst not in g:
            return {"found": False, "reason": "one of the accounts has no edges"}
        try:
            nodes = nx.shortest_path(g, src, dst)
        except nx.NetworkXNoPath:
            return {"found": False, "reason": "no directed path in the export"}
        if len(nodes) - 1 > max_hops:
            return {"found": False, "reason": f"path longer than {max_hops} hops"}
        hops = []
        for a, b in zip(nodes, nodes[1:]):
            e = self.edges[(self.edges["src"] == a) & (self.edges["dst"] == b)].iloc[0]
            hops.append({"src": int(a), "dst": int(b),
                         "sum_kzt": float(e["sum_kzt"]), "n_tx": int(e["n_tx"])})
        return {"found": True, "n_hops": len(hops), "hops": hops}

    def cluster_summary(self, cluster_id: int) -> dict:
        """Size, seeds, turnover, hypothesis and the cluster's top accounts."""
        cid = int(cluster_id)
        row = self.clusters[self.clusters["cluster_id"] == cid]
        if row.empty:
            return {"error": f"cluster {cid} does not exist"}
        r = row.iloc[0]
        members = self.nodes[self.nodes["cluster_id"] == cid]
        return {
            "cluster_id": cid,
            "n_nodes": int(r["n_nodes"]), "n_seed": int(r["n_seed"]),
            "sum_kzt_internal": float(r["sum_kzt_internal"]),
            "hypothesis": r["hypothesis"],
            "role_counts": members["role"].value_counts().to_dict(),
            "top_gids": [int(g) for g in str(r["top_gids"]).split(";") if g],
        }

    def top_nodes(self, n: int = 10, role: str | None = None) -> list[dict]:
        """The priority shortlist, optionally filtered to one role."""
        sel = self.nodes if role is None else self.nodes[self.nodes["role"] == role]
        top = sel.nlargest(int(n), "priority_score")
        return [self.node_card(int(g)) for g in top["gid"]]

    def search_nodes(self, role: str | None = None, min_in_deg: int | None = None,
                     min_out_deg: int | None = None, is_seed: bool | None = None,
                     depth: int | None = None, limit: int = 25) -> list[dict]:
        """Filter accounts by structural criteria."""
        sel = self.nodes
        if role is not None:
            sel = sel[sel["role"] == role]
        if min_in_deg is not None:
            sel = sel[sel["in_deg"] >= int(min_in_deg)]
        if min_out_deg is not None:
            sel = sel[sel["out_deg"] >= int(min_out_deg)]
        if is_seed is not None:
            sel = sel[sel["is_seed"] == bool(is_seed)]
        if depth is not None:
            sel = sel[sel["depth"] == int(depth)]
        top = sel.nlargest(int(limit), "priority_score")
        return [self.node_card(int(g)) for g in top["gid"]]

    def dataset_overview(self) -> dict:
        """Totals, so the agent never has to guess the shape of the data."""
        return {
            "n_nodes": int(len(self.nodes)),
            "n_edges": int(len(self.edges)),
            "n_seeds": int(self.nodes["is_seed"].sum()),
            "max_depth": int(self.nodes["depth"].max()),
            "total_turnover_kzt": float(self.edges["sum_kzt"].sum()),
            "role_counts": self.nodes["role"].value_counts().to_dict(),
            "n_clusters": int(len(self.clusters)),
        }

    # ------------------------------------------------------------ internals

    def _with_roles(self, sel: pd.DataFrame, col: str) -> pd.DataFrame:
        """Annotate edges with the counterparty's role.

        Built column by column rather than by selecting `[col, "src", "dst", …]`:
        `col` is always one of src/dst, so that selection produced a frame with a
        duplicated column name, and `out[col]` then returned a DataFrame rather
        than a Series — which broke `.map` and took every caller down with it.
        """
        if sel.empty:
            return pd.DataFrame(columns=["src", "dst", "sum_kzt", "n_tx",
                                         "role", "is_seed"])
        out = pd.DataFrame({
            "src": sel["src"].astype("int64"),
            "dst": sel["dst"].astype("int64"),
            "sum_kzt": sel["sum_kzt"].astype("float64"),
            "n_tx": sel["n_tx"].astype("int64"),
        })
        counterparty = out[col]
        out["role"] = counterparty.map(self.nodes["role"]).fillna("unknown")
        out["is_seed"] = counterparty.map(self.nodes["is_seed"]).fillna(False)
        return out.sort_values("sum_kzt", ascending=False).head(50).reset_index(drop=True)

    def _reachable(self, gid: int, max_hops: int) -> set[int]:
        from collections import deque

        adj: dict[int, list[int]] = {}
        for s, d in zip(self.edges["src"], self.edges["dst"]):
            adj.setdefault(int(s), []).append(int(d))
        seen, q = {int(gid)}, deque([(int(gid), 0)])
        while q:
            cur, hop = q.popleft()
            if hop >= max_hops:
                continue
            for nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, hop + 1))
        return seen

    # ------------------------------------------------------- tool schemas

    def dispatch(self, name: str, args: dict) -> Any:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name == "dispatch":
            return {"error": f"unknown tool '{name}'"}
        return fn(**args)


def tool_schemas() -> list[dict]:
    """OpenAI function schemas for the tools above."""
    def fn(name, description, properties, required=None):
        return {"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required or []}}}

    gid_list = {"type": "array", "items": {"type": "integer"},
                "description": "account identifiers (gids)"}
    return [
        fn("dataset_overview", "Totals for the whole dataset: node and edge counts, "
           "seeds, role distribution, turnover. Call this first if unsure of scale.", {}),
        fn("node_card", "Everything known about one account: role, scores, cluster, "
           "flows and the evidence sentence.",
           {"gid": {"type": "integer"}}, ["gid"]),
        fn("payers", "Who paid the given accounts, with amounts and the payer's role.",
           {"gids": gid_list}, ["gids"]),
        fn("recipients", "Who the given accounts paid, with amounts and the "
           "recipient's role.", {"gids": gid_list}, ["gids"]),
        fn("common_downstream", "Accounts reachable from ALL the given accounts — "
           "use for 'who collects money from these?'.",
           {"gids": gid_list,
            "max_hops": {"type": "integer", "description": "default 2"}}, ["gids"]),
        fn("path", "Shortest directed money path from one account to another.",
           {"src": {"type": "integer"}, "dst": {"type": "integer"}}, ["src", "dst"]),
        fn("cluster_summary", "Size, seed count, turnover, hypothesis and top "
           "accounts of one cluster.",
           {"cluster_id": {"type": "integer"}}, ["cluster_id"]),
        fn("top_nodes", "The priority shortlist, optionally filtered to one role.",
           {"n": {"type": "integer"},
            "role": {"type": "string",
                     "enum": ["coordinator", "consolidator", "distributor",
                              "transit", "terminal", "cutoff", "peripheral"]}}),
        fn("search_nodes", "Find accounts by structural criteria.",
           {"role": {"type": "string"}, "min_in_deg": {"type": "integer"},
            "min_out_deg": {"type": "integer"}, "is_seed": {"type": "boolean"},
            "depth": {"type": "integer"}, "limit": {"type": "integer"}}),
    ]
