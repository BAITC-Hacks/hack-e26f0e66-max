"""Orchestration (guideline §5). No analytical logic lives here.

The shape of a run:

    ingest -> profile
           -> [PLANNER decides which passes to run on this dataset]
           -> graph -> features -> temporal -> attribution
           -> [CALIBRATOR chooses the role thresholds, simulated then persisted]
           -> roles (pass 1) -> clustering -> roles (pass 2) -> priority
           -> evidence templates
           -> [INVESTIGATOR dossiers] -> [CRITIC challenges the list]
           -> [NARRATOR rephrases] -> [REVIEWER writes the data requests]
           -> export

The agents are not decoration. The planner chooses the depth of the run, and
the calibrator sets the numbers every role gate compares against. What they
cannot do is decide a role: `roles.py` still resolves each node by comparing a
metric to a threshold, and the resulting `RuleTrace` is what the viewer and the
jury see.

Every agent call is individually recoverable. A run with no API key, no
network, or an exhausted budget produces the same three CSVs, from the
`config.yaml` thresholds, with template prose — and says so in the trace.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import (attribution, clustering, evidence, export, features, graph,
               priority, roles, temporal)
from .agents.llm import LLMClient
from .agents.orchestrator import Crew, build_brief
from .io import Dataset, load_config, load_dataset
from .trace import RunTracer


def run(data_dir: str | Path, out_dir: str | Path, config_path: str | Path,
        only_profile: bool = False, recalibrate: bool = False) -> int:
    cfg = load_config(config_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tracer = RunTracer(cfg)
    client = LLMClient(cfg, tracer)
    crew = Crew(cfg, tracer, client)

    print(f"Money Graph — {data_dir} -> {out_dir}")
    if client.available:
        print(f"  crew: {client.model} (reasoning={client.reasoning_effort}), "
              f"budget {cfg['llm']['budget']['max_calls']} calls")
    else:
        print(f"  crew: OFF — {client.disabled_reason}")
        print(f"        the pipeline runs fully; thresholds come from config.yaml "
              f"and all text is templated")
    print()

    try:
        _run_stages(cfg, data_dir, out_dir, tracer, client, crew,
                    Path(config_path).parent, only_profile, recalibrate)
    finally:
        if crew.run_record.results:
            export.write_text("agent_log.md", crew.render_log(), out_dir)
        tracer.write(out_dir)
        tracer.print_summary()

    if tracer.elapsed_s >= tracer.max_runtime_s:
        print(f"\n  ! runtime {tracer.elapsed_s:.1f}s exceeded the "
              f"{tracer.max_runtime_s:.0f}s budget in the brief")
        return 1
    return 0


def _run_stages(cfg: dict, data_dir, out_dir: Path, tracer: RunTracer,
                client: LLMClient, crew: Crew, config_dir: Path,
                only_profile: bool, recalibrate: bool) -> None:
    # ---------------------------------------------------------------- ingest
    with tracer.stage("ingest"):
        ds = load_dataset(data_dir, cfg, llm_client=client, tracer=tracer)
        print(f"     {ds.summary()}")
        for note in ds.provenance.get("derived", []):
            print(f"     derived: {note}")

    with tracer.stage("profile"):
        from .profile import profile

        report, flows = profile(ds, cfg)
        export.write_text("profile_report.md", report.render(), out_dir)
        if report.mismatches:
            tracer.note_warning(
                f"{len(report.mismatches)} announced fact(s) do not reproduce — "
                f"see profile_report.md §8")
    if only_profile:
        return

    # ----------------------------------------------------------------- core
    with tracer.stage("graph"):
        g = graph.build_graph(ds)
        df = graph.annotate(g, ds)

    with tracer.stage("features"):
        df = features.flow_features(g, ds, df)
        df = features.centrality_features(g, df)

    with tracer.stage("temporal"):
        df = temporal.temporal_features(ds, df, cfg)
        if not ds.has_transactions:
            tracer.note("no transaction file — temporal features are NaN")

    with tracer.stage("attribution"):
        df = attribution.attribution_features(g, ds, df)

    # ------------------------------------------------------- planner (agent)
    with tracer.stage("agent:planner"):
        from .agents.calibrator_agent import simulate_counts

        baseline = simulate_counts(df, cfg["roles"], ds.max_depth)
        brief = build_brief(_dataset_facts(ds), baseline, len(df), tracer)
        plan = crew.plan(brief)
        print(f"     {plan.get('reasoning', '')}")
        print(f"     calibrate={plan['calibrate_thresholds']} "
              f"investigate={plan['investigate_top_n']} "
              f"critic={plan['run_critic']} narrate={plan['narrate']}")

    # ---------------------------------------------------- calibrator (agent)
    if plan.get("calibrate_thresholds"):
        with tracer.stage("agent:calibrator"):
            from .agents.calibrator_agent import apply_calibration

            calibration = crew.calibrate(df, ds.max_depth, config_dir,
                                         recalibrate, edges=ds.edges)
            if calibration:
                cfg = apply_calibration(cfg, calibration)

    # ----------------------------------------------------------- rule engine
    with tracer.stage("roles:base"):
        df = roles.assign_base_roles(df, cfg, ds.max_depth)
        print(f"     {_fmt_counts(roles.role_counts(df))}")

    with tracer.stage("clustering"):
        df, diag = clustering.cluster_nodes(g, ds, df, cfg)
        print(f"     {diag['n_clusters']} clusters "
              f"(largest {diag['largest']}, {diag['n_singletons']} singletons)")
        stab = diag.get("stability", {})
        if stab.get("checked"):
            print(f"     stability over {stab['n_seeds']} seeds: "
                  f"mean {stab['mean_stability']:.2f}, "
                  f"{stab['n_stable_clusters']} clusters >= 0.80")
            tracer.note(f"cluster stability mean {stab['mean_stability']:.3f}")

    with tracer.stage("roles:coordinator"):
        df = roles.assign_coordinators(df, ds.edges, cfg)
        counts = roles.role_counts(df)
        print(f"     {_fmt_counts(counts)}")
        _warn_degenerate(counts, len(df), tracer)

    with tracer.stage("priority"):
        df = priority.priority_score(df, cfg, ds.max_depth)

    # ------------------------------------------------------------- evidence
    traces = {int(t.gid): t for t in df["trace_obj"]}
    with tracer.stage("evidence:templates"):
        df["evidence"] = [
            evidence.evidence_for(row, traces[int(row.gid)], cfg)
            for row in df.itertuples(index=False)
        ]
        clusters = clustering.cluster_table(df, ds, cfg)
        members = {int(c): grp for c, grp in df.groupby("cluster_id")}
        clusters["hypothesis"] = [
            evidence.hypothesis_for(row, members[int(row.cluster_id)], cfg)
            for row in clusters.itertuples(index=False)
        ]
        top = _rank(df, cfg)

    # ---------------------------------------------------------- agent crew
    tools = _tools(df, ds, clusters)

    if plan.get("investigate_top_n", 0) and client.available:
        with tracer.stage("agent:investigator"):
            dossiers = crew.investigate(top, traces, tools,
                                        int(plan["investigate_top_n"]))
            print(f"     {len(dossiers)} dossier(s) built")
            df = _attach_dossiers(df, dossiers)

    if plan.get("run_critic"):
        with tracer.stage("agent:critic"):
            from .agents.critic_agent import render_review_notes

            critique = crew.critique(_critic_context(top, df, ds, cfg, counts))
            if critique:
                export.write_text("review_notes.md",
                                  render_review_notes(critique, {}), out_dir)
                print(f"     wrote review_notes.md "
                      f"({len(critique.get('artifacts', []))} concern(s) raised)")
                df = _attach_caveats(df, critique)

    if plan.get("narrate") and client.available:
        with tracer.stage("agent:narrator"):
            from .agents import narrator_agent

            try:
                df, s1 = narrator_agent.narrate_evidence(df, traces, client, cfg, tracer)
                clusters, s2 = narrator_agent.narrate_hypotheses(
                    clusters, members, client, cfg, tracer)
                print(f"     evidence {s1.get('accepted', 0)} narrated / "
                      f"{s1.get('rejected', 0)} rejected; "
                      f"hypotheses {s2.get('accepted', 0)} / {s2.get('rejected', 0)}")
            except Exception as exc:
                tracer.note_warning(f"narrator failed: {type(exc).__name__}: {exc}")

    with tracer.stage("agent:reviewer"):
        _write_requests(df, ds, client, cfg, tracer, out_dir)

    # --------------------------------------------------------------- export
    with tracer.stage("export"):
        top = _rank(df, cfg)
        clusters_final = clustering.cluster_table(df, ds, cfg)
        clusters_final["hypothesis"] = clusters_final["cluster_id"].map(
            dict(zip(clusters["cluster_id"], clusters["hypothesis"])))
        _validate_text_columns(df, top, clusters_final, cfg, tracer)

        paths = [
            export.write_nodes_roles(df, out_dir),
            export.write_clusters(clusters_final, out_dir),
            export.write_top_nodes(top, out_dir),
            export.write_features(df, traces, out_dir),
            export.write_edges(ds.edges, out_dir),
        ]
        export.write_text("dossiers.json",
                          _dossiers_json(crew.run_record.dossiers), out_dir)
        # How each input file was read and what had to be derived. The viewer
        # shows this so the claim "it accepts whatever export you have" is
        # inspectable rather than asserted.
        import json as _json

        export.write_text("ingest_report.json",
                          _json.dumps(ds.provenance, indent=2, ensure_ascii=False,
                                      default=str), out_dir)
        for p in paths:
            print(f"     wrote {p.name}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _rank(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    top = priority.rank_top_nodes(df, cfg)
    top["why"] = [evidence.why_for(row, cfg, priority.top_contributors(row, cfg))
                  for row in top.itertuples(index=False)]
    return top


def _tools(df: pd.DataFrame, ds: Dataset, clusters: pd.DataFrame):
    from .agents.tools import GraphTools

    return GraphTools(df, ds.edges, clusters, ds.tx)


def _dataset_facts(ds: Dataset) -> dict:
    return {
        "n_nodes": int(len(ds.nodes)), "n_edges": int(len(ds.edges)),
        "n_transactions": int(len(ds.tx)),
        "n_seeds": int(ds.nodes["is_seed"].sum()),
        "max_depth": ds.max_depth,
        "total_turnover_kzt": float(ds.edges["sum_kzt"].sum()),
        "hop_distribution": {int(k): int(v) for k, v in
                             ds.nodes["depth"].value_counts().sort_index().items()},
        "has_transaction_dates": ds.has_transactions,
        "derived_rather_than_supplied": ds.provenance.get("derived", []),
    }


def _critic_context(top: pd.DataFrame, df: pd.DataFrame, ds: Dataset,
                    cfg: dict, counts: dict) -> dict:
    by_gid = df.set_index("gid")
    findings = []
    for row in top.itertuples(index=False):
        gid = int(row.gid)
        r = by_gid.loc[gid]
        findings.append({
            "gid": gid, "rank": int(row.rank), "role": row.role,
            "priority_score": round(float(row.priority_score), 4),
            "why": row.why,
            "in_deg": int(r["in_deg"]), "out_deg": int(r["out_deg"]),
            "in_sum_kzt": float(r["in_sum"]), "out_sum_kzt": float(r["out_sum"]),
            "seed_reach": int(r.get("seed_reach", 0)),
            "is_seed": bool(r["is_seed"]),
            "at_frontier": not bool(r.get("outflow_observed", True)),
        })
    thresholds = {f"{section}.{key}": value
                  for section, block in cfg["roles"].items()
                  if isinstance(block, dict)
                  for key, value in block.items()}
    return {
        "findings": findings, "thresholds": thresholds, "role_counts": counts,
        "n_seeds": int(ds.nodes["is_seed"].sum()), "max_depth": ds.max_depth,
        "n_frontier": int((ds.nodes["depth"] == ds.max_depth).sum()),
        "amount_floor": (cfg.get("expected", {}) or {}).get("min_amount_kzt"),
        "period": {"from": str(ds.tx["date"].min().date()),
                   "to": str(ds.tx["date"].max().date())} if ds.has_transactions else None,
    }


def _attach_dossiers(df: pd.DataFrame, dossiers: dict) -> pd.DataFrame:
    """Dossiers are an extra column, never a change to a role or a score."""
    df = df.copy()
    df["dossier_pattern"] = df["gid"].map(
        lambda g: (dossiers.get(int(g)) or {}).get("pattern", ""))
    df["dossier_summary"] = df["gid"].map(
        lambda g: (dossiers.get(int(g)) or {}).get("summary", ""))
    df["dossier_next_step"] = df["gid"].map(
        lambda g: (dossiers.get(int(g)) or {}).get("next_step", ""))
    df["dossier_alternative"] = df["gid"].map(
        lambda g: (dossiers.get(int(g)) or {}).get("alternative_explanation", ""))
    return df


def _attach_caveats(df: pd.DataFrame, critique: dict) -> pd.DataFrame:
    """The critic's concerns, indexed per account for the viewer."""
    caveats: dict[int, list[str]] = {}
    for entry in (critique.get("artifacts") or []):
        for gid in (entry.get("gids") or []):
            caveats.setdefault(int(gid), []).append(
                f"[{str(entry.get('severity', '')).upper()}] {entry.get('concern')}")
    df = df.copy()
    df["critic_caveat"] = df["gid"].map(lambda g: " | ".join(caveats.get(int(g), [])))
    return df


