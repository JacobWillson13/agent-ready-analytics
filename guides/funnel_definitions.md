# Funnel definitions

- Signup: an org is created. Cohort by dim_orgs.signup_date. Exclude internal orgs.
- Activation: the org's cumulative base traces reach 1,000 (dim_orgs.activated_date). Activation rate is by signup cohort, measured as of today.
- Paid: the org starts a plus or enterprise subscription (dim_orgs.first_paid_date). Sandbox orgs never count as paid.
- Use the governed metrics signups, activated_signups, paid_signups, activation_rate, and signup_to_paid_rate grouped by signup date.
- PyPI downloads (fct_pypi_downloads_daily) are real upstream open source downloads, an adoption trend only. They include CI and mirror traffic and cannot be joined to orgs.

