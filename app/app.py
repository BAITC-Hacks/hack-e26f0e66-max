"""Money Graph viewer.

Reads `output_files/` only — it never recomputes, so it opens instantly and
shows exactly what the exported CSVs contain.

Layout follows the analyst's question order:

    Start here -> Who to review first -> Account detail -> everything else

Two rules this file keeps:

* **Nothing on screen without a label saying what it is and what to do with
  it.** A network map with no reading guide is a decoration.
* **Every panel carries its content from the moment the page is built.** No
  component waits for a load event to fill in, because a component that starts
  empty is a component that stays empty when anything goes wrong.

Three languages. Russian is the default — the analyst this is built for works
in a Kazakhstani bank. Switching re-localizes every string in place, including
the evidence sentences, which are rebuilt from each node's rule trace rather
than translated, so the figures cannot drift between languages.
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

from moneygraph.i18n import (          # noqa: E402
    DEFAULT_LANG, LANGUAGES, TAB_GUIDE, evidence_from_trace, fmt_money,
    hypothesis_from_members, machine_translation_notice, role_meaning,
    role_name, t, why_from_row)
from moneygraph.io import load_config  # noqa: E402

CFG = load_config(ROOT / "config.yaml")
OUT = ROOT / CFG["paths"]["outputs"]
VIEW = CFG["viewer"]
ROLE_COLORS = VIEW["role_colors"]
WEIGHTS = CFG["priority"]["weights"]
MAPS = OUT / "_maps"

CSS = """
.gradio-container { max-width: 1340px !important; }

/* --- tab bar: this is the primary navigation, so it reads as navigation --- */
.tab-nav, .tabs > .tab-nav { gap: 2px !important;
    border-bottom: 2px solid var(--border-color-primary) !important;
    margin-bottom: 24px !important; flex-wrap: wrap; }
.tab-nav button, .tabs > .tab-nav > button {
    font-size: 1.05rem !important; font-weight: 650 !important;
    padding: 14px 21px !important; border: none !important;
    border-bottom: 3px solid transparent !important;
    border-radius: 9px 9px 0 0 !important; opacity: .6;
    transition: opacity .15s ease, background .15s ease; }
.tab-nav button:hover { opacity: .92; background: var(--block-background-fill) !important; }
.tab-nav button.selected, .tabs > .tab-nav > button.selected {
    opacity: 1 !important; font-weight: 780 !important;
    border-bottom: 3px solid var(--body-text-color) !important;
    background: var(--block-background-fill) !important; }

.langbar { display: flex; justify-content: flex-end; align-items: center;
            flex-wrap: nowrap !important; margin-bottom: 2px; }
/* All three languages stay on a single row, never stacked. */
.langbar .wrap, .langbar fieldset, .langbar .form {
    display: flex !important; flex-direction: row !important;
    flex-wrap: nowrap !important; gap: 4px; align-items: center; }
.langbar label { white-space: nowrap; margin: 0 !important; }
.mtbar { border-left: 3px solid #c9a227; background: rgba(201,162,39,.10);
         padding: 12px 16px; border-radius: 0 9px 9px 0; margin: 8px 0 16px 0;
         font-size: .9rem; line-height: 1.6; }
.hero { padding: 22px 26px; border-radius: 14px; border: 1px solid var(--border-color-primary);
        background: var(--block-background-fill); margin: 4px 0 18px 0; }
.hero h2 { margin: 0 0 8px 0; font-size: 1.4rem; }
.hero p  { margin: 0; opacity: .82; line-height: 1.6; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
        gap: 14px; margin: 8px 0 24px 0; }
.kpi { text-align: center; padding: 17px 11px; border-radius: 12px;
       background: var(--block-background-fill); border: 1px solid var(--border-color-primary); }
.kpi .v { font-size: 1.85rem; font-weight: 650; line-height: 1.15; }
.kpi .l { font-size: .74rem; opacity: .7; text-transform: uppercase;
          letter-spacing: .05em; margin-top: 5px; }
