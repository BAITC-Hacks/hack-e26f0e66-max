"""Export everything the standalone web interface needs, as one JSON file.

The Gradio app renders server-side; the standalone frontend is a static page
that fetches this file and does the rest in the browser. Both read the same
exported artifacts, so they can never disagree about a number.

Evidence, `why` and cluster hypotheses are emitted in **all three languages**
at build time, rebuilt from each node's rule trace rather than translated, so
switching language in the browser costs nothing and cannot drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .i18n import (EVIDENCE, LANGUAGES, MACHINE_TRANSLATED, ROLE_MEANING,
                   ROLE_NAMES, TAB_GUIDE, UI, evidence_from_trace,
                   hypothesis_from_members, why_from_row)

# Node fields the browser needs. Everything else stays in the parquet.
NODE_FIELDS = [
    "gid", "role", "role_score", "cluster_id", "priority_score", "depth",
    "is_seed", "in_deg", "out_deg", "in_sum", "out_sum", "pass_ratio",
    "seed_reach", "seed_kzt_attributed", "secondary_roles",
    "outflow_observed", "inflow_reliable", "n_flags", "inflow_z_for_hop",
    "flag_near_threshold", "flag_round_amounts", "flag_extreme_for_hop",
    "priority_adjustments", "critic_caveat",
]


def _clean(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if np.isnan(f) else round(f, 6)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


def build(out_dir: str | Path, cfg: dict) -> Path:
    """Write `web_data.json`. Returns its path."""
    out_dir = Path(out_dir)
    nodes = pd.read_parquet(out_dir / "node_features.parquet")
    edges = pd.read_parquet(out_dir / "graph_edges.parquet")
    clusters = pd.read_csv(out_dir / "clusters.csv")
    top = pd.read_csv(out_dir / "top_nodes.csv")
    weights = cfg["priority"]["weights"]

    traces: dict[int, dict] = {}
    for gid, raw in zip(nodes["gid"], nodes["rule_trace"]):
        try:
            traces[int(gid)] = json.loads(raw)
        except (TypeError, ValueError):
            traces[int(gid)] = {}

    langs = list(LANGUAGES)
    node_rows = []
    for row in nodes.to_dict("records"):
        gid = int(row["gid"])
        tr = traces.get(gid, {})
        entry = {f: _clean(row.get(f)) for f in NODE_FIELDS if f in row or f == "gid"}
        entry["gid"] = gid
        entry["trace"] = tr
        entry["evidence"] = {
            l: evidence_from_trace(tr, row, l,
                                   limit=int(cfg["evidence"]["max_chars"]))
            for l in langs}
        node_rows.append(entry)

    top_rows = []
    by_gid = nodes.set_index("gid")
    for r in top.to_dict("records"):
        gid = int(r["gid"])
        src = by_gid.loc[gid].to_dict() if gid in by_gid.index else {}
        src["gid"] = gid
        top_rows.append({
            "rank": int(r["rank"]), "gid": gid, "role": r["role"],
            "priority_score": float(r["priority_score"]),
            "why": {l: why_from_row(src, weights, l) for l in langs},
        })

    cluster_rows = []
    for r in clusters.to_dict("records"):
        cid = int(r["cluster_id"])
        members = nodes[nodes["cluster_id"] == cid]
        cluster_rows.append({
            "cluster_id": cid, "n_nodes": int(r["n_nodes"]),
            "n_seed": int(r["n_seed"]),
            "sum_kzt_internal": float(r["sum_kzt_internal"]),
            "top_gids": [int(g) for g in str(r["top_gids"]).split(";") if g],
            "hypothesis": {l: hypothesis_from_members(r, members, l) for l in langs},
        })

    def load(name: str, default):
        p = out_dir / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, TypeError):
            return default

    def text(name: str) -> str:
        p = out_dir / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    calibration = {}
    cal_path = Path(cfg.get("_config_dir", ".")) / "config.calibrated.yaml"
    if cal_path.exists():
        import yaml

        calibration = yaml.safe_load(cal_path.read_text(encoding="utf-8")) or {}

    payload = {
        "generated_by": "moneygraph.webexport",
        "meta": {
            "n_nodes": int(len(nodes)),
            "n_edges": int(len(edges)),
            "n_seeds": int(nodes["is_seed"].sum()),
            "max_depth": int(nodes["depth"].max()),
            "turnover_kzt": float(edges["sum_kzt"].sum()),
            "n_clusters": int(len(clusters)),
            "n_frontier": int((~nodes["outflow_observed"]).sum())
            if "outflow_observed" in nodes else 0,
            "role_counts": nodes["role"].value_counts().to_dict(),
            "model": cfg["llm"]["model"],
            "seed": int(cfg.get("seed", 42)),
        },
        "i18n": {
            "languages": LANGUAGES,
            "machine_translated": sorted(MACHINE_TRANSLATED),
            "ui": UI,
            "role_names": ROLE_NAMES,
            "role_meaning": ROLE_MEANING,
            "tab_guide": [{"key": k, "for": f, "when": w} for k, f, w in TAB_GUIDE],
        },
        "role_colors": cfg["viewer"]["role_colors"],
        "nodes": node_rows,
        "edges": [{"s": int(e.src), "d": int(e.dst),
                   "v": float(e.sum_kzt), "n": int(e.n_tx)}
                  for e in edges.itertuples(index=False)],
        "clusters": cluster_rows,
        "top": top_rows,
        "dossiers": load("dossiers.json", {}),
        "extras": load("extras.json", {}),
        "ingest": load("ingest_report.json", {}),
        "trace": load("run_trace.json", {}),
        "calibration": calibration,
        "docs": {
            "review_notes": text("review_notes.md"),
            "agent_log": text("agent_log.md"),
            "data_requests": text("data_requests.md"),
            "profile_report": text("profile_report.md"),
            "extras_report": text("extras_report.md"),
            "run_trace": text("run_trace.md"),
        },
    }

    path = out_dir / "web_data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                               default=str), encoding="utf-8")
    return path


def vendor_assets(web_dir: str | Path) -> list[Path]:
    """Copy vis-network out of the installed pyvis package.

    Vendored rather than loaded from a CDN so the interface works with no
    internet, which the brief requires of everything except the optional LLM
    call.
    """
    import shutil

    import pyvis

    web_dir = Path(web_dir)
    vendor = web_dir / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    src_root = Path(pyvis.__file__).parent / "templates" / "lib"
    copied = []
    candidates = sorted(src_root.glob("vis-*"), reverse=True)   # newest first
    for folder in candidates:
        for name in ("vis-network.min.js", "vis-network.css"):
            src = folder / name
            if src.exists():
                dst = vendor / name
                if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                    shutil.copy2(src, dst)
                copied.append(dst)
        if copied:
            break
    return copied
