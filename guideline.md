# guideline.md — Money Graph (HackAlem AI)

This file is the working brief for Claude Code. Read it fully before writing any code, and re-read the relevant section before each phase. When something here conflicts with the organizers' `data/README.md` or the `starter/` code on a factual point (column names, dtypes, paths), the organizers' files win. Update this guideline to match, and tell the user.

---

## 1. Mission in one paragraph

An AML analyst at a second-tier bank has 81 "seed" customers known to have received drug-trafficking money. The bank exported those customers' **outgoing** transfers over **4 hops** (July 2026, intra-bank, only transactions ≥ 5,000 KZT). This produced a graph of 2,248 nodes and 3,119 aggregated edges. Money flows *away* from the seeds, so tracing goes **up** the hierarchy: couriers → collectors → controllers. We build a local, reproducible, explainable tool with three parts:

1. assign every node a role, a confidence score, a cluster and a priority score;
2. write three CSVs with a fixed schema;
3. provide a viewer where the analyst can search a gid and see its flows.

The tool must answer one question: **"Which of these 2,248 customers should I look at first, and why?"**

There is no ground truth. We are judged on **how well the criteria are justified**, how we handle the **announced data flaws**, **reproducibility**, and **explainability**, not on accuracy.

---

## 2. Hard constraints (violating any of these = disqualification or lost points)

- **One command** runs the full pipeline from raw `.parquet` to all three CSVs, with no manual steps. It must finish in **< 5 minutes** on an ordinary laptop (target: < 30 s).
- **No hardcoded gids** anywhere in `src/` or `app/`. Every list of gids must be computed. The only permitted literals are thresholds, and those live in `config.yaml`.
- **No black boxes.** Every role is a formal rule with thresholds. ML may only be used for the *optional* anomaly flag, and even then its features must be interpretable and it must not decide the role.
- **No external data or invented attributes** (no names, gender, age, income, organization). Use only structure, amounts and dates.
- **No cloud, GPU or paid service is required.** An optional LLM assistant may call an external API, but only when `ANTHROPIC_API_KEY` is set. Without the key, the pipeline and viewer must work fully, and the assistant must fall back to deterministic answers.
- **Careful wording.** Every evidence, why and hypothesis string is phrased as a hypothesis for verification ("signs of consolidation", "pattern consistent with transit"), never as a statement of guilt. Forbidden words in generated text: "criminal", "guilty", "launderer", "organizer is", "confirmed".
- **Determinism.** Fix all random seeds (Louvain, layouts). Two runs must produce byte-identical CSVs.
- **Never modify `data/` or `starter/`.** Treat them as read-only inputs.

---

## 3. First actions (Phase 0) — do these before designing anything

1. Read `data/README.md` and every file in `starter/`. Summarize for the user: the column names and dtypes of the three parquet files, what `depth` in `edges.parquet` refers to (the source's hop or the destination's hop), the date granularity in `transactions.parquet`, and what the starter code already provides (loaders, graph build, metrics, export templates). Reuse good starter code rather than rewriting it; wrap it inside our package.
2. Build `src/moneygraph/profile.py` and run it. It prints a data-profile report and saves it to `outputs/profile_report.md`. It must **assert or report** these facts from the brief and flag any mismatch loudly:
   - 2,248 nodes, 3,119 edges, 4,840 transactions;
   - 81 seeds; hop distribution 81 / 472 / 462 / 789 / 444;
   - total turnover 365,890,012 KZT (check both the edges sum and the transactions sum, and whether they agree);
   - 444 nodes with depth = 4 and zero outgoing edges;
   - 19 seeds absent from the edges entirely, and 12 seeds that appear only as recipients;
   - 16 weakly connected components (1,877 nodes with 46 seeds; 270 nodes with 1 seed; 14 more with 2–17 nodes), plus the 19 isolated seeds;
   - 354 nodes whose sent amount exceeds their received amount;
   - about 72 nodes with a pass-through ratio of 0.8–1.2;
   - nodes with 8–24 distinct payers, and nodes with 60–116 distinct recipients;
   - whether per-pair transaction sums reproduce `edges.sum_kzt` and `n_tx`;
   - self-loops, duplicate pairs, min/max dates, minimum amount (should be ≥ 5,000).