.kpi .s { font-size: .74rem; opacity: .55; margin-top: 3px; }
.note { border-left: 3px solid var(--color-accent, #888); padding: 13px 17px; margin: 16px 0;
        background: var(--block-background-fill); border-radius: 0 9px 9px 0;
        font-size: .91rem; line-height: 1.6; }
.warnbox { border-left: 3px solid #d98324; background: rgba(217,131,36,.09);
           padding: 13px 17px; border-radius: 0 9px 9px 0; margin: 16px 0;
           font-size: .91rem; line-height: 1.6; }
.legend { display: grid; grid-template-columns: repeat(auto-fit, minmax(252px, 1fr));
          gap: 10px 24px; padding: 18px 20px; margin: 12px 0 20px 0; border-radius: 12px;
          border: 1px solid var(--border-color-primary);
          background: var(--block-background-fill); font-size: .87rem; }
.legend .row { display: flex; align-items: center; gap: 9px; }
.legend .sw { width: 13px; height: 13px; border-radius: 50%; flex: none; }
.legend .t  { opacity: .78; }
.legend h4 { grid-column: 1/-1; margin: 2px 0; font-size: .77rem; opacity: .6;
             text-transform: uppercase; letter-spacing: .05em; }
.pill { display:inline-block; padding: 3px 12px; border-radius: 999px;
        font-size: .8rem; font-weight: 600; color: #fff; }
.facts { width: 100%; border-collapse: collapse; font-size: .93rem; margin-bottom: 8px; }
.facts td { padding: 8px 4px; border-bottom: 1px solid var(--border-color-primary); }
.facts td:first-child { opacity: .62; width: 48%; }
.facts td:last-child { text-align: right; font-variant-numeric: tabular-nums; }

/* --- room around the network maps --------------------------------------- */
.mapwrap { margin: 20px 0 30px 0; }
.mapwrap iframe { display: block; }

.bars { display: flex; flex-direction: column; gap: 10px; padding: 6px 2px 14px 2px; }
.bar { display: grid; grid-template-columns: 158px 1fr 96px; align-items: center; gap: 13px; }
.bl { display: flex; align-items: center; gap: 8px; font-size: .9rem; }
.bl .sw { width: 11px; height: 11px; border-radius: 50%; flex: none; }
.bt { height: 21px; background: var(--border-color-primary); border-radius: 5px; overflow: hidden; }
.bf { height: 100%; border-radius: 5px; transition: width .4s ease; }
.bn { font-size: .9rem; text-align: right; font-variant-numeric: tabular-nums; }
.bn .bp { opacity: .5; font-size: .78rem; margin-left: 7px; }
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
        self._traces: dict[int, dict] = {}

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
        if gid in self._traces:
            return self._traces[gid]
        if gid not in self.f.index:
            return {}
        try:
            d = json.loads(self.f.at[gid, "rule_trace"])
        except (TypeError, ValueError):
            d = {}
        self._traces[gid] = d
        return d

    def evidence(self, gid: int, lang: str) -> str:
        """Localized evidence, rebuilt from the rule trace."""
        if gid not in self.f.index:
            return ""
        row = self.f.loc[gid].to_dict()
        tr = self.rule_trace(gid)
        if not tr:
            return str(row.get("evidence", ""))
        return evidence_from_trace(tr, row, lang,
                                   limit=int(CFG["evidence"]["max_chars"]))


S = Store()


# ===========================================================================
# formatting
# ===========================================================================

def kzt(x, lang: str = DEFAULT_LANG) -> str:
    return fmt_money(x, lang)


def kpi(value: str, label: str, sub: str = "") -> str:
    return (f"<div class='kpi'><div class='v'>{value}</div>"
            f"<div class='l'>{label}</div>"
            + (f"<div class='s'>{sub}</div>" if sub else "") + "</div>")


def note(text: str) -> str:
    return f"<div class='note'>{text}</div>"


def warn(text: str) -> str:
    return f"<div class='warnbox'>{text}</div>"


def mt_banner(lang: str) -> str:
    """Disclosure that a language's strings are machine translated.

    Empty for reviewed languages, so the same component can carry it and simply
    disappear rather than needing to be shown and hidden.
    """
    notice = machine_translation_notice(lang)
    return f"<div class='mtbar'>{notice}</div>" if notice else ""


def hero(title: str, body: str) -> str:
    return f"<div class='hero'><h2>{title}</h2><p>{body}</p></div>"


def pill(role: str, lang: str) -> str:
    return (f"<span class='pill' style='background:{ROLE_COLORS.get(role, '#888')}'>"
            f"{role_name(role, lang)}</span>")


def legend_html(lang: str) -> str:
    rows = "".join(
        f"<div class='row'><span class='sw' style='background:{c}'></span>"
        f"<b>{role_name(r, lang)}</b><span class='t'>— {role_meaning(r, lang)}</span></div>"
        for r, c in ROLE_COLORS.items())
    shapes = f"<h4>{t('legend.shapes', lang)}</h4>" + "".join(
        f"<div class='row'><span class='t'>{t(k, lang)}</span></div>"
        for k in ("legend.diamond", "legend.circle", "legend.dashed",
                  "legend.arrow", "legend.width", "legend.size"))
    return (f"<div class='legend'><h4>{t('legend.colors', lang)}</h4>"
            f"{rows}{shapes}</div>")


def role_bars(lang: str) -> str:
    """The role distribution, drawn in CSS.

    Deliberately not a charting library: this is one bar chart, and a plotting
    dependency renders it through a JavaScript bundle whose version has to agree
    with the front end's. Hand-drawn, it cannot fail to display.
    """
    counts = S.nodes["role"].value_counts()
    total, widest = int(counts.sum()), int(counts.max() or 1)
    rows = [
        f"<div class='bar'><div class='bl'><span class='sw' style='background:"
        f"{ROLE_COLORS.get(role, '#888')}'></span>{role_name(role, lang)}</div>"
        f"<div class='bt' title='{role_meaning(role, lang)}'><div class='bf' "
        f"style='width:{max(1.2, 100 * n / widest):.1f}%;background:"
        f"{ROLE_COLORS.get(role, '#888')}'></div></div>"
        f"<div class='bn'>{n:,}<span class='bp'>{100 * n / total:.0f}%</span></div>"
        f"</div>".replace(",", " ")
        for role, n in counts.items()]
    return "<div class='bars'>" + "".join(rows) + "</div>"


# ===========================================================================
# network maps
# ===========================================================================

def _layout(gids: list[int], edges: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """Pre-compute node positions rather than letting the browser settle them.

    vis.js packs a small graph into a tight ball, which is what made the group
    maps unreadable. A seeded spring layout, scaled up, spreads the nodes — and
    because the seed is fixed, puts them in the same place on every run, so a
    demo can be rehearsed.
    """
    import networkx as nx

    g = nx.Graph()
    g.add_nodes_from(gids)
    keep = set(gids)
    for a, b in zip(edges["src"], edges["dst"]):
        if a in keep and b in keep:
            g.add_edge(int(a), int(b))
    n = max(len(gids), 1)
    # Spacing has to scale with size. A spread that looks right for a 12-node
    # ego map packs a 200-node cluster into an unreadable ball, so both the
    # target distance and the overall scale grow with the node count.
    k = max(2.2, 12.0 / (n ** 0.5))
    spread = float(VIEW.get("layout_spread", 240)) * (n ** 0.52)
    try:
        pos = nx.spring_layout(g, k=k, iterations=260,
                               seed=int(CFG.get("seed", 42)), scale=1.0)
    except Exception:
        pos = nx.circular_layout(g, scale=1.0)
    return {int(node): (float(xy[0]) * spread, float(xy[1]) * spread)
            for node, xy in pos.items()}


def _network(height: str = "560px"):
    from pyvis.network import Network

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#ffffff", font_color="#1a1a1a",
                  cdn_resources="in_line")          # works offline
    net.set_options(json.dumps({
        # Physics off: positions below are already settled, so the map opens
        # stable instead of writhing for several seconds.
        "physics": {"enabled": False},
        "layout": {"randomSeed": int(CFG.get("seed", 42)), "improvedLayout": False},
        "edges": {"arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
                  "color": {"color": "#ccd4db", "highlight": "#44525f", "opacity": 0.85},
                  "smooth": {"type": "curvedCW", "roundness": 0.12},
                  "scaling": {"min": 1, "max": 7},
                  "font": {"size": 11, "align": "top", "strokeWidth": 5,
                           "strokeColor": "#ffffff"}},
        "nodes": {"font": {"size": 13, "face": "system-ui", "vadjust": -4,
                           "strokeWidth": 5, "strokeColor": "#ffffff"},
                  "borderWidthSelected": 4},
        "interaction": {"hover": True, "tooltipDelay": 100, "zoomView": True,
                        "navigationButtons": True, "keyboard": False,
                        "dragNodes": True},
    }))
    return net


def _add_node(net, gid: int, lang: str, centre: bool = False,
              pos: tuple[float, float] | None = None) -> None:
    r = S.f.loc[gid]
    role = str(r["role"])
    is_seed, traced = bool(r["is_seed"]), bool(r.get("outflow_observed", True))
    tip = (f"{t('col.account', lang)} {gid}\n"
           f"{role_name(role, lang).upper()} — {role_meaning(role, lang)}\n"
           f"{'─' * 34}\n"
           f"{t('f.priority', lang)}: {float(r['priority_score']):.3f}\n"
           f"{t('f.confidence', lang)}: {float(r['role_score']):.2f}\n"
           f"{t('f.received', lang)}: {kzt(r['in_sum'], lang)} "
           f"{t('f.payers_n', lang, n=int(r['in_deg']))}\n"
           f"{t('f.sent', lang)}: {kzt(r['out_sum'], lang)} "
           f"{t('f.recipients_n', lang, n=int(r['out_deg']))}\n"
           f"{t('f.depth', lang)}: {int(r['depth'])}"
           f"{'  · ' + t('f.isseed', lang) if is_seed else ''}\n"
           f"{'─' * 34}\n{S.evidence(gid, lang)}")
    extra = {"x": pos[0], "y": pos[1], "physics": False} if pos else {}
    net.add_node(
        gid, label=str(gid)[-6:], title=tip, **extra,
        color={"background": ROLE_COLORS.get(role, "#999"),
               "border": "#111111" if centre else ("#8d99a4" if traced else "#cc3b3b")},
        shape="diamond" if is_seed else "dot",
        size=(30 if centre else 12 + 20 * float(r["priority_score"])),
        borderWidth=5 if centre else (1 if traced else 3),
        shapeProperties={"borderDashes": [] if traced else [5, 4]})


def _add_edge(net, e, show_amounts: bool, lang: str) -> None:
    import math

    net.add_edge(int(e.src), int(e.dst), value=math.log1p(float(e.sum_kzt)),
                 title=(f"{float(e.sum_kzt):,.0f} KZT · "
                        f"{int(e.n_tx)} {t('col.transfers', lang).lower()}"),
                 label=kzt(e.sum_kzt, lang) if show_amounts else None)


def _iframe(doc: str, height: int, key: str) -> str:
    """Serve the map as a file rather than inlining it.

    A pyvis document is ~1 MB. Pushing that through a `srcdoc` attribute means
    escaping a megabyte and shipping it over the event channel on every
    interaction — which is how the maps ended up blank. On disk and referenced
    by URL, the component value is ~200 bytes.
    """
    MAPS.mkdir(parents=True, exist_ok=True)
    path = MAPS / f"{key}-{hashlib.md5(doc.encode()).hexdigest()[:8]}.html"
    if not path.exists():
        path.write_text(doc, encoding="utf-8")
    return (f'<div class="mapwrap"><iframe src="/gradio_api/file={path}" '
            f'loading="lazy" style="width:100%;height:{height}px;border:1px solid '
            f'var(--border-color-primary);border-radius:12px;background:#fff">'
            f'</iframe></div>')


def ego_html(gid: int, hops: int, show_amounts: bool, lang: str) -> str:
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
    ordered = sorted(int(n) for n in keep)
    pos = _layout(ordered, sub)
    net = _network()
    for n in ordered:
        _add_node(net, n, lang, centre=(n == int(gid)), pos=pos.get(n))
    for e in sub.itertuples(index=False):
        _add_edge(net, e, show_amounts, lang)

    head = warn(t("map.capped", lang, cap=cap)) if capped else ""
    return head + _iframe(net.generate_html(notebook=False), 570,
                          f"ego-{gid}-{hops}-{int(show_amounts)}-{lang}")


def cluster_html(cluster_id: int, show_amounts: bool, lang: str) -> str:
    members = S.nodes[S.nodes["cluster_id"] == int(cluster_id)]
    gids = set(members["gid"].astype(int))
    cap = int(VIEW["cluster_map_max_nodes"])
    capped = len(gids) > cap
    if capped:
        gids = set(members.nlargest(cap, "priority_score")["gid"].astype(int))
    sub = S.edges[S.edges["src"].isin(gids) & S.edges["dst"].isin(gids)]
    ordered = sorted(int(n) for n in gids)
    pos = _layout(ordered, sub)
    # A 200-node group needs the room; a 3-node one does not.
    height = int(min(840, max(540, 440 + len(ordered) * 1.6)))
    net = _network(f"{height}px")
    for n in ordered:
        _add_node(net, n, lang, pos=pos.get(n))
    for e in sub.itertuples(index=False):
        _add_edge(net, e, show_amounts, lang)
    head = (warn(t("map.capped_cluster", lang, cap=cap, total=len(members)))
            if capped else "")
    return head + _iframe(net.generate_html(notebook=False), height + 20,
                          f"cluster-{cluster_id}-{int(show_amounts)}-{lang}")


# ===========================================================================
# tables
# ===========================================================================

def top_table(lang: str) -> pd.DataFrame:
    rows = S.top.merge(S.features, on="gid", how="left", suffixes=("", "_f"))
    return pd.DataFrame({
        t("col.rank", lang): S.top["rank"],
        t("col.account", lang): S.top["gid"],
        t("col.role", lang): [role_name(r, lang) for r in S.top["role"]],
        t("col.priority", lang): S.top["priority_score"].round(3),
        t("col.why", lang): [why_from_row(r, WEIGHTS, lang)
                             for r in rows.to_dict("records")],
    })


def cluster_table(lang: str) -> pd.DataFrame:
    hyps = []
    for row in S.clusters.to_dict("records"):
        members = S.features[S.features["cluster_id"] == row["cluster_id"]]
        hyps.append(hypothesis_from_members(row, members, lang))
    return pd.DataFrame({
        t("col.groupid", lang): S.clusters["cluster_id"],
        t("col.naccounts", lang): S.clusters["n_nodes"],
        t("col.nseeds", lang): S.clusters["n_seed"],
        t("col.internal", lang): [kzt(v, lang) for v in S.clusters["sum_kzt_internal"]],
        t("col.looks", lang): hyps,
    })


def mapping_table(lang: str) -> pd.DataFrame:
    rows = [{
        t("col.file", lang): f.get("file"),
        t("col.readas", lang): f.get("kind"),
        t("col.stdfield", lang): canonical,
        t("col.yourcol", lang): col,
        t("col.matchedby", lang): (f.get("resolved_by") or {}).get(canonical, "?"),
    } for f in (S.ingest.get("files") or [])
      for canonical, col in (f.get("mapping") or {}).items()]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        t("col.file", lang), t("col.readas", lang), t("col.stdfield", lang),
        t("col.yourcol", lang), t("col.matchedby", lang)])


