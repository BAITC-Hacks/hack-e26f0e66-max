"""Discover input files and map their columns onto the canonical schema.

The brief promises three parquet files, but a tool an analyst can actually use
must accept whatever export they happen to have. This module turns an arbitrary
folder of tabular files into the canonical triple the rest of the pipeline
expects:

    edges         src, dst, sum_kzt, n_tx[, depth]     aggregated pairs
    transactions  src, dst, date, sum_kzt              individual transfers
    nodes         gid, depth, is_seed                  the node list

Resolution order, cheapest and most reliable first:

1. **Alias matching** — `config.yaml -> input.aliases`, normalized for case,
   underscores, hyphens and spaces. Resolves the organizers' files outright.
2. **Structural inference** — a column of integers that overlaps the node id
   space is an endpoint; a datetime column is the date; the float column with
   the widest range is the amount.
3. **The ingest agent** — only for fields still unresolved, and only when
   `agents.ingest.enabled`. Its answer is *validated against the data* before
   it is accepted, so a wrong guess is rejected rather than propagated.

Anything still unresolved after all three is reported as a hard error naming
the file and its columns, because guessing an amount column silently would
corrupt every downstream number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

CANONICAL_FIELDS = ["src", "dst", "amount", "n_tx", "date", "gid", "depth", "is_seed"]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


@dataclass
class FileProfile:
    """What we know about one input file before deciding what it is."""

    path: Path
    columns: list[str]
    dtypes: dict[str, str]
    n_rows: int
    sample: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    mapping: dict[str, str] = field(default_factory=dict)   # canonical -> column
    kind: str = "unknown"                                   # edges|transactions|nodes|unknown
    resolved_by: dict[str, str] = field(default_factory=dict)  # canonical -> alias|structure|agent

    def describe(self) -> dict[str, Any]:
        return {
            "file": self.path.name,
            "rows": self.n_rows,
            "columns": [
                {"name": c, "dtype": self.dtypes.get(c, "?"),
                 "examples": _examples(self.sample, c)}
                for c in self.columns
            ],
        }


def _examples(sample: pd.DataFrame, col: str, k: int = 3) -> list[str]:
    if col not in sample.columns or sample.empty:
        return []
    vals = sample[col].dropna().unique()[:k]
    return [str(v)[:40] for v in vals]


# --------------------------------------------------------------------------- 
# discovery
# ---------------------------------------------------------------------------

READERS = {
    ".parquet": lambda p, n: pd.read_parquet(p),
    ".csv": lambda p, n: pd.read_csv(p),
    ".tsv": lambda p, n: pd.read_csv(p, sep="\t"),
    ".json": lambda p, n: pd.read_json(p),
    ".jsonl": lambda p, n: pd.read_json(p, lines=True),
    ".xlsx": lambda p, n: pd.read_excel(p),
}


def discover_files(data_dir: str | Path, cfg: dict) -> list[Path]:
    """Every tabular file under `data_dir`, in a deterministic order."""
    icfg = cfg.get("input", {}) or {}
    exts = [e.lower() for e in icfg.get("extensions", [".parquet", ".csv"])]
    data_dir = Path(data_dir)
    if data_dir.is_file():
        return [data_dir]
    if not data_dir.exists():
        raise FileNotFoundError(f"input folder not found: {data_dir}")
    pattern = "**/*" if icfg.get("recursive", True) else "*"
    found = [
        p for p in sorted(data_dir.glob(pattern))
        if p.is_file() and p.suffix.lower() in exts and not p.name.startswith(".")
    ]
    # Preference order follows `extensions`, then path, for determinism.
    found.sort(key=lambda p: (exts.index(p.suffix.lower()), str(p)))
    return found[: int(icfg.get("max_files", 32))]


def profile_file(path: Path, sample_rows: int) -> FileProfile:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"no reader for {path.suffix}")
    df = reader(path, sample_rows)
    return FileProfile(
        path=path,
        columns=[str(c) for c in df.columns],
        dtypes={str(c): str(df[c].dtype) for c in df.columns},
        n_rows=len(df),
        sample=df.head(sample_rows).copy(),
    )


# ---------------------------------------------------------------------------
# step 1 — alias matching
# ---------------------------------------------------------------------------

def match_by_alias(profile: FileProfile, aliases: dict[str, list[str]]) -> None:
    """Fill `profile.mapping` from the alias table. Exact matches only."""
    lookup: dict[str, str] = {}
    for canonical, names in aliases.items():
        for name in names:
            lookup.setdefault(_norm(name), canonical)
    taken: set[str] = set()
    for col in profile.columns:
        canonical = lookup.get(_norm(col))
        if canonical and canonical not in profile.mapping and col not in taken:
            profile.mapping[canonical] = col
            profile.resolved_by[canonical] = "alias"
            taken.add(col)


# ---------------------------------------------------------------------------
# step 2 — structural inference
# ---------------------------------------------------------------------------

def infer_by_structure(profile: FileProfile) -> None:
    """Resolve what the aliases missed, using dtypes and value shapes.

    Deliberately conservative: it only fills a field when exactly one column is
    a plausible candidate. Ambiguity is left for the agent, which has the
    column names and examples to reason about.
    """
    df, mapped = profile.sample, set(profile.mapping.values())
    free = [c for c in profile.columns if c not in mapped]
    if df.empty:
        return

    def claim(canonical: str, col: str) -> None:
        profile.mapping[canonical] = col
        profile.resolved_by[canonical] = "structure"
        mapped.add(col)

    # date: the single datetime-like column
    if "date" not in profile.mapping:
        cands = [c for c in free if c in df.columns
                 and (pd.api.types.is_datetime64_any_dtype(df[c]) or _parses_as_date(df[c]))]
        if len(cands) == 1:
            claim("date", cands[0])

    # boolean seed flag: the single bool column
    if "is_seed" not in profile.mapping:
        cands = [c for c in free if c in df.columns and c not in mapped
                 and pd.api.types.is_bool_dtype(df[c])]
        if len(cands) == 1:
            claim("is_seed", cands[0])

    # endpoints: integer columns sharing an id space
    int_cols = [c for c in profile.columns if c not in mapped and c in df.columns
                and pd.api.types.is_integer_dtype(df[c])]
    if "src" not in profile.mapping and "dst" not in profile.mapping and len(int_cols) >= 2:
        best = _best_endpoint_pair(df, int_cols)
        if best:
            claim("src", best[0])
            claim("dst", best[1])

    # amount: the single float column, or the widest-range numeric one
    if "amount" not in profile.mapping:
        cands = [c for c in profile.columns if c not in mapped and c in df.columns
                 and pd.api.types.is_numeric_dtype(df[c])]
        floats = [c for c in cands if pd.api.types.is_float_dtype(df[c])]
        pick = floats[0] if len(floats) == 1 else (
            max(cands, key=lambda c: float(df[c].max() or 0)) if cands else None)
        if pick is not None and float(df[pick].max() or 0) > 0:
            claim("amount", pick)

    # gid: on a node-shaped file, the unique integer key
    if "gid" not in profile.mapping and "src" not in profile.mapping:
        cands = [c for c in profile.columns if c not in mapped and c in df.columns
                 and pd.api.types.is_integer_dtype(df[c]) and df[c].is_unique]
        if len(cands) == 1:
            claim("gid", cands[0])


def _parses_as_date(s: pd.Series) -> bool:
    if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return False
    head = s.dropna().head(20)
    if head.empty:
        return False
    try:
        pd.to_datetime(head, errors="raise")
        return True
    except (ValueError, TypeError):
        return False


def _best_endpoint_pair(df: pd.DataFrame, cols: list[str]) -> tuple[str, str] | None:
    """The integer pair whose value sets overlap most — payer and recipient
    draw from the same id space, unlike an id and a count."""
    best, best_score = None, 0.0
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            sa, sb = set(df[a].dropna()), set(df[b].dropna())
            if not sa or not sb:
                continue
            score = len(sa & sb) / len(sa | sb)
            if score > best_score:
                best, best_score = (a, b), score
    # Endpoints that never share a value are not endpoints.
    return best if best_score > 0.01 else None


# ---------------------------------------------------------------------------
# step 3 — classification and validation
# ---------------------------------------------------------------------------

def classify(profile: FileProfile) -> str:
    """Decide what the file is from which canonical fields it carries."""
    m = profile.mapping
    has_pair = "src" in m and "dst" in m
    if has_pair and "date" in m:
        profile.kind = "transactions"
    elif has_pair:
        profile.kind = "edges"
    elif "gid" in m:
        profile.kind = "nodes"
    else:
        profile.kind = "unknown"
    return profile.kind


def validate_mapping(profile: FileProfile) -> list[str]:
    """Check a mapping against the data. Returns human-readable problems."""
    problems: list[str] = []
    df, m = profile.sample, profile.mapping
    if df.empty:
        return [f"{profile.path.name}: file is empty"]

    for fld in ("src", "dst", "gid"):
        col = m.get(fld)
        if col and not pd.api.types.is_integer_dtype(df[col]):
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.isna().mean() > 0.01:
                problems.append(
                    f"{profile.path.name}: column '{col}' mapped to `{fld}` is not "
                    f"an integer id ({df[col].dtype})")

    amount = m.get("amount")
    if amount:
        vals = pd.to_numeric(df[amount], errors="coerce")
        if vals.isna().mean() > 0.01:
            problems.append(f"{profile.path.name}: '{amount}' mapped to `amount` is not numeric")
        elif (vals.dropna() < 0).mean() > 0.5:
            problems.append(f"{profile.path.name}: '{amount}' mapped to `amount` is mostly negative")

    date = m.get("date")
    if date:
        try:
            pd.to_datetime(df[date].dropna().head(50), errors="raise")
        except (ValueError, TypeError):
            problems.append(f"{profile.path.name}: '{date}' mapped to `date` does not parse as a date")

    if profile.kind == "edges" and m.get("src") and m.get("dst"):
        if df[m["src"]].equals(df[m["dst"]]):
            problems.append(f"{profile.path.name}: `src` and `dst` map to identical data")

    return problems


def unresolved_fields(profile: FileProfile) -> list[str]:
    """Canonical fields this file plausibly holds but we could not resolve."""
    m = profile.mapping
    n_unmapped = len([c for c in profile.columns if c not in set(m.values())])
    if n_unmapped == 0:
        return []
    missing = []
    if "src" in m and "dst" in m:
        if "amount" not in m:
            missing.append("amount")
        if "date" not in m and profile.n_rows > 0:
            missing.append("date")       # optional: absence just means "aggregated"
    elif "gid" in m:
        for fld in ("depth", "is_seed"):
            if fld not in m:
                missing.append(fld)
    else:
        missing += [f for f in ("src", "dst", "gid") if f not in m]
    return missing
