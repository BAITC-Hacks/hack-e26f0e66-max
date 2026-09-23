# Solution diagram

Data → metrics → roles → interface, with the agent crew where it actually sits:
**agents run the investigation, the rule engine is the adjudicator.**

```mermaid
flowchart TD
    subgraph IN["Input — any tabular export, read-only"]
        F1[edges-like file]
        F2[transactions-like file]
        F3[nodes-like file]
    end

    F1 --> SC[schema.py<br/>discover · alias match ·<br/>structural inference]
    F2 --> SC
    F3 --> SC
    SC -. ambiguous columns only .-> A0([INGEST AGENT<br/>proposes a column name])
    A0 -. re-validated against the data .-> SC

    SC --> IO[io.py<br/>canonical Dataset ·<br/>derive missing nodes/depth/seeds ·<br/>provenance]
    IO --> PF[profile.py<br/>announced facts checked ·<br/>full percentile tables]

    PF --> A1([PLANNER AGENT<br/>reads the profile, decides<br/>which passes this dataset<br/>is worth · sets depth])

    IO --> G[graph.py] --> FE[features.py]
    IO --> TE[temporal.py]
    G --> AT[attribution.py]

    FE --> A2([CALIBRATOR AGENT<br/>chooses every role threshold<br/>from the distributions,<br/>writes a rationale for each])
    TE --> A2
    AT --> A2

    A2 --> SIM{{simulate against<br/>the real data}}
    SIM -- role emptied, or one role<br/>claims half the graph --> DEF[config.yaml defaults kept]
    SIM -- passes --> CAL[(config.calibrated.yaml<br/>committed -> reproducible)]

    CAL --> RE
    DEF --> RE
    RE[["RULE ENGINE — roles.py<br/>the ONLY thing that assigns a role<br/>formal gate · precedence · RuleTrace"]]

    RE --> CL[clustering.py<br/>Louvain seed=42 · stability x5]
    CL --> R2[roles.py pass 2<br/>coordinator]
    R2 --> PS[priority.py<br/>weighted percentile sum]
    PS --> EV[evidence.py<br/>templates from the RuleTrace]

    PS --> A3([INVESTIGATOR AGENT<br/>multi-step tool loop per<br/>priority account -> dossier,<br/>innocent explanation, next step])
    PS --> A4([CRITIC AGENT<br/>argues AGAINST the list:<br/>collection artifacts,<br/>threshold sensitivity])
    EV --> A5([NARRATOR AGENT<br/>rephrases only])
    A5 --> VAL{every number must<br/>appear in the RuleTrace}
    VAL -- fail --> EV
    VAL -- pass --> EX
    PS --> A6([REVIEWER AGENT<br/>what data is missing,<br/>what to request next])

    A3 --> EX[export.py]
    A4 --> EX
    A6 --> EX

    EX --> O1[nodes_roles.csv]
    EX --> O2[clusters.csv]
    EX --> O3[top_nodes.csv]
    EX --> O4[node_features.parquet<br/>+ graph_edges.parquet]
    EX --> O5[agent_log.md · review_notes.md ·<br/>dossiers.json · data_requests.md ·<br/>profile_report.md · run_trace.md]

    O1 --> V[app/app.py — Gradio<br/>overview · priority · gid search +<br/>ego map + RuleTrace · clusters ·<br/>ANALYST AGENT chat · agents · trace]
    O3 --> V
    O4 --> V
    O5 --> V
    V <--> A7([ANALYST AGENT<br/>natural-language Q&A])
    A7 --> TL[agents/tools.py<br/>deterministic graph functions]
    TL --> O1

    TR[[trace.py — every stage timed,<br/>every token counted, every call priced]]
    LOG[[agent_log.md — every agent's plan,<br/>tool calls, rejections, fallbacks]]

    classDef agent fill:#fff4d6,stroke:#c9931f,stroke-width:2px
    classDef core fill:#e8f0fe,stroke:#3b6fb5,stroke-width:3px
    classDef out fill:#e9f7ec,stroke:#3f8c56
    class A0,A1,A2,A3,A4,A5,A6,A7 agent
    class RE core
    class O1,O2,O3,O4,O5 out
```

## The contract in one line

**Agents decide what to examine and what the thresholds should be. The rule
engine decides what the role is.**

That is what lets this be an agentic system without producing "a role without an
explainable rule", which the case brief (§9) disqualifies. The jury still gets a
formal gate — `in_deg >= 5` — and can still be told in under a minute why any
gid got its role. What the crew adds is *the written reasoning for the 5*, a
case dossier, and a standing counter-argument.

| Agent | Decides | Guardrail |
|---|---|---|
| **planner** | which passes run on this dataset, and how deep | hard cap in config it cannot exceed |
| **calibrator** | every role threshold | must stay in a percentile-derived range; proposal is simulated and rejected if it empties a role or hands one half the graph; result is persisted so runs reproduce |
| **investigator** | what to look at around a priority account | every claim must come from a tool call; cited gids must exist |
| **critic** | what is *wrong* with the shortlist | may only cite accounts it was shown; cannot demote anything |
| **narrator** | wording | every number must appear in the RuleTrace |
| **ingest** | which column is which | re-validated against the data |
| **reviewer** | how to phrase the data requests | the gaps themselves are computed |
| **analyst** | which graph query answers a question | answers only from tool output; transcript shown |

**None of them can assign a role, a score, a cluster or a rank.** Every one has
a deterministic fallback, so `MONEYGRAPH_NO_LLM=1 python run.py` produces the
same three CSVs from the `config.yaml` thresholds.
