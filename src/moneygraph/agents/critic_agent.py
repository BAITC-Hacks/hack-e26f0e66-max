"""Critic agent — argues against the shortlist before the analyst sees it.

A prioritization tool that only ever agrees with itself is how an analyst ends
up spending a week on a payroll account. This agent is given the top findings
and the thresholds that produced them, and is asked to attack them: which
entries are artifacts of how the data was collected, which thresholds are doing
suspicious work, what is conspicuously missing.

It cannot demote anything. Its output is an advisory `review_notes.md` and a
per-node caveat shown in the viewer, so the analyst gets the counter-argument
at the same moment as the recommendation.

This is also where the brief's "no ground truth" constraint is handled
honestly: with nothing to validate against, a written challenge to the method
is the closest thing to a check that exists.
"""

from __future__ import annotations

import json
from typing import Any

from .base import WORDING_RULES, Agent

SYSTEM = f"""You are a senior reviewer auditing another analyst's prioritized list of accounts for review. Your job is to find what is wrong with it.

You are given: the thresholds that produced the roles, how the export was collected and its known limitations, and the top-ranked accounts with the rule that fired for each.

Attack the list on these axes:
- **Collection artifacts.** Which entries rank highly because of how the data was gathered rather than because of behaviour? The export follows outgoing transfers only, from a fixed set of starting accounts, to a fixed depth, above an amount threshold. Each of those creates predictable false signals.
- **Threshold sensitivity.** Which conclusions would change if a threshold moved by one step? Name the threshold and the accounts affected.
- **Alternative explanations.** Which patterns have an ordinary explanation that fits the same numbers?
- **Blind spots.** What would you expect to see in a real network of this kind that is absent here, and what would explain the absence?

Answer with JSON only:
{{"artifacts": [{{"gids": [...], "concern": "...", "severity": "low"|"medium"|"high"}}],
  "threshold_risks": [{{"threshold": "<dotted.key>", "concern": "...", "affected_gids": [...]}}],
  "blind_spots": ["..."],
  "verdict": "<2-3 sentences: how much weight the analyst should put on this list>"}}

Rules:
- Every `gids` entry must be an account you were actually shown.
- Be specific. "The data is limited" is not a finding; "accounts 1, 2 and 3 rank highly only because they sit at the traversal frontier, where outflow is unknown by construction" is.
- If the list looks sound on some axis, say so rather than inventing a concern.

{WORDING_RULES}"""


