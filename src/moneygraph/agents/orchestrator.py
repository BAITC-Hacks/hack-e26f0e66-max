"""Orchestrator — plans the investigation and runs the crew.

The lead agent. It reads what the data profile actually found and decides which
passes are worth running on *this* dataset, within the remaining budget: there
is no point investigating twenty accounts when six carry the signal, and no
point calibrating thresholds when the distribution is too thin to support them.

It then runs the crew in dependency order:

    calibrate -> (deterministic core runs) -> investigate -> critique
              -> narrate -> data requests

and writes `agent_log.md`: every agent, every tool call with its arguments and
result, every rejection, every fallback. That file is the audit trail. In a
compliance setting it is not a nice-to-have — being unable to show how a
conclusion was reached is itself the finding.

The plan is a *suggestion*. `budget_guard` and each agent's own validator still
apply, and the deterministic pipeline runs to completion whatever the crew does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..trace import RunTracer
from .base import WORDING_RULES, Agent, AgentResult
from .llm import LLMClient

DEFAULT_PLAN = {
    "calibrate_thresholds": True,
    "investigate_top_n": 8,
    "run_critic": True,
    "narrate": True,
    "reasoning": "default plan (no planner run)",
}

SYSTEM = f"""You are the lead analyst planning an investigation of a money-transfer network. A deterministic rule engine will assign every role; you decide which additional passes are worth running on this particular dataset, and how deep to go.

Available passes, with their cost:
- `calibrate_thresholds` — one model call. Re-derives the role thresholds from this dataset's distributions. Worth it when the current thresholds produce a lopsided role distribution, or when the data does not look like the export the defaults were tuned for.
- `investigate_top_n` — N multi-step investigations, roughly 3-6 model calls each. This is the expensive pass. Choose N by how many accounts actually carry signal, not by how many you are allowed.
- `run_critic` — one call. Challenges the priority list for collection artifacts and threshold sensitivity. Cheap, and the only counterweight in a system with no ground truth.
- `narrate` — a few batched calls. Rewrites rule traces into readable English. Cosmetic: the deterministic templates are always correct.

Answer with JSON only:
{{"calibrate_thresholds": <bool>, "investigate_top_n": <int>, "run_critic": <bool>, "narrate": <bool>, "reasoning": "<2-3 sentences naming what in the profile drove these choices>"}}

