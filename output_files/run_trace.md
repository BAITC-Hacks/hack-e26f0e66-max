# Run trace

## Latency

- **Total runtime: 159.51 s** (budget 300 s — within)
- Of which spent waiting on the model: 157.42 s

| Stage | Seconds | Share | LLM calls |
|---|---:|---:|---:|
| ingest | 0.03 | 0% | 0 |
| profile | 0.02 | 0% | 0 |
| graph | 0.04 | 0% | 0 |
| features | 0.98 | 1% | 0 |
| temporal | 0.08 | 0% | 0 |
| attribution | 0.01 | 0% | 0 |
| agent:planner | 5.96 | 4% | 1 |
| roles:base | 0.02 | 0% | 0 |
| clustering | 0.39 | 0% | 0 |
| roles:coordinator | 0.02 | 0% | 0 |
| priority | 0.00 | 0% | 0 |
| evidence:templates | 0.06 | 0% | 0 |
| agent:investigator | 125.16 | 78% | 49 |
| agent:critic | 16.88 | 11% | 1 |
| agent:reviewer | 9.61 | 6% | 1 |
| export | 0.09 | 0% | 0 |

## Tokens and spend

- Calls: **52** (0 failed)
- Tokens: **113,291** (105,674 in / 7,617 out, 1,367 reasoning, 58,781 cached)
- Spend: **$0.0091**

| Agent | Calls | In | Out | Reasoning | Seconds | Cost |
|---|---:|---:|---:|---:|---:|---:|
| critic | 1 | 5,366 | 1,471 | 274 | 16.87 | $0.0013 |
| investigator | 49 | 98,590 | 4,945 | 533 | 124.98 | $0.0071 |
| planner | 1 | 639 | 409 | 295 | 5.96 | $0.0003 |
| reviewer | 1 | 1,079 | 792 | 265 | 9.61 | $0.0004 |

## Warnings

- `terminal` claims 1129 of 2248 nodes (50%) — the gate may be too loose to be informative
- stage 'agent:investigator' used 42% of the 300s latency budget
