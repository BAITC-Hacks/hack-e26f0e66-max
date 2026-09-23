# Data requests

What this export cannot show, and what to ask for next. Every item below is computed from the graph, not assumed.

## 1. The traversal frontier

The export stopped at hop 4. **444 accounts** sit on that frontier and their onward transfers were never requested, so their outflow is *unknown*, not zero. They received 56,672,165 KZT in total.

**Request:** outgoing transfers (hop 5) for the 444 frontier accounts showing collection behaviour — starting with 100000000018102100, 100000000299820100, 100000000369781100, 100000000375150100, 100000000404740100, 100000000424935100, 100000000470237100, 100000000500040100, 100000000542087100, 100000000557536100, 100000000561160100, 100000000581662100, 100000000581682100, 100000000600707100, 100000000608031100, 100000000627521100, 100000000634341100, 100000000655469100, 100000000673915100, 100000000704700100, 100000000733940100, 100000000737152100, 100000000803368100, 100000000926078100, 100000000957746100.

These are the highest-value requests: a collection point at the edge of the visible data is exactly where the chain is most likely to continue.

## 2. Inflows to the seed accounts

The graph was built *from* the seeds by following outgoing transfers, so money reaching them from outside the sample is absent. **42 seeds** have no traced inflow at all, and **19** have no transfers in either direction.

**Request:** incoming transfers to all seed accounts for the same period. Without them, no seed's pass-through ratio can be interpreted.

## 3. Activity below the reporting threshold

Transfers under 5,000 KZT were excluded. Structuring just below that line is invisible by construction.

**Request:** all transfers regardless of amount for the priority shortlist, to test whether any account's pattern changes once the floor is removed.

## 4. Disconnected fragments

The export splits into **35 components**. Whether they are genuinely separate networks or connected through accounts outside the sample cannot be answered from this data.

**Request:** transfers between the seed sets of the separate components, including through accounts not currently in the export.

## 5. Period

The export covers 2026-07-01 to 2026-07-31. Patterns that repeat monthly cannot be distinguished from one-off movements in a single month.

**Request:** the same export for the preceding two months.
