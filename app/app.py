"""Money Graph viewer (Gradio).

Reads `output_files/` only — it never recomputes, so it opens instantly and
shows exactly what the exported CSVs contain. Run the pipeline first.

The demo path the brief asks for (must-have 5: "the jury names a gid — the team
finds it on the map and shows its links") is the **Node search** tab: type a
gid, get the role, the rule that produced it with its actual numbers, and the
ego network with flow directions and amounts.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

import gradio as gr
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moneygraph.io import load_config          # noqa: E402

CFG = load_config(ROOT / "config.yaml")
OUT = ROOT / CFG["paths"]["outputs"]
VIEW = CFG["viewer"]
ROLE_COLORS = VIEW["role_colors"]

CSS = """
.kpi { text-align:center; padding:14px 8px; border-radius:10px;
       background:var(--block-background-fill); border:1px solid var(--border-color-primary); }
.kpi .v { font-size:1.7rem; font-weight:650; line-height:1.2; }
.kpi .l { font-size:.78rem; opacity:.72; text-transform:uppercase; letter-spacing:.04em; }
.legend span { display:inline-block; margin:0 10px 6px 0; font-size:.85rem; }
.legend i { display:inline-block; width:11px; height:11px; border-radius:50%;
            margin-right:5px; vertical-align:middle; }
