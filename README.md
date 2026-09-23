# Money Graph

An AML analyst gets 81 customer ids from law enforcement and an export of their
outgoing transfers. This tool turns that export into a ranked list of accounts
to review, each with a role, a cluster and a written rationale — and a viewer
where naming any id shows its role, the rule that produced it, and its money
flows within seconds.

It answers one question: **which of these 2,248 customers should I look at
first, and why?**

```bash
./agent_run.sh
```

That is the whole thing: it sets up the environment, runs the pipeline, verifies
the three required CSVs, reports runtime / tokens / spend, and opens the viewer
with a public share link.

---

## Quick start

```bash
./agent_run.sh                  # everything: setup -> pipeline -> verify -> viewer + share link
./agent_run.sh --offline        # no model at all (deterministic, zero cost)
./agent_run.sh --use-existing   # skip the pipeline, open the viewer on the last run
./agent_run.sh --data ./my_export   # run on your own files
./agent_run.sh --recalibrate    # re-run the calibrator agent
./agent_run.sh --no-app         # stop once the exports are verified
./agent_run.sh --no-share       # viewer on localhost only
```

### Choosing a model

Three setups, all through `.env` — no code changes:

| | How |
|---|---|
| **OpenAI** | `OPENAI_KEY=sk-…` |
| **Any OpenAI-compatible server** — vLLM, Ollama, llama.cpp, TGI, LM Studio, OpenRouter, Together, an internal gateway | `MONEYGRAPH_BASE_URL=http://localhost:8000/v1`, `MONEYGRAPH_MODEL=<name the server serves it under>`, `MONEYGRAPH_API_KEY=<placeholder if the server ignores it>`. Also set `llm.api: chat` in `config.yaml` and clear `reasoning_effort` unless your server accepts it. |
| **No model** | `./agent_run.sh --offline`, or nothing in `.env` at all |

For a local model, set its `llm.pricing` entry to `0` and the tracer reports
`$0.00` honestly rather than `unpriced`.

`agent_run.sh` is self-contained — it finds a Python 3.10+, creates `.venv`, installs
`requirements.txt`, checks for a key, and degrades to offline mode if there
isn't one. It exits `1` if the pipeline fails and `2` if any required CSV is
missing or malformed, so it is safe to use in CI.

Underneath, if you prefer the pieces:

| | |
|---|---|
| Install | `pip install -r requirements.txt` |
| Run the pipeline | `python run.py` |
| Open the viewer | `python app/app.py --share` |
| Run offline (no API calls, no cost) | `MONEYGRAPH_NO_LLM=1 python run.py` |
| Re-run the calibrator agent | `python run.py --recalibrate` |
| Tests | `pytest -q` (add `-m slow` for the determinism + runtime check) |
| Everything above, via make | `make go` · `make offline` · `make test` |

