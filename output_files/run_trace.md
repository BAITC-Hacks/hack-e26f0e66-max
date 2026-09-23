# Run trace

## Latency

- **Total runtime: 49.12 s** (budget 300 s — within)
- Of which spent waiting on the model: 106.03 s

| Stage | Seconds | Share | LLM calls |
|---|---:|---:|---:|
| ingest | 0.03 | 0% | 0 |
| profile | 0.02 | 0% | 0 |
| graph | 0.04 | 0% | 0 |
| features | 0.98 | 2% | 0 |
| temporal | 0.08 | 0% | 0 |
| attribution | 0.01 | 0% | 0 |
| agent:planner | 4.92 | 10% | 1 |
| roles:base | 0.02 | 0% | 0 |
| clustering | 0.38 | 1% | 0 |
| roles:coordinator | 0.02 | 0% | 0 |
| priority | 0.00 | 0% | 0 |
| evidence:templates | 0.06 | 0% | 0 |
| agent:investigator | 19.56 | 40% | 26 |
| agent:critic | 15.67 | 32% | 1 |
| agent:reviewer | 7.08 | 14% | 1 |
| export | 0.09 | 0% | 0 |

## Tokens and spend

- Calls: **29** (0 failed)
- Tokens: **59,349** (54,350 in / 4,999 out, 481 reasoning, 49,419 cached)
- Spend: **$0.0697**

| Agent | Calls | In | Out | Reasoning | Seconds | Cost |
|---|---:|---:|---:|---:|---:|---:|
| critic | 1 | 5,366 | 1,199 | 98 | 15.66 | $0.0131 |
| investigator | 26 | 47,266 | 3,181 | 195 | 78.38 | $0.0490 |
| planner | 1 | 639 | 196 | 83 | 4.92 | $0.0032 |
| reviewer | 1 | 1,079 | 423 | 105 | 7.08 | $0.0045 |

## Warnings

- `terminal` claims 1129 of 2248 nodes (50%) — the gate may be too loose to be informative
