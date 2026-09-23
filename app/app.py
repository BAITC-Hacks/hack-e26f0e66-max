"""Money Graph viewer.

Reads `output_files/` only — it never recomputes, so it opens instantly and
shows exactly what the exported CSVs contain.

The layout follows the analyst's actual question order:

    Start here  ->  Who to review first  ->  Account detail  ->  everything else

Design rule for this file: **nothing on screen without a label that says what
it is and what to do with it.** A network map with no reading guide is a
decoration; a table with no explanation of its ranking is noise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning)

import gradio as gr
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moneygraph.io import load_config          # noqa: E402

CFG = load_config(ROOT / "config.yaml")
OUT = ROOT / CFG["paths"]["outputs"]
VIEW = CFG["viewer"]
ROLE_COLORS = VIEW["role_colors"]

ROLE_MEANING = {
    "coordinator": "Collects from other collection points — candidate upper level",
    "consolidator": "Money from many separate payers converges here",
    "distributor": "Fans money out to many recipients",
    "transit": "Money arrives and moves on, roughly in equals out",
    "terminal": "Money arrives and stays (outflow was traced)",
    "cutoff": "Onward flow was never traced — the export stopped here",
    "peripheral": "No role indicators detected",
}

CSS = """
.gradio-container { max-width: 1320px !important; }
.hero { padding: 20px 24px; border-radius: 14px; border: 1px solid var(--border-color-primary);
        background: var(--block-background-fill); margin-bottom: 6px; }
