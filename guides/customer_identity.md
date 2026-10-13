# Who is a customer

- A customer is a billing entity: an enterprise Salesforce account, or a self-serve org. The key is customer_id everywhere.
- An org that upgrades from Plus to Enterprise keeps one customer_id (its account) across its whole history. Its Plus subscription ending is an upgrade, not churn. dim_customers.upgraded_from_self_serve flags these.
- Paying customers at a point in time = customers with ARR above zero in fct_arr_monthly for that month (the `paying_customers` metric).
- Salesforce account_status is a manual label and lags reality; many churned accounts still say Active. Do not use it to count customers or detect churn.
- Churned enterprise customer: had enterprise ARR at some month end and has no ARR now.
- Self-serve churn: a Plus subscription that ended without the org upgrading to enterprise.
- Internal Lanternfly orgs are excluded from every customer mart. If you query raw or staging tables, exclude them yourself.
