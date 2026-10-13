{% docs customer_id %}
The billing customer. For enterprise customers it is the Salesforce Account ID; for self-serve customers it is the product org_id. An org that upgrades from Plus to Enterprise keeps one customer_id (its account) for its whole history, so an upgrade is not churn. Every revenue and customer count question should group by customer_id, not org_id or account_id.
{% enddocs %}

{% docs org_id %}
A product org (workspace). One self-serve customer is one org. An enterprise customer can have several orgs, for example a production org plus a sandbox. Usage questions can be answered per org; revenue questions must roll up to customer_id.
{% enddocs %}

{% docs motion %}
How the customer buys: enterprise (sales-led contract in Salesforce) or self_serve (Plus plan, card billing in Metronome). The two motions have different revenue sources; total ARR needs both.
{% enddocs %}

{% docs deployment_type %}
How the org runs Lanternfly: cloud, hybrid, or self_hosted, taken from the product database (what the customer actually runs). Salesforce's deployment field is entered at contract time and goes stale after migrations. Self-hosted orgs send no Segment telemetry, so product_events and active_users are always 0 for them; hybrid orgs send only partial telemetry. Use base_traces for any usage comparison across deployment types. See guides/usage_by_deployment_type.md.
{% enddocs %}

{% docs account_status %}
Lifecycle label from Salesforce: Active, Churned, or Prospect. Account owners maintain it by hand and many churned accounts are still marked Active. Never use it to count customers or compute ARR; use fct_arr_monthly (arr_usd > 0) instead. Use it only for questions about how Sales has labeled an account.
{% enddocs %}

{% docs is_internal %}
True for Lanternfly's own employee and test orgs. They generate heavy real usage. Every mart except dim_orgs already excludes them.
{% enddocs %}

{% docs arr_usd %}
Annual recurring revenue in USD as of as_of_date. Enterprise: sum of live contracts, each annualized as amount_tcv_usd * 12 / term_months (Salesforce amount is total contract value, so a 3-year $360k deal is $120k ARR). Self-serve: 12 times the customer's most recent closed monthly Plus invoice, counted only while the Plus subscription is active. ARR is a balance: never sum it across months.
{% enddocs %}

{% docs as_of_date %}
The date a monthly balance is measured on: the last day of the month, or the project as_of_date (dbt var) for the current partial month.
{% enddocs %}
