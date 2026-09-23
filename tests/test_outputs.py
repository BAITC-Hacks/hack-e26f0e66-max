"""Output contract tests (guideline §15).

The CSV tests skip while the pipeline is still being built and become real the
moment `outputs/nodes_roles.csv` exists. Everything that can be checked today —
the input contract, the config contract, determinism of loading, the wording
blacklist — runs now.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
CONFIG = ROOT / "config.yaml"

ALLOWED_ROLES = {
    "consolidator", "transit", "distributor",
    "terminal", "coordinator", "peripheral", "cutoff",
}
NODES_ROLES_COLUMNS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
CLUSTERS_COLUMNS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
TOP_COLUMNS = ["rank", "gid", "role", "priority_score", "why"]

N_NODES = 2248
N_SEEDS = 81


# --------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def cfg():
    from moneygraph.io import load_config

    return load_config(CONFIG)


@pytest.fixture(scope="session")
def dataset():
    from moneygraph.io import load_dataset

    return load_dataset(ROOT / "data")


def _read(name: str) -> pd.DataFrame:
    path = OUT / name
    if not path.exists():
        pytest.skip(f"{name} not generated yet (pipeline phase 1)")
    return pd.read_csv(path)


@pytest.fixture
def nodes_roles():
    return _read("nodes_roles.csv")


@pytest.fixture
def clusters():
    return _read("clusters.csv")


@pytest.fixture
def top_nodes():
    return _read("top_nodes.csv")


# ------------------------------------------------------ input contract

def test_input_volumes(dataset):
    assert len(dataset.nodes) == N_NODES
    assert len(dataset.edges) == 3119
    assert len(dataset.tx) == 4840
    assert int(dataset.nodes.is_seed.sum()) == N_SEEDS


def test_max_depth_is_read_not_assumed(dataset):
    assert dataset.max_depth == int(dataset.nodes.depth.max())


def test_loading_is_deterministic():
    from moneygraph.io import load_dataset

    a, b = load_dataset(ROOT / "data"), load_dataset(ROOT / "data")
    pd.testing.assert_frame_equal(a.nodes, b.nodes)
    pd.testing.assert_frame_equal(a.edges, b.edges)
    pd.testing.assert_frame_equal(a.tx, b.tx)


# ----------------------------------------------------- config contract

def test_priority_weights_sum_to_one(cfg):
    assert abs(sum(cfg["priority"]["weights"].values()) - 1.0) < 1e-9


def test_every_role_has_a_priority_weight(cfg):
    assert set(cfg["priority"]["role_weight"]) == ALLOWED_ROLES


def test_top_n_meets_the_minimum(cfg):
    assert cfg["priority"]["top_n"] >= 20


# ------------------------------------------------- nodes_roles.csv (§15)

def test_nodes_roles_shape_and_columns(nodes_roles):
    assert list(nodes_roles.columns)[:6] == NODES_ROLES_COLUMNS
    assert len(nodes_roles) == N_NODES
    assert nodes_roles.gid.is_unique


def test_nodes_roles_has_no_nulls(nodes_roles):
    assert not nodes_roles[NODES_ROLES_COLUMNS].isnull().any().any()


def test_roles_are_in_the_allowed_set(nodes_roles):
    assert set(nodes_roles.role) <= ALLOWED_ROLES


def test_scores_are_in_range(nodes_roles):
    for col in ("role_score", "priority_score"):
        assert nodes_roles[col].between(0, 1).all(), col


def test_evidence_is_present_and_bounded(nodes_roles, cfg):
    ev = nodes_roles.evidence.astype(str)
    assert (ev.str.strip() != "").all()
    assert (ev.str.len() <= cfg["evidence"]["max_chars"]).all()


def test_evidence_contains_numbers_not_adjectives(nodes_roles):
    """The organizers check this explicitly: evidence must quote metrics."""
    ev = nodes_roles.evidence.astype(str)
    assert ev.str.contains(r"\d").mean() > 0.99


def test_cutoff_nodes_are_never_terminal(nodes_roles, dataset):
    deep = set(dataset.nodes.loc[dataset.nodes.depth == dataset.max_depth, "gid"])
    offenders = nodes_roles[nodes_roles.gid.isin(deep) & (nodes_roles.role == "terminal")]
    assert offenders.empty, f"{len(offenders)} MAX_DEPTH nodes were called terminal"


def test_seeds_are_never_transit_or_terminal(nodes_roles, dataset):
    seeds = set(dataset.seeds)
    bad = nodes_roles[nodes_roles.gid.isin(seeds) & nodes_roles.role.isin({"transit", "terminal"})]
    assert bad.empty, f"{len(bad)} seeds got a role their pass ratio cannot support"


# ---------------------------------------------------- clusters.csv (§15)

def test_clusters_columns(clusters):
    assert list(clusters.columns)[:6] == CLUSTERS_COLUMNS


def test_cluster_totals_cover_every_node_and_seed(clusters):
    assert int(clusters.n_nodes.sum()) == N_NODES
    assert int(clusters.n_seed.sum()) == N_SEEDS


def test_every_cluster_id_resolves(nodes_roles, clusters):
    assert set(nodes_roles.cluster_id) <= set(clusters.cluster_id)


def test_hypotheses_are_present_and_bounded(clusters, cfg):
    h = clusters.hypothesis.astype(str)
    assert (h.str.strip() != "").all()
    assert (h.str.len() <= cfg["clustering"]["max_hypothesis_chars"]).all()


# --------------------------------------------------- top_nodes.csv (§15)

def test_top_nodes_ranks(top_nodes):
    assert len(top_nodes) >= 20
    assert list(top_nodes["rank"]) == list(range(1, len(top_nodes) + 1))


def test_top_nodes_are_sorted_by_priority(top_nodes):
    assert top_nodes.priority_score.is_monotonic_decreasing


def test_top_node_gids_exist(top_nodes, nodes_roles):
    assert set(top_nodes.gid) <= set(nodes_roles.gid)


# ------------------------------------------------------- wording (§2)

@pytest.mark.parametrize(
    "filename,columns",
    [("nodes_roles.csv", ["evidence"]),
     ("clusters.csv", ["hypothesis"]),
     ("top_nodes.csv", ["why"])],
)
def test_no_forbidden_words(filename, columns, cfg):
    df = _read(filename)
    forbidden = cfg["evidence"]["forbidden_words"]
    for col in columns:
        blob = " ".join(df[col].astype(str)).lower()
        hits = [w for w in forbidden if w.lower() in blob]
        assert not hits, f"{filename}.{col} contains {hits}"


# -------------------------------------------------- hardcoding guard (§15)

def test_no_gid_like_literals_in_source(cfg):
    """Any 5+ digit literal in src/ or app/ must be a config value, not a gid."""
    allowed = {str(int(v)) for v in _numeric_values(cfg) if float(v).is_integer()}
    offenders = []
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "app").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            for literal in re.findall(r"(?<![\w.])\d[\d_]{4,}(?![\w.])", code):
                plain = literal.replace("_", "")
                if plain in allowed:
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {literal}")
    assert not offenders, "possible hardcoded gids:\n" + "\n".join(offenders)


def _numeric_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _numeric_values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _numeric_values(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield obj


# ----------------------------------------------------- pipeline (§15)

@pytest.mark.slow
def test_run_is_deterministic_and_fast(tmp_path):
    """Two consecutive runs must produce byte-identical CSVs, in < 300 s."""
    import hashlib
    import time

    def once(dest: Path) -> dict[str, str]:
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "run.py", "--data", "data", "--out", str(dest),
             "--config", "config.yaml"],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        elapsed = time.perf_counter() - t0
        assert elapsed < 300, f"run took {elapsed:.1f}s"
        print(f"run completed in {elapsed:.2f}s")
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(dest.glob("*.csv"))
        }

    first, second = once(tmp_path / "a"), once(tmp_path / "b")
    assert first == second, "two runs differ — a random seed is unfixed"
