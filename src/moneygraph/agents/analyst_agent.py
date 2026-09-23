"""Analyst agent — natural-language questions over the graph (brief §8).

"Who collects money from these five?" becomes a sequence of calls to
`GraphTools`, and the answer is composed only from what those calls returned.
The viewer displays the tool transcript beside the answer, so every claim is
checkable in one glance.

Without an API key the same tools are exposed as a dropdown form, so the
feature degrades to "pick the function yourself" rather than disappearing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import LLMClient
from .tools import GraphTools, tool_schemas

SYSTEM = """You are an assistant to an AML analyst working on an anonymized transfer graph.

How you work:
- Answer ONLY from the output of the tools. If a tool did not return a fact, you do not have it. Never estimate, extrapolate or recall.
- Call tools before answering. If unsure of the dataset's scale, call dataset_overview first.
- Always cite the account identifiers (gids) your answer rests on.
- If the tools cannot answer, say exactly what is missing and which data request would close the gap.

Wording:
- These are hypotheses for verification, not findings of fact. Write "signs of", "pattern consistent with", "candidate for review".
- Never use: criminal, guilty, launderer, "organizer is", confirmed.
- The data is anonymized: no names, ages, genders, incomes or organizations exist. Never invent one.
- Be concise: a short paragraph, or a short list. The analyst is reading many of these."""


@dataclass
class Answer:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    cited_gids: list[int] = field(default_factory=list)
    deterministic: bool = False
    note: str = ""


def ask(question: str, tools: GraphTools, client: LLMClient, cfg: dict) -> Answer:
    """Answer one question. Falls back to a deterministic answer without a key."""
    acfg = (cfg.get("agents", {}) or {}).get("analyst", {}) or {}
    if not acfg.get("enabled", True) or not client.available:
        return _deterministic_answer(question, tools, client.disabled_reason)

    text, transcript = client.converse_with_tools(
        agent="analyst", purpose="question",
        system=SYSTEM, user=question,
        tools=tool_schemas(), dispatch=tools.dispatch,
        max_tool_calls=int(acfg.get("max_tool_calls", 8)),
    )
    if not text:
        fallback = _deterministic_answer(question, tools, "model call failed")
        fallback.tool_calls = transcript
        return fallback
    return Answer(text=text, tool_calls=transcript,
                  cited_gids=_extract_gids(text, tools))


def _extract_gids(text: str, tools: GraphTools) -> list[int]:
    """Gids mentioned in the answer that actually exist — so the viewer can
    turn them into links, and so an invented id is visibly dropped."""
    found = {int(m) for m in re.findall(r"\b\d{3,}\b", text)}
    return sorted(g for g in found if g in tools.nodes.index)


# ---------------------------------------------------------------------------
# deterministic fallback
# ---------------------------------------------------------------------------

def _deterministic_answer(question: str, tools: GraphTools, reason: str | None) -> Answer:
    """Best-effort answer with no model at all.

    Reads gids and a few keywords out of the question and calls the matching
    tool. Crude on purpose: it is a safety net, and the viewer also offers the
    tools directly as a form.
    """
    q = question.lower()
    gids = [int(g) for g in re.findall(r"\b\d{3,}\b", question)
            if int(g) in tools.nodes.index]
    note = (f"Answered without the model ({reason}). "
            f"Use the function form for full control.") if reason else ""

    if gids and any(k in q for k in ("collect", "common", "converge", "downstream", "above")):
        rows = tools.common_downstream(gids)
        if not rows:
            return Answer(text=f"No account downstream of all of {gids} within 2 hops.",
                          deterministic=True, note=note, cited_gids=gids)
        lines = [f"Accounts reachable from all of {gids} (candidates for review):"]
        lines += [f"- {r['gid']} — {r['role']}, priority {r['priority_score']:.3f}, "
                  f"{r['in_deg']} payers" for r in rows[:10]]
        return Answer(text="\n".join(lines), deterministic=True, note=note,
                      cited_gids=[r["gid"] for r in rows[:10]],
                      tool_calls=[{"tool": "common_downstream",
                                   "args": {"gids": gids}, "result": rows[:10]}])

    if gids and any(k in q for k in ("who pays", "payer", "sends to", "incoming", "from whom")):
        rows = tools.payers(gids)
        return Answer(text=_table("Payers", rows, "src"), deterministic=True,
                      note=note, cited_gids=gids,
                      tool_calls=[{"tool": "payers", "args": {"gids": gids}, "result": rows}])

    if gids and any(k in q for k in ("recipient", "sends", "outgoing", "pays to", "to whom")):
        rows = tools.recipients(gids)
        return Answer(text=_table("Recipients", rows, "dst"), deterministic=True,
                      note=note, cited_gids=gids,
                      tool_calls=[{"tool": "recipients", "args": {"gids": gids}, "result": rows}])

    if len(gids) >= 2 and any(k in q for k in ("path", "route", "between", "connect")):
        res = tools.path(gids[0], gids[1])
        if res.get("found"):
            hops = " -> ".join(str(h["src"]) for h in res["hops"]) + \
                   f" -> {res['hops'][-1]['dst']}"
            return Answer(text=f"Path in {res['n_hops']} hops: {hops}",
                          deterministic=True, note=note, cited_gids=gids,
                          tool_calls=[{"tool": "path", "result": res}])
        return Answer(text=f"No path found: {res.get('reason')}",
                      deterministic=True, note=note, cited_gids=gids)

    if gids:
        card = tools.node_card(gids[0])
        return Answer(text=json.dumps(card, indent=2, ensure_ascii=False),
                      deterministic=True, note=note, cited_gids=gids[:1],
                      tool_calls=[{"tool": "node_card", "args": {"gid": gids[0]},
                                   "result": card}])

    rows = tools.top_nodes(10)
    lines = ["Top accounts by priority:"]
    lines += [f"- {r['gid']} — {r['role']}, priority {r['priority_score']:.3f}. "
              f"{r['evidence']}" for r in rows]
    return Answer(text="\n".join(lines), deterministic=True, note=note,
                  cited_gids=[r["gid"] for r in rows],
                  tool_calls=[{"tool": "top_nodes", "args": {"n": 10}, "result": rows}])


def _table(title: str, rows: list[dict], col: str) -> str:
    if not rows:
        return f"{title}: none found."
    lines = [f"{title}:"]
    for r in rows[:15]:
        lines.append(f"- {int(r[col])} — {r.get('role', '?')}, "
                     f"{float(r['sum_kzt']):,.0f} KZT over {int(r['n_tx'])} transfer(s)")
    return "\n".join(lines)