def _dossiers_json(dossiers: dict) -> str:
    import json

    return json.dumps({str(k): v for k, v in dossiers.items()},
                      indent=2, ensure_ascii=False, default=str)


def _write_requests(df, ds, client, cfg, tracer, out_dir: Path) -> None:
    from .agents import review_agent

    try:
        gaps = review_agent.compute_gaps(df, ds.edges, ds, cfg)
        text = review_agent.write_brief(gaps, client, cfg, tracer)
        export.write_text("data_requests.md", text, out_dir)
        print(f"     wrote data_requests.md")
    except Exception as exc:
        tracer.note_warning(f"reviewer failed: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def _validate_text_columns(df, top, clusters, cfg: dict, tracer: RunTracer) -> None:
    """Last line of defence before anything is written.

    Whatever produced a string — template, narrator, investigator or critic — it
    does not leave this process without passing the length cap and the
    forbidden-word list.
    """
    checks = [
        (df, "evidence", int(cfg["evidence"]["max_chars"])),
        (top, "why", int(cfg["evidence"]["max_why_chars"])),
        (clusters, "hypothesis", int(cfg["clustering"]["max_hypothesis_chars"])),
    ]
    for frame, col, limit in checks:
        values = frame[col].astype(str)
        if int((values.str.strip() == "").sum()):
            raise AssertionError(f"{col}: empty value(s)")
        overlong = int((values.str.len() > limit).sum())
        if overlong:
            frame[col] = values.map(lambda t: evidence.truncate(t, limit))
            tracer.note_warning(f"{col}: truncated {overlong} overlong value(s)")
        blob = " ".join(values).lower()
        hits = [w for w in cfg["evidence"]["forbidden_words"] if w.lower() in blob]
        if hits:
            raise AssertionError(f"{col} contains forbidden wording {hits}")

    # Agent-written columns are checked too, but a failure there only drops the
    # column: it must never take the deliverables down with it.
    for col in ("dossier_summary", "dossier_next_step", "dossier_alternative",
                "critic_caveat"):
        if col not in df.columns:
            continue
        blob = " ".join(df[col].astype(str)).lower()
        hits = [w for w in cfg["evidence"]["forbidden_words"] if w.lower() in blob]
        if hits:
            df[col] = ""
            tracer.note_warning(f"{col} contained {hits}; column cleared")


def _warn_degenerate(counts: dict[str, int], n: int, tracer: RunTracer) -> None:
    """Guideline §16: catch a threshold that has collapsed the role space."""
    for role in ("coordinator", "consolidator", "distributor"):
        if counts.get(role, 0) == 0:
            tracer.note_warning(
                f"no node was classified `{role}` — the gate may be too strict; "
                f"check the percentiles in profile_report.md §6")
    for role, count in counts.items():
        if role != "peripheral" and count > 0.5 * n:
            tracer.note_warning(
                f"`{role}` claims {count} of {n} nodes ({100 * count / n:.0f}%) — "
                f"the gate may be too loose to be informative")
    # `coordinator` is the apex role: it should be a handful of accounts, not a
    # tier. A 50% check would never catch a gate that promotes 12% of the graph.
    n_coord = counts.get("coordinator", 0)
    if n_coord > 0.02 * n:
        tracer.note_warning(
            f"`coordinator` claims {n_coord} of {n} nodes "
            f"({100 * n_coord / n:.1f}%) — the apex role should be a handful of "
            f"accounts; check that its convergence requirement is enabled")


def _fmt_counts(counts: dict[str, int]) -> str:
    return "  ".join(f"{r}={c}" for r, c in counts.items() if c)
