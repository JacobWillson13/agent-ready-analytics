# Revenue definitions: ARR, invoices, and prices

Lanternfly earns revenue through two motions, and total ARR needs both.

- Enterprise ARR comes from Salesforce contracts. Each closed-won opportunity is annualized: amount is total contract value, so ARR = amount * 12 / term months. A 3-year $360k deal is $120k ARR. Expansions are co-terminous and annualized over their own remaining term.
- Self-serve ARR comes from Metronome. It is 12 times the customer's most recent closed monthly Plus invoice (seats plus usage overage), counted only while the Plus subscription is active. A brand new subscriber shows ARR after their first invoice closes.
- Use the `arr` metric, or fct_arr_monthly.arr_usd. Never rebuild ARR from Salesforce alone; that misses all self-serve revenue.

Rules:

- ARR is a balance. "ARR in Q3" means ARR at the end of Q3, never the sum of three months.
- Metronome also holds enterprise `platform_commit` invoices. Those are annual prepayments of the same Salesforce contracts. Adding them to ARR double counts.
- Billed revenue (what was invoiced for a period) comes from fct_invoices. Never recompute past revenue from the price book: the Plus overage price dropped from $5.00 to $2.50 per 1k traces on 2025-07-01.
- Net new ARR for a period = ARR at period end minus ARR at the prior period end.