def calibration_table(lang: str) -> pd.DataFrame:
    import yaml

    path = ROOT / "config.calibrated.yaml"
    cols = [t("col.threshold", lang), t("col.value", lang), t("col.whychosen", lang)]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    th, rat = data.get("thresholds") or {}, data.get("rationale") or {}
    if not th:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame({cols[0]: list(th), cols[1]: [th[k] for k in th],
                         cols[2]: [rat.get(k, "—") for k in th]})


def dossier_table(lang: str) -> pd.DataFrame:
    cols = [t("col.account", lang), t("col.role", lang), t("col.pattern", lang),
            t("col.found", lang), t("col.alt", lang), t("col.next", lang)]
    rows = [dict(zip(cols, [
        gid,
        role_name(S.f.at[gid, "role"], lang) if gid in S.f.index else "",
        d.get("pattern", ""), d.get("summary", ""),
        d.get("alternative_explanation", ""), d.get("next_step", "")]))
        for gid, d in sorted(S.dossiers.items())]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)


def links_table(gid: int, match: str, other: str, lang: str) -> pd.DataFrame:
    cols = [t("col.account", lang), t("col.itsrole", lang), t("col.seedq", lang),
            t("col.amount", lang), t("col.transfers", lang)]
    sel = S.edges[S.edges[match] == gid]
    if sel.empty:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        cols[0]: sel[other].astype("int64"),
        cols[1]: [role_name(r, lang) if isinstance(r, str) else "—"
                  for r in sel[other].map(S.f["role"])],
        cols[2]: sel[other].map(S.f["is_seed"]).map(
            {True: t("yes", lang), False: ""}).fillna(""),
        cols[3]: sel["sum_kzt"].round(0).astype("int64"),
        cols[4]: sel["n_tx"].astype("int64"),
    })
    return out.sort_values(cols[3], ascending=False).reset_index(drop=True)


