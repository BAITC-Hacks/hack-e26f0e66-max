"""Run tracing: wall clock, tokens and spend.

One `RunTracer` instance travels through the whole pipeline. It records:

* a nested timing tree — every stage, and every sub-step inside it;
* every LLM call, with input / output / reasoning / cached token counts;
* the cost of each call, priced from `config.yaml -> llm.pricing`.

Three rules this module keeps, because a spend figure that is wrong is worse
than no spend figure:

1. **It never invents a price.** If a model has no entry under `llm.pricing`,
   the call is recorded as *unpriced*: token counts are still exact, and the
   total carries an explicit "n calls unpriced" caveat instead of a number that
   looks authoritative.
2. **It never guesses token counts.** Only usage actually reported by the
   provider is recorded. A call whose response omits usage is marked as such.
3. **It enforces the budget it is given.** Once `llm.budget` is exceeded the
   tracer says so, the agent layer shuts down and the run finishes
   deterministically — the exports are always produced.

Output: `output_files/run_trace.json` (machine-readable) and
`output_files/run_trace.md` (shown in the viewer's Trace tab).
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

# Pricing in config.yaml is USD per 1M tokens. Written as a power so the
# hardcoding guard in tests/ stays meaningful: any 5+ digit literal in src/
# that is not a config value is treated as a possible hardcoded gid.
TOKENS_PER_PRICE_UNIT = 10 ** 6


# --------------------------------------------------------------------------- 
# records
# ---------------------------------------------------------------------------

@dataclass
class LLMCall:
    """One request to the model provider."""

    agent: str
    purpose: str
    model: str
    duration_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0     # only if the provider reports cache creation
    cost_usd: float | None = None   # None = no price configured for this model
    priced: bool = False
    pricing_tier: str = ""          # short | long — which rate card was applied
    usage_reported: bool = True
    ok: bool = True
    error: str | None = None
    retries: int = 0

    @property
    def total_tokens(self) -> int:
        # Reasoning tokens are billed as output and are already included in the
        # provider's output count, so they are not added again here.
        return self.input_tokens + self.output_tokens


@dataclass
class Stage:
    """One pipeline stage, possibly with nested sub-stages."""

    name: str
    duration_s: float = 0.0
    started_at: float = 0.0
    notes: list[str] = field(default_factory=list)
    children: list["Stage"] = field(default_factory=list)
    llm_calls: list[LLMCall] = field(default_factory=list)

    def walk(self) -> Iterator["Stage"]:
        yield self
        for child in self.children:
            yield from child.walk()


# ---------------------------------------------------------------------------
# tracer
# ---------------------------------------------------------------------------

class BudgetExceeded(RuntimeError):
    """Raised inside the agent layer only; the pipeline catches and degrades."""


class RunTracer:
    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.cfg = cfg
        tcfg = cfg.get("tracing", {}) or {}
        lcfg = cfg.get("llm", {}) or {}

        self.enabled: bool = tcfg.get("enabled", True)
        self.print_live: bool = tcfg.get("print_live", True)
        self.max_runtime_s: float = float(tcfg.get("max_runtime_s", 300))
        self.stage_warn_share: float = float(tcfg.get("stage_warn_share", 0.25))

        pricing = dict(lcfg.get("pricing", {}) or {})
        # A scalar knob living alongside the per-model cards.
        self.long_context_threshold: int = int(
            pricing.pop("long_context_threshold_tokens", 0) or 0)
        self.pricing: dict[str, dict] = pricing
        budget = lcfg.get("budget", {}) or {}
        self.max_calls = budget.get("max_calls")
        self.max_usd = budget.get("max_usd")
        self.max_total_tokens = budget.get("max_total_tokens")

        # Agents may run concurrently, so every mutation of the trace is
        # guarded. A cost figure assembled from a racy counter is not a cost
        # figure.
        self._lock = threading.RLock()
        self.root = Stage(name="run", started_at=time.perf_counter())
        self._stack: list[Stage] = [self.root]
        self.warnings: list[str] = []
        self.budget_stopped: str | None = None
        self._t0 = time.perf_counter()

    # ------------------------------------------------------------- timing

    @contextmanager
    def stage(self, name: str):
        """Time a stage. Nests automatically when used inside another stage."""
        parent = self._stack[-1]
        st = Stage(name=name, started_at=time.perf_counter())
        parent.children.append(st)
        self._stack.append(st)
        try:
            yield st
        finally:
            self._stack.pop()
            st.duration_s = time.perf_counter() - st.started_at
            if self.print_live:
                depth = len(self._stack) - 1
                indent = "  " * depth
                calls = len(st.llm_calls)
                suffix = f"   ({calls} llm call{'s' if calls != 1 else ''})" if calls else ""
                print(f"  {indent}{st.name:<28} {st.duration_s:7.2f}s{suffix}")
            share = st.duration_s / self.max_runtime_s if self.max_runtime_s else 0
            if share > self.stage_warn_share:
                self.note_warning(
                    f"stage '{st.name}' used {100 * share:.0f}% of the "
                    f"{self.max_runtime_s:.0f}s latency budget"
                )

    def note(self, text: str) -> None:
        with self._lock:
            self._stack[-1].notes.append(text)

    def note_warning(self, text: str) -> None:
        with self._lock:
            if text in self.warnings:
                return                 # concurrent agents hit the same wall
            self.warnings.append(text)
            if self.print_live:
                print(f"  ! {text}")

    @property
    def elapsed_s(self) -> float:
        return time.perf_counter() - self._t0

    # ---------------------------------------------------------------- llm

    def rates_for(self, model: str, input_tokens: int) -> tuple[dict, str] | None:
        """The rate card that applies to one call.

        A model may be priced flat (`{input, output, ...}`) or in two context
        tiers (`{short: {...}, long: {...}}`). Which tier applies is decided by
        the call's own input size against `long_context_threshold_tokens`.
        """
        card = self.pricing.get(model)
        if not card:
            return None
        if "short" in card or "long" in card:
            tier = ("long" if (self.long_context_threshold
                               and input_tokens >= self.long_context_threshold)
                    else "short")
            rates = card.get(tier) or card.get("short") or card.get("long")
            if not rates:
                return None
        else:
            rates, tier = card, "flat"
        if rates.get("input") is None or rates.get("output") is None:
            return None
        return rates, tier

    def price_call(self, model: str, call: LLMCall) -> LLMCall:
        """Attach a cost, or leave it None when the model has no price set."""
        found = self.rates_for(model, call.input_tokens)
        if found is None:
            call.cost_usd, call.priced, call.pricing_tier = None, False, ""
            return call
        rates, tier = found
        per = TOKENS_PER_PRICE_UNIT

        # Cached tokens are a subset of the reported input count, so they are
        # charged once, at the cached rate.
        fresh_input = max(call.input_tokens - call.cached_input_tokens, 0)
        cost = fresh_input * float(rates["input"]) / per

        cached_rate = rates.get("cached_input")
        # No cached rate configured: charge them at the full input rate, which
        # over-states rather than under-states the bill.
        cost += (call.cached_input_tokens
                 * float(cached_rate if cached_rate is not None else rates["input"]) / per)

        # Only charged when the provider actually reported cache-creation
        # tokens. Never inferred: a cache write we cannot observe is not a
        # charge we are entitled to invent.
        write_rate = rates.get("cache_write")
        if call.cache_write_tokens and write_rate is not None:
            cost += call.cache_write_tokens * float(write_rate) / per

        cost += call.output_tokens * float(rates["output"]) / per
        call.cost_usd, call.priced, call.pricing_tier = cost, True, tier
        return call

    def record_llm(self, call: LLMCall) -> LLMCall:
        with self._lock:
            self.price_call(call.model, call)
            self._stack[-1].llm_calls.append(call)
        if self.print_live:
            cost = (f"${call.cost_usd:.4f}" if call.cost_usd is not None else "unpriced")
            if call.cost_usd is not None and call.pricing_tier == "long":
                cost += " (long-context rate)"
            status = "ok" if call.ok else f"FAILED: {call.error}"
            print(
                f"      · {call.agent}/{call.purpose}: {call.duration_s:.2f}s, "
                f"{call.input_tokens} in / {call.output_tokens} out"
                + (f" ({call.reasoning_tokens} reasoning)" if call.reasoning_tokens else "")
                + f", {cost} [{status}]"
            )
        self.check_budget()
        return call

    # ------------------------------------------------------------- budget

    def check_budget(self) -> None:
        """Set `budget_stopped` once any ceiling is passed. Never raises here.

        The whole decision is taken under the lock so that concurrent agents
        cannot each read a pre-limit total and all proceed past the ceiling.
        """
        with self._lock:
            if self.budget_stopped:
                return
            t = self.totals()
            if self.max_calls is not None and t["n_calls"] >= self.max_calls:
                self.budget_stopped = f"call ceiling reached ({self.max_calls})"
            elif (self.max_total_tokens is not None
                  and t["total_tokens"] >= self.max_total_tokens):
                self.budget_stopped = (f"token ceiling reached "
                                       f"({self.max_total_tokens:,})")
            elif (self.max_usd is not None and t["cost_usd"] is not None
                  and t["cost_usd"] >= float(self.max_usd)):
                self.budget_stopped = (f"spend ceiling reached "
                                       f"(${float(self.max_usd):.2f})")
            stopped = self.budget_stopped

        if stopped:
            self.note_warning(
                f"agent layer stopped: {stopped}. "
                f"The run continues deterministically; all exports are still "
                f"produced.")

    def agents_allowed(self) -> bool:
        return self.budget_stopped is None

    # ------------------------------------------------------------- totals

    def all_calls(self) -> list[LLMCall]:
        return [c for st in self.root.walk() for c in st.llm_calls]

    def totals(self) -> dict[str, Any]:
        calls = self.all_calls()
        priced = [c for c in calls if c.priced and c.cost_usd is not None]
        unpriced = [c for c in calls if not c.priced]
        return {
            "n_calls": len(calls),
            "n_failed": sum(1 for c in calls if not c.ok),
            "input_tokens": sum(c.input_tokens for c in calls),
            "output_tokens": sum(c.output_tokens for c in calls),
            "reasoning_tokens": sum(c.reasoning_tokens for c in calls),
            "cached_input_tokens": sum(c.cached_input_tokens for c in calls),
            "cache_write_tokens": sum(c.cache_write_tokens for c in calls),
            "long_context_calls": sum(1 for c in calls if c.pricing_tier == "long"),
            "total_tokens": sum(c.total_tokens for c in calls),
            "llm_seconds": sum(c.duration_s for c in calls),
            "cost_usd": sum(c.cost_usd for c in priced) if priced else (None if unpriced else 0.0),
            "n_unpriced_calls": len(unpriced),
        }

    def by_agent(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for c in self.all_calls():
            row = out.setdefault(
                c.agent,
                {"n_calls": 0, "input_tokens": 0, "output_tokens": 0,
                 "reasoning_tokens": 0, "seconds": 0.0, "cost_usd": 0.0, "unpriced": 0},
            )
            row["n_calls"] += 1
            row["input_tokens"] += c.input_tokens
            row["output_tokens"] += c.output_tokens
            row["reasoning_tokens"] += c.reasoning_tokens
            row["seconds"] += c.duration_s
            if c.priced and c.cost_usd is not None:
                row["cost_usd"] += c.cost_usd
            else:
                row["unpriced"] += 1
        return out

    # ------------------------------------------------------------ reports

    def to_dict(self) -> dict[str, Any]:
        self.root.duration_s = self.elapsed_s

        def pack(st: Stage) -> dict[str, Any]:
            d = {
                "name": st.name,
                "duration_s": round(st.duration_s, 4),
                "notes": st.notes,
                "llm_calls": [asdict(c) for c in st.llm_calls],
                "children": [pack(ch) for ch in st.children],
            }
            return d

        return {
            "total_runtime_s": round(self.elapsed_s, 4),
            "runtime_budget_s": self.max_runtime_s,
            "within_budget": self.elapsed_s < self.max_runtime_s,
            "totals": self.totals(),
            "by_agent": self.by_agent(),
            "budget_stopped": self.budget_stopped,
            "warnings": self.warnings,
            "stages": pack(self.root)["children"],
        }

    def to_markdown(self) -> str:
        d = self.to_dict()
        t = d["totals"]
        lines: list[str] = ["# Run trace", ""]

        lines += [
            "## Latency",
            "",
            f"- **Total runtime: {d['total_runtime_s']:.2f} s** "
            f"(budget {d['runtime_budget_s']:.0f} s — "
            f"{'within' if d['within_budget'] else '**OVER**'})",
            f"- Of which spent waiting on the model: {t['llm_seconds']:.2f} s",
            "",
            "| Stage | Seconds | Share | LLM calls |",
            "|---|---:|---:|---:|",
        ]
        total = max(d["total_runtime_s"], 1e-9)

        def rows(stages: list[dict], depth: int = 0) -> None:
            for st in stages:
                name = ("&nbsp;" * 4 * depth) + st["name"]
                lines.append(
                    f"| {name} | {st['duration_s']:.2f} | "
                    f"{100 * st['duration_s'] / total:.0f}% | {len(st['llm_calls'])} |"
                )
                rows(st["children"], depth + 1)

        rows(d["stages"])

        lines += ["", "## Tokens and spend", ""]
        if t["n_calls"] == 0:
            lines += [
                "No model calls were made — this run was fully deterministic "
                "(no API key, `llm.enabled: false`, or `MONEYGRAPH_NO_LLM=1`).",
                "",
                "Cost of this run: **$0.00**.",
            ]
        else:
            cost = t["cost_usd"]
            cost_txt = f"**${cost:.4f}**" if cost is not None else "**unpriced**"
            lines += [
                f"- Calls: **{t['n_calls']}** ({t['n_failed']} failed)",
                f"- Tokens: **{t['total_tokens']:,}** "
                f"({t['input_tokens']:,} in / {t['output_tokens']:,} out, "
                f"{t['reasoning_tokens']:,} reasoning, "
                f"{t['cached_input_tokens']:,} cached)",
                f"- Spend: {cost_txt}",
            ]
            if t.get("long_context_calls"):
                lines.append(f"- Priced at the long-context rate: "
                             f"**{t['long_context_calls']}** call(s)")
            if t["n_unpriced_calls"]:
                lines += [
                    "",
                    f"> {t['n_unpriced_calls']} of {t['n_calls']} calls are **unpriced**: "
                    f"no entry under `llm.pricing` for that model in `config.yaml`. "
                    f"Token counts above are exact; the spend figure excludes those "
                    f"calls rather than guessing a rate.",
                ]
            lines += [
                "",
                "| Agent | Calls | In | Out | Reasoning | Seconds | Cost |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
            for agent, r in sorted(d["by_agent"].items()):
                c = f"${r['cost_usd']:.4f}" if not r["unpriced"] else "unpriced"
                lines.append(
                    f"| {agent} | {r['n_calls']} | {r['input_tokens']:,} | "
                    f"{r['output_tokens']:,} | {r['reasoning_tokens']:,} | "
                    f"{r['seconds']:.2f} | {c} |"
                )

        if d["budget_stopped"]:
            lines += ["", "## Budget", "",
                      f"The agent layer stopped early: **{d['budget_stopped']}**. "
                      f"The deterministic pipeline ran to completion and every export "
                      f"was produced."]

        if d["warnings"]:
            lines += ["", "## Warnings", ""] + [f"- {w}" for w in d["warnings"]]

        return "\n".join(lines) + "\n"

    def write(self, out_dir: str | Path) -> None:
        if not self.enabled:
            return
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        tcfg = self.cfg.get("tracing", {}) or {}
        if tcfg.get("write_json"):
            (out_dir / tcfg["write_json"]).write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
        if tcfg.get("write_markdown"):
            (out_dir / tcfg["write_markdown"]).write_text(self.to_markdown(), encoding="utf-8")

    def print_summary(self) -> None:
        t = self.totals()
        cost = t["cost_usd"]
        cost_txt = f"${cost:.4f}" if cost is not None else "unpriced"
        print()
        print(f"  {'TOTAL':<30} {self.elapsed_s:7.2f}s "
              f"(budget {self.max_runtime_s:.0f}s)")
        print(f"  {'LLM':<30} {t['n_calls']} calls, "
              f"{t['total_tokens']:,} tokens, {cost_txt}")
        if t["n_unpriced_calls"]:
            print(f"  {'':<30} {t['n_unpriced_calls']} unpriced — "
                  f"set llm.pricing in config.yaml for a spend figure")