3. From the profile, print **distributions** (percentiles p50/p75/p90/p95/p99) of in-degree, out-degree, in_sum, out_sum and pass_ratio. Initial thresholds in `config.yaml` are set from these distributions, and the rationale is written next to each threshold as a YAML comment.
4. Commit: `chore: project skeleton, config, data profiling`.

---

## 4. Tech stack

- Python 3.10+.
- Core: `pandas`, `pyarrow`, `numpy`, `networkx>=3.2` (use `nx.community.louvain_communities(seed=42)` rather than an extra Louvain dependency), `pyyaml`.
- Viewer: `streamlit` and `pyvis`. Pyvis must use `cdn_resources="in_line"` so the map works offline.
- Optional assistant: `anthropic` (imported lazily, and only if the key exists).
- Tests: `pytest`.
- Pin exact versions in `requirements.txt`. Do not add heavy dependencies (no torch, no graph-tool, no Spark).

---

## 5. Repository layout

```
money-graph/
├── guideline.md                # this file (also referenced from CLAUDE.md)
├── CLAUDE.md                   # short pointer: "Follow guideline.md"
├── README.md                   # jury-facing documentation (see §13)
├── requirements.txt
├── Makefile                    # make setup | make run | make app | make test
├── run.py                      # ONE command entry point: python run.py
├── config.yaml                 # every threshold and weight, with rationale comments
├── data/                       # organizers' parquet files + README.md (read-only)
├── starter/                    # organizers' starter code (read-only)
├── src/moneygraph/
│   ├── __init__.py
│   ├── io.py                   # load parquet, normalize column names, validate schema
│   ├── profile.py              # Phase 0 data profiling report
│   ├── graph.py                # DiGraph build; ALL 2,248 nodes incl. isolated seeds
│   ├── features.py             # structural + flow metrics per node
│   ├── temporal.py             # pass-through lag, same-day bursts
│   ├── attribution.py          # seed-money propagation, seed_reach
│   ├── roles.py                # rule engine: gates, role_score, precedence
│   ├── clustering.py           # Louvain + singleton handling + hypotheses
│   ├── priority.py             # transparent weighted priority score
│   ├── evidence.py             # templated text, ≤200 chars, hypothesis wording
│   ├── extras.py               # optional: cycles/routes, resilience, completeness
│   ├── assistant.py            # optional: graph Q&A (deterministic + LLM)
│   ├── export.py               # write the 3 CSVs + node_features.parquet
│   └── pipeline.py             # orchestration, timing log
├── app/
│   └── app.py                  # Streamlit viewer
├── docs/
│   ├── diagram.md              # Mermaid: data → metrics → roles → interface
│   └── roles.md                # full rule table (can be embedded in README)
├── outputs/                    # generated; committed in the final submission
│   ├── nodes_roles.csv
│   ├── clusters.csv
│   ├── top_nodes.csv
│   ├── node_features.parquet   # all metrics, used by the viewer
│   └── profile_report.md
└── tests/
    └── test_outputs.py
```

`run.py` accepts `--data data/ --out outputs/ --config config.yaml`, with those as defaults. `python run.py` alone must work.

---

## 6. Graph construction rules (`graph.py`)

- Build a directed graph from `edges.parquet`, with edge attributes `sum_kzt`, `n_tx`, `depth`.
- **Add every gid from `nodes.parquet` as a node** so the 19 isolated seeds are present. Assert `G.number_of_nodes() == len(nodes)`.
- Node attributes: `depth`, `is_seed`, `component_id` (weakly connected component, numbered by size descending), `component_size`.
- `MAX_DEPTH` is read from the data (`nodes.depth.max()`), not hardcoded.
- Define `outflow_observed = depth < MAX_DEPTH`. Nodes at `MAX_DEPTH` were never expanded, so their outflow is **unknown**, not zero. (Verify with the profile whether any depth-4 node has outgoing edges. If some do, those edges point to nodes already discovered at lower depth. Document this.)
- Define `inflow_reliable = (not is_seed) and in_sum > 0`. Seeds' inflows are understated by construction.

---

## 7. Node features (`features.py`, `temporal.py`, `attribution.py`)

Compute, for every node (using NaN where undefined, never a silent 0):

