"""Ingest agent — resolves input columns the deterministic matcher could not.

This is the one place where an agent touches the data itself, and it is safe
because of two properties:

* it only ever proposes a **column name**, never a value, a role or a score;
* whatever it proposes is re-validated against the data by
  `schema.validate_mapping` before being accepted. A wrong guess is rejected
  and the field stays unresolved, which surfaces as a clear error naming the
  file and its columns.

With the organizers' three parquet files the alias matcher resolves everything,
`only_when_ambiguous` is true, and this agent costs nothing because it is never
called. It exists for the input the analyst actually has.
"""

from __future__ import annotations

import json

from ..schema import (
    CANONICAL_FIELDS,
    FileProfile,
    classify,
    unresolved_fields,
    validate_mapping,
)
from .llm import LLMClient

SYSTEM = """You map columns of a financial transfer export onto a fixed schema.

Canonical fields:
  src      payer / sender account id (integer)
  dst      recipient account id (integer)
  amount   transferred amount, positive number
  n_tx     number of individual transfers aggregated into one row
  date     date of the transfer
  gid      account id, on a file that lists accounts rather than transfers
  depth    traversal hop at which the account was discovered
  is_seed  boolean: the account was one of the starting points

Rules:
- Answer with JSON only: {"mapping": {"<canonical>": "<exact column name>"}, "unmapped": ["..."], "confidence": 0.0-1.0, "reasoning": "one sentence"}
- Use the EXACT column names given to you. Never invent one.
- Map a field only if you are confident. Leaving it out is correct and safe;
  a wrong mapping corrupts every downstream figure.
- Never map two canonical fields to the same column.
"""


def resolve_with_agent(
    profile: FileProfile, client: LLMClient, cfg: dict
) -> tuple[bool, str]:
    """Try to fill the gaps in `profile.mapping`. Returns (changed, note)."""
    acfg = (cfg.get("agents", {}) or {}).get("ingest", {}) or {}
    if not acfg.get("enabled", True):
        return False, "ingest agent disabled in config"
    if not client.available:
        return False, f"ingest agent unavailable: {client.disabled_reason}"

    missing = unresolved_fields(profile)
    if acfg.get("only_when_ambiguous", True) and not missing:
        return False, "nothing ambiguous — matcher resolved every field"

    already = set(profile.mapping.values())
    payload = {
        "file": profile.path.name,
        "row_count": profile.n_rows,
        "columns": profile.describe()["columns"],
        "already_mapped": profile.mapping,
        "still_needed": missing or [f for f in CANONICAL_FIELDS if f not in profile.mapping],
    }
    answer = client.complete_json(
        agent="ingest",
        purpose=f"map columns of {profile.path.name}",
        system=SYSTEM,
        user=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    if not isinstance(answer, dict) or not isinstance(answer.get("mapping"), dict):
        return False, "ingest agent returned nothing usable; matcher result kept"

    proposed, rejected = {}, []
    for canonical, col in answer["mapping"].items():
        if canonical not in CANONICAL_FIELDS:
            rejected.append(f"{canonical} (not a canonical field)")
        elif col not in profile.columns:
            rejected.append(f"{canonical}->{col} (no such column)")
        elif col in already:
            rejected.append(f"{canonical}->{col} (column already used)")
        elif canonical in profile.mapping:
            rejected.append(f"{canonical} (already resolved by the matcher)")
        else:
            proposed[canonical] = col
            already.add(col)

    if not proposed:
        return False, f"ingest agent proposed nothing acceptable ({'; '.join(rejected) or 'empty'})"

    # Accept provisionally, then validate against the data and roll back if bad.
    backup = dict(profile.mapping), dict(profile.resolved_by)
    profile.mapping.update(proposed)
    for k in proposed:
        profile.resolved_by[k] = "agent"
    classify(profile)
    problems = validate_mapping(profile)
    if problems:
        profile.mapping, profile.resolved_by = backup
        classify(profile)
        return False, f"ingest agent mapping rejected by validation: {problems[0]}"

    note = f"ingest agent resolved {', '.join(f'{k}->{v}' for k, v in proposed.items())}"
    if rejected:
        note += f" (rejected: {'; '.join(rejected)})"
    return True, note
