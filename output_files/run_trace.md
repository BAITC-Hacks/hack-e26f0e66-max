# Run trace

## Latency

- **Total runtime: 59.01 s** (budget 300 s — within)
- Of which spent waiting on the model: 144.71 s

| Stage | Seconds | Share | LLM calls |
|---|---:|---:|---:|
| ingest | 0.03 | 0% | 0 |
| profile | 0.02 | 0% | 0 |
| graph | 0.04 | 0% | 0 |
| features | 0.99 | 2% | 0 |
| temporal | 0.08 | 0% | 0 |
| attribution | 0.01 | 0% | 0 |
| agent:planner | 4.91 | 8% | 1 |
| agent:calibrator | 0.00 | 0% | 0 |
| roles:base | 0.02 | 0% | 0 |
| clustering | 0.39 | 1% | 0 |
| roles:coordinator | 0.02 | 0% | 0 |
| priority | 0.00 | 0% | 0 |
| extras | 0.13 | 0% | 0 |
| evidence:templates | 0.06 | 0% | 0 |
| agent:investigator | 28.97 | 49% | 36 |
| agent:critic | 15.76 | 27% | 1 |
| agent:reviewer | 7.32 | 12% | 1 |
| export | 0.08 | 0% | 0 |

## Tokens and spend

- Calls: **39** (0 failed)
- Tokens: **79,065** (73,118 in / 5,947 out, 516 reasoning, 53,060 cached)
- Spend: **$0.1102**

| Agent | Calls | In | Out | Reasoning | Seconds | Cost |
|---|---:|---:|---:|---:|---:|---:|
| critic | 1 | 5,366 | 1,235 | 116 | 15.75 | $0.0231 |
| investigator | 36 | 66,034 | 3,962 | 252 | 116.74 | $0.0781 |
| planner | 1 | 639 | 196 | 80 | 4.91 | $0.0032 |
| reviewer | 1 | 1,079 | 554 | 68 | 7.32 | $0.0058 |