- **Degree and flow:** `in_deg` (distinct payers), `out_deg` (distinct recipients), `in_sum`, `out_sum`, `n_tx_in`, `n_tx_out`, `seed_in_deg` (distinct seed payers).
- **Pass ratio:** `pass_ratio = out_sum / in_sum`, only where `inflow_reliable` and `outflow_observed`. Otherwise NaN, and the reason is recorded.
- **Fan metrics:** `fan_in_share` = in_deg / (in_deg + out_deg); `retention = 1 − min(pass_ratio, 1)`.
- **Temporal** (from transactions): `median_lag_days`, the median delay between an incoming transfer and the next outgoing transfer; `fast_pass_share`, the share of outgoing KZT sent within `transit_max_lag_days` (default 2) of a preceding inflow; `max_payers_same_day`, the maximum number of distinct payers on a single day (synchronized collection); `active_days`.
- **Seed attribution** (our original contribution, documented as a heuristic):
  - `seed_reach` is the number of distinct seeds that have a directed path to this node (BFS from each seed; cheap at this size).
  - `seed_kzt_attributed` is the amount of seed-originated money estimated to reach the node. Initialize each seed's outgoing edges with their full `sum_kzt`. For a non-seed node, split its attributed inflow across outgoing edges in proportion to edge amounts, scaled by `min(1, pass_ratio)`. Iterate `MAX_DEPTH + 1` rounds (this handles cycles without looping forever). Record this in the README as an upper-bound-style estimate, not an accounting fact.
- **Centrality:** `pagerank` (weighted by `log1p(sum_kzt)`), `betweenness` (exact; fine at this size), and `n_payer_clusters` (distinct clusters among payers, computed after clustering).
- **Role-context features** (second pass, after the base roles): `n_key_payers`, the number of payers whose role is consolidator, distributor or transit.

---

## 8. Role rules (`roles.py`)

All thresholds live in `config.yaml`. The values below are **starting points** that must be re-checked against the Phase 0 percentiles. Keep them round and explainable ("at least 5 distinct payers"), not fitted to decimals.

### 8.1 Allowed roles

Mandatory dictionary: `consolidator`, `transit`, `distributor`, `terminal`, `coordinator`, `peripheral`.

Documented extension (switchable with `use_extended_roles: true` in the config): **`cutoff`**. It means the node is at the maximum traversal depth, its onward flow was never traced, and no inflow-based role applies. If the switch is off, these nodes become `peripheral` with a cut-off note in the evidence. This extension is how we score the optional "cut-off artifact" item. It must be explained in the README.

### 8.2 Gates (a node is a *candidate* for a role only if its gate passes)

- **consolidator:** `in_deg ≥ cons_min_payers` (start: 5). Allowed at any depth, including MAX_DEPTH, because collection is visible from the inflow side alone. Strength grows up to `cons_strong_payers` (start: 10).
- **distributor:** `out_deg ≥ dist_min_recipients` (start: 10) AND `out_deg ≥ dist_fan_ratio × max(in_deg, 1)` (start: 3). Strength grows up to `dist_strong_recipients` (start: 50).
- **transit:** `inflow_reliable` AND `outflow_observed` AND `transit_ratio_low ≤ pass_ratio ≤ transit_ratio_high` (start: 0.8–1.2) AND `in_deg < cons_min_payers` AND `out_deg < dist_min_recipients`. Strength is boosted when `fast_pass_share ≥ 0.5`.
- **terminal:** `outflow_observed` AND `in_sum > 0` AND `out_sum ≤ terminal_max_pass × in_sum` (start: 0.1). **Never assigned to nodes at MAX_DEPTH.** This is the fix for the 444 false sinks.
- **coordinator** (second pass): (`n_key_payers ≥ coord_min_key_payers` (start: 2) AND `seed_reach ≥ coord_min_seed_reach` (start: 5)) OR (`seed_reach` ≥ the p99 of seed_reach AND `n_payer_clusters ≥ 2`). Rationale: a node where money from several collectors or many couriers converges is a candidate upper-level controller. Allowed at MAX_DEPTH.
- **cutoff:** depth == MAX_DEPTH AND no other gate passed.
- **peripheral:** nothing passed. This includes seeds with no observed transfers.

### 8.3 Seed handling

- Seeds never get `transit` or `terminal`, because their pass ratio is invalid.
- Seeds can be `distributor` (a courier fanning money out), `consolidator` (if they receive from several other seeds), or `peripheral`.
- The 19 isolated seeds get `peripheral` with the evidence "Known seed; no transfers ≥5,000 KZT observed in July 2026 export."

### 8.4 role_score (confidence, 0–1)