# ===========================================================================
# panels
# ===========================================================================

def overview_kpis(lang: str) -> str:
    frontier = (int((~S.features["outflow_observed"]).sum())
                if "outflow_observed" in S.features else 0)
    cells = [
        kpi(f"{len(S.nodes):,}".replace(",", " "), t("kpi.accounts", lang),
            t("kpi.accounts.sub", lang)),
        kpi(f"{len(S.top)}", t("kpi.shortlist", lang), t("kpi.shortlist.sub", lang)),
        kpi(kzt(float(S.edges["sum_kzt"].sum()), lang).split(" ")[0],
            t("kpi.turnover", lang), t("kpi.turnover.sub", lang)),
        kpi(f"{len(S.clusters)}", t("kpi.groups", lang), t("kpi.groups.sub", lang)),
        kpi(f"{frontier}", t("kpi.frontier", lang), t("kpi.frontier.sub", lang)),
    ]
    return "<div class='kpis'>" + "".join(cells) + "</div>"


def trace_kpis(lang: str) -> str:
    d = S.trace
    if not d:
        return note(t("notgenerated", lang))
    tot = d.get("totals", {})
    cost = tot.get("cost_usd")
    cells = [
        kpi(f"{d.get('total_runtime_s', 0):.0f}s", t("cost.runtime", lang),
            t("cost.budget", lang, n=int(d.get("runtime_budget_s", 300)))),
        kpi(f"{tot.get('n_calls', 0)}", t("cost.calls", lang),
            t("cost.failed", lang, n=tot["n_failed"]) if tot.get("n_failed")
            else t("cost.allok", lang)),
        kpi(f"{tot.get('total_tokens', 0):,}".replace(",", " "),
            t("cost.tokens", lang),
            t("cost.reasoning", lang, n=tot.get("reasoning_tokens", 0))),
        kpi(f"${cost:.4f}" if isinstance(cost, (int, float))
            else t("cost.unpriced", lang), t("cost.spend", lang),
            t("cost.thisrun", lang)),
    ]
    return "<div class='kpis'>" + "".join(cells) + "</div>"


def ingest_summary(lang: str) -> str:
    p = S.ingest
    if not p:
        return note(t("notgenerated", lang))
    rows = "".join(f"<tr><td>{k}</td><td><code>{v}</code></td></tr>"
                   for k, v in (p.get("used") or {}).items())
    out = [f"<table class='facts'>{rows}</table>"]
    derived = p.get("derived") or []
    out.append(warn(t("data.derived", lang) + "<ul>"
                    + "".join(f"<li>{d}</li>" for d in derived) + "</ul>")
               if derived else note(t("data.allsupplied", lang)))
    return "".join(out)