.hero h2 { margin: 0 0 6px 0; font-size: 1.35rem; }
.hero p  { margin: 0; opacity: .82; line-height: 1.55; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.kpi { text-align: center; padding: 16px 10px; border-radius: 12px;
       background: var(--block-background-fill); border: 1px solid var(--border-color-primary); }
.kpi .v { font-size: 1.9rem; font-weight: 640; line-height: 1.15; }
.kpi .l { font-size: .74rem; opacity: .7; text-transform: uppercase; letter-spacing: .05em; margin-top: 4px; }
.kpi .s { font-size: .74rem; opacity: .55; margin-top: 2px; }
.note { border-left: 3px solid var(--color-accent, #888); padding: 10px 14px; margin: 10px 0;
        background: var(--block-background-fill); border-radius: 0 8px 8px 0;
        font-size: .9rem; line-height: 1.55; }
.legend { display: grid; grid-template-columns: repeat(auto-fit, minmax(238px, 1fr)); gap: 6px 18px;
          padding: 14px 16px; border-radius: 12px; border: 1px solid var(--border-color-primary);
          background: var(--block-background-fill); font-size: .86rem; }
.legend .row { display: flex; align-items: center; gap: 9px; }
.legend .sw { width: 13px; height: 13px; border-radius: 50%; flex: none; }
.legend .t  { opacity: .78; }
.legend h4 { grid-column: 1/-1; margin: 0 0 2px 0; font-size: .78rem; opacity: .6;
             text-transform: uppercase; letter-spacing: .05em; }
.pill { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem;
        font-weight: 600; color: #fff; }
.facts { width: 100%; border-collapse: collapse; font-size: .92rem; }
.facts td { padding: 7px 4px; border-bottom: 1px solid var(--border-color-primary); }
.facts td:first-child { opacity: .62; width: 46%; }
.facts td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.bars { display: flex; flex-direction: column; gap: 9px; padding: 4px 2px; }
.bar { display: grid; grid-template-columns: 124px 1fr 96px; align-items: center; gap: 12px; }
.bl { display: flex; align-items: center; gap: 8px; font-size: .9rem; }
.bl .sw { width: 11px; height: 11px; border-radius: 50%; flex: none; }
.bt { height: 20px; background: var(--border-color-primary); border-radius: 5px; overflow: hidden; }
.bf { height: 100%; border-radius: 5px; transition: width .4s ease; }
.bn { font-size: .9rem; text-align: right; font-variant-numeric: tabular-nums; }
.bn .bp { opacity: .5; font-size: .78rem; margin-left: 7px; }
.warnbox { border-left: 3px solid #d98324; background: rgba(217,131,36,.08);
           padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 10px 0; font-size: .9rem; }
"""


# ===========================================================================
# data
# ===========================================================================

class Store:
    def __init__(self) -> None:
        self.load()

    def load(self) -> None:
        required = ["nodes_roles.csv", "clusters.csv", "top_nodes.csv",
                    "node_features.parquet", "graph_edges.parquet"]
        self.missing = [f for f in required if not (OUT / f).exists()]
        self.ok = not self.missing
        if not self.ok:
            return
        self.nodes = pd.read_csv(OUT / "nodes_roles.csv")
        self.clusters = pd.read_csv(OUT / "clusters.csv")
        self.top = pd.read_csv(OUT / "top_nodes.csv")
        self.features = pd.read_parquet(OUT / "node_features.parquet")
        self.edges = pd.read_parquet(OUT / "graph_edges.parquet")
        self.f = self.features.set_index("gid", drop=False)
        self.dossiers = self._json("dossiers.json", key_int=True)
        self.ingest = self._json("ingest_report.json")
        self.trace = self._json("run_trace.json")

    def _json(self, name: str, key_int: bool = False):
        p = OUT / name
        if not p.exists():
            return {}
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, TypeError):
            return {}
        return {int(k): v for k, v in d.items()} if key_int else d

    def text(self, name: str, fallback: str = "") -> str:
        p = OUT / name
        return p.read_text(encoding="utf-8") if p.exists() else fallback

    def rule_trace(self, gid: int) -> dict:
        if gid not in self.f.index:
            return {}
        try:
            return json.loads(self.f.at[gid, "rule_trace"])
        except (TypeError, ValueError):
            return {}


S = Store()


# ===========================================================================
# formatting helpers
# ===========================================================================

def kzt(x, unit: bool = False) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if pd.isna(x):
        return "n/a"
    suffix = " KZT" if unit else ""
    if abs(x) >= 1e9:
        return f"{x / 1e9:.2f}B{suffix}"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f}M{suffix}"
    if abs(x) >= 1e3:
        return f"{x / 1e3:.0f}k{suffix}"
    return f"{x:,.0f}{suffix}"


def kpi(value: str, label: str, sub: str = "") -> str:
    return (f"<div class='kpi'><div class='v'>{value}</div>"
            f"<div class='l'>{label}</div>"
            + (f"<div class='s'>{sub}</div>" if sub else "") + "</div>")


def kpis(cells: list[str]) -> str:
    return "<div class='kpis'>" + "".join(cells) + "</div>"


def note(text: str) -> str:
    return f"<div class='note'>{text}</div>"


def pill(role: str) -> str:
    return (f"<span class='pill' style='background:{ROLE_COLORS.get(role, '#888')}'>"
            f"{role}</span>")


def legend_html() -> str:
    rows = "".join(
        f"<div class='row'><span class='sw' style='background:{c}'></span>"
        f"<b>{r}</b><span class='t'>— {ROLE_MEANING.get(r, '')}</span></div>"
        for r, c in ROLE_COLORS.items())
    shapes = (
        "<h4>Shapes and lines</h4>"
        "<div class='row'><span class='t'><b>◆ diamond</b> — one of the 81 known "
        "seed accounts</span></div>"
        "<div class='row'><span class='t'><b>● circle</b> — an account the trace "
        "reached</span></div>"
        "<div class='row'><span class='t'><b>dashed red ring</b> — the export "
        "stopped here; onward flow unknown</span></div>"
        "<div class='row'><span class='t'><b>arrow</b> — direction the money "
        "moved</span></div>"
        "<div class='row'><span class='t'><b>thicker line</b> — larger amount "
        "(log scale)</span></div>"
        "<div class='row'><span class='t'><b>bigger circle</b> — higher review "
        "priority</span></div>")
    return f"<div class='legend'><h4>What the colours mean</h4>{rows}{shapes}</div>"


READING_GUIDE = note(
    "<b>How to read this map.</b> Money flows along the arrows, away from the "
    "known seed accounts and up towards whoever collects it. The account you "
    "searched for is outlined in black. <b>Hover any node</b> for its role, "
    "amounts and the one-line evidence; <b>hover any arrow</b> for the amount "
    "and number of transfers. Drag to pan, scroll to zoom, drag a node to move it."
)


# ===========================================================================
# network rendering
# ===========================================================================

def _network(height: str = "540px"):
    from pyvis.network import Network

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#ffffff", font_color="#1a1a1a",
                  cdn_resources="in_line")          # works offline
    net.set_options(json.dumps({
        "physics": {"enabled": bool(VIEW["physics"]),
                    "stabilization": {"iterations": 150},
                    "barnesHut": {"springLength": 150, "avoidOverlap": 0.4}},
        "layout": {"randomSeed": int(CFG.get("seed", 42))},
        "edges": {"arrows": {"to": {"enabled": True, "scaleFactor": 0.55}},
                  "color": {"color": "#c2cad1", "highlight": "#5a6a78"},
                  "smooth": {"type": "continuous", "roundness": 0.15},
                  "font": {"size": 10, "align": "middle",
                           "strokeWidth": 4, "strokeColor": "#ffffff"}},
        "nodes": {"font": {"size": 12, "face": "system-ui",
                           "strokeWidth": 4, "strokeColor": "#ffffff"},
                  "borderWidthSelected": 4},
        "interaction": {"hover": True, "tooltipDelay": 100,
                        "navigationButtons": True, "keyboard": False},
    }))
    return net


def _add_node(net, gid: int, centre: bool = False) -> None:
    r = S.f.loc[gid]
    role = str(r["role"])
    is_seed = bool(r["is_seed"])
    traced = bool(r.get("outflow_observed", True))
    tip = (f"Account {gid}\n"
           f"{role.upper()} — {ROLE_MEANING.get(role, '')}\n"
           f"{'─' * 34}\n"
           f"Review priority   {float(r['priority_score']):.3f}\n"
           f"Role confidence   {float(r['role_score']):.2f}\n"
           f"Received          {kzt(r['in_sum'], True)} from {int(r['in_deg'])}\n"
           f"Sent              {kzt(r['out_sum'], True)} to {int(r['out_deg'])}\n"
           f"Hop from seed     {int(r['depth'])}"
           f"{'   · KNOWN SEED' if is_seed else ''}\n"
           f"{'' if traced else 'Onward flow NOT traced (export limit)'}\n"
           f"{'─' * 34}\n{r['evidence']}")
    net.add_node(
        gid, label=str(gid)[-6:], title=tip,
        color={"background": ROLE_COLORS.get(role, "#999"),
               "border": "#111111" if centre else ("#8d99a4" if traced else "#cc3b3b")},
        shape="diamond" if is_seed else "dot",
        size=(30 if centre else 12 + 20 * float(r["priority_score"])),
        borderWidth=5 if centre else (1 if traced else 3),
        shapeProperties={"borderDashes": [] if traced else [5, 4]},
    )


def _add_edge(net, e, show_amounts: bool) -> None:
    import math

    net.add_edge(int(e.src), int(e.dst),
                 value=math.log1p(float(e.sum_kzt)),
                 title=f"{float(e.sum_kzt):,.0f} KZT over {int(e.n_tx)} transfer(s)",
                 label=kzt(e.sum_kzt) if show_amounts else None)


MAPS = OUT / "_maps"


def _iframe(doc: str, height: int, key: str) -> str:
    """Serve the network map as a file rather than inlining it.

    A pyvis document is ~1 MB. Pushing that through a `srcdoc` attribute means
    HTML-escaping a megabyte, shipping it over the event channel on every
    interaction, and trusting the browser to parse an enormous attribute — which
    is how the maps ended up blank. Written to disk and referenced by URL, the
    component value is ~200 bytes and the browser fetches the document normally.
    """
    MAPS.mkdir(parents=True, exist_ok=True)
    path = MAPS / f"{key}-{hashlib.md5(doc.encode()).hexdigest()[:8]}.html"
    if not path.exists():
        path.write_text(doc, encoding="utf-8")
    return (f'<iframe src="/gradio_api/file={path}" loading="lazy" '
            f'style="width:100%;height:{height}px;border:1px solid '
            f'var(--border-color-primary);border-radius:12px;background:#fff"'
            f'></iframe>')


def ego_html(gid: int, hops: int, show_amounts: bool) -> str:
    if gid not in S.f.index:
        return ""
    keep, frontier = {gid}, {gid}
    for _ in range(max(int(hops), 1)):
        sel = S.edges[S.edges["src"].isin(frontier) | S.edges["dst"].isin(frontier)]
        nxt = set(sel["src"]) | set(sel["dst"])
        frontier, keep = nxt - keep, keep | nxt

    cap = int(VIEW["ego_max_nodes"])
    capped = len(keep) > cap
    if capped:
        sel = S.edges[S.edges["src"].isin(keep) & S.edges["dst"].isin(keep)]
        sel = sel.nlargest(cap, "sum_kzt")
        keep = {gid} | set(sel["src"]) | set(sel["dst"])

    sub = S.edges[S.edges["src"].isin(keep) & S.edges["dst"].isin(keep)]
    net = _network()
    for n in sorted(keep):
        _add_node(net, int(n), centre=(int(n) == int(gid)))
    for e in sub.itertuples(index=False):
        _add_edge(net, e, show_amounts)

    head = (f"<div class='warnbox'>This neighbourhood has more than {cap} "
            f"accounts, so only the {cap} largest flows are drawn. Switch to "
            f"1 hop for the full picture.</div>") if capped else ""
    return head + _iframe(net.generate_html(notebook=False), 560,
                          f'ego-{gid}-{hops}-{int(show_amounts)}')


def cluster_html(cluster_id: int, show_amounts: bool) -> str:
    members = S.nodes[S.nodes["cluster_id"] == int(cluster_id)]
    gids = set(members["gid"].astype(int))
    cap = int(VIEW["cluster_map_max_nodes"])
    capped = len(gids) > cap
    if capped:
        gids = set(members.nlargest(cap, "priority_score")["gid"].astype(int))
    sub = S.edges[S.edges["src"].isin(gids) & S.edges["dst"].isin(gids)]
    net = _network("600px")
    for n in sorted(gids):
        _add_node(net, int(n))
    for e in sub.itertuples(index=False):
        _add_edge(net, e, show_amounts)
    head = (f"<div class='warnbox'>Showing the {cap} highest-priority of "
            f"{len(members)} accounts in this cluster.</div>") if capped else ""
    return head + _iframe(net.generate_html(notebook=False), 620,
                          f'cluster-{cluster_id}-{int(show_amounts)}')


# ===========================================================================
# account detail
# ===========================================================================

BLANK = ("", "", "", pd.DataFrame(), pd.DataFrame())


def account_detail(gid_text, hops, show_amounts):
    try:
        gid = int(str(gid_text).strip())
    except (TypeError, ValueError):
        return ("<div class='note'>Type an account number above, or pick one "
                "from the list.</div>", "", "", pd.DataFrame(), pd.DataFrame())
    if gid not in S.f.index:
        return (f"<div class='warnbox'>Account <b>{gid}</b> is not in this "
                f"dataset.</div>", "", "", pd.DataFrame(), pd.DataFrame())

    r = S.f.loc[gid]
    role = str(r["role"])
    traced = bool(r.get("outflow_observed", True))

    facts = [
        ("Review priority", f"<b>{float(r['priority_score']):.3f}</b>"),
        ("Role confidence", f"{float(r['role_score']):.2f}"),
        ("Received", f"{kzt(r['in_sum'], True)} from {int(r['in_deg'])} payer(s)"),
        ("Sent", f"{kzt(r['out_sum'], True)} to {int(r['out_deg'])} recipient(s)"),
        ("Seeds that can reach it", f"{int(r.get('seed_reach', 0))} of "
                                    f"{int(S.nodes['is_seed'].sum())}"),
        ("Est. seed-linked flow", kzt(r.get("seed_kzt_attributed", 0), True)),
        ("Hops from a seed", str(int(r["depth"]))),
        ("Known seed account", "yes" if bool(r["is_seed"]) else "no"),
        ("Cluster", str(int(r["cluster_id"]))),
    ]
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in facts)

    card = [
        f"<div class='hero'><h2>Account {gid} &nbsp; {pill(role)}</h2>",
        f"<p>{ROLE_MEANING.get(role, '')}</p></div>",
        f"<table class='facts'>{rows}</table>",
        note(f"<b>Evidence.</b> {r['evidence']}"),
    ]
    if not traced:
        card.append("<div class='warnbox'><b>Careful.</b> This account sits at "
                    "the edge of the export. Its outgoing transfers were never "
                    "requested, so <b>we do not know</b> whether the money "
                    "stopped here. It is a strong candidate for a follow-up "
                    "data request.</div>")
    if str(r.get("secondary_roles", "")):
        card.append(note(f"Also matched: <b>{r['secondary_roles']}</b>"))
    caveat = str(r.get("critic_caveat", "") or "")
    if caveat:
        card.append(f"<div class='warnbox'><b>Reviewer's caveat.</b> "
                    f"{caveat.replace(' | ', '<br><br>')}</div>")

    # ---- why this role -----------------------------------------------------
    t = S.rule_trace(gid)
    why = ["### Why it was classified this way", "",
           "*This is the rule the engine applied. No AI model was involved in "
           "assigning the role — the numbers below are the ones the rule "
           "actually compared.*", ""]
    if t:
        why += [f"**Rule that fired**", "", f"> `{t.get('gate', 'n/a')}`", ""]
        if t.get("metrics"):
            why += ["**Values it used**", "", "| | |", "|---|---:|"]
            why += [f"| {k} | {_fmt_v(v)} |" for k, v in t["metrics"].items()]
            why.append("")
        if t.get("thresholds"):
            why += ["**Thresholds it compared against** *(from `config.yaml`)*",
                    "", "| | |", "|---|---:|"]
            why += [f"| {k} | {_fmt_v(v)} |" for k, v in t["thresholds"].items()]
            why.append("")
        if t.get("penalties"):
            why += ["**Confidence reduced because**", ""] + \
                   [f"- {p}" for p in t["penalties"]] + [""]
        if t.get("notes"):
            why += [f"- {n}" for n in t["notes"]] + [""]
    adj = str(r.get("priority_adjustments", "") or "")
    if adj:
        why += [f"**Priority adjustment.** {adj}", ""]

    d = S.dossiers.get(gid)
    if d:
        why += ["---", "", "### Investigator's dossier", "",
                f"**Pattern.** {d.get('pattern', '—')}"
                + (f" *(confidence: {d.get('confidence')})*" if d.get("confidence") else ""),
                "", str(d.get("summary", "")), ""]
        if d.get("alternative_explanation"):
            why += [f"**Could equally be.** {d['alternative_explanation']}", ""]
        if d.get("next_step"):
            why += [f"**Suggested next step.** {d['next_step']}", ""]
        why += ["*Advisory only — this did not affect the role or the ranking.*"]

    return ("\n".join(card), "\n".join(why),
            ego_html(gid, hops, show_amounts),
            _links(gid, "dst", "src", "Paid in from"),
            _links(gid, "src", "dst", "Paid out to"))


def _fmt_v(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1e5 else f"{v:,.0f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def _links(gid: int, match: str, other: str, label: str) -> pd.DataFrame:
    sel = S.edges[S.edges[match] == gid]
    cols = ["Account", "Its role", "Seed?", "Amount (KZT)", "Transfers"]
    if sel.empty:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        "Account": sel[other].astype("int64"),
        "Its role": sel[other].map(S.f["role"]).fillna("—"),
        "Seed?": sel[other].map(S.f["is_seed"]).map({True: "yes", False: ""}).fillna(""),
        "Amount (KZT)": sel["sum_kzt"].round(0).astype("int64"),
        "Transfers": sel["n_tx"].astype("int64"),
    })
    return out.sort_values("Amount (KZT)", ascending=False).reset_index(drop=True)


# ===========================================================================
# tab content
# ===========================================================================

def role_bars() -> str:
    """The role distribution, as plain HTML.

    Deliberately not a charting library: this is one horizontal bar chart, and a
    plotting dependency renders it through a JavaScript bundle whose version has
    to agree with the front end's. Hand-drawn, it cannot fail to display, works
    with no network, and inherits the page theme.
    """
    counts = S.nodes["role"].value_counts()
    total = int(counts.sum())
    widest = int(counts.max()) if len(counts) else 1
    rows = []
    for role, n in counts.items():
        pct = 100 * n / total
        rows.append(
            f"<div class='bar'>"
            f"<div class='bl'><span class='sw' style='background:"
            f"{ROLE_COLORS.get(role, '#888')}'></span>{role}</div>"
            f"<div class='bt' title='{ROLE_MEANING.get(role, '')}'>"
            f"<div class='bf' style='width:{max(1.2, 100 * n / widest):.1f}%;"
            f"background:{ROLE_COLORS.get(role, '#888')}'></div></div>"
            f"<div class='bn'>{n:,}<span class='bp'>{pct:.0f}%</span></div>"
            f"</div>")
    return "<div class='bars'>" + "".join(rows) + "</div>"


def overview_kpis() -> str:
    n = len(S.nodes)
    frontier = int((~S.features["outflow_observed"]).sum()) \
        if "outflow_observed" in S.features else 0
    shortlist = len(S.top)
    return kpis([
        kpi(f"{n:,}", "accounts traced", "from 81 known seeds"),
        kpi(f"{shortlist}", "to review first", "ranked, with reasons"),
        kpi(kzt(float(S.edges['sum_kzt'].sum())), "KZT traced", "July 2026"),
        kpi(f"{len(S.clusters)}", "groups found", "with a hypothesis each"),
        kpi(f"{frontier}", "dead ends", "flow not traced — request more"),
    ])


def top_table() -> pd.DataFrame:
    t = S.top.copy()
    return pd.DataFrame({
        "#": t["rank"],
        "Account": t["gid"],
        "Role": t["role"],
        "Priority": t["priority_score"].round(3),
        "Why it is on this list": t["why"],
    })


def cluster_table() -> pd.DataFrame:
    c = S.clusters.copy()
    return pd.DataFrame({
        "Group": c["cluster_id"],
        "Accounts": c["n_nodes"],
        "Known seeds": c["n_seed"],
        "Internal flow": c["sum_kzt_internal"].map(kzt),
        "What it looks like": c["hypothesis"],
    })


def trace_kpis() -> str:
    d = S.trace
    if not d:
        return note("No run trace found. Run the pipeline to generate one.")
    t = d.get("totals", {})
    cost = t.get("cost_usd")
    cost_txt = (f"${cost:.4f}" if isinstance(cost, (int, float))
                else "unpriced")
    return kpis([
        kpi(f"{d.get('total_runtime_s', 0):.0f}s", "total runtime",
            f"budget {d.get('runtime_budget_s', 300):.0f}s"),
        kpi(f"{t.get('n_calls', 0)}", "model calls",
            f"{t.get('n_failed', 0)} failed" if t.get("n_failed") else "all succeeded"),
        kpi(f"{t.get('total_tokens', 0):,}", "tokens",
            f"{t.get('reasoning_tokens', 0):,} reasoning"),
        kpi(cost_txt, "spend", "this run"),
    ])


def ingest_summary() -> str:
    p = S.ingest
    if not p:
        return note("No ingest report — run the pipeline to generate one.")
    used = p.get("used", {})
    rows = "".join(f"<tr><td>{k}</td><td><code>{v}</code></td></tr>"
                   for k, v in used.items())
    html_ = [f"<table class='facts'>{rows}</table>"]
    derived = p.get("derived") or []
    if derived:
        html_.append("<div class='warnbox'><b>Derived, not supplied.</b><ul>"
                     + "".join(f"<li>{d}</li>" for d in derived) + "</ul></div>")
    else:
        html_.append(note("Everything the pipeline needed was present in the "
                          "input. Nothing had to be inferred."))
    return "".join(html_)


def mapping_table() -> pd.DataFrame:
    rows = []
    for f in (S.ingest.get("files") or []):
        for canonical, col in (f.get("mapping") or {}).items():
            rows.append({
                "File": f.get("file"),
                "Read as": f.get("kind"),
                "Standard field": canonical,
                "Column in your file": col,
                "Matched by": (f.get("resolved_by") or {}).get(canonical, "?"),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["File", "Read as", "Standard field", "Column in your file", "Matched by"])


def calibration_table() -> pd.DataFrame | None:
    import yaml

    path = ROOT / "config.calibrated.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    th = data.get("thresholds") or {}
    if not th:
        return None
    rat = data.get("rationale") or {}
    return pd.DataFrame({
        "Threshold": list(th),
        "Value": [th[k] for k in th],
        "Why the agent chose this number": [rat.get(k, "—") for k in th],
    })


def dossier_table() -> pd.DataFrame:
    rows = [{
        "Account": gid,
        "Role": S.f.at[gid, "role"] if gid in S.f.index else "",
        "Pattern": d.get("pattern", ""),
        "What the investigator found": d.get("summary", ""),
        "Could equally be": d.get("alternative_explanation", ""),
        "Next step": d.get("next_step", ""),
    } for gid, d in sorted(S.dossiers.items())]
    return pd.DataFrame(rows)


def ask_agent(question: str, history: list):
    history = history or []
    if not question or not question.strip():
        return history, ""
    from moneygraph.agents.analyst_agent import ask
    from moneygraph.agents.llm import LLMClient
    from moneygraph.agents.tools import GraphTools
    from moneygraph.trace import RunTracer

    tracer = RunTracer(CFG)
    client = LLMClient(CFG, tracer)
    answer = ask(question, GraphTools(S.nodes, S.edges, S.clusters), client, CFG)

    parts = [answer.text]
    if answer.note:
        parts.append(f"\n*{answer.note}*")
    if answer.tool_calls:
        calls = "\n".join(
            f"- `{c['tool']}({json.dumps(c.get('args', {}), default=str)})`"
            + (f" — error: {c['error']}" if c.get("error") else "")
            for c in answer.tool_calls)
        parts.append(f"\n<details><summary>The {len(answer.tool_calls)} graph "
                     f"queries this answer is built from</summary>\n\n{calls}\n"
                     f"</details>")
    t = tracer.totals()
    if t["n_calls"]:
        cost = t["cost_usd"]
        parts.append(f"\n<sub>{t['n_calls']} call(s) · {t['total_tokens']:,} tokens "
                     f"· {f'${cost:.4f}' if cost is not None else 'unpriced'} "
                     f"· {tracer.elapsed_s:.1f}s</sub>")
    return history + [{"role": "user", "content": question},
                      {"role": "assistant", "content": "\n".join(parts)}], ""


# ===========================================================================
# app
# ===========================================================================

def build() -> gr.Blocks:
    with gr.Blocks(title="Money Graph", css=CSS,
                   theme=gr.themes.Soft(primary_hue="slate",
                                        neutral_hue="slate")) as demo:

        if not S.ok:
            gr.Markdown(f"# Money Graph\n\n### No results yet\n\nMissing from "
                        f"`{OUT}`: `{'`, `'.join(S.missing)}`\n\nRun this first:\n"
                        f"```bash\n./agent_run.sh\n```")
            prof = S.text("profile_report.md")
            if prof:
                with gr.Accordion("Data profile (already generated)", open=False):
                    gr.Markdown(prof)
            return demo

        # ---------------------------------------------------------- 1. start
        with gr.Tab("Start here"):
            gr.HTML(
                "<div class='hero'><h2>Money Graph</h2><p>Law enforcement gave "
                "the bank 81 customers known to have received drug-trafficking "
                "money. This tool followed their outgoing transfers four hops "
                "through the bank and worked out <b>who sits above them</b> — "
                "then ranked every account by how much it is worth reviewing, "
                "with a written reason for each.<br><br><b>Everything here is a "
                "hypothesis for an analyst to verify, not a finding of "
                "fact.</b></p></div>")
            gr.HTML(overview_kpis())

            gr.Markdown("### Where to go")
            with gr.Row():
                gr.HTML(note(
                    "<b>1 · Who to review first</b><br>The ranked shortlist. "
                    "Start at the top and read the reason column. This is the "
                    "answer to the question the case asks."))
                gr.HTML(note(
                    "<b>2 · Account detail</b><br>Type any account number to get "
                    "its role, <i>the exact rule that produced it</i>, and a map "
                    "of the money moving through it."))
                gr.HTML(note(
                    "<b>3 · Groups</b><br>The network split into communities, "
                    "each with a hypothesis about what it is."))

            gr.Markdown("### How the accounts were classified")
            with gr.Row():
                with gr.Column(scale=3):
                    gr.HTML(role_bars())
                with gr.Column(scale=2):
                    gr.HTML("<div class='legend'><h4>What each role means</h4>"
                            + "".join(
                                f"<div class='row'><span class='sw' "
                                f"style='background:{ROLE_COLORS.get(r)}'></span>"
                                f"<b>{r}</b><span class='t'>— {m}</span></div>"
                                for r, m in ROLE_MEANING.items()) + "</div>")
            gr.HTML(note(
                "<b>Why so many <i>terminal</i> and <i>cutoff</i>?</b> Both are "
                "artifacts of how the data was collected, and both are handled "
                "deliberately. <i>cutoff</i> accounts sit at the four-hop edge of "
                "the export — their onward transfers were never requested, so we "
                "say <i>unknown</i> rather than pretending the money stopped. "
                "<i>terminal</i> accounts were traced, but most are ordinary "
                "leaves that simply had nothing above the 5,000 KZT reporting "
                "floor leaving them. Neither is treated as a strong signal."))

        # ------------------------------------------------------- 2. shortlist
        with gr.Tab("Who to review first"):
            gr.HTML("<div class='hero'><h2>The shortlist</h2><p>Every account "
                    "scored on five signals, ranked highest first. The last "
                    "column says, in plain language, what put it there.</p></div>")
            gr.HTML(note(
                "<b>Click any row</b> to open that account's full detail below. "
                "The score combines: its role, how much seed-linked money flows "
                "through it, how many separate courier chains reach it, how many "
                "different payers it has, and how seed-heavy its group is. "
                "<b>Known seeds are deliberately pushed down</b> — police already "
                "have those 81; the value is in what sits above them."))
            top_df = gr.Dataframe(top_table(), wrap=True, max_height=460,
                                  interactive=False)
            sel_card = gr.HTML()
            sel_why = gr.Markdown()

            def pick_row(evt: gr.SelectData):
                try:
                    gid = int(top_table().iloc[evt.index[0]]["Account"])
                except Exception:
                    return "", ""
                card, why, _map, _p, _r = account_detail(gid, 1, False)
                return card, why

            top_df.select(pick_row, None, [sel_card, sel_why])

        # ---------------------------------------------------- 3. account view
        with gr.Tab("Account detail"):
            gr.HTML("<div class='hero'><h2>Look up an account</h2><p>Type any "
                    "account number to see its role, the exact rule that produced "
                    "it, and how money moves through it.</p></div>")
            with gr.Row():
                gid_in = gr.Textbox(label="Account number", scale=3,
                                    placeholder="paste a gid, then press Enter")
                pick = gr.Dropdown(
                    choices=[str(int(g)) for g in S.top["gid"]],
                    label="…or pick from the shortlist", value=None, scale=2)
            with gr.Row():
                hops_in = gr.Radio([1, 2], value=int(VIEW["ego_hops_default"]),
                                   label="How far around it to draw",
                                   info="1 = direct counterparties only "
                                        "(clearest). 2 = their counterparties too.")
                amt_in = gr.Checkbox(False, label="Label arrows with amounts",
                                     info="Off keeps the map readable; the amount "
                                          "is always in the tooltip.")

            # Rendered here, not in a load event: the page then arrives with
            # content already in it. A component that starts empty and waits for
            # a round-trip is a component that shows nothing if anything at all
            # goes wrong on the way.
            d_card, d_why, d_map, d_pay, d_rec = account_detail(
                int(S.top["gid"].iloc[0]), int(VIEW["ego_hops_default"]), False)

            with gr.Row():
                with gr.Column(scale=1):
                    card_out = gr.HTML(d_card)
                with gr.Column(scale=1):
                    why_out = gr.Markdown(d_why)

            gr.Markdown("### The money around this account")
            gr.HTML(READING_GUIDE)
            map_out = gr.HTML(d_map)
            with gr.Accordion("Colour and shape key", open=False):
                gr.HTML(legend_html())
            with gr.Row():
                payers_out = gr.Dataframe(d_pay,
                                          label="Money in — who paid this account",
                                          max_height=300, interactive=False)
                recips_out = gr.Dataframe(d_rec, label="Money out — who it paid",
                                          max_height=300, interactive=False)

            outs = [card_out, why_out, map_out, payers_out, recips_out]
            ins = [gid_in, hops_in, amt_in]
            gid_in.submit(account_detail, ins, outs)
            hops_in.change(account_detail, ins, outs)
            amt_in.change(account_detail, ins, outs)
            pick.change(lambda g, h, a: account_detail(g, h, a) if g else BLANK,
                        [pick, hops_in, amt_in], outs)

        # ---------------------------------------------------------- 4. groups
        with gr.Tab("Groups"):
            gr.HTML("<div class='hero'><h2>Communities in the network</h2><p>The "
                    "network split into groups of accounts that move money among "
                    "themselves. Each one gets a hypothesis about what it looks "
                    "like.</p></div>")
            gr.Dataframe(cluster_table(), wrap=True, max_height=300,
                         interactive=False)
            gr.HTML(note(
                "Grouping uses the Louvain method on an <b>undirected</b> view of "
                "the network — community detection needs one. Direction is "
                "dropped <i>for grouping only</i>: every role, number and arrow "
                "elsewhere still uses the real direction of the money. Small "
                "disconnected fragments are kept as their own groups rather than "
                "being folded into the big one."))
            first_cluster = str(int(S.clusters["cluster_id"].iloc[0]))
            cl = gr.Dropdown([str(int(c)) for c in S.clusters["cluster_id"]],
                             value=first_cluster, label="Show group")
            cl_amt = gr.Checkbox(False, label="Label arrows with amounts")

            def show_cluster(cid, amounts):
                cid = int(cid)
                row = S.clusters[S.clusters["cluster_id"] == cid].iloc[0]
                m = S.nodes[S.nodes["cluster_id"] == cid].sort_values(
                    "priority_score", ascending=False)
                info = (f"<div class='hero'><h2>Group {cid}</h2><p>"
                        f"<b>{int(row['n_nodes'])}</b> accounts · "
                        f"<b>{int(row['n_seed'])}</b> known seeds · "
                        f"<b>{kzt(row['sum_kzt_internal'], True)}</b> moving "
                        f"inside the group</p></div>"
                        + note(f"<b>Hypothesis.</b> {row['hypothesis']}"))
                table = pd.DataFrame({
                    "Account": m["gid"], "Role": m["role"],
                    "Priority": m["priority_score"].round(3),
                    "Evidence": m["evidence"]}).reset_index(drop=True)
                return info, cluster_html(cid, amounts), table

            c_info, c_map, c_members = show_cluster(first_cluster, False)
            cl_info = gr.HTML(c_info)
            gr.HTML(READING_GUIDE)
            cl_map = gr.HTML(c_map)
            cl_members = gr.Dataframe(c_members, label="Accounts in this group",
                                      max_height=300, interactive=False)

            cl.change(show_cluster, [cl, cl_amt], [cl_info, cl_map, cl_members])
            cl_amt.change(show_cluster, [cl, cl_amt], [cl_info, cl_map, cl_members])

        # ------------------------------------------------------------- 5. ask
        with gr.Tab("Ask"):
            gr.HTML("<div class='hero'><h2>Ask about the network</h2><p>Questions "
                    "in plain English. The answer is assembled only from "
                    "deterministic queries against the graph — expand the "
                    "disclosure under any answer to see exactly which ones."
                    "</p></div>")
            gr.HTML(note(
                "Without a model configured this still works: the same queries "
                "run, the phrasing is just plainer. Nothing here can invent an "
                "account number — one that does not exist is dropped."))
            chat = gr.Chatbot(type="messages", height=420, allow_tags=True,
                              show_label=False)
            q = gr.Textbox(label="Your question", show_label=False,
                           placeholder="e.g. who collects money from these five? "
                                       "1234; 5678; …")
            with gr.Row():
                send = gr.Button("Ask", variant="primary")
                clear = gr.Button("Clear")
            gr.Examples([
                "Which accounts should I review first, and why?",
                "Which collection points sit at the edge of the export?",
                "What would I need to request to see past the fourth hop?",
            ], inputs=q, label="Try one of these")
            send.click(ask_agent, [q, chat], [chat, q])
            q.submit(ask_agent, [q, chat], [chat, q])
            clear.click(lambda: ([], ""), None, [chat, q])

        # ---------------------------------------------------------- 6. agents
        with gr.Tab("How it decided"):
            gr.HTML("<div class='hero'><h2>The agent crew, and what it was "
                    "allowed to do</h2><p>AI agents chose <b>what to examine and "
                    "what the thresholds should be</b>. A deterministic rule "
                    "engine decided <b>every role, score, cluster and rank</b>. "
                    "No agent can change a classification.</p></div>")

            calib = calibration_table()
            if calib is not None and not calib.empty:
                gr.Markdown("### Thresholds the calibrator agent chose")
                gr.HTML(note(
                    "The agent read the real distribution of every metric and "
                    "picked these numbers, writing a justification for each. "
                    "Before being accepted, each set was <b>simulated against "
                    "the actual data</b> — a set that emptied a role, or handed "
                    "one role half the network, is rejected and the hand-set "
                    "defaults stand. The result is saved and reused, so the run "
                    "reproduces exactly."))
                gr.Dataframe(calib, wrap=True, max_height=380, interactive=False)

            dossiers = dossier_table()
            if not dossiers.empty:
                gr.Markdown("### Case dossiers")
                gr.HTML(note(
                    "For each top account, an agent ran a multi-step "
                    "investigation using only graph queries. It is required to "
                    "offer a plausible <b>innocent</b> explanation — a payroll "
                    "account and a collection point look identical in this data."))
                gr.Dataframe(dossiers, wrap=True, max_height=380, interactive=False)

            with gr.Accordion("The argument against this shortlist", open=True):
                gr.HTML(note(
                    "A reviewer agent was asked to attack the results: which "
                    "entries rank highly because of how the data was collected, "
                    "which thresholds are doing suspicious work, what is missing. "
                    "With no ground truth to validate against, this is the "
                    "closest thing to a check that exists."))
                gr.Markdown(S.text("review_notes.md", "*The critic did not run.*"))
            with gr.Accordion("Full audit log — every agent action and tool call",
                              open=False):
                gr.Markdown(S.text("agent_log.md", "*No agent log.*"))
            with gr.Accordion("What data is missing, and what to request next",
                              open=False):
                gr.Markdown(S.text("data_requests.md", "*Not generated.*"))

        # ------------------------------------------------------------ 7. data
        with gr.Tab("Your data"):
            gr.HTML("<div class='hero'><h2>What was loaded</h2><p>This tool does "
                    "not require the three files from the case pack. It reads "
                    "whatever tabular export you point it at and works out which "
                    "column is which.</p></div>")
            gr.Markdown("### Files used in this run")
            gr.HTML(ingest_summary())
            gr.Markdown("### How each column was understood")
            gr.HTML(note(
                "Columns are matched by name first (an alias list covers "
                "<code>from</code>/<code>payer</code>/<code>src</code>, "
                "<code>amount</code>/<code>sum_kzt</code>/<code>value</code>, and "
                "so on), then by structure — a date column is the date, the "
                "integer pair whose values overlap is the two ends of a transfer. "
                "Anything still unresolved is passed to an agent, whose answer is "
                "<b>re-checked against the data</b> before it is accepted."))
            gr.Dataframe(mapping_table(), wrap=True, max_height=340,
                         interactive=False)
            gr.HTML(note(
                "<b>To run this on your own export:</b> put the files in a folder "
                "and run <code>./agent_run.sh --data /path/to/folder</code>. "
                "Parquet, CSV, TSV, JSON, JSONL and XLSX are all read. If there "
                "is no account list, it is derived from the transfers; if there "
                "is no hop number, it is recomputed; if there is no seed flag, "
                "accounts with no traced inflow are treated as seeds — and the "
                "report says so, because that assumption drives every role."))
            with gr.Accordion("Full data profile — every announced fact checked",
                              open=False):
                gr.Markdown(S.text("profile_report.md", "*Not generated.*"))

        # ----------------------------------------------------------- 8. trace
        with gr.Tab("Cost & timing"):
            gr.HTML("<div class='hero'><h2>What this run cost</h2><p>Every stage "
                    "timed, every token counted, every call priced.</p></div>")
            gr.HTML(trace_kpis())
            gr.HTML(note(
                "Token counts are exactly what the provider reported — never "
                "estimated. If a model has no rates configured, the spend reads "
                "<b>unpriced</b> rather than showing a number that looks "
                "authoritative."))
            gr.Markdown(S.text(CFG["tracing"].get("write_markdown") or "run_trace.md",
                               "*No trace file.*"))

        # --------------------------------------------------------- 9. exports
        with gr.Tab("Downloads"):
            gr.HTML("<div class='hero'><h2>Deliverables</h2><p>The three required "
                    "exports, plus everything the viewer reads.</p></div>")
            names = ["nodes_roles.csv", "clusters.csv", "top_nodes.csv",
                     "node_features.parquet", "graph_edges.parquet",
                     "profile_report.md", "data_requests.md", "review_notes.md",
                     "agent_log.md", "dossiers.json", "ingest_report.json",
                     "run_trace.md", "run_trace.json"]
            gr.File([str(OUT / n) for n in names if (OUT / n).exists()],
                    label="Download", interactive=False, file_count="multiple")
            gr.HTML(note(
                "<b>nodes_roles.csv</b> — one row per account: role, confidence, "
                "group, priority and the evidence sentence.<br>"
                "<b>clusters.csv</b> — one row per group, with its hypothesis.<br>"
                "<b>top_nodes.csv</b> — the ranked shortlist with reasons."))
            gr.Dataframe(S.nodes.head(40), wrap=True, max_height=330,
                         label="nodes_roles.csv — first 40 rows", interactive=False)

    return demo


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Money Graph viewer")
    ap.add_argument("--share", action="store_true")
    ap.add_argument("--no-share", action="store_true")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default=None)
    a = ap.parse_args()

    share = bool(VIEW["share"]) or _truthy(os.environ.get("MONEYGRAPH_SHARE")) or a.share
    if a.no_share:
        share = False
    build().launch(
        server_name=a.host or os.environ.get("MONEYGRAPH_HOST") or VIEW["host"],
        server_port=int(a.port or os.environ.get("MONEYGRAPH_PORT") or VIEW["port"]),
        share=share, show_api=False, inbrowser=False, quiet=False,
        # The network maps are written under output_files/_maps and served from
        # there; without this Gradio refuses to hand them to the browser.
        allowed_paths=[str(OUT)])