- For the winning gate: `role_score = 0.5 + 0.5 × clip((metric − threshold) / (strong − threshold), 0, 1)`, where `metric` is that role's main metric.
- Multiply by `0.8` when the node is at MAX_DEPTH (outflow unknown), and by `0.8` when the rule relied on an inflow side that is unreliable. Clip the result to [0, 1].
- For `peripheral`, the score expresses confidence that nothing is going on: `0.9` if the node has at most 1 edge, lower (`0.6`) if it has several edges but no gate passed.
- For `cutoff`: a fixed `0.7`, with the reason stated.

### 8.5 Precedence (when several gates pass)

`coordinator > consolidator > distributor > transit > terminal > cutoff > peripheral`.

Secondary roles that also passed are kept in a `secondary_roles` column in `node_features.parquet` and mentioned in the evidence when space allows (e.g. "also fans out to 14 recipients").

---

## 9. Clustering (`clustering.py`)

- Run Louvain on the **undirected** projection with weights `log1p(sum_kzt)`, `seed=42`, `resolution` taken from the config (start at 1.0).
- Isolated nodes and tiny components (< `min_cluster_size`, start: 3) are **not** merged into big clusters. Each small weakly connected component becomes its own cluster, and each isolated seed its own singleton cluster. Every node must have a `cluster_id`.
- Renumber clusters by `n_nodes` descending (cluster 0 is the largest), with ties broken by the smallest gid, for determinism.
- `clusters.csv` columns: `cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis`.
  - `sum_kzt_internal` is the sum of `sum_kzt` over edges with both ends in the cluster.
  - `top_gids` is the top 5 gids by priority_score, separated by `;`.
  - `hypothesis` is a **template-generated** sentence driven by the cluster's role mix and flows. Examples:
    - "Signs of a collection hub: money from 7 seeds converges on consolidator {gid} (41% of internal turnover)."
    - "Pattern consistent with a distribution layer: {gid} fans out to 63 recipients."
    - "Transit chain: 5 pass-through accounts forward funds within 2 days."
    - "Isolated known seed; no observed transfers."
  - Keep it ≤ 250 characters, in hypothesis wording.
- Also report cluster stability. Run Louvain with 5 different seeds and compute, for each final cluster, the share of node pairs that stay together. Put this in `node_features` or a log line, not in the fixed CSV schema. This supports the organizers' "8 stable communities with more than one seed".

---

## 10. Priority score (`priority.py`)

A transparent weighted sum of percentile-ranked components, clipped to 0–1. Default weights in the config:

- `w_role` 0.30 — role weight: coordinator 1.0, consolidator 0.9, distributor 0.6, transit 0.5, terminal 0.5, cutoff 0.3, peripheral 0.05;
- `w_seed_money` 0.25 — percentile of `seed_kzt_attributed`;
- `w_seed_reach` 0.20 — percentile of `seed_reach`;
- `w_payers` 0.15 — percentile of `in_deg`;
- `w_cluster` 0.10 — the cluster's seed density (n_seed / n_nodes, percentile).

Adjustments, each documented:

- **Known seeds × `seed_discount` (0.5).** Law enforcement already knows them; the analyst's value lies above them. This must be stated in the README.
- **MAX_DEPTH consolidators or coordinators × `cutoff_boost` (1.1, capped at 1).** The chain probably continues beyond the visible data, so these are the best candidates for a follow-up data request.

`top_nodes.csv` contains the top 30 by priority_score (at least 20 are required). Columns: `rank, gid, role, priority_score, why`. The `why` string names the two or three largest components in plain language, e.g. "Receives from 11 different payers incl. 4 seeds; forwards 3% of inflow; money from 9 seeds converges here."

---

## 11. Evidence text (`evidence.py`)

- One template per role, filled with the node's actual metrics. The metrics quoted must be exactly the ones the rule used, so the explanation can never contradict the logic.
- At most 200 characters (hard truncation at a word boundary, with "…"), never empty, English, no personal data.
- Format numbers readably: "1.2M KZT", "11 payers", "3%".
- Examples:
  - consolidator: "Receives from 11 distinct payers (4 seeds), 8.4M KZT; forwards 3% — signs of consolidation."
  - transit: "In 2.1M / out 2.0M KZT (ratio 0.95), 80% forwarded within 2 days — pattern consistent with transit."
  - terminal: "Receives 1.5M KZT from 2 payers, forwards <10%; outflow was traced (hop 2) — possible final recipient."
  - cutoff: "Hop-4 node: onward transfers were not traced (export limit). Receives 0.4M KZT from 1 payer."
  - coordinator: "Money from 14 seeds converges via 3 collector accounts — candidate upper-level node for review."

