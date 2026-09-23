# Run trace

## Latency

- **Total runtime: 1.77 s** (budget 300 s — within)
- Of which spent waiting on the model: 0.00 s

| Stage | Seconds | Share | LLM calls |
|---|---:|---:|---:|
| ingest | 0.03 | 2% | 0 |
| profile | 0.02 | 1% | 0 |
| graph | 0.03 | 2% | 0 |
| features | 0.88 | 50% | 0 |
| temporal | 0.08 | 5% | 0 |
| attribution | 0.01 | 1% | 0 |
| agent:planner | 0.00 | 0% | 0 |
| agent:calibrator | 0.00 | 0% | 0 |
| roles:base | 0.01 | 1% | 0 |
| clustering | 0.42 | 23% | 0 |
| roles:coordinator | 0.02 | 1% | 0 |
| priority | 0.00 | 0% | 0 |
| extras | 0.13 | 8% | 0 |
| evidence:templates | 0.06 | 4% | 0 |
| agent:critic | 0.00 | 0% | 0 |
| agent:reviewer | 0.00 | 0% | 0 |
| export | 0.06 | 3% | 0 |

## Tokens and spend

No model calls were made — this run was fully deterministic (no API key, `llm.enabled: false`, or `MONEYGRAPH_NO_LLM=1`).

Cost of this run: **$0.00**.
