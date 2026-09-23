"""Investigator agent — builds a case dossier for one priority account.

The rule engine says *what* an account is. This agent works out *what is going
on around it*: it pulls the payers, the recipients, the timing, the paths back
to seeds and the cluster context, then writes the short brief an analyst would
otherwise assemble by hand over an afternoon.

It is a genuine multi-step agent — it decides which tools to call and in what
order, and the transcript of those calls is kept beside its conclusion, so
nothing it writes is unverifiable. It cannot change a role, a score or a rank;
its output is an extra `dossier` artifact and a `next_step` recommendation.
"""

from __future__ import annotations

import json
from typing import Any

from .base import WORDING_RULES, Agent
from .tools import tool_schemas

SYSTEM = f"""You are an AML analyst investigating one account in an anonymized transfer network.

Work like an investigator:
1. Start from the account's card, which already contains its rule-assigned role and metrics.
2. Use the tools to establish context: who pays it, who it pays, whether the money moves on quickly, how it connects back to the known seed accounts, what its cluster looks like.
3. Stop as soon as you can answer the questions below. Do not call tools you do not need.

Then answer with JSON only:
{{"summary": "<2-3 sentences: what this account looks like structurally and why it is on the review list>",
  "pattern": "<one short label, e.g. 'multi-payer collection point', 'fast pass-through', 'frontier collector'>",
  "supporting_gids": [<the accounts your reading rests on>],
  "alternative_explanation": "<the most plausible innocent explanation for this pattern, given only structure and amounts>",
  "next_step": "<the single most useful thing the analyst should do or request next>",
  "confidence": "low" | "medium" | "high"}}

Rules:
- Every factual claim must come from a tool result. If a tool did not tell you, you do not know it.
- `alternative_explanation` is mandatory and must be genuine. A salary account, a merchant settling with suppliers and a collection point can look identical in this data. Say so when it is true.
- Keep `summary` under 400 characters.

{WORDING_RULES}"""


class InvestigatorAgent(Agent):
    name = "investigator"
    role = "build a case dossier for one priority account"
    system = SYSTEM
    max_steps = 6

    def tool_schemas(self) -> list[dict] | None:
        return tool_schemas()

    def build_task(self, context: dict) -> str:
        gid = context["gid"]
        card = self.tools.node_card(gid)
        return json.dumps({
            "account_under_review": gid,
            "rule_engine_verdict": {
                "role": card.get("role"),
                "role_score": card.get("role_score"),
                "rule_that_fired": context.get("gate"),
                "metrics_the_rule_used": context.get("metrics"),
                "evidence_sentence": card.get("evidence"),
            },
            "card": card,
            "rank_in_priority_list": context.get("rank"),
            "question": "Establish the structural context of this account and "
                        "what the analyst should do next.",
        }, ensure_ascii=False, indent=2, default=str)

    def validate(self, output: Any, context: dict) -> tuple[bool, str]:
        if not isinstance(output, dict):
            return False, "not an object"
        for field in ("summary", "pattern", "alternative_explanation", "next_step"):
            if not str(output.get(field, "")).strip():
                return False, f"missing `{field}`"
        if len(str(output["summary"])) > 600:
            return False, "summary too long"

        blob = " ".join(str(output.get(k, "")) for k in
                        ("summary", "pattern", "alternative_explanation", "next_step")).lower()
        forbidden = self.cfg["evidence"]["forbidden_words"]
        hits = [w for w in forbidden if w.lower() in blob]
        if hits:
            return False, f"forbidden wording {hits}"

        # Cited accounts must exist. An invented gid invalidates the dossier.
        cited = output.get("supporting_gids") or []
        if isinstance(cited, list):
            unknown = [g for g in cited
                       if not isinstance(g, int) or g not in self.tools.nodes.index]
            if unknown:
                return False, f"cites accounts not in the dataset: {unknown[:5]}"
        if str(output.get("confidence", "")).lower() not in ("low", "medium", "high", ""):
            return False, "confidence must be low, medium or high"
        return True, "ok"

    def fallback(self, context: dict) -> Any:
        """A dossier assembled deterministically from the same tools."""
        gid = context["gid"]
        card = self.tools.node_card(gid)
        payers = self.tools.payers([gid])[:5]
        recipients = self.tools.recipients([gid])[:5]
        role = card.get("role", "peripheral")

        pattern = {
            "consolidator": "multi-payer collection point",
            "distributor": "fan-out distribution",
            "transit": "pass-through account",
            "terminal": "funds retained",
            "coordinator": "convergence point",
            "cutoff": "traversal frontier — onward flow unknown",
        }.get(role, "no dominant pattern")

        summary = (f"Account {gid} is classified {role} "
                   f"(confidence {card.get('role_score')}). It received "
                   f"{card.get('in_sum_kzt', 0):,.0f} KZT from "
                   f"{card.get('in_deg')} payer(s) and sent "
                   f"{card.get('out_sum_kzt', 0):,.0f} KZT to "
                   f"{card.get('out_deg')} recipient(s). "
                   f"{card.get('seed_reach')} seed account(s) can reach it.")

        if not card.get("outflow_observed", True):
            next_step = (f"Request outgoing transfers for {gid} beyond the export "
                         f"depth — its onward flow was never traced.")
        elif role in ("consolidator", "coordinator"):
            next_step = (f"Review the {card.get('in_deg')} payers of {gid} for a "
                         f"common origin, and request inflows from outside the sample.")
        else:
            next_step = f"Request transfers below the reporting threshold for {gid}."

        return {
            "summary": summary,
            "pattern": pattern,
            "supporting_gids": [int(p["src"]) for p in payers]
                               + [int(r["dst"]) for r in recipients],
            "alternative_explanation": _innocent(role),
            "next_step": next_step,
            "confidence": "low",
            "source": "deterministic (no model)",
        }


def _innocent(role: str) -> str:
    return {
        "consolidator": "A legitimate collection account — a landlord, a small "
                        "wholesaler settling with customers, or a shared household "
                        "account — produces the same many-payers shape.",
        "distributor": "A payroll or supplier-payment account fans out to many "
                       "recipients in exactly this way.",
        "transit": "A personal account that forwards money to family shortly "
                   "after receiving salary shows the same balanced fast flow.",
        "terminal": "Money simply being saved or spent outside the bank produces "
                    "the same retained balance.",
        "coordinator": "A common service provider paid by many unrelated parties "
                       "would also show convergence from several chains.",
        "cutoff": "Nothing is known about this account's onward behaviour; the "
                  "pattern may disappear entirely once it is traced.",
    }.get(role, "Ordinary personal activity produces this shape.")