.trace { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.85rem; }
"""


# ---------------------------------------------------------------------------
# data access
# ---------------------------------------------------------------------------

class Store:
    """Everything the viewer needs, loaded once from output_files/."""

    def __init__(self) -> None:
        self.ok = False
        self.missing: list[str] = []
        self.load()

    def load(self) -> None:
        required = ["nodes_roles.csv", "clusters.csv", "top_nodes.csv",
                    "node_features.parquet", "graph_edges.parquet"]
        self.missing = [f for f in required if not (OUT / f).exists()]
        if self.missing:
            self.ok = False
            return
        self.nodes = pd.read_csv(OUT / "nodes_roles.csv")
        self.clusters = pd.read_csv(OUT / "clusters.csv")
        self.top = pd.read_csv(OUT / "top_nodes.csv")
        self.features = pd.read_parquet(OUT / "node_features.parquet")
        self.edges = pd.read_parquet(OUT / "graph_edges.parquet")
        self.f = self.features.set_index("gid", drop=False)
        self.dossiers = {}
        p = OUT / "dossiers.json"
        if p.exists():
            try:
                self.dossiers = {int(k): v for k, v in
                                 json.loads(p.read_text(encoding="utf-8")).items()}
            except (ValueError, TypeError):
                self.dossiers = {}
        self.ok = True

    def text(self, name: str, fallback: str = "") -> str:
        p = OUT / name
        return p.read_text(encoding="utf-8") if p.exists() else fallback

    def trace_json(self) -> dict:
        p = OUT / (CFG["tracing"].get("write_json") or "run_trace.json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def rule_trace(self, gid: int) -> dict:
        if gid not in self.f.index:
            return {}
        raw = self.f.at[gid, "rule_trace"]
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {}


S = Store()


def _tools():
    from moneygraph.agents.tools import GraphTools

    return GraphTools(S.nodes, S.edges, S.clusters)


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def kzt(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if pd.isna(x):
        return "n/a"
    if abs(x) >= 1e9:
        return f"{x / 1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f}M"
    if abs(x) >= 1e3:
        return f"{x / 1e3:.0f}k"
    return f"{x:,.0f}"


def legend_html() -> str:
    items = "".join(
        f"<span><i style='background:{c}'></i>{r}</span>"
        for r, c in ROLE_COLORS.items())
    return (f"<div class='legend'>{items}"
            "<span>◆ seed &nbsp; ● other &nbsp; dashed border = onward flow not traced"
            " &nbsp; arrow = direction of money &nbsp; thickness = log(amount)</span></div>")


def kpi(value: str, label: str) -> str:
    return f"<div class='kpi'><div class='v'>{value}</div><div class='l'>{label}</div></div>"


# ---------------------------------------------------------------------------
# graph rendering
# ---------------------------------------------------------------------------

def ego_html(gid: int, hops: int) -> str:
    """Pyvis ego network, inlined so it works with no internet access."""
    from pyvis.network import Network

    if gid not in S.f.index:
        return "<p>Unknown gid.</p>"

    keep = {gid}
    frontier = {gid}
    for _ in range(max(int(hops), 1)):
        nxt = set()
        sel = S.edges[S.edges["src"].isin(frontier) | S.edges["dst"].isin(frontier)]
        nxt |= set(sel["src"]) | set(sel["dst"])
        frontier = nxt - keep
        keep |= nxt
    cap = int(VIEW["ego_max_nodes"])
    capped = len(keep) > cap
    if capped:
        # Keep the centre plus its heaviest links, so the map stays readable.
        sel = S.edges[S.edges["src"].isin(keep) & S.edges["dst"].isin(keep)]
        sel = sel.nlargest(cap, "sum_kzt")
        keep = {gid} | set(sel["src"]) | set(sel["dst"])

    sub = S.edges[S.edges["src"].isin(keep) & S.edges["dst"].isin(keep)]
    net = _network()
    for n in sorted(keep):
        _add_node(net, int(n), centre=(int(n) == int(gid)))
    for e in sub.itertuples(index=False):
        _add_edge(net, e)
    body = net.generate_html(notebook=False)
    note = (f"<p style='font-size:.85rem;opacity:.75'>Map capped at {cap} nodes "
            f"(heaviest links kept).</p>") if capped else ""
    return note + _iframe(body, height=560)


def cluster_html(cluster_id: int) -> str:
    from pyvis.network import Network

    members = S.nodes[S.nodes["cluster_id"] == int(cluster_id)]
    gids = set(members["gid"].astype(int))
    cap = int(VIEW["cluster_map_max_nodes"])
    capped = len(gids) > cap
    if capped:
        gids = set(members.nlargest(cap, "priority_score")["gid"].astype(int))
    sub = S.edges[S.edges["src"].isin(gids) & S.edges["dst"].isin(gids)]
    net = _network()
    for n in sorted(gids):
        _add_node(net, int(n))
    for e in sub.itertuples(index=False):
        _add_edge(net, e)
    note = (f"<p style='font-size:.85rem;opacity:.75'>Showing the {cap} "
            f"highest-priority of {len(members)} nodes.</p>") if capped else ""
    return note + _iframe(net.generate_html(notebook=False), height=620)


def _network():
    from pyvis.network import Network

    net = Network(height="540px", width="100%", directed=True,
                  bgcolor="#ffffff", font_color="#222222",
                  cdn_resources="in_line")   # offline
    net.set_options(json.dumps({
        "physics": {"enabled": bool(VIEW["physics"]),
                    "stabilization": {"iterations": 120}},
        "layout": {"randomSeed": int(CFG.get("seed", 42))},
        "edges": {"arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
                  "smooth": {"type": "dynamic"}, "font": {"size": 10}},
        "nodes": {"font": {"size": 13}},
        "interaction": {"hover": True, "tooltipDelay": 120},
    }))
    return net


def _add_node(net, gid: int, centre: bool = False) -> None:
    r = S.f.loc[gid]
    role = str(r["role"])
    is_seed = bool(r["is_seed"])
    traced = bool(r.get("outflow_observed", True))
    tooltip = (f"gid {gid}\nrole: {role} (score {float(r['role_score']):.2f})\n"
               f"priority: {float(r['priority_score']):.3f}\n"
               f"cluster {int(r['cluster_id'])} · hop {int(r['depth'])}"
               f"{' · SEED' if is_seed else ''}\n"
               f"in {kzt(r['in_sum'])} from {int(r['in_deg'])} · "
               f"out {kzt(r['out_sum'])} to {int(r['out_deg'])}\n\n"
               f"{r['evidence']}")
    net.add_node(
        gid, label=str(gid), title=tooltip,
        color={"background": ROLE_COLORS.get(role, "#999999"),
               "border": "#222222" if centre else ("#888888" if traced else "#cc3333"),
               "highlight": {"background": ROLE_COLORS.get(role, "#999999"),
                             "border": "#000000"}},
        shape="diamond" if is_seed else "dot",
        size=26 if centre else (10 + 22 * float(r["priority_score"])),
        borderWidth=4 if centre else (1 if traced else 3),
        shapeProperties={"borderDashes": [] if traced else [4, 3]},
    )


def _add_edge(net, e) -> None:
    import math

    net.add_edge(int(e.src), int(e.dst),
                 value=math.log1p(float(e.sum_kzt)),
                 title=f"{float(e.sum_kzt):,.0f} KZT over {int(e.n_tx)} transfer(s)",
                 label=kzt(e.sum_kzt), color="#9aa5ad")


def _iframe(doc: str, height: int) -> str:
    return (f'<iframe srcdoc="{html.escape(doc, quote=True)}" '
            f'style="width:100%;height:{height}px;border:1px solid #ddd;'
            f'border-radius:8px;background:#fff"></iframe>')


# ---------------------------------------------------------------------------
# node card
# ---------------------------------------------------------------------------

def node_card(gid_text: str, hops: int):
    """The demo answer: role, the rule that fired, the numbers, the map."""
    try:
        gid = int(str(gid_text).strip())
    except (TypeError, ValueError):
        return "Enter a numeric gid.", "", "", pd.DataFrame(), pd.DataFrame()
    if gid not in S.f.index:
        return f"**gid {gid} is not in this dataset.**", "", "", pd.DataFrame(), pd.DataFrame()

    r = S.f.loc[gid]
    t = S.rule_trace(gid)
    role = str(r["role"])
    colour = ROLE_COLORS.get(role, "#999")

    card = [
        f"## gid {gid} &nbsp; <span style='color:{colour}'>●</span> **{role}**",
        "",
        f"| | |\n|---|---|",
        f"| Role confidence | {float(r['role_score']):.2f} |",
        f"| Review priority | **{float(r['priority_score']):.4f}** |",
        f"| Cluster | {int(r['cluster_id'])} |",
        f"| Hop from seed | {int(r['depth'])}"
        + (" — **traversal frontier, onward flow never traced**"
           if not bool(r.get("outflow_observed", True)) else "") + " |",
        f"| Known seed | {'yes' if bool(r['is_seed']) else 'no'} |",
        f"| Received | {kzt(r['in_sum'])} KZT from {int(r['in_deg'])} payer(s) |",
        f"| Sent | {kzt(r['out_sum'])} KZT to {int(r['out_deg'])} recipient(s) |",
        f"| Seeds that can reach it | {int(r.get('seed_reach', 0))} |",
        f"| Est. seed-originated flow | {kzt(r.get('seed_kzt_attributed', 0))} KZT |",
        "",
        f"**Evidence.** {r['evidence']}",
    ]
    if str(r.get("secondary_roles", "")):
        card.append(f"\n**Also matches:** {r['secondary_roles']}")

    # The rule trace — this is what answers "explain this gid in under a minute".
    rule = ["### Why this role", ""]
    if t:
        rule += [f"**Rule that fired:** `{t.get('gate', 'n/a')}`", ""]
        metrics, thresholds = t.get("metrics", {}), t.get("thresholds", {})
        if metrics:
            rule += ["| Metric the rule used | Value |", "|---|---:|"]
            rule += [f"| {k} | {_v(v)} |" for k, v in metrics.items()]
            rule.append("")
        if thresholds:
            rule += ["| Threshold (from config.yaml) | Value |", "|---|---:|"]
            rule += [f"| {k} | {_v(v)} |" for k, v in thresholds.items()]
            rule.append("")
        if t.get("penalties"):
            rule += ["**Confidence penalties applied:**"] + \
                    [f"- {p}" for p in t["penalties"]] + [""]
        if t.get("notes"):
            rule += ["**Notes:**"] + [f"- {n}" for n in t["notes"]] + [""]
    adj = str(r.get("priority_adjustments", "") or "")
    if adj:
        rule += [f"**Priority adjustment:** {adj}", ""]
    rule += ["_Every figure above comes from the rule engine, not from a model._"]

    # The investigator's dossier and the critic's caveat, when this account was
    # deep-dived. Both are advisory: neither changed the role or the rank.
    d = S.dossiers.get(gid)
    if d:
        rule += ["", "---", "", "### Investigator dossier", "",
                 f"**Pattern:** {d.get('pattern', '—')}"
                 + (f" &nbsp;·&nbsp; confidence: {d.get('confidence')}"
                    if d.get("confidence") else ""), "",
                 str(d.get("summary", "")), ""]
        if d.get("alternative_explanation"):
            rule += [f"**Most plausible innocent explanation.** "
                     f"{d['alternative_explanation']}", ""]
        if d.get("next_step"):
            rule += [f"**Suggested next step.** {d['next_step']}", ""]
        rule += ["_Advisory only — the role and rank above were set by the rule "
                 "engine and are unaffected by this._"]

    caveat = str(r.get("critic_caveat", "") or "")
    if caveat:
        card += ["", "> **Reviewer's caveat.** " + caveat.replace(" | ", "\n>\n> ")]

    payers = _links(gid, "dst", "src", "Payer")
    recipients = _links(gid, "src", "dst", "Recipient")
    return "\n".join(card), "\n".join(rule), ego_html(gid, hops), payers, recipients


def _v(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1e5 else f"{v:,.0f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def _links(gid: int, match_col: str, other_col: str, label: str) -> pd.DataFrame:
    sel = S.edges[S.edges[match_col] == gid]
    if sel.empty:
        return pd.DataFrame({label: [], "Role": [], "KZT": [], "Transfers": []})
    out = pd.DataFrame({
        label: sel[other_col].astype(int),
        "Role": sel[other_col].map(S.f["role"]),
        "Seed": sel[other_col].map(S.f["is_seed"]).map({True: "yes", False: ""}),
        "KZT": sel["sum_kzt"].round(0).astype("int64"),
        "Transfers": sel["n_tx"].astype(int),
    })
    return out.sort_values("KZT", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# tab builders
# ---------------------------------------------------------------------------

def role_figure():
    import plotly.express as px

    counts = S.nodes["role"].value_counts().reset_index()
    counts.columns = ["role", "n"]
    fig = px.bar(counts, x="n", y="role", orientation="h", text="n",
                 color="role", color_discrete_map=ROLE_COLORS)
    fig.update_layout(showlegend=False, height=300,
                      margin=dict(l=8, r=8, t=8, b=8),
                      xaxis_title="nodes", yaxis_title=None)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig


def overview_kpis() -> str:
    n = len(S.nodes)
    turnover = float(S.edges["sum_kzt"].sum())
    frontier = int((~S.features["outflow_observed"]).sum()) \
        if "outflow_observed" in S.features else 0
    cells = [
        kpi(f"{n:,}", "accounts"),
        kpi(f"{int(S.nodes['is_seed'].sum())}", "known seeds"),
        kpi(f"{kzt(turnover)}", "KZT traced"),
        kpi(f"{len(S.clusters)}", "clusters"),
        kpi(f"{frontier}", "on the frontier"),
    ]
    return ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));"
            "gap:10px'>" + "".join(cells) + "</div>")


def trace_summary() -> str:
    d = S.trace_json()
    if not d:
        return "_No run trace found. Run `python run.py` to generate one._"
    t = d.get("totals", {})
    cost = t.get("cost_usd")
    cost_txt = f"${cost:.4f}" if isinstance(cost, (int, float)) else "unpriced"
    cells = [
        kpi(f"{d.get('total_runtime_s', 0):.1f}s", "total runtime"),
        kpi(f"{d.get('runtime_budget_s', 300):.0f}s", "budget"),
        kpi(f"{t.get('n_calls', 0)}", "model calls"),
        kpi(f"{t.get('total_tokens', 0):,}", "tokens"),
        kpi(cost_txt, "spend"),
    ]
    return ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));"
            "gap:10px'>" + "".join(cells) + "</div>")


def _calibration() -> pd.DataFrame | None:
    """The calibrator's thresholds and its written rationale for each."""
    import yaml

    path = ROOT / "config.calibrated.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    thresholds = data.get("thresholds") or {}
    if not thresholds:
        return None
    rationale = data.get("rationale") or {}
    return pd.DataFrame({
        "threshold": list(thresholds),
        "value": [thresholds[k] for k in thresholds],
        "why the agent chose it": [rationale.get(k, "—") for k in thresholds],
    })


