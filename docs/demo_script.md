# Demo script — 5 minutes

**Track 2 — Finances.** HackAlem AI: *Money Graph — reconstructing the
financial structure of an organized group from a transaction network.*

The brief asks for "a live run and a substantive walkthrough of 2–3 nodes".
This is that, timed, with the actual account numbers from the committed run.

> Every figure below is reproducible: run `./agent_run.sh --offline --no-app`
> and the same accounts come out, because the pipeline is deterministic and the
> agent-chosen thresholds are committed in `config.calibrated.yaml`.

---

## Before you start

```bash
./agent_run.sh --use-existing      # opens the interface on the committed results
```

Have the browser open on the **Who to review first** tab. If you intend to show
a live run instead, open a second terminal ready with `./agent_run.sh`.

---

## 0:00 — 0:45 · The problem in one breath

> "Police give the bank 81 customers who received drug money. That is the
> **bottom** of the chain — the couriers. Who collects from them, who moves it,
> who controls it, an analyst reconstructs by hand: hours per account.
>
> We took the bank's export — those 81 customers' outgoing transfers, four hops
> deep, 2,248 accounts — and answer one question: **which of these 2,248 do I
> look at first, and why.**"

---

## 0:45 — 1:30 · Live run

```bash
./agent_run.sh --offline
```

Talk over it:

> "One command. It builds the environment, runs the pipeline, checks the three
> required CSVs itself, and opens the interface.
>
> **1.7 seconds** against the five-minute limit. `--offline` means no AI calls
> at all — I want to show first that the classification is fully deterministic.
> The AI layer changes the prose, not the roles."

Point at the role histogram as it prints:

> "2,248 accounts, every one classified. 10 coordinators at the top — 0.4%.
> And 444 `cutoff`: those are the hop-4 accounts where the export simply
> stopped. We will come back to them, because they are the trap in this case."

---

## 1:30 — 3:15 · Three accounts

Go to **Account detail**. This is the part the brief asks the jury to test:
*"the jury names 3 arbitrary gids; within a minute the team explains why the
role is what it is."*

### Account 1 — `100000004015047100` · coordinator · priority 0.975

Paste it. Read straight off the card:

> "Top of the list. The rule that fired is right here:
>
> `in_deg 9 >= 5 (collection point) and 3 payers are themselves collectors (>= 2) and seed_reach 11 >= p90 (9)`
>
> Three conditions. It receives from **9** different payers, so it is itself a
> collection point. **3 of those payers are collectors in their own right** —
> it collects from collectors, not from couriers. And **11 of the 81 seeds**
> can reach it, which is the top decile.
>
> No model assigned that. It is a comparison against thresholds in a config
> file, and those numbers are the ones the comparison used."

Point at the map:

> "Arrows are direction of money. Black outline is the account we searched.
> Diamonds are the known seeds."

### Account 2 — `100000005075949100` · cutoff · hop 4

> "This is the trap. It received **2.2M KZT** and sends nothing. The naive rule
> — out-degree zero means the money stopped — produces **444 false final
> recipients**, because these accounts sit at the four-hop edge where the
> export stopped. Their outgoing transfers were **never requested**.
>
> So we never call them `terminal`. They get their own role, `cutoff`, their
> confidence is discounted, and the card says in plain language that we do not
> know. And if such an account also collects, we *raise* its priority — the
> chain most likely continues right there, and that is the best possible
> hop-5 data request."

### Account 3 — `100000004135268100` · transit

> "In 1.24M, out 1.00M, ratio 0.81 — money arrives and moves on. The rule needs
> both sides of that ratio to be trustworthy, which is why seeds are barred
> from this role: the export was built *from* them, so their inflow is missing
> by construction. We return NaN rather than a zero that would look like a
> finding."

---

## 3:15 — 4:15 · Agentic, but not a black box

Go to **How it decided**.

> "The brief says a role without an explainable rule does not count. It also
> scores agentic AI. Those only conflict if agents assign the roles — so ours
> do not.
>
> **Agents run the investigation. The rule engine is the adjudicator.**"

Point at the threshold table:

> "An agent chose every one of these thresholds and wrote the justification
> next to it. Before any set is accepted it is **simulated against the real
> distribution** — a set that empties a role, or hands one role half the
> network, is rejected and the hand-set defaults stand. The accepted set is
> committed, so your run reproduces exactly these numbers."

Scroll to the critic's notes:

> "And this agent's whole job is to attack our own list. It found something we
> had not: several high-ranked accounts show zero outflow but are *not* at the
> frontier — so the export did request their transfers and found nothing above
> the 5,000 floor. Zero outflow there means 'nothing reportable', not 'the
> money stopped'.
>
> With no ground truth, a written argument against your own result is the
> closest thing to validation that exists."

---

## 4:15 — 4:45 · Ask it something

Go to **Ask**:

> "Which collection points sit at the edge of the export?"

> "Plain language in, and the answer is assembled only from deterministic graph
> queries — which are listed underneath. It cannot invent an account number: one
> that does not exist gets dropped."

---

## 4:45 — 5:00 · Close

> "Three CSVs in the required schema. 1.7 seconds offline, about 90 seconds with
> the full agent crew, at twenty-one cents. 74 tests, including one that runs
> the pipeline twice and compares file hashes.
>
> It runs on any tabular export, not just these three files. It speaks English,
> Russian and Kazakh. And every number on every screen traces back to a rule you
> can read."

---

## If a juror names their own gid

That is the designed path — **Account detail**, paste, read the rule line. Three
things to say, whatever the account:

1. **The rule that fired**, verbatim from the card — it names the metric, the
   value and the threshold.
2. **Whether the outflow was observed.** If the card shows the frontier warning,
   say we do not know rather than guessing.
3. **The innocent explanation.** For top accounts the investigator's dossier
   supplies one. A payroll account and a collection point look identical in
   this data, and saying so is the honest answer.

## If something breaks

* Interface will not start → `./agent_run.sh --use-existing --no-share`
* No key / no network → `./agent_run.sh --offline`; exports are identical
* Need the raw rule for an account, no UI:

```bash
.venv/bin/python - <<'PY'
import json, pandas as pd
f = pd.read_parquet("output_files/node_features.parquet").set_index("gid", drop=False)
gid = 100000004015047100          # replace with the one you were asked about
print(json.dumps(json.loads(f.at[gid, "rule_trace"]), indent=2))
PY
```

---

## Numbers worth having memorised

| | |
|---|---|
| Accounts / edges / transactions | 2,248 / 3,119 / 4,840 |
| Known seeds | 81, of which 19 have no transfers at all |
| Roles | terminal 1,100 · peripheral 540 · cutoff 444 · transit 67 · distributor 46 · consolidator 41 · **coordinator 10** |
| Clusters | 88, stability 0.95 mean over 5 seeds |
| Runtime | 1.7 s offline · ~90 s with the agent crew |
| Cost of a full agentic run | ~$0.21 on `gpt-6-sol` |
| Tests | 74 |
