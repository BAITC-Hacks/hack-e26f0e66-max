# Prioritized data requests

1. **Trace onward transfers from the frontier.** Ask for outgoing transfers beyond depth 4 for all 444 frontier accounts, prioritizing the identified frontier collectors: 100000000018102100, 100000000299820100, 100000000369781100, 100000000375150100, 100000000404740100, 100000000424935100, 100000000470237100, 100000000500040100, 100000000542087100, 100000000557536100, 100000000561160100, 100000000581662100, 100000000581682100, 100000000600707100, 100000000608031100, 100000000627521100, 100000000634341100, 100000000655469100, 100000000673915100, 100000000704700100, 100000000733940100, 100000000737152100, 100000000803368100, 100000000926078100, 100000000957746100. This would show whether funds continue beyond the visible graph; the frontier accounts received 56,672,164.68 KZT, but their onward activity is unknown.

2. **Establish seed inflows and apparent inactivity.** Ask for incoming and outgoing transfers for all seed accounts, with particular attention to the 42 without traced inflow and the 19 with no transfers in the export. This would help distinguish activity absent from the sample from activity absent during 2026-07-01 to 2026-07-31.

3. **Remove the amount floor.** Ask for transfers below 5,000 KZT involving the seed accounts and frontier collectors. This would test whether excluded smaller transfers change the apparent flows.

4. **Check links between fragments.** Ask for transfers involving accounts in the 35 components and intermediary accounts outside the export. This would test whether the components are separate or connected through unobserved accounts.

5. **Check persistence.** Ask for comparable transfers for the seed accounts and frontier collectors outside 2026-07-01 to 2026-07-31. This would help assess whether the observed activity is recurring or confined to the export period.