def _dossier_table() -> pd.DataFrame:
    rows = []
    for gid, d in sorted(S.dossiers.items()):
        rows.append({
            "gid": gid,
            "role": S.f.at[gid, "role"] if gid in S.f.index else "",
            "pattern": d.get("pattern", ""),
            "summary": d.get("summary", ""),
            "innocent explanation": d.get("alternative_explanation", ""),
            "next step": d.get("next_step", ""),
            "confidence": d.get("confidence", ""),
        })
    return pd.DataFrame(rows)


def ask_agent(question: str, history: list):
    """Natural-language question -> deterministic tool calls -> cited answer."""
    history = history or []
    if not question or not question.strip():
        return history, ""
    from moneygraph.agents.analyst_agent import ask
    from moneygraph.agents.llm import LLMClient
    from moneygraph.trace import RunTracer

    tracer = RunTracer(CFG)
    client = LLMClient(CFG, tracer)
    answer = ask(question, _tools(), client, CFG)

    parts = [answer.text]
    if answer.note:
        parts.append(f"\n_{answer.note}_")
    if answer.tool_calls:
        calls = "\n".join(
            f"- `{c['tool']}({json.dumps(c.get('args', {}), default=str)})`"
            + (f" — error: {c['error']}" if c.get("error") else "")
            for c in answer.tool_calls)
        parts.append(f"\n<details><summary>Graph queries behind this answer "
                     f"({len(answer.tool_calls)})</summary>\n\n{calls}\n</details>")
    t = tracer.totals()
    if t["n_calls"]:
        cost = t["cost_usd"]
        parts.append(f"\n<sub>{t['n_calls']} model call(s), {t['total_tokens']:,} "
                     f"tokens, {f'${cost:.4f}' if cost is not None else 'unpriced'}, "
                     f"{tracer.elapsed_s:.1f}s</sub>")

    history = history + [{"role": "user", "content": question},
                         {"role": "assistant", "content": "\n".join(parts)}]
    return history, ""


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------