def account_detail(gid_text, hops, show_amounts, lang):
    """The demo path: role, the rule that produced it, and the money around it."""
    empty = pd.DataFrame()
    try:
        gid = int(str(gid_text).strip())
    except (TypeError, ValueError):
        return note(t("acc.prompt", lang)), "", "", empty, empty
    if gid not in S.f.index:
        return warn(t("acc.notfound", lang, gid=gid)), "", "", empty, empty

    r = S.f.loc[gid]
    role = str(r["role"])
    traced = bool(r.get("outflow_observed", True))

    facts = [
        (t("f.priority", lang), f"<b>{float(r['priority_score']):.3f}</b>"),
        (t("f.confidence", lang), f"{float(r['role_score']):.2f}"),
        (t("f.received", lang), f"{kzt(r['in_sum'], lang)} "
                                f"{t('f.payers_n', lang, n=int(r['in_deg']))}"),
        (t("f.sent", lang), f"{kzt(r['out_sum'], lang)} "
                            f"{t('f.recipients_n', lang, n=int(r['out_deg']))}"),
        (t("f.reach", lang), f"{int(r.get('seed_reach', 0))} / "
                             f"{int(S.nodes['is_seed'].sum())}"),
        (t("f.attributed", lang), kzt(r.get("seed_kzt_attributed", 0), lang)),
        (t("f.depth", lang), str(int(r["depth"]))),
        (t("f.isseed", lang), t("yes", lang) if bool(r["is_seed"]) else t("no", lang)),
        (t("f.cluster", lang), str(int(r["cluster_id"]))),
    ]
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in facts)
    card = [hero(f"{t('col.account', lang)} {gid} &nbsp; {pill(role, lang)}",
                 role_meaning(role, lang)),
            f"<table class='facts'>{rows}</table>",
            note(f"<b>{t('acc.evidence', lang)}.</b> {S.evidence(gid, lang)}")]
    if not traced:
        card.append(warn(t("acc.frontier_warn", lang)))
    if str(r.get("secondary_roles", "")):
        extra = ", ".join(role_name(x, lang)
                          for x in str(r["secondary_roles"]).split(";") if x)
        card.append(note(f"{t('acc.also', lang)}: <b>{extra}</b>"))
    caveat = str(r.get("critic_caveat", "") or "")
    if caveat:
        card.append(warn(f"<b>{t('acc.caveat', lang)}.</b> "
                         + caveat.replace(" | ", "<br><br>")))

    tr = S.rule_trace(gid)
    why = [f"### {t('why.heading', lang)}", "", t("why.lead", lang), ""]
    if tr:
        why += [t("why.rule", lang), "", f"> `{tr.get('gate', '—')}`", ""]
        if tr.get("metrics"):
            why += [t("why.values", lang), "", "| | |", "|---|---:|"]
            why += [f"| {k} | {_fmt_v(v)} |" for k, v in tr["metrics"].items()]
            why.append("")
        if tr.get("thresholds"):
            why += [t("why.thresholds", lang), "", "| | |", "|---|---:|"]
            why += [f"| {k} | {_fmt_v(v)} |" for k, v in tr["thresholds"].items()]
            why.append("")
        if tr.get("penalties"):
            why += [t("why.penalties", lang), ""] + \
                   [f"- {p}" for p in tr["penalties"]] + [""]
        if tr.get("notes"):
            why += [f"- {n}" for n in tr["notes"]] + [""]
    adj = str(r.get("priority_adjustments", "") or "")
    if adj:
        why += [f"{t('why.adjust', lang)} {adj}", ""]

    d = S.dossiers.get(gid)
    if d:
        why += ["---", "", f"### {t('dossier.heading', lang)}", "",
                f"{t('dossier.pattern', lang)} {d.get('pattern', '—')}", "",
                str(d.get("summary", "")), ""]
        if d.get("alternative_explanation"):
            why += [f"{t('dossier.alt', lang)} {d['alternative_explanation']}", ""]
        if d.get("next_step"):
            why += [f"{t('dossier.next', lang)} {d['next_step']}", ""]
        why.append(t("dossier.advisory", lang))

    return ("\n".join(card), "\n".join(why),
            ego_html(gid, hops, show_amounts, lang),
            links_table(gid, "dst", "src", lang),
            links_table(gid, "src", "dst", lang))


def _fmt_v(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1e5 else f"{v:,.0f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def cluster_panel(cid, amounts, lang):
    cid = int(cid)
    row = S.clusters[S.clusters["cluster_id"] == cid].iloc[0]
    members = S.features[S.features["cluster_id"] == cid].sort_values(
        "priority_score", ascending=False)
    info = hero(
        f"{t('grp.word', lang)} {cid}",
        f"<b>{int(row['n_nodes'])}</b> {t('grp.accounts', lang)} · "
        f"<b>{int(row['n_seed'])}</b> {t('grp.seeds', lang)} · "
        f"<b>{kzt(row['sum_kzt_internal'], lang)}</b> {t('grp.internal', lang)}"
    ) + note(f"<b>{t('grp.hypothesis', lang)}.</b> "
             f"{hypothesis_from_members(row.to_dict(), members, lang)}")
    table = pd.DataFrame({
        t("col.account", lang): members["gid"].astype("int64"),
        t("col.role", lang): [role_name(r, lang) for r in members["role"]],
        t("col.priority", lang): members["priority_score"].round(3),
        t("col.evidence", lang): [S.evidence(int(g), lang) for g in members["gid"]],
    }).reset_index(drop=True)
    return info, cluster_html(cid, amounts, lang), table


def ask_agent(question: str, history: list, lang: str):
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
            + (f" — {c['error']}" if c.get("error") else "")
            for c in answer.tool_calls)
        parts.append(f"\n<details><summary>"
                     f"{t('ask.queries', lang, n=len(answer.tool_calls))}"
                     f"</summary>\n\n{calls}\n</details>")
    tot = tracer.totals()
    if tot["n_calls"]:
        cost = tot["cost_usd"]
        parts.append(f"\n<sub>{tot['n_calls']} · {tot['total_tokens']:,} tokens · "
                     f"{f'${cost:.4f}' if cost is not None else t('cost.unpriced', lang)}"
                     f" · {tracer.elapsed_s:.1f}s</sub>")
    return history + [{"role": "user", "content": question},
                      {"role": "assistant", "content": "\n".join(parts)}], ""


# ===========================================================================
# app
# ===========================================================================