Spend the budget where it changes what the analyst does. {WORDING_RULES}"""


@dataclass
class CrewRun:
    """Everything the crew produced, for the log and for the viewer."""

    plan: dict = field(default_factory=dict)
    results: list[AgentResult] = field(default_factory=list)
    calibration: dict | None = None
    dossiers: dict[int, dict] = field(default_factory=dict)
    critique: dict | None = None

    def add(self, result: AgentResult) -> AgentResult:
        self.results.append(result)
        return result

    def to_dict(self) -> dict:
        return {"plan": self.plan,
                "results": [r.to_dict() for r in self.results],
                "n_dossiers": len(self.dossiers),
                "has_critique": self.critique is not None}


class PlannerAgent(Agent):
    name = "planner"
    role = "decide which investigative passes to run"
    system = SYSTEM

    def build_task(self, context: dict) -> str:
        return json.dumps(context["brief"], ensure_ascii=False, indent=2, default=str)

    def validate(self, output: Any, context: dict) -> tuple[bool, str]:
        if not isinstance(output, dict):
            return False, "not an object"
        n = output.get("investigate_top_n")
        if not isinstance(n, int) or isinstance(n, bool):
            return False, "investigate_top_n must be an integer"
        cap = context["max_investigations"]
        if not (0 <= n <= cap):
            return False, f"investigate_top_n={n} outside 0..{cap}"
        for key in ("calibrate_thresholds", "run_critic", "narrate"):
            if not isinstance(output.get(key), bool):
                return False, f"`{key}` must be true or false"
        if not str(output.get("reasoning", "")).strip():
            return False, "no reasoning given"
        return True, "ok"

    def fallback(self, context: dict) -> Any:
        plan = dict(DEFAULT_PLAN)
        plan["investigate_top_n"] = min(plan["investigate_top_n"],
                                        context["max_investigations"])
        return plan


# ---------------------------------------------------------------------------
# the crew
# ---------------------------------------------------------------------------

class Crew:
    """Owns the agents and the log. One instance per pipeline run."""

    def __init__(self, cfg: dict, tracer: RunTracer, client: LLMClient) -> None:
        self.cfg = cfg
        self.tracer = tracer
        self.client = client
        self.run_record = CrewRun()

    # ------------------------------------------------------------- planning

    def plan(self, brief: dict) -> dict:
        ocfg = (self.cfg.get("agents", {}) or {}).get("planner", {}) or {}
        cap = int(ocfg.get("max_investigations", 20))
        planner = PlannerAgent(self.client, self.cfg, self.tracer)
        result = self.run_record.add(planner.run(
            {"brief": brief, "max_investigations": cap}, "plan the run"))
        plan = result.output or dict(DEFAULT_PLAN)
        plan["investigate_top_n"] = min(int(plan.get("investigate_top_n", 0)), cap)
        self.run_record.plan = plan
        return plan

    # ---------------------------------------------------------- calibration

    def calibrate(self, features, max_depth: int, config_dir: Path,
                  recalibrate: bool, edges=None) -> dict | None:
        """Returns the calibration to apply, or None to keep config.yaml."""
        from . import calibrator_agent as ca

        path = Path(config_dir) / ca.CALIBRATED_FILE
        if not recalibrate:
            saved = ca.load_calibration(path)
            if saved:
                self.run_record.calibration = saved
                print(f"     reusing {ca.CALIBRATED_FILE} "
                      f"({len(saved.get('thresholds', {}))} thresholds) "
                      f"— pass --recalibrate to redo")
                return saved

        context = ca.build_context(features, self.cfg, max_depth, edges=edges)
        agent = ca.CalibratorAgent(self.client, self.cfg, self.tracer)
        result = self.run_record.add(agent.run(context, "calibrate thresholds"))
        calibration = result.output
        if not calibration or not calibration.get("thresholds"):
            print("     kept config.yaml thresholds "
                  f"({result.reason})")
            return None

        ca.save_calibration(calibration, path, self.client.model)
        counts = calibration.get("simulated_counts", {})
        print(f"     agent set {len(calibration['thresholds'])} thresholds "
              f"-> {counts}")
        print(f"     saved to {ca.CALIBRATED_FILE} (commit it for reproducibility)")
        self.run_record.calibration = calibration
        return calibration

    # -------------------------------------------------------- investigation

    def investigate(self, top_df, traces: dict, tools, n: int) -> dict[int, dict]:
        """Investigate the top `n` accounts, several at a time.

        Each dossier is an independent multi-step tool loop of roughly five
        calls, so run serially they dominate the wall clock — on one run the
        stage took 125s, 42% of the whole latency budget, while the process sat
        waiting on the network. They share no state, so they parallelize
        cleanly; the tracer is locked and the budget is still checked before
        each one is submitted.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from .investigator_agent import InvestigatorAgent

        if n <= 0:
            return {}
        rows = list(top_df.head(n).itertuples(index=False))
        workers = int((self.cfg.get("agents", {}) or {})
                      .get("investigator", {}).get("concurrency", 5))
        workers = max(1, min(workers, len(rows)))

        def one(row):
            gid = int(row.gid)
            trace = traces.get(gid)
            # A fresh agent per thread: they hold no shared mutable state, but
            # one instance per task keeps that true by construction.
            agent = InvestigatorAgent(self.client, self.cfg, self.tracer, tools=tools)
            return agent.run({
                "gid": gid, "rank": int(row.rank),
                "gate": trace.gate if trace else "",
                "metrics": trace.metrics if trace else {},
            }, f"investigate {gid}")

        dossiers: dict[int, dict] = {}
        results = []
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="investigator") as pool:
            futures = {}
            for row in rows:
                if not self.tracer.agents_allowed():
                    self.tracer.note_warning(
                        f"investigation stopped after {len(futures)} of {n} "
                        f"accounts (budget)")
                    break
                futures[pool.submit(one, row)] = int(row.gid)
            for fut in as_completed(futures):
                gid = futures[fut]
                try:
                    results.append((gid, fut.result()))
                except Exception as exc:
                    self.tracer.note_warning(
                        f"investigation of {gid} raised {type(exc).__name__}: {exc}")

        # Record in rank order, not completion order, so the log and the
        # dossier file are identical across runs.
        order = {int(r.gid): i for i, r in enumerate(rows)}
        for gid, result in sorted(results, key=lambda kv: order.get(kv[0], 0)):
            self.run_record.add(result)
            if result.output:
                dossiers[gid] = result.output
        self.run_record.dossiers = dossiers
        return dossiers

    # ------------------------------------------------------------- critique

    def critique(self, context: dict) -> dict | None:
        from .critic_agent import CriticAgent

        agent = CriticAgent(self.client, self.cfg, self.tracer)
        result = self.run_record.add(agent.run(context, "challenge the shortlist"))
        self.run_record.critique = result.output
        return result.output

    # ------------------------------------------------------------- the log

    def render_log(self) -> str:
        """`agent_log.md` — the audit trail."""
        rec = self.run_record
        md = ["# Agent log", "",
              "Every agent action in this run: what it was asked, which "
              "deterministic tools it called, what it returned, and whether that "
              "output was accepted or rejected.", "",
              "> No agent in this system assigns a role, a score, a cluster or a "
              "rank. Those come from the rule engine, which is deterministic and "
              "unaffected by anything below.", ""]

        if rec.plan:
            md += ["## Plan", "", "```json",
                   json.dumps(rec.plan, indent=2, ensure_ascii=False), "```", ""]

        if rec.calibration and rec.calibration.get("thresholds"):
            md += ["## Thresholds chosen by the calibrator", "",
                   "| Threshold | Value | Why |", "|---|---:|---|"]
            rationale = rec.calibration.get("rationale") or {}
            for key, value in rec.calibration["thresholds"].items():
                md.append(f"| `{key}` | {value} | {rationale.get(key, '—')} |")
            counts = rec.calibration.get("simulated_counts")
            if counts:
                md += ["", f"Simulated role counts under these thresholds: "
                           f"`{json.dumps(counts)}`"]
            concerns = rec.calibration.get("expected_concerns") or []
            if concerns:
                md += ["", "Concerns the agent raised about its own choice:"]
                md += [f"- {c}" for c in concerns]
            md.append("")

        md += ["## Run", "",
               "| Agent | Task | Outcome | Steps | Seconds |",
               "|---|---|---|---:|---:|"]
        for r in rec.results:
            outcome = ("fallback: " + r.reason) if r.used_fallback else "accepted"
            md.append(f"| {r.agent} | {r.task} | {outcome} | "
                      f"{len(r.steps)} | {r.duration_s:.2f} |")
        md.append("")

        md += ["## Transcripts", ""]
        for r in rec.results:
            md += [f"### {r.agent} — {r.task}", "",
                   f"*{'deterministic fallback' if r.used_fallback else 'model output accepted'}"
                   f" — {r.reason}*", ""]
            for step in r.steps:
                if step.kind == "tool":
                    md += [f"- **tool** `{step.summary}` ({step.duration_s:.2f}s)",
                           "  <details><summary>result</summary>",
                           "",
                           f"  ```\n  {_indent(step.detail)}\n  ```", "  </details>"]
                elif step.kind in ("output", "fallback"):
                    md += [f"- **{step.kind}**",
                           "", f"  ```json\n  {_indent(step.detail)}\n  ```", ""]
                elif step.kind == "error":
                    md += [f"- **rejected** — {step.summary}", ""]
                else:
                    md += [f"- **{step.kind}** {step.summary}"]
            md.append("")
        return "\n".join(md) + "\n"


def _indent(detail: Any, width: int = 2) -> str:
    if detail is None:
        return ""
    text = detail if isinstance(detail, str) else json.dumps(detail, indent=2,
                                                             ensure_ascii=False,
                                                             default=str)
    pad = " " * width
    return ("\n" + pad).join(str(text).splitlines())


def build_brief(profile_facts: dict, role_counts: dict, n_nodes: int,
                tracer: RunTracer) -> dict:
    """What the planner is shown: the shape of the data, not the data."""
    totals = tracer.totals()
    return {
        "dataset": profile_facts,
        "role_counts_at_current_thresholds": role_counts,
        "n_nodes": n_nodes,
        "budget_remaining": {
            "calls_used": totals["n_calls"],
            "tokens_used": totals["total_tokens"],
            "seconds_elapsed": round(tracer.elapsed_s, 1),
            "seconds_budget": tracer.max_runtime_s,
        },
    }
