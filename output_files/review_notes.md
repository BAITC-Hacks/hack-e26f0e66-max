# Review notes: what is wrong with this list

Written against the priority list, not in support of it. Read it before acting on the rankings.

## Verdict

Treat this as a candidate-review queue, not reliable evidence of the assigned roles. Several ranks rest on path estimates, observed stopping points, or inflow/outflow ratios that the collection design cannot substantiate; check the underlying transfers and rerun the thresholds before prioritizing action.

## Entries that may be collection artifacts

**HIGH** — accounts 100000004015047100, 100000003115284100, 100000002718366100, 100000001253557100, 100000001303311100, 100000001282143100

> These high-ranked coordinator candidates have 0–24% observed forwarding. Seed reach means a path exists from a starting account; it does not establish that the estimated seed-originated amount was received and passed onward. The outgoing-only, one-month export also permits ordinary receipt or holding of funds as an explanation.

**MEDIUM** — accounts 100000002957306100, 100000002894076100, 100000001924185100, 100000003404627100, 100000004105288100, 100000001072022100, 100000002605548100, 100000005778283100, 100000003158727100, 100000005432267100

> These terminal candidates all have zero observed outflow, but none is marked at the depth frontier. Their apparent stopping point could instead reflect transfers below 5,000 KZT, transfers after July, or no onward transfer; the export cannot distinguish those explanations. No shown entry is marked at the frontier, so the 444 depth-cutoff accounts cannot be identified or criticized by gid here.

**HIGH** — accounts 100000007594394100, 100000004156082100, 100000008547948100, 100000002224132100, 100000008730846100

> Observed outflow exceeds observed inflow by 234%–854% according to the stated reasons, consistent with funding outside the captured incoming paths or an opening balance rather than forwarding the sampled inflows. For 100000008547948100, the stated 999% also conflicts with the displayed sums: 5,185,600 / 212,665 is about 2,438%. Verify the calculations before relying on these ranks.

**HIGH** — accounts 100000003404627100, 100000002957306100, 100000001924185100

> The stated estimated seed-originated amounts exceed each account's displayed total inflow. That is not an observed cash-flow balance; it is a sign that the path-based estimate needs validation before it supports priority.

## Thresholds carrying more weight than they should

**`consolidator.min_payers`** — Raising the minimum from 5 to 6 would remove the displayed five-payer basis for these consolidator or coordinator labels; coordinator status may depend on the consolidator gate. Their final labels need recomputation, not an assumed replacement.

Affects 8 of the listed accounts: 100000001253557100, 100000001303311100, 100000001282143100, 100000002838861100, 100000004156082100, 100000008144528100, 100000008244300100, 100000002224132100

**`terminal.max_pass`** — Raising the maximum observed pass share from 5% to 10% could make the approximately 8% and 6% forwarding accounts terminal-eligible. Whether role precedence changes their displayed labels requires a rerun.

Affects 2 of the listed accounts: 100000004015047100, 100000002398779100

**`distributor.strong_recipients`** — Raising the strong-recipient cutoff from 25 to 26 would not remove the displayed 26-recipient evidence for these accounts. This particular one-step change is not a supported objection to their recipient counts, although their displayed consolidator labels still merit checking against the distributor rule.

Affects 2 of the listed accounts: 100000004156082100, 100000008547948100

## Blind spots

- A fuller network could show outside inflows or opening balances explaining the excess outflows of 100000007594394100 and 100000008547948100; incoming transfers to the 81 starting accounts from outside the sample were not collected.
- A fuller network could show onward transfers from some of the 444 depth-four accounts, but no displayed gid is flagged at the frontier. The fixed-depth crawl, rather than observed stopping behavior, explains why that onward activity is absent.
- Smaller or later transfers could change the apparent zero-outflow pattern for 100000002718366100 and 100000003404627100. Transfers below 5,000 KZT and outside July are absent by design.

