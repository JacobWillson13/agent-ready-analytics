# Interpreting product usage across deployment types

Orgs run cloud, hybrid, or self_hosted. deployment_type comes from the product database; Salesforce's field is stale.

- Self-hosted orgs send no Segment telemetry. product_events and active_users are 0 for them. That is a data gap, not inactivity.
- Hybrid orgs send telemetry from the hosted UI only; their event counts undercount real activity.
- Metronome metering covers every deployment type, so base_traces is the only usage measure comparable across all three.
- billed_seats is a daily balance. For seats "in September", take the value on the last day; never sum days.
- Internal Lanternfly orgs generate heavy usage and are excluded from fct_daily_usage. Exclude them if you touch raw tables.

Rules for answering:

- Cross-deployment comparisons or "most active customers": use base_traces.
- Feature adoption or user behavior: restrict to cloud and say so.
- Never call a self-hosted customer inactive based on events or active users.
