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
        self.base_url: str | None = None
        self.provider_label: str = "openai"
        self._client: Any = None
        # Which wire format to use. "auto" means the Responses API for
        # single-turn calls (it reports reasoning tokens) and Chat Completions
        # for tool loops, which every OpenAI-compatible server implements.
        self.api_mode: str = str(lcfg.get("api", "auto")).lower()
        self._use_responses = self.api_mode in ("auto", "responses")

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

        # A self-hosted or third-party OpenAI-compatible server (vLLM, Ollama,
        # llama.cpp, TGI, LM Studio, OpenRouter, Together, …) is configured by
        # pointing base_url at it. Nothing else in the agent layer changes.
        self.base_url = (os.environ.get("MONEYGRAPH_BASE_URL")
                         or lcfg.get("base_url") or None)
        client_kwargs: dict[str, Any] = {"api_key": key, "timeout": self.timeout_s,
                                         "max_retries": 0}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
            self.provider_label = self.base_url
            # Custom servers implement /v1/chat/completions; /v1/responses is
            # rare outside OpenAI itself, so do not probe for it.
            if self.api_mode == "auto":
                self._use_responses = False
        self._client = OpenAI(**client_kwargs)
        self.model = os.environ.get("MONEYGRAPH_MODEL", self.model)

    # ------------------------------------------------------------------ api

    @property
    def available(self) -> bool:
        return self._client is not None and self.tracer.agents_allowed()

    def output_budget(self, agent: str) -> int:
        """Per-agent output cap. A truncated reply is a wasted call: the critic
        in particular writes long structured JSON and silently produced invalid
        output when it hit the global default."""
        per = (self.cfg.get("agents", {}) or {}).get(agent, {}) or {}
        return int(per.get("max_output_tokens") or self.max_output_tokens)

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
        cleaned = _strip_code_fence(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # A reply cut off at the token ceiling is still mostly-valid JSON.
            # Salvaging it beats throwing away a call that has already been
            # paid for — but only when the salvage itself parses.
            repaired = _repair_truncated_json(cleaned)
            if repaired is not None:
                self.tracer.note_warning(
                    f"{agent}/{purpose}: reply was truncated; recovered the "
                    f"complete portion (raise agents.{agent}.max_output_tokens)")
                return repaired
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

        # Two wire formats, because providers disagree about how a reasoning
        # model may call a function:
        #
        # * Responses API — tool turns are `function_call` / `function_call_output`
        #   items, NOT chat messages. OpenAI reasoning models require this path
        #   when `reasoning.effort` is set; Chat Completions rejects the
        #   combination outright ("Function tools with reasoning_effort are not
        #   supported ... use /v1/responses or set reasoning_effort to none").
        # * Chat Completions — what every self-hosted OpenAI-compatible server
        #   implements. Used for a custom base_url, or when `llm.api: chat`.
        #   There, `reasoning_effort` is dropped for tool calls rather than
        #   sending a request the server will refuse.
        if self._use_responses:
            return self._tool_loop_responses(agent, purpose, system, user, tools,
                                             dispatch, max_tool_calls, transcript)
        return self._tool_loop_chat(agent, purpose, system, user, tools,
                                    dispatch, max_tool_calls, transcript)

    # ---------------------------------------------------------- responses

    def _tool_loop_responses(self, agent, purpose, system, user, tools, dispatch,
                             max_tool_calls, transcript):
        """Tool loop over the Responses API.

        Each turn's output items are echoed back verbatim before the results are
        appended — including reasoning items, which the model needs in order to
        continue its own chain of thought across a tool call.
        """
        items: list[Any] = [{"role": "system", "content": system},
                            {"role": "user", "content": user}]
        schemas = [{"type": "function", **t["function"]} for t in tools]

        for _ in range(max_tool_calls):
            resp = self._responses_turn(agent, purpose, items, schemas)
            if resp is None:
                return None, transcript

            calls = [i for i in (getattr(resp, "output", None) or [])
                     if getattr(i, "type", None) == "function_call"]
            if not calls:
                return (getattr(resp, "output_text", "") or ""), transcript

            items.extend(_as_item(i) for i in (resp.output or []))
            for fc in calls:
                name = fc.name
                try:
                    args = json.loads(fc.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    result, error = dispatch(name, args), None
                except Exception as exc:
                    result, error = None, f"{type(exc).__name__}: {exc}"
                transcript.append({"tool": name, "args": args,
                                   "result": result, "error": error})
                items.append({
                    "type": "function_call_output",
                    "call_id": getattr(fc, "call_id", None) or getattr(fc, "id", ""),
                    "output": json.dumps({"error": error} if error else result,
                                         ensure_ascii=False,
                                         default=str)[:self.max_tool_result_chars],
                })

        # Out of tool budget: one last turn with no tools, to force a conclusion.
        resp = self._responses_turn(agent, purpose, items, None)
        return ((getattr(resp, "output_text", "") or "") if resp else None), transcript

    def _responses_turn(self, agent: str, purpose: str, items: list,
                        schemas: list | None):
        """One Responses API call, traced. Returns the raw response or None."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            kwargs: dict[str, Any] = {
                "model": self.model, "input": items,
                "max_output_tokens": self.output_budget(agent),
            }
            if self.reasoning_effort:
                kwargs["reasoning"] = {"effort": self.reasoning_effort}
            else:
                kwargs["temperature"] = self.temperature
            if schemas:
                kwargs["tools"] = schemas
            try:
                resp = self._client.responses.create(**kwargs)
                self.tracer.record_llm(
                    self._usage_from_responses(agent, purpose, resp, t0, attempt))
                return resp
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                self.tracer.record_llm(LLMCall(
                    agent=agent, purpose=purpose, model=self.model,
                    duration_s=time.perf_counter() - t0, ok=False,
                    error=last_error, retries=attempt))
                self.tracer.note_warning(
                    f"{agent}/{purpose}: tool call failed ({last_error}); "
                    f"falling back to the deterministic path")
                return None
        return None

    # ----------------------------------------------------- chat completions

    def _tool_loop_chat(self, agent, purpose, system, user, tools, dispatch,
                        max_tool_calls, transcript):
        # Chat Completions refuses `reasoning_effort` alongside function tools on
        # reasoning models, so it is dropped for the duration of the loop.
        previous_effort, self.reasoning_effort = self.reasoning_effort, None
        try:
            return self._tool_loop(agent, purpose, system, user, tools,
                                   dispatch, max_tool_calls, transcript)
        finally:
            self.reasoning_effort = previous_effort

    def _tool_loop(self, agent, purpose, system, user, tools, dispatch,
                   max_tool_calls, transcript):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        for _ in range(max_tool_calls):
            out = self._chat(agent, purpose, messages, tools=tools)
            if out is None:
                return None, transcript
            # _chat returns (text, tool_calls, assistant_message, LLMCall).
            text, tool_calls, raw_message, _call = out
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
                         max_output_tokens=max_output_tokens
                         or self.output_budget(agent))
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
                "role": "assistant", "content": text or "",
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
        # Never None: some servers reject a null assistant content outright.
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": text or ""}
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
        # Not part of the OpenAI usage payload today; read it if it ever appears
        # rather than guessing at cache-write volume.
        call.cache_write_tokens = int(
            getattr(in_details, "cache_creation_tokens", 0)
            or getattr(u, "cache_creation_input_tokens", 0) or 0)
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
        call.cache_write_tokens = int(
            getattr(in_details, "cache_creation_tokens", 0)
            or getattr(u, "cache_creation_input_tokens", 0) or 0)
        return call


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _as_item(item: Any) -> Any:
    """Normalize one Responses output item for echoing back as input."""
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(item, attr, None)
        if callable(fn):
            try:
                return fn(exclude_none=True) if attr == "model_dump" else fn()
            except TypeError:
                try:
                    return fn()
                except Exception:
                    break
            except Exception:
                break
    return item


def _repair_truncated_json(text: str) -> Any | None:
    """Recover the complete prefix of a JSON reply cut off at the token ceiling.

    Scans once to record every position where the parser is outside a string
    and inside at least one container — those are the only places a cut can be
    closed. Then tries them newest-first, closing the open brackets and
    parsing. The first candidate that parses wins; if none do, the reply is
    discarded and the caller falls back.

    Salvaging beats discarding here because the call has already been paid for
    and a long structured answer is usually complete except for its last item.
    """
    if not text or text[0] not in "{[":
        return None

    cuts: list[tuple[int, tuple[str, ...]]] = []
    stack: list[str] = []
    in_string = escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            if stack:
                cuts.append((i + 1, tuple(stack)))
        elif ch == ",":
            if stack:
                cuts.append((i, tuple(stack)))      # cut BEFORE the comma

    for index, open_stack in reversed(cuts):
        candidate = text[:index].rstrip().rstrip(",")
        candidate += "".join(reversed(open_stack))
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _looks_like_unsupported(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in (
        "unknown parameter", "unsupported parameter", "not supported",
        "no attribute 'responses'", "404", "unrecognized request argument",
    ))