def build() -> gr.Blocks:
    # Every localizable component registers the function that produces its value
    # for a given language. Switching language then reapplies all of them in one
    # event, so there is exactly one place a translation can go missing.
    reg: list[tuple[object, object]] = []

    def L(component, producer):
        reg.append((component, producer))
        return component

    lang0 = DEFAULT_LANG

    with gr.Blocks(title="Money Graph", css=CSS,
                   theme=gr.themes.Soft(primary_hue="slate",
                                        neutral_hue="slate")) as demo:
        if not S.ok:
            gr.Markdown(f"# Money Graph\n\n### {t('nomaps', lang0)}\n\n"
                        f"`{'`, `'.join(S.missing)}`\n\n```bash\n./agent_run.sh\n```")
            return demo

        with gr.Row(elem_classes="langbar"):
            lang = gr.Radio([(name, code) for code, name in LANGUAGES.items()],
                            value=lang0, show_label=False, container=False,
                            scale=0, min_width=380)
        # Sits above the tabs so it is seen before anything it applies to.
        L(gr.HTML(mt_banner(lang0)), mt_banner)

        with gr.Tabs():
            # ------------------------------------------------------- about
            # First tab on purpose: someone who opens this and reads nothing
            # else should still know what the tool does and where to look.
            with L(gr.Tab(t("tab.about", lang0)),
                   lambda l: gr.Tab(label=t("tab.about", l))):
                L(gr.HTML(hero(t("about.title", lang0), t("about.lead", lang0))),
                  lambda l: hero(t("about.title", l), t("about.lead", l)))
                L(gr.Markdown(f"### {t('about.steps', lang0)}"),
                  lambda l: f"### {t('about.steps', l)}")
                for _k in ("about.step1", "about.step2", "about.step3"):
                    L(gr.HTML(note(t(_k, lang0))),
                      (lambda k: (lambda l: note(t(k, l))))(_k))
                L(gr.Markdown(f"### {t('about.map', lang0)}"),
                  lambda l: f"### {t('about.map', l)}")
                L(gr.Dataframe(tab_guide_table(lang0), wrap=True, max_height=430,
                               interactive=False), tab_guide_table)
                L(gr.HTML(note(t("about.safety", lang0))),
                  lambda l: note(t("about.safety", l)))
                L(gr.HTML(overview_kpis(lang0)), overview_kpis)

            # ------------------------------------------------------- start
            with L(gr.Tab(t("tab.start", lang0)),
                   lambda l: gr.Tab(label=t("tab.start", l))):
                L(gr.HTML(hero(t("start.title", lang0), t("start.lead", lang0))),
                  lambda l: hero(t("start.title", l), t("start.lead", l)))
                L(gr.HTML(note(t("purpose.start", lang0))),
                  lambda l: note(t("purpose.start", l)))
                L(gr.HTML(overview_kpis(lang0)), overview_kpis)
                L(gr.Markdown(f"### {t('start.where', lang0)}"),
                  lambda l: f"### {t('start.where', l)}")
                with gr.Row():
                    for key in ("start.card1", "start.card2", "start.card3"):
                        L(gr.HTML(note(t(key, lang0))),
                          (lambda k: (lambda l: note(t(k, l))))(key))
                L(gr.Markdown(f"### {t('start.classified', lang0)}"),
                  lambda l: f"### {t('start.classified', l)}")
                with gr.Row():
                    with gr.Column(scale=3):
                        L(gr.HTML(role_bars(lang0)), role_bars)
                    with gr.Column(scale=2):
                        L(gr.HTML(_rolekey(lang0)), _rolekey)
                L(gr.HTML(note(t("start.artifacts", lang0))),
                  lambda l: note(t("start.artifacts", l)))

            # --------------------------------------------------- shortlist
            with L(gr.Tab(t("tab.priority", lang0)),
                   lambda l: gr.Tab(label=t("tab.priority", l))):
                L(gr.HTML(hero(t("prio.title", lang0), t("prio.lead", lang0))),
                  lambda l: hero(t("prio.title", l), t("prio.lead", l)))
                L(gr.HTML(note(t("purpose.priority", lang0))),
                  lambda l: note(t("purpose.priority", l)))
                L(gr.HTML(note(t("prio.note", lang0))),
                  lambda l: note(t("prio.note", l)))
                top_df = L(gr.Dataframe(top_table(lang0), wrap=True, max_height=470,
                                        interactive=False), top_table)
                # Pre-filled with the top-ranked account, so the panel below is
                # never an empty box waiting for a click.
                _first = int(S.top["gid"].iloc[0])
                _card0, _why0, *_rest = account_detail(_first, 1, False, lang0)
                L(gr.Markdown(f"### {t('prio.selected', lang0)}"),
                  lambda l: f"### {t('prio.selected', l)}")
                L(gr.HTML(note(t("prio.clickhint", lang0))),
                  lambda l: note(t("prio.clickhint", l)))
                sel_card = gr.HTML(_card0)
                sel_why = gr.Markdown(_why0)

                def pick_row(lang_now, evt: gr.SelectData):
                    try:
                        gid = int(top_table(lang_now).iloc[evt.index[0]][
                            t("col.account", lang_now)])
                    except Exception:
                        return "", ""
                    card, why, *_ = account_detail(gid, 1, False, lang_now)
                    return card, why

                top_df.select(pick_row, lang, [sel_card, sel_why])

            # ----------------------------------------------------- account
            with L(gr.Tab(t("tab.account", lang0)),
                   lambda l: gr.Tab(label=t("tab.account", l))):
                L(gr.HTML(hero(t("acc.title", lang0), t("acc.lead", lang0))),
                  lambda l: hero(t("acc.title", l), t("acc.lead", l)))
                L(gr.HTML(note(t("purpose.account", lang0))),
                  lambda l: note(t("purpose.account", l)))
                with gr.Row():
                    gid_in = L(gr.Textbox(label=t("acc.input", lang0), scale=3,
                                          placeholder=t("acc.placeholder", lang0)),
                               lambda l: gr.update(label=t("acc.input", l),
                                                   placeholder=t("acc.placeholder", l)))
                    pick = L(gr.Dropdown([str(int(g)) for g in S.top["gid"]],
                                         label=t("acc.pick", lang0), value=None,
                                         scale=2),
                             lambda l: gr.update(label=t("acc.pick", l)))
                with gr.Row():
                    hops_in = L(gr.Radio([1, 2], value=int(VIEW["ego_hops_default"]),
                                         label=t("acc.hops", lang0),
                                         info=t("acc.hops.info", lang0)),
                                lambda l: gr.update(label=t("acc.hops", l),
                                                    info=t("acc.hops.info", l)))
                    amt_in = L(gr.Checkbox(False, label=t("acc.amounts", lang0),
                                           info=t("acc.amounts.info", lang0)),
                               lambda l: gr.update(label=t("acc.amounts", l),
                                                   info=t("acc.amounts.info", l)))

                first = int(S.top["gid"].iloc[0])
                d_card, d_why, d_map, d_pay, d_rec = account_detail(
                    first, int(VIEW["ego_hops_default"]), False, lang0)
                with gr.Row():
                    with gr.Column(scale=1):
                        card_out = gr.HTML(d_card)
                    with gr.Column(scale=1):
                        why_out = gr.Markdown(d_why)
                L(gr.Markdown(f"### {t('acc.mapheading', lang0)}"),
                  lambda l: f"### {t('acc.mapheading', l)}")
                L(gr.HTML(note(t("map.guide", lang0))),
                  lambda l: note(t("map.guide", l)))
                map_out = gr.HTML(d_map)
                with L(gr.Accordion(t("legend.key", lang0), open=False),
                       lambda l: gr.Accordion(label=t("legend.key", l), open=False)):
                    L(gr.HTML(legend_html(lang0)), legend_html)
                with gr.Row():
                    payers_out = L(gr.Dataframe(d_pay, label=t("acc.payers", lang0),
                                                max_height=300, interactive=False),
                                   lambda l: gr.update(label=t("acc.payers", l)))
                    recips_out = L(gr.Dataframe(d_rec,
                                                label=t("acc.recipients", lang0),
                                                max_height=300, interactive=False),
                                   lambda l: gr.update(label=t("acc.recipients", l)))

                outs = [card_out, why_out, map_out, payers_out, recips_out]
                ins = [gid_in, hops_in, amt_in, lang]
                gid_in.submit(account_detail, ins, outs)
                hops_in.change(account_detail, ins, outs)
                amt_in.change(account_detail, ins, outs)
                pick.change(lambda g, h, a, l: account_detail(g, h, a, l) if g
                            else ("", "", "", pd.DataFrame(), pd.DataFrame()),
                            [pick, hops_in, amt_in, lang], outs)

            # ------------------------------------------------------ groups
            with L(gr.Tab(t("tab.groups", lang0)),
                   lambda l: gr.Tab(label=t("tab.groups", l))):
                L(gr.HTML(hero(t("grp.title", lang0), t("grp.lead", lang0))),
                  lambda l: hero(t("grp.title", l), t("grp.lead", l)))
                L(gr.HTML(note(t("purpose.groups", lang0))),
                  lambda l: note(t("purpose.groups", l)))
                L(gr.Dataframe(cluster_table(lang0), wrap=True, max_height=300,
                               interactive=False), cluster_table)
                L(gr.HTML(note(t("grp.note", lang0))),
                  lambda l: note(t("grp.note", l)))
                first_c = str(int(S.clusters["cluster_id"].iloc[0]))
                cl = L(gr.Dropdown([str(int(c)) for c in S.clusters["cluster_id"]],
                                   value=first_c, label=t("grp.show", lang0)),
                       lambda l: gr.update(label=t("grp.show", l)))
                cl_amt = L(gr.Checkbox(False, label=t("acc.amounts", lang0)),
                           lambda l: gr.update(label=t("acc.amounts", l)))
                c_info, c_map, c_members = cluster_panel(first_c, False, lang0)
                cl_info = gr.HTML(c_info)
                L(gr.HTML(note(t("map.guide", lang0))),
                  lambda l: note(t("map.guide", l)))
                cl_map = gr.HTML(c_map)
                cl_members = L(gr.Dataframe(c_members, label=t("grp.members", lang0),
                                            max_height=300, interactive=False),
                               lambda l: gr.update(label=t("grp.members", l)))
                cl.change(cluster_panel, [cl, cl_amt, lang],
                          [cl_info, cl_map, cl_members])
                cl_amt.change(cluster_panel, [cl, cl_amt, lang],
                              [cl_info, cl_map, cl_members])

            # --------------------------------------------------------- ask
            with L(gr.Tab(t("tab.ask", lang0)),
                   lambda l: gr.Tab(label=t("tab.ask", l))):
                L(gr.HTML(hero(t("ask.title", lang0), t("ask.lead", lang0))),
                  lambda l: hero(t("ask.title", l), t("ask.lead", l)))
                L(gr.HTML(note(t("purpose.ask", lang0))),
                  lambda l: note(t("purpose.ask", l)))
                L(gr.HTML(note(t("ask.note", lang0))),
                  lambda l: note(t("ask.note", l)))
                chat = gr.Chatbot(type="messages", height=420, allow_tags=True,
                                  show_label=False)
                q = L(gr.Textbox(label=t("ask.q", lang0), show_label=False,
                                 placeholder=t("ask.placeholder", lang0)),
                      lambda l: gr.update(placeholder=t("ask.placeholder", l)))
                with gr.Row():
                    send = L(gr.Button(t("ask.send", lang0), variant="primary"),
                             lambda l: gr.update(value=t("ask.send", l)))
                    clear = L(gr.Button(t("ask.clear", lang0)),
                              lambda l: gr.update(value=t("ask.clear", l)))
                gr.Examples([t("ask.ex1", lang0), t("ask.ex2", lang0),
                             t("ask.ex3", lang0)], inputs=q,
                            label=t("ask.examples", lang0))
                send.click(ask_agent, [q, chat, lang], [chat, q])
                q.submit(ask_agent, [q, chat, lang], [chat, q])
                clear.click(lambda: ([], ""), None, [chat, q])

            # ------------------------------------------------------ agents
            with L(gr.Tab(t("tab.agents", lang0)),
                   lambda l: gr.Tab(label=t("tab.agents", l))):
                L(gr.HTML(hero(t("ag.title", lang0), t("ag.lead", lang0))),
                  lambda l: hero(t("ag.title", l), t("ag.lead", l)))
                L(gr.HTML(note(t("purpose.agents", lang0))),
                  lambda l: note(t("purpose.agents", l)))
                L(gr.Markdown(f"### {t('ag.thresholds', lang0)}"),
                  lambda l: f"### {t('ag.thresholds', l)}")
                L(gr.HTML(note(t("ag.thresholds.note", lang0))),
                  lambda l: note(t("ag.thresholds.note", l)))
                L(gr.Dataframe(calibration_table(lang0), wrap=True, max_height=360,
                               interactive=False), calibration_table)
                L(gr.Markdown(f"### {t('ag.dossiers', lang0)}"),
                  lambda l: f"### {t('ag.dossiers', l)}")
                L(gr.HTML(note(t("ag.dossiers.note", lang0))),
                  lambda l: note(t("ag.dossiers.note", l)))
                L(gr.Dataframe(dossier_table(lang0), wrap=True, max_height=360,
                               interactive=False), dossier_table)
                with L(gr.Accordion(t("ag.critic", lang0), open=True),
                       lambda l: gr.Accordion(label=t("ag.critic", l), open=True)):
                    L(gr.HTML(note(t("ag.critic.note", lang0))),
                      lambda l: note(t("ag.critic.note", l)))
                    gr.Markdown(S.text("review_notes.md", "—"))
                with L(gr.Accordion(t("ag.log", lang0), open=False),
                       lambda l: gr.Accordion(label=t("ag.log", l), open=False)):
                    gr.Markdown(S.text("agent_log.md", "—"))
                with L(gr.Accordion(t("ag.requests", lang0), open=False),
                       lambda l: gr.Accordion(label=t("ag.requests", l), open=False)):
                    gr.Markdown(S.text("data_requests.md", "—"))

            # -------------------------------------------------------- data
            with L(gr.Tab(t("tab.data", lang0)),
                   lambda l: gr.Tab(label=t("tab.data", l))):
                L(gr.HTML(hero(t("data.title", lang0), t("data.lead", lang0))),
                  lambda l: hero(t("data.title", l), t("data.lead", l)))
                L(gr.HTML(note(t("purpose.data", lang0))),
                  lambda l: note(t("purpose.data", l)))
                L(gr.Markdown(f"### {t('data.files', lang0)}"),
                  lambda l: f"### {t('data.files', l)}")
                L(gr.HTML(ingest_summary(lang0)), ingest_summary)
                L(gr.Markdown(f"### {t('data.mapping', lang0)}"),
                  lambda l: f"### {t('data.mapping', l)}")
                L(gr.HTML(note(t("data.mapping.note", lang0))),
                  lambda l: note(t("data.mapping.note", l)))
                L(gr.Dataframe(mapping_table(lang0), wrap=True, max_height=340,
                               interactive=False), mapping_table)
                L(gr.HTML(note(t("data.own", lang0))),
                  lambda l: note(t("data.own", l)))
                with L(gr.Accordion(t("data.profile", lang0), open=False),
                       lambda l: gr.Accordion(label=t("data.profile", l), open=False)):
                    gr.Markdown(S.text("profile_report.md", "—"))

            # -------------------------------------------------------- cost
            with L(gr.Tab(t("tab.cost", lang0)),
                   lambda l: gr.Tab(label=t("tab.cost", l))):
                L(gr.HTML(hero(t("cost.title", lang0), t("cost.lead", lang0))),
                  lambda l: hero(t("cost.title", l), t("cost.lead", l)))
                L(gr.HTML(note(t("purpose.cost", lang0))),
                  lambda l: note(t("purpose.cost", l)))
                L(gr.HTML(trace_kpis(lang0)), trace_kpis)
                L(gr.HTML(note(t("cost.note", lang0))),
                  lambda l: note(t("cost.note", l)))
                gr.Markdown(S.text(CFG["tracing"].get("write_markdown")
                                   or "run_trace.md", "—"))

            # --------------------------------------------------- downloads
            with L(gr.Tab(t("tab.downloads", lang0)),
                   lambda l: gr.Tab(label=t("tab.downloads", l))):
                L(gr.HTML(hero(t("dl.title", lang0), t("dl.lead", lang0))),
                  lambda l: hero(t("dl.title", l), t("dl.lead", l)))
                L(gr.HTML(note(t("purpose.downloads", lang0))),
                  lambda l: note(t("purpose.downloads", l)))
                names = ["nodes_roles.csv", "clusters.csv", "top_nodes.csv",
                         "node_features.parquet", "graph_edges.parquet",
                         "profile_report.md", "data_requests.md",
                         "review_notes.md", "agent_log.md", "dossiers.json",
                         "ingest_report.json", "run_trace.md", "run_trace.json"]
                L(gr.File([str(OUT / n) for n in names if (OUT / n).exists()],
                          label=t("dl.button", lang0), interactive=False,
                          file_count="multiple"),
                  lambda l: gr.update(label=t("dl.button", l)))
                L(gr.HTML(note(t("dl.note", lang0))),
                  lambda l: note(t("dl.note", l)))
                L(gr.Dataframe(S.nodes.head(40), wrap=True, max_height=330,
                               label=t("dl.preview", lang0), interactive=False),
                  lambda l: gr.update(label=t("dl.preview", l)))

        components = [c for c, _ in reg]
        producers = [p for _, p in reg]
        lang.change(lambda l: [p(l) for p in producers], lang, components)

    return demo


def tab_guide_table(lang: str) -> pd.DataFrame:
    """One row per tab: what it is for, and when to open it."""
    return pd.DataFrame({
        t("about.col.tab", lang): [t(key, lang) for key, _, _ in TAB_GUIDE],
        t("about.col.for", lang): [w.get(lang, w["en"]) for _, w, _ in TAB_GUIDE],
        t("about.col.when", lang): [w.get(lang, w["en"]) for _, _, w in TAB_GUIDE],
    })


def _rolekey(lang: str) -> str:
    return ("<div class='legend'><h4>" + t("start.rolekey", lang) + "</h4>"
            + "".join(f"<div class='row'><span class='sw' style='background:"
                      f"{ROLE_COLORS.get(r)}'></span><b>{role_name(r, lang)}</b>"
                      f"<span class='t'>— {role_meaning(r, lang)}</span></div>"
                      for r in ROLE_COLORS) + "</div>")


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
        # Opens the browser itself, so the run ends with the interface on
        # screen rather than a URL to copy.
        share=share, show_api=False, quiet=False,
        inbrowser=not _truthy(os.environ.get('MONEYGRAPH_NO_BROWSER')),
        # The maps live under output_files/_maps and are served from there.
        allowed_paths=[str(OUT)])
