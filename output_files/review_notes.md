# Review notes: what is wrong with this list

Written against the priority list, not in support of it. Read it before acting on the rankings.

## Verdict

Treat the ranking as a set of candidates for review, not a reliable ordering of behavioural concern. Boundary-dependent roles, incomplete flow coverage, and apparent inconsistencies in the reported figures warrant checking source transactions and calculations before prioritizing by score.

## Entries that may be collection artifacts

**HIGH** — accounts 100000004015047100, 100000002718366100, 100000001253557100, 100000001303311100, 100000001282143100

> These highly ranked coordinator candidates forward 8% or 0% of observed inflow. A one-month, outgoing-only export can make retained balances or transfers outside July look like network endpoints; seed reach establishes a possible path, not coordinated behaviour.

**MEDIUM** — accounts 100000002957306100, 100000002894076100, 100000001924185100, 100000003404627100, 100000004105288100, 100000001072022100, 100000002605548100, 100000005778283100, 100000003158727100, 100000005432267100

> These terminal candidates have no observed onward transfers, but none is marked at the depth-four frontier. Their zero outflow is therefore not explained by the stated frontier cutoff; it could still reflect ordinary receipt, transfers after July, or onward payments below 5,000 KZT. Check depth and export coverage before treating terminal status as behavioural evidence.

**HIGH** — accounts 100000007594394100, 100000004156082100, 100000008547948100, 100000002224132100

> Observed outflow substantially exceeds observed inflow, a pattern consistent with opening balances, inflows outside the sampled paths, or other funding rather than rapid forwarding of the displayed inflows. The quoted 999% forwarding figure for 100000008547948100 also conflicts with its displayed sums: 5,185,600 / 212,665 is about 2,438%.

**HIGH** — accounts 100000003404627100, 100000002957306100, 100000001924185100

> The stated estimated seed-originated flow exceeds displayed total inflow for these candidates. Verify what the estimate measures and whether paths are counted more than once before using it to justify their ranks.

## Thresholds carrying more weight than they should

**`consolidator.min_payers`** — Raising the five-payer minimum to six removes the displayed payer-count basis for consolidator status and, where applicable, the required coordinator gate. Recheck resulting roles rather than treating current labels as stable.

Affects 8 of the listed accounts: 100000001253557100, 100000002838861100, 100000004156082100, 100000001303311100, 100000001282143100, 100000008144528100, 100000002224132100, 100000008244300100

**`consolidator.min_payers`** — Raising the minimum from five to six would not affect these six-payer candidates, but a further one-payer step from six to seven would remove their displayed payer-count basis. This distinguishes them from candidates already on the current boundary.

Affects 7 of the listed accounts: 100000002718366100, 100000007594394100, 100000004299488100, 100000007055802100, 100000008547948100, 100000002547110100, 100000008686313100

**`terminal.max_pass`** — Reducing the maximum pass fraction from 0.1 to 0.0 would change whether the 8%-forwarding candidate meets that particular terminal criterion; its displayed coordinator label need not change.

Affects 1 of the listed accounts: 100000004015047100

## Blind spots

- No top-30 candidate is marked at the depth-four frontier, although 444 accounts are there. Inspect those omitted candidates separately: their onward flow is unknown by construction, so neither a terminal label nor their absence from this ranking establishes low relevance.
- Starting-account inflows from outside the sample are absent. Consequently, the export cannot show the full funding side of paths reaching the listed candidates, and seed reach should not be read as the number of independent funding sources.
- Transfers below 5,000 KZT and activity outside July are absent. Check whether the zero-outflow and low-forwarding candidates made smaller or later onward transfers before interpreting the pattern.
- The displayed list contains no timing or counterparty-cluster detail with which to audit transit lag, fast-pass share, or coordinator payer-cluster gates. Those threshold conclusions cannot be sensitivity-tested from these rows.

