# Data generation

One seeded run (`python -m generator --seed 42`) writes raw tables for five source systems plus an
answer key. Same seed, config, and numpy version produce identical output.

## Company and calibration

Fictional Lanternfly Labs, calibrated to the public pricing and scale of developer-tool SaaS companies: free Developer plan, Plus at
$39/seat with 10k included traces, enterprise contracts with self-hosted and hybrid options.

| Knob | Value |
|---|---|
| Window | 2024-01-01 to 2026-10-14 (snapshot date; also the dbt `as_of_date`) |
| Signups | 80k orgs, growing about 4x across the window |
| Activation | about 50% reach 1,000 cumulative traces |
| Plus conversion | 22% of activated orgs |
| Enterprise | 200 sales-led plus about 3.5% of Plus orgs that upgrade |
| Enterprise ARR | lognormal, median $48k |
| Price book | overage $5.00 per 1k traces before 2025-07-01, $2.50 after |

Result at full scale (end of September 2026): $36.2M ARR, 6,048 paying customers, 251 enterprise.

## How it simulates

Each paying customer gets an archetype (grower, steady, at_risk_saved, churner) that drives one daily
activity curve. Traces, seats, Segment events, and support tickets all derive from that curve, so
usage decline, ticket spikes, and churn stay correlated. Enterprise contracts run as sequences of New
Business, Expansion, and Renewal opportunities with 12, 24, or 36-month terms.

## Traps

| Trap | Where the defense lives |
|---|---|
| Salesforce amount is TCV; multi-year deals | int_contracts, arr_usd doc, unit test |
| Self-serve revenue is not in Salesforce | fct_arr_monthly combines both motions |
| Enterprise prepay invoices in Metronome double count ARR | revenue guide, fct_invoices doc |
| Churned accounts still marked Active | account_status doc, paying_customers metric |
| Plus to Enterprise upgrade looks like churn | customer_id resolution, customer identity guide |
| Self-hosted has no Segment telemetry; hybrid partial | deployment_type doc, usage guide |
| Cloud orgs migrated to self-hosted, Salesforce not updated | dim_customers.deployment_type |
| Internal orgs with heavy usage | is_internal, mart filters |
| Segment duplicates (1.5%) | incremental dedupe in stg_segment__tracks |
| Salesforce soft deletes (3%) | staging filters |
| Seats are a daily balance | billed_seats doc, non-additive metric |
| ARR summed across months | non_additive_dimension on ARR metrics |
| Overage price changed | price book, revenue guide |

`--no-traps` regenerates clean data. All three context levels should score about the same on it,
which shows the gap comes from the traps, not the question set.

## Answer key (`data/truth`, loaded to `eval_truth`)

Computed from simulation state, never from raw tables: ARR per customer-month, org-day usage, org funnel
dates, customer archetypes and churn dates, contracts. dbt reconciliation tests compare marts to it;
`evals/build_golden.py` computes golden answers from it.