def build() -> gr.Blocks:
    with gr.Blocks(title="Money Graph", css=CSS,
                   theme=gr.themes.Soft(primary_hue="slate")) as demo:
        gr.Markdown(
            "# Money Graph\n"
            "Roles, clusters and review priority over an intra-bank transfer "
            "export. **Every figure shown is a hypothesis for an analyst to "
            "verify, not a finding of fact.**")

        if not S.ok:
            gr.Markdown(
                f"### Outputs not found\n\nMissing from `{OUT}`: "
                f"`{'`, `'.join(S.missing)}`\n\nRun the pipeline first:\n"
                f"```bash\npython run.py\n```")
            prof = S.text("profile_report.md")
            if prof:
                with gr.Accordion("Data profile (already generated)", open=False):
                    gr.Markdown(prof)
            return demo

        with gr.Tab("Overview"):
            gr.HTML(overview_kpis())
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Roles assigned")
                    gr.Plot(role_figure())
                with gr.Column(scale=1):
                    gr.Markdown("### Clusters and what they look like")
                    gr.Dataframe(
                        S.clusters.assign(
                            sum_kzt_internal=S.clusters["sum_kzt_internal"].map(kzt)),
                        wrap=True, max_height=340)
            with gr.Accordion("Data profile report", open=False):
                gr.Markdown(S.text("profile_report.md", "_not generated_"))
            with gr.Accordion("What data is missing, and what to request next",
                              open=False):
                gr.Markdown(S.text("data_requests.md", "_not generated_"))

        with gr.Tab("Priority list"):
            gr.Markdown(
                "### Who to look at first\n"
                "Ranked by `priority_score`. The `why` column names the "
                "components that actually drove the rank.")
            gr.Dataframe(S.top, wrap=True, max_height=520)
            gr.Markdown("_Open any gid in **Node search** to see its rule trace "
                        "and its links._")

        with gr.Tab("Node search"):
            gr.Markdown("### Find an account and explain it\n"
                        "Type a gid — the card shows the rule that produced its "
                        "role, with the exact numbers the rule compared.")
            with gr.Row():
                gid_in = gr.Textbox(label="gid", scale=3,
                                    placeholder="e.g. one of the top_nodes gids")
                hops_in = gr.Slider(1, 2, value=int(VIEW["ego_hops_default"]),
                                    step=1, label="ego hops", scale=1)
                go = gr.Button("Show", variant="primary", scale=1)
            pick = gr.Dropdown(
                choices=[str(int(g)) for g in S.top["gid"]],
                label="…or pick from the priority list", value=None)
            with gr.Row():
                card_out = gr.Markdown()
                rule_out = gr.Markdown()
            gr.HTML(legend_html())
            map_out = gr.HTML()
            with gr.Row():
                payers_out = gr.Dataframe(label="Payers (money in)", max_height=280)
                recips_out = gr.Dataframe(label="Recipients (money out)", max_height=280)

            outputs = [card_out, rule_out, map_out, payers_out, recips_out]
            go.click(node_card, [gid_in, hops_in], outputs)
            gid_in.submit(node_card, [gid_in, hops_in], outputs)
            pick.change(lambda g, h: node_card(g, h) if g else
                        ("", "", "", pd.DataFrame(), pd.DataFrame()),
                        [pick, hops_in], outputs)

        with gr.Tab("Cluster map"):
            gr.Markdown("### Clusters\n"
                        "Louvain on the undirected projection (grouping only — "
                        "every metric and every arrow still uses direction).")
            cl = gr.Dropdown(
                choices=[str(int(c)) for c in S.clusters["cluster_id"]],
                value=str(int(S.clusters["cluster_id"].iloc[0])),
                label="cluster")
            cl_info = gr.Markdown()
            gr.HTML(legend_html())
            cl_map = gr.HTML()
            cl_members = gr.Dataframe(label="Members", max_height=320)

            def show_cluster(cid):
                cid = int(cid)
                row = S.clusters[S.clusters["cluster_id"] == cid].iloc[0]
                members = S.nodes[S.nodes["cluster_id"] == cid].sort_values(
                    "priority_score", ascending=False)
                info = (f"**Cluster {cid}** — {int(row['n_nodes'])} accounts, "
                        f"{int(row['n_seed'])} seed(s), "
                        f"{kzt(row['sum_kzt_internal'])} KZT internal turnover\n\n"
                        f"> {row['hypothesis']}")
                cols = ["gid", "role", "role_score", "priority_score", "evidence"]
                return info, cluster_html(cid), members[cols].reset_index(drop=True)

            cl.change(show_cluster, cl, [cl_info, cl_map, cl_members])
            demo.load(show_cluster, cl, [cl_info, cl_map, cl_members])

        with gr.Tab("Analyst"):
            gr.Markdown(
                "### Ask a question about the network\n"
                "The answer is composed only from deterministic graph queries — "
                "expand *Graph queries behind this answer* to check every claim. "
                "Without an API key the same functions still run; only the "
                "phrasing is plainer.")
            chat = gr.Chatbot(type="messages", height=430)
            q = gr.Textbox(label="Question", placeholder=
                           "Who collects money from these five? 1234; 5678; …")
            with gr.Row():
                send = gr.Button("Ask", variant="primary")
                clear = gr.Button("Clear")
            gr.Examples(
                ["Which accounts should I review first, and why?",
                 "Who are the biggest collection points that sit on the traversal frontier?",
                 "What would I need to request to see past hop 4?"],
                inputs=q)
            send.click(ask_agent, [q, chat], [chat, q])
            q.submit(ask_agent, [q, chat], [chat, q])
            clear.click(lambda: ([], ""), None, [chat, q])

        with gr.Tab("Agents"):
            gr.Markdown(
                "### What the crew did\n"
                "Agents choose **what to examine and what the thresholds should "
                "be**. The rule engine decides **what the role is** — no agent "
                "can change a role, a score, a cluster or a rank. Every action "
                "below is logged with the tool calls behind it.")

            calib = _calibration()
            if calib:
                gr.Markdown("#### Thresholds chosen by the calibrator agent")
                gr.Dataframe(calib, wrap=True, max_height=320)
                gr.Markdown(
                    "_Persisted to `config.calibrated.yaml` and reused on every "
                    "run, so the submitted result reproduces exactly. Each "
                    "proposal was simulated against the real distribution before "
                    "being accepted; one that emptied a role or claimed half the "
                    "graph would have been rejected._")

            if S.dossiers:
                gr.Markdown("#### Case dossiers")
                gr.Dataframe(_dossier_table(), wrap=True, max_height=380)

            with gr.Accordion("Review notes — the argument against this list",
                              open=True):
                gr.Markdown(S.text("review_notes.md",
                                   "_critic did not run_"))
            with gr.Accordion("Full agent log (every tool call and rejection)",
                              open=False):
                gr.Markdown(S.text("agent_log.md", "_no agent log_"))

        with gr.Tab("Run trace"):
            gr.Markdown("### Time, tokens and spend")
            gr.HTML(trace_summary())
            gr.Markdown(S.text(CFG["tracing"].get("write_markdown") or "run_trace.md",
                               "_no trace file_"))

        with gr.Tab("Exports"):
            gr.Markdown("### Deliverables\nThe three required CSVs, plus the "
                        "artifacts the viewer reads.")
            files = [OUT / n for n in
                     ["nodes_roles.csv", "clusters.csv", "top_nodes.csv",
                      "node_features.parquet", "profile_report.md",
                      "data_requests.md", "review_notes.md", "agent_log.md",
                      "dossiers.json", "run_trace.md", "run_trace.json"]
                     if (OUT / n).exists()]
            gr.File(value=[str(p) for p in files], label="Download",
                    interactive=False, file_count="multiple")
            gr.Dataframe(S.nodes.head(50), label="nodes_roles.csv (first 50 rows)",
                         wrap=True, max_height=340)

    return demo


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Money Graph viewer")
    ap.add_argument("--share", action="store_true",
                    help="create a public gradio.live link (also MONEYGRAPH_SHARE=1)")
    ap.add_argument("--no-share", action="store_true", help="force local only")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default=None)
    a = ap.parse_args()

    share = bool(VIEW["share"]) or _truthy(os.environ.get("MONEYGRAPH_SHARE")) or a.share
    if a.no_share:
        share = False

    build().launch(
        server_name=a.host or os.environ.get("MONEYGRAPH_HOST") or VIEW["host"],
        server_port=int(a.port or os.environ.get("MONEYGRAPH_PORT") or VIEW["port"]),
        share=share, show_api=False, inbrowser=False, quiet=False)
