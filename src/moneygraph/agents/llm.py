"""Thin, traced wrapper around the model provider.

Everything the agent layer sends goes through `LLMClient`, so that:

* every call is timed and its token usage recorded on the `RunTracer`;
* the budget in `config.yaml -> llm.budget` is enforced centrally;
* a missing key, a network failure or a provider error is never fatal — the
  caller gets `None` and falls back to its deterministic path.

The provider API is accessed defensively. The Responses API is tried first
(it is the one that carries `reasoning.effort`); if the installed SDK or the
configured model rejects it, the call is retried against Chat Completions.
Token usage is read from whichever shape came back and is **never estimated**:
if the provider reports no usage, the call is flagged `usage_reported=False`
and its tokens stay at zero rather than being invented.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from ..trace import LLMCall, RunTracer


def load_env(root: Path | None = None) -> None:
    """Load `.env` if python-dotenv is installed; fall back to a manual parse."""
    root = root or Path(__file__).resolve().parents[3]
    env_path = root / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


class LLMClient:
    """Traced client. `client.available` is False whenever the layer is off."""

    def __init__(self, cfg: dict, tracer: RunTracer) -> None:
        self.cfg = cfg
        self.tracer = tracer
        lcfg = cfg.get("llm", {}) or {}
        self.model: str = lcfg.get("model", "gpt-6-luna")
        self.reasoning_effort: str | None = lcfg.get("reasoning_effort")
        self.temperature: float = float(lcfg.get("temperature", 0.2))
        self.max_output_tokens: int = int(lcfg.get("max_output_tokens", 2000))
        self.timeout_s: float = float(lcfg.get("timeout_s", 60))
        acfg = (cfg.get("agents", {}) or {}).get("analyst", {}) or {}
        # A tool can return a large table; truncate before it reaches the model
        # so one wide query cannot blow the token budget.
        self.max_tool_result_chars: int = int(acfg.get("max_tool_result_chars", 20 * 1024))
        self.max_retries: int = int(lcfg.get("max_retries", 2))
        self.disabled_reason: str | None = None
        self._client: Any = None
        self._use_responses = True

        if not lcfg.get("enabled", True):
            self.disabled_reason = "llm.enabled is false in config.yaml"
            return
        if os.environ.get("MONEYGRAPH_NO_LLM"):
            self.disabled_reason = "MONEYGRAPH_NO_LLM is set"
            return

        load_env()
        key_names = lcfg.get("api_key_env") or ["OPENAI_KEY", "OPENAI_API_KEY"]
        if isinstance(key_names, str):
            key_names = [key_names]
        key = next((os.environ[n] for n in key_names if os.environ.get(n)), None)
        if not key:
            self.disabled_reason = (
                f"no API key found in {', '.join(key_names)} (checked .env and the "
                f"environment) — running fully deterministically"
            )
            return

        try:
            from openai import OpenAI
        except ImportError:
            self.disabled_reason = "the `openai` package is not installed"
            return

        self._client = OpenAI(api_key=key, timeout=self.timeout_s, max_retries=0)
        self.model = os.environ.get("MONEYGRAPH_MODEL", self.model)

    # ------------------------------------------------------------------ api

    @property
    def available(self) -> bool:
        return self._client is not None and self.tracer.agents_allowed()

    def complete(
        self,
        agent: str,
        purpose: str,
        system: str,
        user: str,
        *,
        json_object: bool = False,
        tools: list[dict] | None = None,
        max_output_tokens: int | None = None,
    ) -> str | None:
        """Single turn. Returns the text, or None if the call could not be made."""
        if not self.available:
            return None
        result = self._call(agent, purpose, system, user,
                            json_object=json_object, tools=tools,
                            max_output_tokens=max_output_tokens)
        return None if result is None else result[0]

    def complete_json(
        self, agent: str, purpose: str, system: str, user: str,
        *, max_output_tokens: int | None = None,
    ) -> Any | None:
        """Single turn expected to return JSON. Returns None on any failure,
        including a reply that does not parse — a malformed answer must never
        reach the pipeline as if it were valid."""
        text = self.complete(agent, purpose, system, user,
                             json_object=True, max_output_tokens=max_output_tokens)
        if not text:
            return None
        try:
            return json.loads(_strip_code_fence(text))
        except json.JSONDecodeError:
            self.tracer.note_warning(
                f"{agent}/{purpose}: reply was not valid JSON; using the "
                f"deterministic fallback"
            )
            return None

    def converse_with_tools(
        self,
        agent: str,
        purpose: str,
        system: str,
        user: str,
        tools: list[dict],
        dispatch: Callable[[str, dict], Any],
        max_tool_calls: int = 8,
    ) -> tuple[str | None, list[dict]]:
        """Tool-calling loop.

        `tools` are OpenAI-style function schemas; `dispatch(name, args)` runs the
        corresponding deterministic graph function. Returns the final answer and
        the transcript of tool calls, so the viewer can show the analyst exactly
        which graph queries produced the answer. Nothing the model says is
        trusted as fact — only `dispatch` output is.
        """
        transcript: list[dict] = []
        if not self.available:
            return None, transcript

        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        for _ in range(max_tool_calls):
            out = self._chat(agent, purpose, messages, tools=tools)
            if out is None:
                return None, transcript
            text, tool_calls, raw_message = out
            if not tool_calls:
                return text, transcript
            messages.append(raw_message)
            for tc in tool_calls:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    result = dispatch(name, args)
                    error = None
                except Exception as exc:  # a bad tool call must not kill the chat
                    result, error = None, f"{type(exc).__name__}: {exc}"
                transcript.append({"tool": name, "args": args,
                                   "result": result, "error": error})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(
                        {"error": error} if error else result,
                        ensure_ascii=False, default=str)[:self.max_tool_result_chars],
                })
        # Out of tool budget: ask for a final answer with no further tools.
        out = self._chat(agent, purpose, messages, tools=None)
        return (out[0] if out else None), transcript

    # -------------------------------------------------------------- plumbing

    def _call(self, agent, purpose, system, user, *, json_object, tools,
              max_output_tokens) -> tuple[str, LLMCall] | None:
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        out = self._chat(agent, purpose, messages, tools=tools,
                         json_object=json_object,
                         max_output_tokens=max_output_tokens)
        if out is None:
            return None
        return out[0], out[3]

    def _chat(self, agent, purpose, messages, *, tools=None, json_object=False,
              max_output_tokens=None):
        """Returns (text, tool_calls, assistant_message, LLMCall) or None."""
        if not self.available:
            return None
        last_error = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                if self._use_responses:
                    try:
                        return self._via_responses(
                            agent, purpose, messages, tools, json_object,
                            max_output_tokens, t0, attempt)
                    except TypeError:
                        # SDK too old for the Responses API shape.
                        self._use_responses = False
                    except Exception as exc:
                        if _looks_like_unsupported(exc):
                            self._use_responses = False
                        else:
                            raise
                return self._via_chat_completions(
                    agent, purpose, messages, tools, json_object,
                    max_output_tokens, t0, attempt)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                self.tracer.record_llm(LLMCall(
                    agent=agent, purpose=purpose, model=self.model,
                    duration_s=time.perf_counter() - t0,
                    ok=False, error=last_error, retries=attempt,
                ))
                self.tracer.note_warning(
                    f"{agent}/{purpose}: model call failed ({last_error}); "
                    f"falling back to the deterministic path"
                )
                return None
        return None

    def _via_responses(self, agent, purpose, messages, tools, json_object,
                       max_output_tokens, t0, attempt):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": messages,
            "max_output_tokens": max_output_tokens or self.max_output_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}
        else:
            kwargs["temperature"] = self.temperature
        if json_object:
            kwargs["text"] = {"format": {"type": "json_object"}}
        if tools:
            kwargs["tools"] = [{"type": "function", **t["function"]} for t in tools]

        resp = self._client.responses.create(**kwargs)
        call = self._usage_from_responses(agent, purpose, resp, t0, attempt)
        self.tracer.record_llm(call)

        text = getattr(resp, "output_text", None) or ""
        tool_calls, assistant_msg = [], {"role": "assistant", "content": text}
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", None) == "function_call":
                tool_calls.append({
                    "id": getattr(item, "call_id", None) or getattr(item, "id", ""),
                    "name": item.name,
                    "arguments": item.arguments,
                })
        if tool_calls:
            assistant_msg = {
                "role": "assistant", "content": text or None,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tool_calls
                ],
            }
        return text, tool_calls, assistant_msg, call

    def _via_chat_completions(self, agent, purpose, messages, tools, json_object,
                              max_output_tokens, t0, attempt):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_output_tokens or self.max_output_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        else:
            kwargs["temperature"] = self.temperature
        if json_object:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools

        resp = self._client.chat.completions.create(**kwargs)
        call = self._usage_from_chat(agent, purpose, resp, t0, attempt)
        self.tracer.record_llm(call)

        msg = resp.choices[0].message
        text = msg.content or ""
        tool_calls = [
            {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ]
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in tool_calls
            ]
        return text, tool_calls, assistant_msg, call

    # ------------------------------------------------------------ usage

    def _usage_from_responses(self, agent, purpose, resp, t0, attempt) -> LLMCall:
        u = getattr(resp, "usage", None)
        call = LLMCall(agent=agent, purpose=purpose, model=self.model,
                       duration_s=time.perf_counter() - t0, retries=attempt)
        if u is None:
            call.usage_reported = False
            return call
        call.input_tokens = int(getattr(u, "input_tokens", 0) or 0)
        call.output_tokens = int(getattr(u, "output_tokens", 0) or 0)
        details = getattr(u, "output_tokens_details", None)
        call.reasoning_tokens = int(getattr(details, "reasoning_tokens", 0) or 0)
        in_details = getattr(u, "input_tokens_details", None)
        call.cached_input_tokens = int(getattr(in_details, "cached_tokens", 0) or 0)
        return call

    def _usage_from_chat(self, agent, purpose, resp, t0, attempt) -> LLMCall:
        u = getattr(resp, "usage", None)
        call = LLMCall(agent=agent, purpose=purpose, model=self.model,
                       duration_s=time.perf_counter() - t0, retries=attempt)
        if u is None:
            call.usage_reported = False
            return call
        call.input_tokens = int(getattr(u, "prompt_tokens", 0) or 0)
        call.output_tokens = int(getattr(u, "completion_tokens", 0) or 0)
        details = getattr(u, "completion_tokens_details", None)
        call.reasoning_tokens = int(getattr(details, "reasoning_tokens", 0) or 0)
        in_details = getattr(u, "prompt_tokens_details", None)
        call.cached_input_tokens = int(getattr(in_details, "cached_tokens", 0) or 0)
        return call


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _looks_like_unsupported(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in (
        "unknown parameter", "unsupported parameter", "not supported",
        "no attribute 'responses'", "404", "unrecognized request argument",
    ))
