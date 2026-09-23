"""A small agent framework: plan, act with tools, observe, produce, be checked.

Every agent in this package is a subclass of `Agent` and inherits four
properties that make an agentic system usable in a compliance setting:

* **Bounded.** `max_steps` caps the tool loop; the shared `RunTracer` caps
  calls, tokens and spend across the whole crew. An agent that runs away stops.
* **Traced.** Every step — the plan, each tool call with its arguments and raw
  result, the final output — is recorded and written to `agent_log.md`. An
  analyst can reconstruct exactly how a conclusion was reached.
* **Validated.** Each subclass declares `validate()`. Output that fails is
  discarded, and the reason is logged. The agent does not get to mark its own
  homework.
* **Replaceable.** Each subclass declares `fallback()`, a deterministic result
  used when there is no API key, the budget is spent, the call fails, or
  validation rejects the output. No agent is load-bearing for the deliverables.

The division of labour with the deterministic core is the design of the whole
system: agents choose *what to examine and what the thresholds should be*; the
rule engine in `roles.py` decides *what the role is*. That keeps the system
agentic without producing a role nobody can explain, which the brief forbids.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..trace import RunTracer
from .llm import LLMClient


@dataclass
class AgentStep:
    """One observable action. `kind` is plan | tool | output | fallback | error."""

    kind: str
    summary: str
    detail: Any = None
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {"kind": self.kind, "summary": self.summary,
                "detail": self.detail, "duration_s": round(self.duration_s, 3)}


@dataclass
class AgentResult:
    agent: str
    task: str
    output: Any = None
    steps: list[AgentStep] = field(default_factory=list)
    ok: bool = False
    used_fallback: bool = False
    reason: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {"agent": self.agent, "task": self.task, "ok": self.ok,
                "used_fallback": self.used_fallback, "reason": self.reason,
                "duration_s": round(self.duration_s, 3),
                "steps": [s.to_dict() for s in self.steps],
                "output": self.output}


class Agent:
    """Base class. Subclasses set `name`/`role`/`system`, and implement
    `build_task`, `validate` and `fallback`."""

    name: str = "agent"
    role: str = ""
    system: str = ""
    json_output: bool = True
    max_steps: int = 1               # >1 enables the tool loop

    def __init__(self, client: LLMClient, cfg: dict, tracer: RunTracer,
                 tools: Any = None) -> None:
        self.client = client
        self.cfg = cfg
        self.tracer = tracer
        self.tools = tools
        acfg = (cfg.get("agents", {}) or {}).get(self.name, {}) or {}
        self.settings = acfg
        self.enabled = acfg.get("enabled", True)
        self.max_steps = int(acfg.get("max_steps", self.max_steps))

    # ------------------------------------------------------------ interface

    def build_task(self, context: dict) -> str:
        """The user-side prompt. Subclasses render their own context."""
        raise NotImplementedError

    def validate(self, output: Any, context: dict) -> tuple[bool, str]:
        """Accept or reject the agent's own output. Rejection is not an error —
        it is the system working."""
        return (output is not None), "empty output" if output is None else "ok"

    def fallback(self, context: dict) -> Any:
        """The deterministic result used whenever the agent cannot be trusted
        or cannot be reached."""
        raise NotImplementedError

    def tool_schemas(self) -> list[dict] | None:
        """Return schemas to enable the multi-step tool loop."""
        return None

    # ----------------------------------------------------------------- run

    def run(self, context: dict, task_label: str = "") -> AgentResult:
        t0 = time.perf_counter()
        result = AgentResult(agent=self.name, task=task_label or self.role)

        def finish(reason: str, used_fallback: bool, ok: bool) -> AgentResult:
            result.reason = reason
            result.used_fallback = used_fallback
            result.ok = ok
            result.duration_s = time.perf_counter() - t0
            return result

        if not self.enabled:
            result.output = self._safe_fallback(context, result)
            return finish(f"{self.name} disabled in config.yaml", True, True)
        if not self.client.available:
            result.output = self._safe_fallback(context, result)
            return finish(self.client.disabled_reason or "no model available", True, True)

        try:
            task = self.build_task(context)
        except Exception as exc:
            result.steps.append(AgentStep("error", f"could not build task: {exc}"))
            result.output = self._safe_fallback(context, result)
            return finish(f"task construction failed: {exc}", True, True)

        result.steps.append(AgentStep("plan", f"{self.role}",
                                      detail={"prompt_chars": len(task)}))

        schemas = self.tool_schemas()
        try:
            if schemas and self.max_steps > 1 and self.tools is not None:
                raw, transcript = self.client.converse_with_tools(
                    agent=self.name, purpose=task_label or self.role,
                    system=self.system, user=task, tools=schemas,
                    dispatch=self._dispatch(result), max_tool_calls=self.max_steps)
                for call in transcript:
                    pass   # already recorded by _dispatch
                output = self._parse(raw)
            elif self.json_output:
                output = self.client.complete_json(
                    agent=self.name, purpose=task_label or self.role,
                    system=self.system, user=task)
            else:
                output = self.client.complete(
                    agent=self.name, purpose=task_label or self.role,
                    system=self.system, user=task)
        except Exception as exc:
            result.steps.append(AgentStep("error", f"{type(exc).__name__}: {exc}"))
            self.tracer.note_warning(f"{self.name}: {type(exc).__name__}: {exc}")
            result.output = self._safe_fallback(context, result)
            return finish(f"call failed: {exc}", True, True)

        if output is None:
            result.output = self._safe_fallback(context, result)
            return finish("no usable output returned", True, True)

        ok, reason = self.validate(output, context)
        if not ok:
            result.steps.append(AgentStep("error", f"output rejected: {reason}",
                                          detail=_trim(output)))
            self.tracer.note_warning(f"{self.name}: output rejected ({reason})")
            result.output = self._safe_fallback(context, result)
            return finish(f"rejected: {reason}", True, True)

        result.steps.append(AgentStep("output", "accepted", detail=_trim(output)))
        result.output = output
        return finish("ok", False, True)

    # ------------------------------------------------------------ internals

    def _dispatch(self, result: AgentResult) -> Callable[[str, dict], Any]:
        """Wrap the tool dispatcher so every call lands in the agent log."""
        def call(name: str, args: dict) -> Any:
            t0 = time.perf_counter()
            try:
                out = self.tools.dispatch(name, args)
                result.steps.append(AgentStep(
                    "tool", f"{name}({_args(args)})", detail=_trim(out),
                    duration_s=time.perf_counter() - t0))
                return out
            except Exception as exc:
                result.steps.append(AgentStep(
                    "tool", f"{name}({_args(args)}) FAILED",
                    detail=f"{type(exc).__name__}: {exc}",
                    duration_s=time.perf_counter() - t0))
                raise
        return call

    def _parse(self, raw: str | None) -> Any:
        if raw is None:
            return None
        if not self.json_output:
            return raw
        from .llm import _strip_code_fence

        try:
            return json.loads(_strip_code_fence(raw))
        except (json.JSONDecodeError, TypeError):
            return None

    def _safe_fallback(self, context: dict, result: AgentResult) -> Any:
        try:
            out = self.fallback(context)
            result.steps.append(AgentStep("fallback", "deterministic result used",
                                          detail=_trim(out)))
            return out
        except Exception as exc:
            result.steps.append(AgentStep("error", f"fallback failed: {exc}"))
            return None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _args(args: dict) -> str:
    s = json.dumps(args, default=str)
    return s if len(s) <= 120 else s[:117] + "…"


def _trim(obj: Any, limit: int = 1200) -> Any:
    """Keep the agent log readable without losing the shape of a result."""
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    except (TypeError, ValueError):
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"… [{len(s)} chars]"


WORDING_RULES = """Wording rules that apply to everything you write:
- These are hypotheses for an analyst to verify, never statements about a person. Write "signs of", "pattern consistent with", "candidate for review".
- Never use: criminal, guilty, launderer, "organizer is", confirmed.
- The data is anonymized. No names, ages, genders, incomes or organizations exist; inventing one is a disqualification.
- Cite account identifiers (gids) for anything you claim."""