Optional, for the agent layer: copy `.env.example` to `.env` and set
`OPENAI_KEY`. **Without a key everything still works** — the pipeline, all three
CSVs and the whole viewer, including natural-language questions. Only the prose
becomes plainer. That is a hard requirement of the brief ("no paid service to
reproduce the result"), not a convenience.

`python run.py` accepts `--data`, `--out`, `--config` and `--only-profile`;
the defaults come from `config.yaml`.

### What a run produces, in `output_files/`

| File | What it is |
|---|---|
| `nodes_roles.csv` | One row per account: `gid, role, role_score, cluster_id, priority_score, evidence` (+ context columns) |
| `clusters.csv` | One row per cluster: `cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis` |
| `top_nodes.csv` | The ranked shortlist: `rank, gid, role, priority_score, why` |
| `node_features.parquet` | Every computed metric plus the full rule trace per node — what the viewer reads |
| `graph_edges.parquet` | The edges, so the viewer never re-reads `data/` |
| `profile_report.md` | Data profile: announced facts checked, all percentiles |
| `agent_log.md` | **The audit trail**: every agent action, tool call, rejection and fallback |
| `review_notes.md` | The critic's argument *against* the priority list |
| `dossiers.json` | Per-account case dossiers from the investigator |
| `config.calibrated.yaml` | The thresholds the calibrator chose, with rationale (written next to `config.yaml`, committed) |
| `data_requests.md` | What is missing and what to request next |
| `run_trace.md` / `run_trace.json` | Per-stage timing, token counts and spend |

---

## Architecture: an agent crew with a deterministic adjudicator

The case brief disqualifies "a role without an explainable rule" (§9) and asks
the jury to name three arbitrary gids and hear why each got its role (must-have
3). It also scores *"use of AI/agentic AI"* as part of technical implementation.
Those are only in tension if agents assign the roles. So they do not:

> **Agents run the investigation. The rule engine is the adjudicator.**

Agents choose *what to examine, how deep to go, and what the thresholds should
be*. `roles.py` decides *what the role is*, by comparing one metric to one
threshold, and emits a `RuleTrace` that the viewer shows verbatim. The jury
still gets `in_deg >= 5`. What the crew adds is the written reasoning for the
5, a case dossier per priority account, and a standing argument against the
list.

### The crew

| Agent | What it decides | What stops it |
|---|---|---|
| **planner** | Which passes are worth running on *this* dataset and how deep to investigate | A hard cap in `config.yaml` it cannot exceed |
| **calibrator** | **Every role threshold**, with a written rationale naming the percentile | Must stay inside a percentile-derived legal range; the proposal is **simulated against the real data** and rejected if it empties a role or hands one role half the graph; the accepted result is persisted so runs reproduce |
| **investigator** | What to examine around each priority account — a real multi-step tool loop | Every claim must come from a tool result; cited gids must exist; must supply a plausible *innocent* explanation |
| **critic** | What is **wrong** with the shortlist: collection artifacts, threshold sensitivity, blind spots | May only cite accounts it was shown; cannot demote anything — its output is advisory |
| **narrator** | Wording only | Every number in a narrated string must appear in the RuleTrace, or it is discarded |
| **ingest** | Which input column is which | Re-validated against the data before acceptance |
| **reviewer** | How to phrase the data-request brief | The gaps themselves are computed from the graph |
| **analyst** | Which graph query answers the user's question | Answers only from tool output; the transcript is shown beside the answer |

**None of them can assign a role, a score, a cluster or a rank.** Every one has
a deterministic fallback. `MONEYGRAPH_NO_LLM=1 python run.py` produces the same
three CSVs from the `config.yaml` thresholds, with template prose — which the
brief requires ("no paid service to reproduce the result").

### The calibrator, in detail

This is the part worth looking at. Picking "at least 5 distinct payers" is a
judgement call: the number has to sit far enough into the tail to mean
something, be round enough to defend out loud, and not collapse the role space.
That is reasoning over a distribution.

1. The agent is shown the real percentile tables and the meaning of each role.
2. It proposes thresholds **and a one-sentence justification for each**, naming
   the percentile it used.
3. Each proposal is bounds-checked against a range derived from the data's own
   percentiles.
4. The surviving set is **applied to the real distribution** and the resulting
   role counts computed with the same comparisons `roles.py` uses. A set that
   empties `consolidator`, or gives one role >50% of the graph, is rejected and
   the `config.yaml` defaults stand.
5. The accepted result is written to `config.calibrated.yaml` **and committed**,
   so the jury's run reproduces exactly those numbers. `--recalibrate` reruns it.

A test asserts that the simulation and the rule engine agree node-for-node, so
the guardrail cannot silently drift from what it is guarding.

### The audit trail

`output_files/agent_log.md` records every agent's plan, every tool call with
arguments and raw result, every rejected output with its reason, and every
fallback. In a compliance setting, being unable to show how a conclusion was
reached *is* the finding — so the log is a deliverable, not a debug artifact.
The viewer's **Agents** tab renders it alongside the calibrator's threshold
table and the critic's review notes.

### Run shape

```
ingest -> profile
       -> [PLANNER: which passes, how deep]
       -> graph -> features -> temporal -> attribution
       -> [CALIBRATOR: thresholds, simulated then persisted]
       -> roles(1) -> clustering -> roles(2) -> priority -> evidence
       -> [INVESTIGATOR: dossiers] -> [CRITIC: counter-argument]
       -> [NARRATOR: wording] -> [REVIEWER: data requests]
       -> export
```

Full diagram: [`docs/diagram.md`](docs/diagram.md).

## Input: it does not have to be three parquet files

The organizers supply `edges.parquet`, `nodes.parquet` and
`transactions.parquet`, and those load with zero configuration. But an analyst's
real export is whatever their system produced, so ingestion is built to cope:

- **Discovery** — any `.parquet`, `.csv`, `.tsv`, `.json`, `.jsonl` or `.xlsx`
  under the input folder.
- **Alias matching** — `input.aliases` in `config.yaml` maps common column names
  (`from`/`payer`/`src`, `amount`/`sum_kzt`/`value`, …) with case, underscores
  and spaces normalized.
- **Structural inference** — a datetime column is the date; the integer pair
  whose value sets overlap is the endpoints; the float column is the amount.
- **The ingest agent** — consulted only for what is still unresolved, and its
  proposal is validated against the data before acceptance.
- **Derivation** — no node list? Derived from the endpoints. No `depth`?
  Recomputed by BFS from the seeds. No `is_seed`? Nodes with no traced inflow
  are treated as seeds **and the report says so loudly**, because that
  assumption drives every role. No aggregated edges? Built from the transactions.

Every such decision is recorded in the dataset's provenance and reproduced in
§0 of `profile_report.md`, so it is always visible what was given and what was
inferred.

---

## Data limitations and how each one is handled

| Announced flaw | Handling |
|---|---|
| **Cut-off at hop 4** (444 nodes with no outgoing transfers) | `outflow_observed = depth < MAX_DEPTH`. Those nodes can never be `terminal` — this is the fix for the 444 false sinks. They get the documented `cutoff` role, their confidence is multiplied by 0.8, and if they also collect, their *priority is boosted*: a collection point at the edge of the visible data is the best candidate for a hop-5 request. |
| **Outgoing transfers only** | `pass_ratio` is computed only where both sides are trustworthy, and is NaN elsewhere with the reason recorded — never a silent 0. |
| **Seed inflows understated** | Seeds get `pass_ratio = NaN` and are barred from `transit` and `terminal`. Their raw out/in ratios run up to 53, which is an export artifact, not behaviour. |
| **5,000 KZT threshold** | Structuring below it is invisible. Recorded as a completeness gap and turned into a concrete request in `data_requests.md`. |
| **19 seeds absent, 12 receive-only** | All present as nodes, `peripheral`, with evidence stating exactly that. Never dropped — the CSV must have one row per account. |
| **16 components + 19 isolated seeds** | Components are never merged. Anything below `min_cluster_size` becomes its own cluster; each isolated seed is a singleton. |
| **No attributes** | Only structure, amounts and dates are used. The wording rules forbid inventing any. |
| **No ground truth** | Nothing is validated against labels and no output claims certainty. Thresholds are justified by percentile, not by fit. |

---

## Role criteria

All thresholds live in `config.yaml` with the distribution they came from, and
may be **re-derived by the calibrator agent** into `config.calibrated.yaml` —
which is committed, so the numbers a jury sees are the numbers that ran. The
table below is the hand-set baseline and the fallback whenever no model is
available. `MAX_DEPTH` is read from the data, never hardcoded.

| Role | Gate | Starting threshold | Why that number |
|---|---|---|---|
| `consolidator` | `in_deg >= min_payers` | 5 | `in_deg` p95 = 3, p99 = 6. A cut at 5 selects 51 nodes (2.3%) — "an unusual number of distinct payers", not "more than one". Allowed at any depth: collection is visible from the inflow side alone. |
| `distributor` | `out_deg >= min_recipients` **and** `out_deg >= fan_ratio × max(in_deg,1)` | 10, 3× | `out_deg` p95 = 5, p99 = 24. 10 selects 64 nodes; the ratio term drops it to 56 and stops a busy hub being filed as a distributor. |
| `transit` | both flow sides observed, `pass_ratio ∈ [0.8, 1.2]`, `in_deg < 5`, `out_deg < 10` | 0.8–1.2 | 70 non-seed nodes sit in the band (72 counting seeds, which we exclude). Confidence is boosted when ≥50% of the money moves within 2 days. |
| `terminal` | outflow traced, `in_sum > 0`, `out_sum <= max_pass × in_sum` | 0.1 | **Never assigned at MAX_DEPTH.** Broad by nature — 1,143 nodes qualify, 1,079 with no outgoing edge at all — so it carries the second-lowest priority weight. |
| `coordinator` | passes the consolidator gate **and** `n_key_payers >= 2` **and** `seed_reach >= p90` | 2, p90 | A collection point that collects from **other** collection points. All three conditions are needed — see below. Runs in a second pass because it needs its payers' roles and clusters. **10 accounts (0.4%).** |
| `cutoff` | `depth == MAX_DEPTH` and no other gate passed | — | Documented extension, switchable via `use_extended_roles`. Fixed confidence 0.7. Off → these become `peripheral` with a cut-off note. |
| `peripheral` | nothing passed | — | Includes the isolated seeds. Confidence expresses certainty that nothing is happening: 0.9 with ≤1 edge, 0.6 with several. |

### Why `coordinator` needs all three conditions

The guideline's starting gate was `n_key_payers >= 2 AND seed_reach >= 5`. On
this data that promotes **264 accounts — 11.7% of the graph**, 103 of them
`terminal`, i.e. accounts where the money demonstrably *stays*. The opposite of
a controller.

Two things were wrong, and both are visible in the profile:

1. **`seed_reach >= 5` selects 71% of the graph.** Its range here is p50 = 7,
   max = 15, because the largest component contains 46 seeds that feed almost
   everything downstream. An absolute threshold on a metric whose range depends
   entirely on the input carries no information. It is now a **percentile**
   (p90), which rescales with whatever data the tool is pointed at.
2. **Being *paid by* two collectors is not the same as being a collection
   point.** A coordinator must itself pass the consolidator gate. That single
   requirement drops the count from 264 to 10, and every one of them is a
   consolidator — which is exactly the concept: *collects from other
   collectors*.

`require_consolidator_gate` can be turned off in `config.yaml`, and the
pipeline now warns if `coordinator` ever exceeds 2% of the graph, since a 50%
check would never have caught 11.7%.

**Precedence:** `coordinator > consolidator > distributor > transit > terminal >
cutoff > peripheral`. Gates that also passed are kept in `secondary_roles`.

**Confidence (`role_score`):** `0.5 + 0.5 × clip((metric − threshold) / (strong −
threshold), 0, 1)`, then `×0.8` at MAX_DEPTH (outflow unknown) and `×0.8` where
the inflow side is unreliable.

**Seeds** never receive `transit` or `terminal` — the export never captured what
they received, so their ratio is meaningless. They can be `distributor` (a
courier fanning out), `consolidator`, or `peripheral`.

---

### What the rules actually produce on the organizers' data

| Role | Accounts | |
|---|---:|---|
| `terminal` | 1,129 | Broad by nature — most are leaves that simply had nothing above the 5,000 KZT floor leaving them. Carries a low priority weight for that reason. |
| `peripheral` | 511 | No gate passed, including the 19 isolated seeds. |
| `cutoff` | 444 | **Exactly** the announced count of hop-4 nodes whose onward flow was never traced. |
| `transit` | 67 | |
| `distributor` | 46 | |
| `consolidator` | 41 | |
| `coordinator` | 10 | The apex role, 0.4% of the graph. |

Full run: **1.6 s**, against a 300 s budget.

## Priority score

A weighted sum of **percentile ranks**, not raw values — turnover spans four
orders of magnitude, so ranking first is what makes the weights mean what they
say.

| Component | Weight | Reads as |
|---|---|---|
| role weight | 0.30 | coordinator 1.0 · consolidator 0.9 · distributor 0.6 · transit/terminal 0.5 · cutoff 0.3 · peripheral 0.05 |
| `seed_kzt_attributed` | 0.25 | how much seed-originated money plausibly passed through |
| `seed_reach` | 0.20 | how many separate courier chains reach it |
| `in_deg` | 0.15 | how many distinct payers |
| cluster seed density | 0.10 | how seed-heavy its neighbourhood is |

Two documented adjustments:

- **Known seeds × 0.5.** Law enforcement already has the 81. The analyst's value
  is in what sits *above* them, so being a seed lowers review priority.
- **Frontier collectors × 1.1** (capped at 1). A `consolidator` or `coordinator`
  at MAX_DEPTH is where the chain most likely continues past the visible data —
  the highest-value target for a follow-up request.

`top_nodes.csv` carries the top 30. The `why` column names the components that
actually drove the rank, taken from the stored per-component contributions.

---

## Clustering

Louvain (`seed=42`, resolution from config) on the **undirected** projection
weighted by `log1p(sum_kzt)`. Dropping direction for grouping is a real
concession and is stated rather than hidden — community detection needs an
undirected graph, and every role, metric and arrow shown to the analyst still
uses the directed one.

Small components are **never absorbed** into large clusters: anything below
`min_cluster_size` becomes its own cluster, each isolated seed a singleton.
Clusters are renumbered by size descending with ties broken by smallest gid, so
the numbering is stable across runs.

**Stability** is measured, not assumed: Louvain is re-run under 5 seeds and the
share of node pairs that stay together is reported per cluster in the run log.

Hypotheses are template-generated from the cluster's role mix and flows, then
optionally rephrased by the narrator under the same number-checking rule.

---

## Tracing: time, tokens and spend

Every run writes `output_files/run_trace.md` and `run_trace.json`, and the
viewer shows them in the **Run trace** tab:

- wall-clock for every stage and sub-stage, as a share of the 5-minute budget;
- every model call with input / output / reasoning / cached token counts,
  aggregated per agent;
- cost per call, priced from `llm.pricing` in `config.yaml`.

Rates are per model and per **context tier** — a call is billed at the
long-context rate once its input passes `long_context_threshold_tokens`. The
tier that was applied is recorded on every call.

Four rules the tracer keeps:

1. **It never invents a price.** A model with no `llm.pricing` entry is reported
   as *unpriced*: exact token counts, no dollar figure, and the total carries an
   explicit caveat rather than a number that looks authoritative.
2. **It never guesses token counts.** Only usage the provider actually reported
   is recorded. Cached tokens are charged **once**, at the cached rate — they
   are a subset of the reported input count, so adding the full input rate on
   top would double-bill them.
3. **It never charges for a cache write it cannot see.** `cache_write` rates are
   configured, but nothing is billed unless the provider reports
   cache-creation tokens. The OpenAI usage payload reports cached tokens as
   *reads*, so on this stack cache writes arrive as ordinary input.
4. **It enforces the budget.** `llm.budget` caps calls, tokens and dollars per
   run. Hitting any ceiling shuts down the agent layer; the deterministic
   pipeline finishes and every export is still produced.

### What a full run costs

A complete agentic run — planner, calibrator, 10 investigations, critic,
reviewer — is **14 calls and ~25,500 tokens**:

| Model | Cost per run |
|---|---:|
| `gpt-6-luna` (configured) | **$0.0043** |
| `gpt-6-sol` | $0.0869 |
| `gpt-6-astra` | $0.4346 |

Every call sits in the short-context tier: the largest prompt the crew sends is
~5.4k tokens, three orders of magnitude below the tier boundary. The `max_usd`
budget of $2.00 is therefore ~460 full runs on the configured model.

Configured model: `gpt-6-luna`, `reasoning_effort: low`. Both are one-line
changes in `config.yaml`, and the other two models are already priced there.

---

## Output schemas

**`nodes_roles.csv`** — one row per account, `gid` ascending.

| Column | Type | Meaning |
|---|---|---|
| `gid` | int64 | account identifier |
| `role` | str | one of the seven roles |
| `role_score` | float | confidence in the role, 0–1 |
| `cluster_id` | int64 | cluster number |
| `priority_score` | float | review priority, 0–1 |
| `evidence` | str | why, with numbers, ≤ 200 chars |

Followed by context columns (`depth`, `is_seed`, degrees, flows, `pass_ratio`,
`seed_reach`, `seed_kzt_attributed`, `secondary_roles`, the two observability
flags). Extra columns are permitted; the required six lead, in order.

**`clusters.csv`** — `cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids,
hypothesis`. `sum_kzt_internal` sums edges with both ends inside the cluster;
`top_gids` is the top 5 by priority, `;`-separated.

**`top_nodes.csv`** — `rank, gid, role, priority_score, why`, 30 rows, rank 1..N.

---

## Reproducibility

- Thresholds and weights are in `config.yaml`, each with the distribution it
  came from. No magic numbers in the code.
- No gid is hardcoded. A test greps `src/` and `app/` for 5+ digit literals and
  fails on anything that is not a declared config value.
- One seed (`seed: 42`) drives Louvain, the stability sampling and the layout.
  A test runs the pipeline twice offline and compares file hashes.
- **Agent-chosen thresholds are persisted, not re-sampled.**
  `config.calibrated.yaml` is committed, so a run on the jury's machine uses the
  exact numbers the calibrator picked here — an agentic pipeline that is still
  bit-reproducible. `--recalibrate` is the explicit opt-in to change them.
- Versions pinned in `requirements.txt`. No cloud, no GPU, no paid service.
- Announced facts are checked, not trusted: `profile_report.md` §1 compares
  every number in the brief against the files and flags mismatches loudly.

---

## Wording and privacy

Every generated string — `evidence`, `why`, `hypothesis`, the data-request
brief, every agent answer — is phrased as a hypothesis for verification ("signs
of consolidation", "pattern consistent with transit", "candidate for review"),
never as a statement about a person. The words *criminal*, *guilty*,
*launderer*, *organizer is* and *confirmed* are blacklisted in `config.yaml`,
enforced in the narrator's validator, re-checked before export, and asserted in
the test suite.

The data is anonymized: `gid` is a synthetic identifier. No names, ages,
genders, incomes or organizations are used, and the agent prompts explicitly
forbid inventing them.

---

## Limitations of the approach

- **Seed attribution is a heuristic.** Money is fungible; once two inflows mix,
  no export can say which tenge went where. `seed_kzt_attributed` is an
  upper-bound-style estimate of exposure, not an accounting fact.
- **Thresholds are defensible, not optimal.** They come from the observed
  percentiles and are deliberately round. With no ground truth there is nothing
  to tune against, and tuning to decimals would only look more precise.
- **`terminal` is broad.** Half the graph qualifies, because most leaves simply
  had nothing above 5,000 KZT leaving them. It is correct and nearly
  uninformative, which is why it carries a low priority weight.
- **Direction is dropped for clustering.** Stated above; it affects grouping
  only.
- **One month, one bank.** Nothing here distinguishes a recurring structure from
  a single month's coincidence.
- **No validation.** With no labels, every output is a prioritization aid for an
  analyst, not a finding.

---

## Scaling to ~1M nodes

What would change, in order of how soon it would bite:

1. **Betweenness goes first.** Exact betweenness is O(VE) and is already the
   most expensive stage here. At 1M nodes: sample-based approximation
   (`k≈1000` pivots), or drop it — it contributes to no gate, only to context.
2. **Graph library.** `networkx` is Python objects per node. Move to
   `python-igraph` or `graph-tool` (C cores, 10–100× on the same algorithms)
   with no change to the rule logic, which only reads scalars per node.
3. **Louvain → Leiden.** Leiden guarantees well-connected communities and is
   faster at scale; `igraph` ships it. The stability check would sample
   components rather than re-running globally.
4. **Seed attribution becomes sparse linear algebra.** The current round-based
   propagation is a sparse matrix-vector product in disguise:
   `scipy.sparse` with `MAX_DEPTH+1` multiplications, or one `spsolve` on
   `(I − αA)`. Seed reach becomes a boolean bitset product over components.
5. **I/O.** DuckDB or Polars over the parquet files, with predicate pushdown, so
   ingestion never materializes the full frame.
6. **Per-component parallelism.** The graph is already disconnected — 16
   components here. Features, roles and clustering are component-local and
   embarrassingly parallel.
7. **Thresholds are already percentile-derived,** so they rescale without being
   re-tuned. That is why they are written as percentiles in the profile report
   rather than as fitted constants.
8. **The viewer stops loading the graph.** A precomputed backend — Neo4j or a
   parquet-backed adjacency index — answering ego queries on demand. The
   viewer's contract is already "read only what is exported", so only the
   storage layer changes.
9. **The agent layer barely changes.** It is already bounded by node count via
   the narration scope (the shortlist plus cluster leaders), not by graph size.

---

## Project structure

```
.
├── agent_run.sh                 # ONE command: setup -> run -> verify -> viewer
├── run.py                       # pipeline entry point
├── config.yaml                  # thresholds, weights, agents, budget, pricing
├── config.calibrated.yaml       # thresholds the calibrator chose (generated, COMMITTED)
├── requirements.txt             # pinned
├── Makefile                     # setup | run | run-nollm | app | profile | test
├── .env.example                 # OPENAI_KEY (optional)
├── guideline.md                 # the working brief
├── data/                        # organizers' input               (READ-ONLY)
├── starter/                     # organizers' starter code        (READ-ONLY)
├── src/moneygraph/
│   ├── schema.py                # file discovery + column mapping
│   ├── io.py                    # canonical Dataset + provenance
│   ├── profile.py               # data profile report
│   ├── graph.py                 # DiGraph over every gid
│   ├── features.py              # degrees, flows, centrality
│   ├── temporal.py              # lag, fast pass-through, same-day collection
│   ├── attribution.py           # seed_reach, seed_kzt_attributed
│   ├── roles.py                 # the rule engine + RuleTrace
│   ├── clustering.py            # Louvain + stability
│   ├── priority.py              # weighted percentile sum
│   ├── evidence.py              # templates + the validation gate
│   ├── export.py                # the deliverables
│   ├── trace.py                 # time / token / spend tracer
│   ├── pipeline.py              # orchestration only
│   └── agents/
│       ├── base.py              # Agent framework: plan/act/validate/fallback
│       ├── orchestrator.py      # the Crew + agent_log.md
│       ├── llm.py               # traced, budget-aware provider wrapper
│       ├── tools.py             # deterministic graph functions
│       ├── calibrator_agent.py  # chooses the role thresholds  <-- the interesting one
│       ├── investigator_agent.py# multi-step case dossiers
│       ├── critic_agent.py      # argues against the shortlist
│       ├── ingest_agent.py      # unfamiliar schemas
│       ├── narrator_agent.py    # rule trace -> English, validated
│       ├── analyst_agent.py     # natural-language Q&A
│       └── review_agent.py      # data-request brief
├── app/app.py                   # Gradio viewer
├── docs/
│   ├── diagram.md               # solution diagram (Mermaid)
│   └── case_brief.docx          # organizers' case brief
├── output_files/                # generated deliverables
└── tests/test_outputs.py        # contract, wording, agent and hardcoding guards
```
