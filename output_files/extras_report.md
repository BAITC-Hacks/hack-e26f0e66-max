# Optional analyses

Computed from structure, amounts and dates only. **None of this changes a role, a score or a rank** — these are flags and context shown next to an account, as the brief requires.

## Anomaly flags

- **9** accounts send mostly amounts just above the reporting floor. That is what structuring looks like from the side that is visible; below the floor nothing is.
- **0** accounts send almost entirely round-number amounts.
- **48** accounts have an inflow that is extreme *for their own hop* — the only fair comparison, since hop drives most of the distribution.
- **57** accounts carry at least one flag.

## Return flows (cycles)

**At least 200** directed cycles within the length bound — money returning to someone who sent it. A two-cycle is ordinary mutual settlement; longer ones carrying real amounts are worth a look.

> Enumeration stopped at 200 cycles, so this is a lower bound, not a total. The ones listed are the ones whose narrowest hop carries the most money.

| Length | Accounts | Narrowest hop |
|---:|---|---:|
| 2 | 100000005171642100 → 100000004221668100 | 683,600 KZT |
| 2 | 100000001872484100 → 100000008601794100 | 475,400 KZT |
| 2 | 100000004603109100 → 100000002224132100 | 300,000 KZT |
| 2 | 100000002958343100 → 100000000274067100 | 300,000 KZT |
| 3 | 100000004979498100 → 100000008571433100 → 100000004135268100 | 200,000 KZT |

## Recurring routes

**At least 50** A→B→C chains where B forwarded within three days of receiving, more than once. Listing is capped; this is a lower bound.

| Route | Times | Amount |
|---|---:|---:|
| 100000008314203100 → 100000008637537100 → 100000001732159100 | 74 | 2,300,000 KZT |
| 100000008637537100 → 100000001732159100 → 100000008314203100 | 37 | 3,336,200 KZT |
| 100000005287097100 → 100000003016635100 → 100000006518161100 | 36 | 531,200 KZT |
| 100000000437046100 → 100000007055802100 → 100000004299488100 | 35 | 2,353,000 KZT |
| 100000005287097100 → 100000003016635100 → 100000000667713100 | 34 | 427,800 KZT |

## Network resilience

Baseline: largest connected component **1877** accounts, **35** components, **1233** accounts still reachable from a seed at three hops or more.

Removing the top-N by priority, against removing N accounts at random. The baseline is the point: any graph fragments if enough of it is deleted, so the question is whether removing *these* accounts does more damage than removing any N.

| Removed | Largest component | Drop | Random drop | Advantage |
|---:|---:|---:|---:|---:|
| 5 | 1858 | 1.0% | 0.4% | +0.6 pp |
| 10 | 1830 | 2.5% | 0.7% | +1.8 pp |
| 20 | 1814 | 3.4% | 1.4% | +2.0 pp |

A positive advantage means the priority ranking is finding accounts that actually hold the network together.
