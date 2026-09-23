# Review notes: what is wrong with this list

Written against the priority list, not in support of it. Read it before acting on the rankings.

## Verdict

Treat this as a hypothesis-generating review queue, not a validated ranking of account roles: the terminal cases and extreme flow ratios are particularly exposed to collection omissions, while several consolidators sit exactly on the five-payer cutoff. The lack of labels and customer attributes, plus the seed- and direction-dependent export, means analysts should verify underlying transfers and test sensitivity before assigning much weight to the role labels or priority order.

## Entries that may be collection artifacts

**MEDIUM** — accounts 100000004015047100, 100000003115284100, 100000008165763100, 100000002718366100, 100000001253557100, 100000001303311100, 100000001282143100

> These coordinator-ranked accounts are not marked at the traversal frontier, so the known unknown-onward-flow artifact does not directly explain their zero or low observed outflow. However, because collection follows outgoing transfers only from fixed starting accounts, their observed inflows and seed reach omit incoming funds and connections outside that sampled path; the coordinator interpretation is conditional on the selected seeds, not a complete network view.

**HIGH** — accounts 100000002957306100, 100000002894076100, 100000001924185100, 100000003404627100, 100000004105288100, 100000001072022100, 100000002605548100, 100000005778283100, 100000003158727100, 100000005432267100

> These terminal-ranked accounts show zero observed outflow, but that is not evidence of zero actual onward flow: transfers below 5,000 KZT are excluded, and transfers to destinations not reached by the outgoing-only traversal are absent. Their apparent terminal pattern is therefore especially sensitive to the collection boundary and amount floor.

**HIGH** — accounts 100000004156082100, 100000008547948100, 100000002224132100, 100000008730846100

> Observed outflow substantially exceeds observed inflow (307%–999% where stated). This may reflect omitted inflows from outside the sampled paths, transfers below the floor, or activity outside the collection window; it is not by itself evidence of unusually rapid pass-through.

## Thresholds carrying more weight than they should

**`consolidator.min_payers`** — The listed consolidator cases with exactly five observed payers sit directly on the inclusion boundary; raising the minimum by one would remove their consolidator classification, while lowering it would admit accounts with four payers. The shown counts do not establish that their rank would remain high under that change.

Affects 8 of the listed accounts: 100000002838861100, 100000001924185100, 100000008144528100, 100000002398779100, 100000004299488100, 100000007055802100, 100000002224132100, 100000002547110100

**`terminal.max_pass`** — The terminal examples have zero observed pass-through, so their role is not numerically close to the 0.1 cutoff in this export. But one-step changes to the amount floor or inclusion of omitted onward transfers could move their observed pass-through across that threshold; the supplied findings do not show whether any would remain terminal.

Affects 10 of the listed accounts: 100000002957306100, 100000002894076100, 100000001924185100, 100000003404627100, 100000004105288100, 100000001072022100, 100000002605548100, 100000005778283100, 100000003158727100, 100000005432267100

## Blind spots

- No listed account is marked at the max-depth frontier, so the specific artifact of unknown onward flow for the 444 frontier accounts is not visibly driving these top findings. Still, the findings cannot characterize paths beyond the four-hop collection boundary, and none of the shown accounts' observed status establishes that their wider-network role is complete.
- Incoming transfers to the 81 starting accounts from outside the sample are absent. This makes seed-originated flow and seed reach incomplete at the source, and could also help explain the outflow-to-inflow ratios above 100% for 100000007594394100, 100000004156082100, 100000008547948100, 100000002224132100, and 100000008730846100.
- The 5,000 KZT floor removes small transfers entirely. The export therefore cannot show whether apparently terminal accounts such as 100000002957306100 or 100000002894076100 make many small onward payments, or whether omitted small payments materially change payer and recipient counts.
- The top findings contain no strong-distributor examples despite 46 distributor roles overall. That absence may reflect the ranking or role rules, but the shown data do not let a reviewer assess whether high-recipient accounts were deprioritized or whether recipient counts are truncated by collection.