---

## 12. Viewer (`app/app.py`, Streamlit)

It reads only from `outputs/` (it never recomputes), so it starts instantly. Pages or tabs:

1. **Overview.** KPI cards (nodes, seeds, turnover, role counts, number of clusters), a role distribution chart, and a clusters table with hypotheses.
2. **Priority list.** `top_nodes.csv` as a sortable table; clicking a row (or choosing it in a selectbox) opens its node card.
3. **Node search** (the critical demo feature: the jury names a gid and we must show it within seconds). A gid text input leads to:
   - a **node card**: role, role_score, priority, cluster, depth, seed flag, all key metrics, evidence, secondary roles, and an auto-generated summary of what to pay attention to;
   - an **ego network** (1 or 2 hops, selectable) rendered with pyvis: arrows for flow direction, edge width proportional to log amount, edge label with the KZT amount, node color by role, a distinct shape for seeds, a dashed border for cutoff nodes, and the searched node enlarged;
   - tables of the node's payers and recipients with amounts and dates.
4. **Cluster map.** Choose a cluster and see its whole subgraph (the large cluster should render with physics stabilization off after a precomputed layout, or with a node cap and a warning).
5. **Assistant** (optional). A natural-language question, answered from the graph (see §14).

A legend explaining the colors and shapes must appear on every map. The map must work fully offline.

---

## 13. README (worth 25 points — write it as a deliverable, not an afterthought)

Required sections, in this order:

1. What it does (3 sentences) and a screenshot.
2. **Quick start**: `pip install -r requirements.txt` then `python run.py` then `streamlit run app/app.py`. Include the expected runtime and the list of generated files.
3. Project structure (tree).
4. Solution diagram (Mermaid from `docs/diagram.md`): data → validation → graph → metrics → roles → clusters → priority → exports → viewer.
5. **Data limitations and how we handle each one.** One paragraph per announced flaw: the hop-4 cut-off, outgoing-only tracing, understated seed inflows, the 5,000 KZT threshold, the 19 and 12 seed cases, the 16 components, no attributes, no ground truth.
6. **Role criteria.** The full rule table with thresholds, the percentile rationale for each, the precedence order, the role_score formula, and the `cutoff` extension.
7. Priority score formula and weights, with the rationale for the seed discount and the cut-off boost.
8. Clustering method and how the hypotheses are generated.
9. Output schemas for the three CSVs.
10. Worked examples: 3 nodes walked through from metrics to rule to role.
11. Optional features implemented.
12. **Limitations of the approach** (heuristic attribution, threshold sensitivity, no validation labels).
13. **Scaling to ~1M nodes**, in text: igraph or graph-tool in C, or GraphFrames/Spark for distributed runs; Leiden instead of Louvain; approximate betweenness (sampling) or dropping it; seed attribution as sparse matrix propagation (scipy.sparse); per-component parallelism; DuckDB/Polars for the parquet I/O; thresholds kept as percentiles so they rescale automatically; a precomputed viewer backend with a graph DB (e.g. Neo4j) and on-demand ego queries instead of loading the whole graph.
14. Wording and privacy statement.

---

## 14. Optional features (only after all must-haves pass the tests)

In order of value per hour:

1. **Cut-off separation.** Already built into the roles via `cutoff`; also report counts in the Overview.
2. **Temporal transit and synchronized collection.** Already covered by the features; surface them in the evidence and in the node card.
3. **Completeness assessment.** Per cluster and per top node, state what data is missing and what to request next. For example: "Request outgoing transfers of the 12 hop-4 consolidators (hop 5)"; "Request incoming transfers to seeds from outside the sample"; "Request transactions below 5,000 KZT for {gid}". Show this in the node card and as `outputs/data_requests.md`.
4. **Network resilience.** Remove the top-N nodes by priority (N = 5, 10, 20) and report the largest weakly connected component size, the number of components, and the share of seed money that still reaches depth ≥ 3. Compare against removing N random nodes as a baseline. Show a small chart in the Overview.
5. **Recurring routes and return flows.** `nx.simple_cycles` with `length_bound=5` for money returning to its sender; frequent A→B→C chains taken from dated transactions.
6. **Anomaly flags.** Amounts just above the 5,000 threshold, round-number amounts, and nodes whose profile is extreme for their hop (z-score within the depth group). These are shown as flags, not roles.
7. **Assistant.** Deterministic graph functions do the work: `node_card(gid)`, `payers(gids)`, `recipients(gids)`, `common_downstream(gids)` (answers "who collects money from these five?"), `path(a, b)`, `cluster_summary(id)`. If `ANTHROPIC_API_KEY` is set, the LLM only parses the question into a function call and phrases the answer, citing gids. Without the key, provide a simple form with a function dropdown and a gid-list input. The LLM must never invent facts; every answer must be traceable to function output.

