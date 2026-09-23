# Money Graph

Reconstructing the financial structure of an organized group from a transaction
network. HackAlem AI case.

> Languages: **English** · [Русский](README.ru.md) · [Қазақша](README.kk.md)

```bash
./agent_run.sh
```

One command: install dependencies → compute → verify the exports → report time
and cost → open the web interface with a public link.

---

## Contents

1. [What it does and who it is for](#1-what-it-does-and-who-it-is-for) *(описание решения и его назначения)*
2. [Architecture](#2-architecture) *(описание архитектуры)*
3. [Technologies used](#3-technologies-used) *(используемые технологии)*
4. [Installation](#4-installation) *(инструкции по установке)*
5. [Running it](#5-running-it) *(инструкции по запуску)*
6. [Dependencies](#6-dependencies) *(необходимые зависимости)*
7. [Environment parameters](#7-environment-parameters) *(параметры окружения)*
8. [Verifying the main scenario](#8-verifying-the-main-scenario) *(порядок проверки основного сценария работы)*
9. [Role criteria](#9-role-criteria)
10. [Priority score](#10-priority-score)
11. [Clustering](#11-clustering)
12. [Data limitations and how each is handled](#12-data-limitations-and-how-each-is-handled)
13. [Output schemas](#13-output-schemas)
14. [Reproducibility](#14-reproducibility)
15. [Wording and privacy](#15-wording-and-privacy)
16. [Limitations of the approach](#16-limitations-of-the-approach)
17. [Scaling to ~1M nodes](#17-scaling-to-1m-nodes)
18. [Repository layout](#18-repository-layout)

---

## 1. What it does and who it is for

### The problem

Law enforcement hands an AML analyst at a second-tier bank a list of customers
who received money from drug trafficking — the **bottom of the chain**. Who sits
above them, who collects the money, through whom it moves and who ultimately
controls it, has to be reconstructed by hand, hours per node.

### What the solution does

**In:** an export of **outgoing** transfers from 81 known customers across
4 hops (July 2026, intra-bank, transfers ≥ 5,000 KZT) — 2,248 nodes, 3,119 edges,
4,840 transactions.

**Out:** an answer to one question — **which of the 2,248 customers to review
first, and why.** Specifically:

* every node gets a **role** from the dictionary, a **confidence** (0–1), a
  **cluster** and a **review priority** (0–1);
* every role carries **evidence with numbers** — the exact figures the rule
  compared;
* three CSV exports with a fixed schema;
* a **web interface** where typing an account number shows its role, the rule
  that produced it and a map of the money around it, in seconds.

### Who uses it

A financial-monitoring analyst. The scenario: receive a list of gids → load the
export → open the priority list → read the reason for each entry → assemble the
accounts for in-depth review and the request to law enforcement.

### The defining property

**This is not a black box.** Every role is the result of a formal rule with a
threshold, and that rule is shown in the interface together with the numbers it
compared. AI agents are involved, but they **do not assign roles** (see §2).

---

## 2. Architecture

### The governing principle

> **Agents run the investigation. The rule engine is the adjudicator.**

Agents decide *what to examine, how deep to go, and what the thresholds should
be*. `roles.py` decides *what the role is*, by comparing a metric to a
threshold, and emits a `RuleTrace` holding the rule that fired, the values it
used and the thresholds it compared against. The brief's requirement — "a role
without an explainable rule does not count" — is satisfied by construction.

### The pipeline

```
ingest → data profiling
       → [PLANNER: which passes this dataset needs]
       → graph → features → temporal → attribution
       → [CALIBRATOR: role thresholds, simulated then persisted]
       → roles (pass 1) → clustering → roles (pass 2: coordinator)
       → priority → evidence
       → [INVESTIGATOR: dossiers] → [CRITIC: the argument against]
       → [NARRATOR: wording] → [REVIEWER: data requests]
       → exports
```

Full diagram: [`docs/diagram.md`](docs/diagram.md).

### The agents and what constrains them

| Agent | What it decides | What constrains it |
|---|---|---|
| **planner** | which passes to run on this dataset, and how deep | a hard cap in `config.yaml` it cannot exceed |
| **calibrator** | **every role threshold**, with a written justification for each | must stay inside a percentile-derived range; the proposal is **simulated against the real data** and rejected if it empties a role or hands one role more than half the network; the result is persisted for reproducibility |
| **investigator** | what to examine around each priority account (a multi-step tool loop) | every claim must come from a tool result; cited gids must exist; must offer a plausible **innocent** explanation |
| **critic** | what is **wrong** with the shortlist: collection artifacts, threshold sensitivity, blind spots | may only cite accounts it was shown; cannot demote anything — its output is advisory |
| **narrator** | wording only | every number in a rewritten sentence must appear in the `RuleTrace`, or the rewrite is discarded |
| **ingest** | which input column is which | the answer is re-validated against the data before acceptance |
| **reviewer** | how to phrase the data-request brief | the gaps themselves are computed from the graph |
| **analyst** | which graph query answers the user's question | answers only from tool output; the call transcript is shown beside the answer |

**None of them assigns a role, a score, a cluster or a rank.** Each has a
deterministic fallback: `./agent_run.sh --offline` produces the same three CSVs
with the same roles.

### The wording-validation contract

1. `roles.py` assigns a role and emits a `RuleTrace`.
2. `evidence.py` fills a template from it — always correct.
3. The narrator may rewrite the sentence. The rewrite is accepted only if it
   passes the length cap, the forbidden-word list **and** the number check:
   every number in the text must be derivable from the `RuleTrace`.
4. Rejections are counted and reported in `run_trace.md`.

### The audit trail

`output_files/agent_log.md` records each agent's plan, every tool call with its
arguments and result, every rejected output with its reason, and every fallback.
In a compliance setting, being unable to show how a conclusion was reached *is*
the finding — so the log is a deliverable, not a debug artifact.

---

## 3. Technologies used

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.10+ (tested on 3.13) | recommended by the organizers |
| Data | `pandas`, `pyarrow`, `numpy` | parquet/CSV reading, vectorized computation |
| Graphs | `networkx` 3.7, `scipy` | directed weighted graph, PageRank, betweenness, Louvain, connected components |
| Configuration | `PyYAML` | every threshold and weight lives outside the code |
| Interface | `gradio` 5.50, `pyvis` 0.3.2 | web interface and interactive network maps that work offline |
| Agents | `openai` (compatible client), `python-dotenv` | the AI layer; **optional at runtime** |
| Tests | `pytest` | 73 tests: export contract, wording, agents, interface |

**No charting library, deliberately.** The one chart in the interface is drawn
in CSS: otherwise its rendering depends on a JS bundle version agreeing with
Gradio's front end.

**Not required:** cloud, GPU, paid services. Internet access is needed only for
an external LLM API, and only if it is enabled.

---

## 4. Installation

### The short path (recommended)

```bash
git clone <repository-url>
cd hack-e26f0e66-max
./agent_run.sh
```

The script finds a Python 3.10+, creates `.venv`, installs from
`requirements.txt`, creates `.env` from the template and continues. No separate
installation step is needed. If `.venv` exists but its interpreter does not run
— a half-finished creation, a copied working tree, an upgraded system Python —
it is detected and rebuilt.

### The manual path

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # the key may stay empty
```

### Verifying the installation

```bash
.venv/bin/python -m pytest -q      # expected: 73 passed
```

Machine requirements: an ordinary laptop. The computation takes **under 2
seconds** without the AI layer and roughly 30–90 seconds with it, against the
brief's 5-minute limit.

---

## 5. Running it

### One command

```bash
./agent_run.sh
```

Six steps: environment → dependencies → model check → computation → export
verification → web interface with a public link.

### Modes

```bash
./agent_run.sh                 # full run with the AI layer (needs .env)
./agent_run.sh --offline       # no model calls at all; exports are identical
./agent_run.sh --use-existing  # skip the computation, open the viewer on the last result
./agent_run.sh --data ./my_export   # your own files instead of data/
./agent_run.sh --recalibrate   # re-run the calibrator agent
./agent_run.sh --no-app        # stop after the exports are verified
./agent_run.sh --no-share      # viewer on localhost only
./agent_run.sh --port 7861
```

Exit codes: `0` success, `1` computation failed, `2` exports missing or
malformed, `3` environment problem. Suitable for CI.

### The pieces

```bash
.venv/bin/python run.py                  # computation only: data/ → output_files/
.venv/bin/python run.py --only-profile   # data profile report only
.venv/bin/python app/app.py --share      # interface only
make run | make offline | make existing | make test
```

### What appears in `output_files/`

| File | Contents |
|---|---|
| `nodes_roles.csv` | **required.** One row per account: `gid, role, role_score, cluster_id, priority_score, evidence` |
| `clusters.csv` | **required.** One row per cluster: size, seed count, internal turnover, top gids, hypothesis |
| `top_nodes.csv` | **required.** 30 accounts by descending priority, with a written reason |
| `node_features.parquet` | every metric plus each node's `rule_trace` — this is what the viewer reads |
| `graph_edges.parquet` | the edges, so the viewer never touches `data/` |
| `profile_report.md` | data profile: every announced fact checked, all percentiles |
| `agent_log.md` | the AI agents' audit trail |
| `review_notes.md` | the critic's argument against the shortlist |
| `data_requests.md` | what is missing and what to request next |
| `dossiers.json` | the investigator's dossiers on the priority accounts |
| `ingest_report.json` | which file was read as what, and how each column was matched |
| `run_trace.md` / `.json` | per-stage timing, tokens, spend |

---

## 6. Dependencies

The full pinned list is [`requirements.txt`](requirements.txt). The set was
**resolved and installed**, not hand-written: `gradio` caps `pandas` below 3.0,
so the whole stack sits on the `pandas` 2.x line.

```
pandas==2.3.3          pyarrow==25.0.1     numpy==2.5.3
networkx==3.7          scipy==1.18.1       PyYAML==6.0.3
gradio==5.50.0         pyvis==0.3.2
openai==3.19.0         python-dotenv==1.2.3
pytest==9.1.1
```

Notes:

* `scipy` is required: `networkx` delegates weighted PageRank to it.
* `gradio` is held below 6.0: `app/app.py` targets the 5.x API.
* `openai` and `python-dotenv` are only for the AI layer. Without them the
  computation and the interface work fully and the agents take their
  deterministic path.

Before changing any pin, re-resolve the set:

```bash
pip install --dry-run -r requirements.txt
```

---

## 7. Environment parameters

### The `.env` file

Created automatically from [`.env.example`](.env.example) and never committed.
Three supported setups.

**1. OpenAI**

```bash
OPENAI_KEY=sk-...
```

**2. A self-hosted or third-party OpenAI-compatible server** — vLLM, Ollama,
llama.cpp, TGI, LM Studio, OpenRouter, Together, an internal gateway:

```bash
MONEYGRAPH_BASE_URL=http://localhost:8000/v1
MONEYGRAPH_MODEL=Qwen/Qwen3-32B-Instruct
MONEYGRAPH_API_KEY=local        # many local servers ignore the key
```

Also set `llm.api: chat` in `config.yaml`, and clear `llm.reasoning_effort`
unless your server accepts it. Add the model's rates under `llm.pricing` — for a
local model set them to `0` and the report honestly shows `$0.00` rather than
"unpriced".

**3. No model at all**

```bash
MONEYGRAPH_NO_LLM=1
```

or `./agent_run.sh --offline`. The brief's requirement — reproducible without
paid services — is met.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_KEY` / `OPENAI_API_KEY` / `MONEYGRAPH_API_KEY` | API key; the first non-empty one wins | — |
| `MONEYGRAPH_BASE_URL` | address of an OpenAI-compatible server | OpenAI's API |
| `MONEYGRAPH_MODEL` | model name, overrides `config.yaml` | `gpt-6-sol` |
| `MONEYGRAPH_NO_LLM` | `1` — fully deterministic run | unset |
| `MONEYGRAPH_SHARE` | `1` — public interface link | `0` |
| `MONEYGRAPH_HOST` / `MONEYGRAPH_PORT` | interface address and port | `127.0.0.1:7860` |

### `config.yaml`

Every threshold, weight, budget and rate, each with a comment on where it came
from. Key sections: `roles` (role thresholds), `priority` (score weights),
`clustering`, `llm` (model, budgets, pricing), `agents` (per-agent switches),
`tracing` (latency budget), `viewer`, `input` (column aliases).

Current model: **`gpt-6-sol`**, `reasoning_effort: low`. A full run with the AI
layer is about 53 calls and 76,000 tokens, roughly **$0.21**.
`llm.budget.max_usd` is a **per-run** ceiling of $2.00 — about 10× headroom.
`gpt-6-luna` and `gpt-6-astra` are priced too, so switching is one line.

### `config.calibrated.yaml`

The thresholds the calibrator agent chose, with a justification for each.
**Committed deliberately:** it makes a run on a reviewer's machine reproduce
exactly the numbers chosen here. Re-run the agent with
`./agent_run.sh --recalibrate`.

---

## 8. Verifying the main scenario

A sequence that can be followed end to end without reading the code.

### Step 1. Deploy and run

```bash
git clone <repository-url> && cd hack-e26f0e66-max
./agent_run.sh --offline --no-app
```

`--offline` is deliberate: it needs no key, costs nothing, and exercises exactly
the deterministic core.

**Expected:**

```
[1/5] Python environment      ✓
[2/5] Dependencies            ✓
[3/5] Agent layer             ! offline mode
[4/5] Pipeline                ✓ pipeline finished in 2s
[5/5] Deliverables
  nodes_roles.csv   2248  ok
  clusters.csv        88  ok
  top_nodes.csv       30  ok
  ✓ all three required CSVs are present and valid in output_files/
```

### Step 2. Check the required exports

```bash
wc -l output_files/nodes_roles.csv          # 2249 (2248 rows + header)
head -2 output_files/nodes_roles.csv        # gid,role,role_score,cluster_id,priority_score,evidence,...
head -4 output_files/top_nodes.csv          # rank,gid,role,priority_score,why
```

The schema is checked automatically in step 5 of the script: files present,
required column order, no nulls, unique gids, at least 20 rows in
`top_nodes.csv`.

### Step 3. Check explainability (must-have 3 of the brief)

The scenario is "the jury names three arbitrary gids, the team explains each
role within a minute". From the terminal:

```bash
.venv/bin/python - <<'PY'
import json, pandas as pd
f = pd.read_parquet("output_files/node_features.parquet").set_index("gid", drop=False)
for gid in pd.read_csv("output_files/top_nodes.csv").gid[:3]:
    tr = json.loads(f.at[gid, "rule_trace"])
    print(f"\ngid {gid}  ->  {tr['role']}")
    print(f"  rule:       {tr['gate']}")
    print(f"  values:     {tr['metrics']}")
    print(f"  thresholds: {tr['thresholds']}")
PY
```

Every node returns the rule that fired, the values it compared and the
thresholds. The same thing is shown in the interface on the **Account detail**
tab.

### Step 4. Check reproducibility

```bash
.venv/bin/python -m pytest -q -m slow
```

One test runs the computation twice and compares CSV hashes — they must match.
Another confirms the exports are produced with no access to a model.

### Step 5. Open the interface

```bash
./agent_run.sh --use-existing
```

It opens at `http://127.0.0.1:7860` and prints a public link. The default
language is English; Русский and Қазақша are one click away, top right.

**The first tab, "About",** explains the other eight and contains a three-step
demo path.

Verifying the main scenario in the interface:

1. **Who to review first** — 30 accounts sorted by priority, each with a reason.
   Clicking a row opens that account's card below.
2. **Account detail** — type any gid (for example from `top_nodes.csv`). You
   should see the role, the rule that fired with its numbers, a link map with
   arrows showing the direction of money, and tables of payers and recipients.
3. **How it decided** — the thresholds the agent chose with its reasoning, the
   dossiers, the critic's argument against the result, and the full agent log.
4. **Cost & timing** — per-stage timing against the 300-second limit.

### Step 6 (optional). Check the AI layer

```bash
cp .env.example .env && $EDITOR .env      # set OPENAI_KEY
./agent_run.sh
```

The output shows the planner, calibrator, investigator (running concurrently),
critic and reviewer, and the token and cost totals.

### Step 7 (optional). Check it on other data

```bash
./agent_run.sh --data /path/to/your/export
```

`.parquet`, `.csv`, `.tsv`, `.json`, `.jsonl` and `.xlsx` are read. The column
mapping is visible on the **Your data** tab and in `ingest_report.json`.

---

## 9. Role criteria

Every threshold is in `config.yaml` with the distribution it came from.
`MAX_DEPTH` is read from the data, never hardcoded.

| Role | Rule | Threshold | Rationale |
|---|---|---|---|
| `consolidator` | `in_deg >= min_payers` | 5 | p95 = 3, p99 = 6. A cut at 5 selects 51 nodes (2.3%) — "an unusual number of distinct payers", not "more than one". Allowed at any hop: collection is visible from the inflow side alone. |
| `distributor` | `out_deg >= min_recipients` **and** `out_deg >= fan_ratio × max(in_deg,1)` | 10, ×3 | p95 = 5, p99 = 24. A cut at 10 gives 64 nodes; the ratio term drops it to 56 and stops a node that also collects heavily being filed as a distributor. |
| `transit` | both flow sides observed, `pass_ratio ∈ [0.8, 1.2]`, `in_deg < 5`, `out_deg < 10` | 0.8–1.2 | 70 nodes in the band (72 counting seeds, which are excluded). Confidence rises when ≥ 50% of the amount moves within 2 days. |
| `terminal` | outflow traced, `in_sum > 0`, `out_sum <= max_pass × in_sum` | 0.1 | **never assigned at MAX_DEPTH.** Broad by the nature of the data, hence a low weight in the priority score. |
| `coordinator` | passes the consolidator gate **and** `n_key_payers >= 2` **and** `seed_reach >= p90` | 2, p90 | a collection point that collects **from other collection points**. All three conditions are needed (below). **10 accounts, 0.4%.** |
| `cutoff` | `depth == MAX_DEPTH` and no rule fired | — | a documented extension of the dictionary, switched by `use_extended_roles`. Fixed confidence 0.7. |
| `peripheral` | nothing fired | — | includes the 19 isolated seeds. Confidence expresses certainty that nothing is happening: 0.9 with ≤ 1 edge, 0.6 with several. |

**Precedence:** `coordinator > consolidator > distributor > transit > terminal >
cutoff > peripheral`. Other rules that also fired are kept in `secondary_roles`.

**Confidence (`role_score`):** `0.5 + 0.5 × clip((metric − threshold) /
(strong − threshold), 0, 1)`, then `×0.8` at MAX_DEPTH (outflow unknown) and
`×0.8` where the inflow side is unreliable.

**Seed customers** never receive `transit` or `terminal`: their inflow is
understated by the export's construction, so the ratio is meaningless. They can
be `distributor`, `consolidator` or `peripheral`.

### Why coordinator needs all three conditions

The brief's starting rule (`n_key_payers >= 2 AND seed_reach >= 5`) assigned the
role to **264 accounts — 11.7% of the graph** — 103 of which were `terminal`,
i.e. accounts where the money demonstrably stays. The opposite of a controller.
Two causes:

1. **`seed_reach >= 5` selects 71% of the graph.** Its range here is p50 = 7,
   max = 15: the largest component holds 46 seeds feeding almost everything
   downstream. An absolute threshold on a metric whose range is entirely
   data-dependent carries no information. It is now a **percentile** (p90),
   which rescales to any input.
2. **Being paid by two collectors is not the same as being a collection
   point.** A coordinator must itself pass the consolidator gate. That one
   condition drops the count from 264 to 10, and all ten are collection points —
   which is exactly the definition: *collects from other collectors*.

The pipeline warns if `coordinator` ever exceeds 2% of the graph.

### Actual distribution on the organizers' data

| Role | Accounts | |
|---|---:|---|
| `terminal` | 1,100 | broad by the nature of the data: most are ordinary leaves that simply had nothing above the 5,000 KZT floor leaving them |
| `peripheral` | 540 | |
| `cutoff` | 444 | **exactly** the announced count of hop-4 nodes with no outgoing transfers |
| `transit` | 67 | |
| `distributor` | 46 | |
| `consolidator` | 41 | |
| `coordinator` | 10 | the apex role, 0.4% of the graph |

Full computation: **1.6 s** against a 300 s limit.

---

## 10. Priority score

A weighted sum of **percentile ranks**, not of raw values: turnover spans four
orders of magnitude, so ranking before weighting is what makes the weights mean
what they say.

| Component | Weight | Meaning |
|---|---:|---|
| role weight | 0.30 | coordinator 1.0 · consolidator 0.9 · distributor 0.6 · transit/terminal 0.5 · cutoff 0.3 · peripheral 0.05 |
| `seed_kzt_attributed` | 0.25 | how much seed money plausibly passed through |
| `seed_reach` | 0.20 | how many independent chains reach it |
| `in_deg` | 0.15 | how many distinct payers |
| cluster seed density | 0.10 | how seed-heavy its neighbourhood is |

Two documented adjustments:

* **Known seeds × 0.5.** Law enforcement already has those 81; the value is in
  what sits above them, so being a seed lowers priority.
* **Frontier collectors × 1.1** (capped at 1.0). A `consolidator` or
  `coordinator` at MAX_DEPTH is the most likely place the chain continues and
  the best candidate for a hop-5 data request.

`top_nodes.csv` holds 30 accounts. The `why` column names the components that
actually drove the rank, taken from stored contributions rather than guessed.

---

## 11. Clustering

Louvain (`seed=42`, resolution from config) on the **undirected** projection
weighted by `log1p(sum_kzt)`. Dropping direction is a real concession and is
stated openly: community detection needs an undirected graph, while every role,
metric and arrow shown to the analyst uses the directed one.

Small components are **never absorbed** into large clusters: anything below
`min_cluster_size` becomes its own cluster, each isolated seed a singleton.
Numbering is by descending size with ties broken on the smallest gid, so it is
stable across runs.

**Stability is measured, not assumed:** Louvain is re-run under 5 seeds and the
share of node pairs staying together is computed per cluster. On the organizers'
data: mean 0.95, **78 clusters at ≥ 0.80**.

---

## 12. Data limitations and how each is handled

| Announced limitation | Handling |
|---|---|
| **Cut-off at hop 4** (444 nodes with no outgoing transfers) | `outflow_observed = depth < MAX_DEPTH`. These nodes can never be `terminal` — this is the fix for the 444 false sinks. They get the `cutoff` role, confidence is multiplied by 0.8, and if such a node also collects, its **priority is raised**: a collection point at the edge of the visible data is the best candidate for a hop-5 request. |
| **Outgoing transfers only** | `pass_ratio` is computed only where both sides are trustworthy, otherwise NaN with the reason recorded — never a silent zero. |
| **Seed inflows understated** | seeds get `pass_ratio = NaN` and are barred from `transit` and `terminal`. Their raw ratio runs up to 53 — an export artifact, not behaviour. |
| **5,000 KZT floor** | structuring below it is invisible. Recorded as a gap and turned into a concrete request in `data_requests.md`. |
| **19 seeds absent from the edges, 12 receive-only** | all present as nodes, role `peripheral`, with evidence saying exactly that. Never dropped: the export must have one row per participant. |
| **16 components + 19 isolated seeds** | components are never merged. Anything below `min_cluster_size` is its own cluster, each isolated seed a singleton. |
| **No customer attributes** | only structure, amounts and dates are used. The wording rules forbid inventing anything else. |
| **No labelled roles** | nothing is validated against ground truth and no output claims certainty. Thresholds are justified by percentile, not by fitting. |

---

## 13. Output schemas

**`nodes_roles.csv`** — one row per account, ascending `gid`.

| Column | Type | Meaning |
|---|---|---|
| `gid` | int64 | customer identifier |
| `role` | str | one of the seven roles |
| `role_score` | float | confidence in the role, 0–1 |
| `cluster_id` | int64 | cluster number |
| `priority_score` | float | review priority, 0–1 |
| `evidence` | str | reason with numbers, ≤ 200 characters |

Context columns follow (`depth`, `is_seed`, degrees, turnover, `pass_ratio`,
`seed_reach`, `seed_kzt_attributed`, `secondary_roles`, the two observability
flags). Extra columns are permitted by the brief; the six required ones lead, in
order.

**`clusters.csv`** — `cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids,
hypothesis`. `sum_kzt_internal` sums edges with both ends inside the cluster;
`top_gids` is the five highest-priority accounts, `;`-separated.

**`top_nodes.csv`** — `rank, gid, role, priority_score, why`, 30 rows, ranks
1..N.

The exports are written **in English**: the jury checks the schema mechanically
and the forbidden-word list is defined in English. The interface translates the
evidence on the fly by rebuilding it from the `rule_trace`.

---

## 14. Reproducibility

* Thresholds and weights are in `config.yaml`, each with the distribution it
  came from. No magic numbers in the code.
* No gid is hardcoded. A test greps `src/` and `app/` for 5+ digit literals and
  fails on anything that is not a declared config value.
* One seed (`seed: 42`) drives Louvain, the stability sampling and the map
  layouts. A test runs the computation twice and compares file hashes.
* **Agent-chosen thresholds are persisted, not re-sampled.**
  `config.calibrated.yaml` is committed, so a run on a reviewer's machine uses
  exactly the numbers the calibrator picked here. `--recalibrate` is the
  explicit opt-in to change them.
* Versions are pinned in `requirements.txt`. No cloud, GPU or paid service.
* Announced facts are checked, not trusted: §1 of `profile_report.md` compares
  every figure from the brief against the files and flags mismatches loudly.

---

## 15. Wording and privacy

Every generated string — `evidence`, `why`, `hypothesis`, the data-request
brief, every agent answer — is phrased as a hypothesis for verification ("signs
of consolidation", "pattern consistent with transit", "candidate for review"),
never as a statement about a person. The words *criminal*, *guilty*,
*launderer*, *organizer is* and *confirmed* are blacklisted in `config.yaml`,
checked in each agent's validator, again before the exports are written, and in
the tests.

The data is anonymized: `gid` is a synthetic identifier. No names, ages,
genders, incomes or organizations are used, and the agent prompts explicitly
forbid inventing them.

---

## 16. Limitations of the approach

* **Seed attribution is a heuristic.** Money is fungible: once two inflows mix,
  no export can say which tenge went where. `seed_kzt_attributed` is an
  upper-bound-style estimate of exposure, not an accounting fact.
* **Thresholds are defensible, not optimal.** They come from observed
  percentiles and are deliberately round. There is no ground truth to tune
  against, and tuning to decimals would only look more precise.
* **`terminal` is broad.** Half the graph qualifies, because most leaves simply
  had nothing above the floor leaving them. Correct and nearly uninformative —
  hence its low weight in the priority score.
* **Direction is dropped for clustering.** Stated above; it affects grouping
  only.
* **One month, one bank.** Nothing here distinguishes a persistent structure
  from a single month's coincidence.
* **No validation.** With no labels, every output is a prioritization aid for an
  analyst, not an established fact.

---

## 17. Scaling to ~1M nodes

In the order things would bite:

1. **Betweenness goes first.** Exact computation is O(VE) and is already the
   most expensive stage. At 1M nodes: sampled approximation (`k≈1000` pivots) or
   drop it — it feeds no rule, only context.
2. **Graph library.** `networkx` stores a Python object per node. Moving to
   `python-igraph` or `graph-tool` (C cores, 10–100× faster) does not touch the
   rule logic, which reads only per-node scalars.
3. **Louvain → Leiden.** Leiden guarantees well-connected communities and is
   faster at scale; `igraph` ships it. The stability check would sample
   components rather than re-running globally.
4. **Attribution becomes sparse linear algebra.** The current round-based
   propagation is a sparse matrix-vector product in disguise: `scipy.sparse`
   with `MAX_DEPTH+1` multiplications, or one `spsolve` on `(I − αA)`.
   `seed_reach` becomes a bitset product per component.
5. **I/O.** DuckDB or Polars over the parquet files with predicate pushdown, so
   ingestion never materializes the full frame.
6. **Per-component parallelism.** The graph is already disconnected — 16
   components here. Features, roles and clustering are component-local.
7. **Thresholds are already percentile-derived**, so they rescale
   automatically. That is why the report states them as percentiles rather than
   as fitted constants.
8. **The viewer stops loading the graph.** A precomputed backend — Neo4j or a
   parquet-backed adjacency index — answering ego queries on demand. The
   viewer's contract is already "read only what was exported", so only the
   storage layer changes.
9. **The agent layer barely changes.** It is bounded by the number of accounts
   examined — the shortlist plus cluster leaders — not by graph size.

---

## 18. Repository layout

```
.
├── agent_run.sh                 # ONE command: install → compute → verify → interface
├── run.py                       # computation entry point
├── config.yaml                  # thresholds, weights, agents, budgets, pricing
├── config.calibrated.yaml       # agent-chosen thresholds (generated, COMMITTED)
├── requirements.txt             # pinned versions
├── .env.example                 # three model setups
├── Makefile                     # make run | offline | existing | test
├── guideline.md                 # the working brief
├── README.md / README.ru.md / README.kk.md
├── data/                        # organizers' input files            (read-only)
├── starter/                     # organizers' starter code           (read-only)
├── src/moneygraph/
│   ├── schema.py                # file discovery and column matching
│   ├── io.py                    # canonical Dataset and provenance
│   ├── profile.py               # data profile report
│   ├── graph.py                 # DiGraph over every gid
│   ├── features.py              # degrees, flows, centrality
│   ├── temporal.py              # lag, fast pass-through, synchronized collection
│   ├── attribution.py           # seed_reach, seed_kzt_attributed
│   ├── roles.py                 # the rule engine and RuleTrace
│   ├── clustering.py            # Louvain and stability
│   ├── priority.py              # weighted percentile sum
│   ├── evidence.py              # templates and the wording validator
│   ├── i18n.py                  # three interface languages and evidence
│   ├── export.py                # the deliverables
│   ├── trace.py                 # time, tokens, spend
│   ├── pipeline.py              # orchestration only
│   └── agents/
│       ├── base.py              # agent framework: plan → act → validate → fall back
│       ├── orchestrator.py      # the crew and agent_log.md
│       ├── llm.py               # traced, budget-aware provider client
│       ├── tools.py             # deterministic graph functions
│       ├── calibrator_agent.py  # chooses role thresholds
│       ├── investigator_agent.py# multi-step dossiers
│       ├── critic_agent.py      # the argument against the shortlist
│       ├── ingest_agent.py      # unfamiliar input schemas
│       ├── narrator_agent.py    # RuleTrace → text, validated
│       ├── analyst_agent.py     # natural-language questions
│       └── review_agent.py      # data-request brief
├── app/app.py                   # Gradio interface (en / ru / kk)
├── docs/
│   ├── diagram.md               # solution diagram (Mermaid)
│   └── case_brief.docx          # the organizers' case description
├── output_files/                # computation results
└── tests/test_outputs.py        # 73 tests
```
