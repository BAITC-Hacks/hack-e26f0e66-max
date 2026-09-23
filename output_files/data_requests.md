# Prioritized data requests

1. **Frontier outflows:** Request outgoing transfers for all **444 frontier accounts** beyond the export’s **4-hop** limit, starting with accounts `100000000018102100`, `100000000299820100`, and `100000000369781100`. This would show whether funds continued beyond the visible graph; the accounts received **56,672,164.68 KZT** in the export, but their onward activity is unknown.

2. **Seed inflows and missing activity:** Request incoming transfers for all seed accounts from **2026-07-01 to 2026-07-31**, and complete transfer histories for the **19 seeds** with no transfers shown. This would help explain why **42 seeds** have no traced inflow and whether the apparently inactive seeds had activity outside the export.

3. **Transfers below the floor:** Request transfers regardless of amount for the frontier and seed accounts, including those below **5,000 KZT**. This would test whether the amount floor hides activity relevant to their apparent flow patterns.

4. **Links between components:** Request transfers involving accounts in the **35 components**, including intermediary accounts absent from the export. This would test whether the components are separate or connected through unobserved accounts.

5. **Activity outside the period:** Request the same transfer data for the frontier and seed accounts outside **2026-07-01 to 2026-07-31**. This would help distinguish recurring patterns from activity limited to the exported period.