---

## 15. Tests (`tests/test_outputs.py`) — run after every meaningful change

- `nodes_roles.csv` has exactly 2,248 rows, unique gids, and exactly the columns `gid, role, role_score, cluster_id, priority_score, evidence` in that order and with those dtypes.
- There are no nulls; evidence is non-empty and ≤ 200 characters; every role is in the allowed set; `role_score` and `priority_score` are in [0, 1].
- Every `cluster_id` in `nodes_roles.csv` exists in `clusters.csv`; the sum of `n_nodes` equals 2,248; the sum of `n_seed` equals 81.
- `top_nodes.csv` has at least 20 rows, ranks 1..N, and gids that exist in nodes_roles.
- **Cut-off check:** no node with depth == MAX_DEPTH has role `terminal`.
- **Seed check:** no seed has role `transit` or `terminal`.
- **Wording check:** no forbidden words (§2) appear in the evidence, why or hypothesis columns.
- **Determinism:** two consecutive runs produce identical CSVs (compare hashes).
- **Runtime:** the full pipeline finishes in < 300 s (assert, and print the timing).
- **Hardcoding guard:** grep `src/` and `app/` for integer literals with 5 or more digits that are not in the config, and fail if any look like gids.

---

## 16. Working rules for Claude Code

- Work in the phases below. Every commit must leave `python run.py` and `pytest` working.
- Before each phase, state a short plan. After it, report what changed, how many nodes landed in each role, and anything surprising in the data.
- Every threshold or weight goes in `config.yaml` with a comment explaining why. No magic numbers in the code.
- After changing any threshold, re-run and show the new role counts. Watch for degenerate outcomes (e.g. 0 coordinators, or 900 consolidators) and propose adjustments grounded in the data distributions.
- Keep functions small and pure (DataFrame in, DataFrame out). The pipeline is orchestration only.
- Log the timing of each stage.
- Do not ask for confirmation on routine steps. Do ask before deleting files, changing the output schema, or adding a dependency.

---

## 17. Phase plan (5-hour hackathon)

- **Phase 0 (0:00–0:30):** skeleton, `requirements.txt`, `config.yaml`, `io.py`, `profile.py`, the profile report. Commit.
- **Phase 1 (0:30–1:45):** graph, features, roles, clustering, priority, evidence, export, and `run.py`. All three CSVs valid, tests passing. Commit: `feat: end-to-end pipeline, all must-have exports`.
- **Phase 2 (1:45–2:45):** Streamlit viewer: overview, priority list, node search with ego map, cluster map. Commit.
- **Phase 3 (2:45–3:30):** README, `docs/diagram.md`, `docs/roles.md`, and 3 worked examples picked from the actual outputs (a consolidator, a cutoff node and a transit or coordinator node). Commit.
- **Phase 4 (3:30–4:30):** optional features in the §14 order, each committed separately.
- **Phase 5 (4:30–5:00):** freeze. Clean-machine test (fresh venv, `pip install -r requirements.txt`, `python run.py`, `pytest`, `streamlit run`), final outputs committed, and demo notes written to `docs/demo_script.md` (a live run, then 2–3 nodes walked through, then one optional feature).

---

## 18. Definition of done

- [ ] `python run.py` on a clean environment creates the 3 CSVs in < 5 minutes.
- [ ] All tests in §15 pass.
- [ ] Every role has a written rule with thresholds in the README, and any gid can be explained in under 1 minute from the node card.
- [ ] The viewer finds any gid and shows its directed links, roles and amounts.
- [ ] The README contains the limitations, how each data flaw is handled, and the scaling section.
- [ ] The solution diagram is present.
- [ ] All generated text is phrased as hypotheses; no personal data is assumed.