class CriticAgent(Agent):
    name = "critic"
    role = "challenge the priority list and the thresholds behind it"
    system = SYSTEM

    def build_task(self, context: dict) -> str:
        return json.dumps({
            "how_the_export_was_collected": {
                "starting_accounts": context["n_seeds"],
                "direction": "outgoing transfers only",
                "max_depth": context["max_depth"],
                "amount_floor_kzt": context.get("amount_floor"),
                "period": context.get("period"),
                "known_limitations": [
                    f"{context['n_frontier']} accounts sit at max depth; their "
                    f"onward flow was never requested, so it is unknown, not zero",
                    "inflows to the starting accounts from outside the sample are absent",
                    f"transfers below the amount floor were excluded entirely",
                    "no customer attributes of any kind are available",
                    "there are no labelled roles to validate against",
                ],
            },
            "thresholds_in_use": context["thresholds"],
            "role_counts": context["role_counts"],
            "top_findings": context["findings"],
        }, ensure_ascii=False, indent=2, default=str)

    def validate(self, output: Any, context: dict) -> tuple[bool, str]:
        if not isinstance(output, dict):
            return False, "not an object"
        if not str(output.get("verdict", "")).strip():
            return False, "missing verdict"

        known = {int(f["gid"]) for f in context["findings"]}
        for entry in (output.get("artifacts") or []):
            if not isinstance(entry, dict):
                return False, "malformed artifacts entry"
            unknown = [g for g in (entry.get("gids") or []) if int(g) not in known]
            if unknown:
                return False, f"cites accounts it was not shown: {unknown[:5]}"
            if not str(entry.get("concern", "")).strip():
                return False, "artifact entry without a concern"

        valid_keys = set(context["thresholds"])
        for entry in (output.get("threshold_risks") or []):
            key = str(entry.get("threshold", ""))
            if key and key not in valid_keys:
                return False, f"unknown threshold '{key}'"

        blob = json.dumps(output, ensure_ascii=False).lower()
        hits = [w for w in self.cfg["evidence"]["forbidden_words"] if w.lower() in blob]
        if hits:
            return False, f"forbidden wording {hits}"
        return True, "ok"

    def fallback(self, context: dict) -> Any:
        """The structural critiques that follow from the export's design alone —
        they hold whether or not a model is available."""
        findings = context["findings"]
        frontier = [int(f["gid"]) for f in findings if f.get("at_frontier")]
        seeds = [int(f["gid"]) for f in findings if f.get("is_seed")]
        thin = [int(f["gid"]) for f in findings if int(f.get("in_deg", 0)) <= 1]

        artifacts = []
        if frontier:
            artifacts.append({
                "gids": frontier, "severity": "high",
                "concern": "These accounts sit at the traversal frontier. Their "
                           "onward transfers were never requested, so any reading "
                           "of 'money stops here' is unsupported — the pattern may "
                           "vanish once they are expanded.",
            })
        if seeds:
            artifacts.append({
                "gids": seeds, "severity": "medium",
                "concern": "Known starting accounts. Their inflows from outside "
                           "the sample are missing, so every ratio computed for "
                           "them is understated, and law enforcement already has them.",
            })
        if thin:
            artifacts.append({
                "gids": thin, "severity": "medium",
                "concern": "Ranked largely on attributed seed money rather than on "
                           "structure. Attribution is a heuristic that assumes "
                           "proportional forwarding; a single large transfer can "
                           "carry an account up the list.",
            })

        return {
            "artifacts": artifacts,
            "threshold_risks": [{
                "threshold": "terminal.max_pass",
                "concern": "The terminal gate matches any account that forwards "
                           "little, which includes most leaves that simply had "
                           "nothing above the reporting floor leaving them. The "
                           "role is correct but nearly uninformative.",
                "affected_gids": [int(f["gid"]) for f in findings
                                  if f.get("role") == "terminal"],
            }],
            "blind_spots": [
                "Structuring below the reporting floor is invisible by construction.",
                "Only one month and one bank: a recurring structure cannot be "
                "distinguished from a single month's coincidence.",
                "No account attributes, so a merchant, a payroll account and a "
                "collection point are indistinguishable on structure alone.",
            ],
            "verdict": "Treat the list as a reading order, not as a set of "
                       "conclusions. The ranking is defensible on structure, but "
                       "nothing here is validated against a known outcome, and "
                       "several high-ranked entries are explained by how the "
                       "export was collected.",
            "source": "deterministic (no model)",
        }


def render_review_notes(critique: dict, context: dict) -> str:
    """`review_notes.md` — the counter-argument, in the analyst's hands."""
    md = ["# Review notes: what is wrong with this list", "",
          "Written against the priority list, not in support of it. "
          "Read it before acting on the rankings.", "",
          "## Verdict", "", str(critique.get("verdict", "")).strip(), ""]

    artifacts = critique.get("artifacts") or []
    if artifacts:
        md += ["## Entries that may be collection artifacts", ""]
        for a in artifacts:
            gids = ", ".join(str(g) for g in (a.get("gids") or [])[:15])
            sev = str(a.get("severity", "")).upper()
            md += [f"**{sev}** — accounts {gids}", "", f"> {a.get('concern')}", ""]

    risks = critique.get("threshold_risks") or []
    if risks:
        md += ["## Thresholds carrying more weight than they should", ""]
        for r in risks:
            md += [f"**`{r.get('threshold')}`** — {r.get('concern')}"]
            affected = r.get("affected_gids") or []
            if affected:
                md += ["", f"Affects {len(affected)} of the listed accounts: "
                           f"{', '.join(str(g) for g in affected[:15])}"]
            md.append("")

    spots = critique.get("blind_spots") or []
    if spots:
        md += ["## Blind spots", ""] + [f"- {s}" for s in spots] + [""]

    if critique.get("source"):
        md += ["---", "", f"_Generated {critique['source']}._"]
    return "\n".join(md) + "\n"
