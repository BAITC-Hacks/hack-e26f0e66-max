"""Pipeline orchestration (guideline §5). Orchestration only — no logic here.

Phase 0 wires up loading, config and profiling. The remaining stages are listed
in ``STAGES`` and are filled in during Phase 1; each one is a pure
DataFrame-in / DataFrame-out function living in its own module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .io import load_config, load_dataset

# The full stage list, in order. Modules marked "phase 1" do not exist yet;
# the pipeline runs the implemented prefix and reports the rest as pending.
STAGES = [
    ("profile", "moneygraph.profile"),
    ("graph", "moneygraph.graph"),
    ("features", "moneygraph.features"),
    ("temporal", "moneygraph.temporal"),
    ("attribution", "moneygraph.attribution"),
    ("roles", "moneygraph.roles"),
    ("clustering", "moneygraph.clustering"),
    ("priority", "moneygraph.priority"),
    ("evidence", "moneygraph.evidence"),
    ("export", "moneygraph.export"),
]


@dataclass
class Timing:
    """Per-stage wall clock, printed at the end of every run."""

    marks: list[tuple[str, float]] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter)

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        elapsed = now - (self.marks[-1][1] if self.marks else self._t0)
        self.marks.append((stage, now))
        print(f"[{stage:>12}] {elapsed:6.2f}s")

    @property
    def total(self) -> float:
        return (self.marks[-1][1] if self.marks else time.perf_counter()) - self._t0

    def report(self) -> None:
        print(f"[{'TOTAL':>12}] {self.total:6.2f}s")


def run(data_dir: str | Path, out_dir: str | Path, config_path: str | Path) -> int:
    """Run every implemented stage. Returns a process exit code."""
    t = Timing()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config(config_path)
    ds = load_dataset(data_dir)
    t.mark("load")
    print(f"             {len(ds.nodes)} nodes, {len(ds.edges)} edges, "
          f"{len(ds.tx)} transactions, MAX_DEPTH={ds.max_depth}")

    from .profile import profile

    report, _flows = profile(ds)
    (out_dir / "profile_report.md").write_text(report.render(), encoding="utf-8")
    t.mark("profile")
    if report.mismatches:
        print(f"             WARNING: {len(report.mismatches)} announced fact(s) "
              f"do not reproduce — see {out_dir / 'profile_report.md'} §8")

    pending = [name for name, mod in STAGES[1:] if not _module_exists(mod)]
    if pending:
        print()
        print("Pending stages (guideline §17, phase 1): " + ", ".join(pending))
        print("The three CSVs are not written yet.")

    print()
    t.report()
    # Hard constraint: the whole run must stay well under 5 minutes.
    assert t.total < 300, f"pipeline took {t.total:.1f}s, budget is 300s"
    _ = cfg
    return 0


def _module_exists(dotted: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(dotted) is not None
    except ModuleNotFoundError:
        return False
