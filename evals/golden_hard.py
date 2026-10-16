"""Hard split: multi-step questions written for the Phase 2 model x context benchmark.

Written from the trap taxonomy before any model was run on them, so the context layer was not tuned to
them. Each question combines at least two of: a trap, a time window, a cross-system join, or a derived
metric (growth, retention, share, median). Answers come from the generator's answer key (data/truth) or
from raw tables that carry no trap for the question asked, never from dbt.
"""
from __future__ import annotations

import pandas as pd


def build_hard(data, arr, daily, orgs, cust, r, add):
    H = "hard"
    m = lambda d: arr[arr.month_start == pd.Timestamp(d)]
    by_c = lambda df: df.groupby("customer_id").arr_usd.sum()
    jun, sep, sep25, dec25 = m("2026-06-01"), m("2026-09-01"), m("2025-09-01"), m("2025-12-01")
    region = cust.drop_duplicates("customer_id").set_index("customer_id")["region"]
    upgraded = set(cust[cust.upgraded_from_self_serve].customer_id)

    # ---------------- ARR movements (balance metric, two revenue streams, customer identity) ----------------
    j, s = by_c(jun), by_c(sep)
    new_ids = s.index.difference(j.index)
    add("x_new_logo_arr_q3", "How much ARR at the end of September 2026 came from customers that had no ARR at the "
        "end of June 2026?", round(s[new_ids].sum(), 2),
        traps=["two_revenue_streams", "customer_identity", "arr_summed_over_months"], split=H)
    lost = j.index.difference(s.index)
    add("x_churned_arr_q3", "How much ARR did we lose in Q3 2026 from customers that had ARR at the end of June 2026 "
        "and none at the end of September 2026? A move from self-serve to enterprise is not a loss.",
        round(j[lost].sum(), 2), traps=["upgrade_is_not_churn", "customer_identity", "stale_status"], split=H)
    both = j.index.intersection(s.index)
    delta = s[both] - j[both]
    add("x_expansion_arr_q3", "For customers with ARR at both the end of June 2026 and the end of September 2026, "
        "what was the total ARR increase among those whose ARR went up?", round(delta[delta > 0].sum(), 2),
        traps=["customer_identity", "tcv_vs_arr"], split=H)
    s25 = by_c(sep25)
    kept = s.reindex(s25.index).fillna(0)
    add("x_nrr_sep", "What was net revenue retention from the end of September 2025 to the end of September 2026: "
        "ARR at the end of September 2026 from customers who had ARR at the end of September 2025, as a percent of "
        "their September 2025 ARR?", round(100 * kept.sum() / s25.sum(), 2), kind="percent", tol=0.5,
        traps=["customer_identity", "upgrade_is_not_churn", "two_revenue_streams"], split=H)
    e25 = by_c(sep25[sep25.motion == "enterprise"])
    e26 = by_c(sep[sep.motion == "enterprise"])
    add("x_ent_grr_sep", "What was enterprise gross revenue retention from the end of September 2025 to the end of "
        "September 2026? For each enterprise customer at the end of September 2025, count its September 2026 "
        "enterprise ARR capped at its September 2025 ARR, and give the total as a percent of September 2025 "
        "enterprise ARR.", round(100 * e26.reindex(e25.index).fillna(0).clip(upper=e25).sum() / e25.sum(), 2),
        kind="percent", tol=0.5, traps=["tcv_vs_arr", "stale_status"], split=H)
    monthly = arr.groupby("month_start").arr_usd.sum()
    nn = monthly.diff()
    nn26 = nn[(nn.index >= pd.Timestamp("2026-01-01")) & (nn.index <= pd.Timestamp("2026-09-01"))]
    add("x_best_nn_month", "Between January and September 2026, which month had the largest net new ARR (ARR at the "
        "end of the month minus ARR at the end of the prior month)? Answer with the month number, 1 to 12.",
        int(nn26.idxmax().month), tol=0, traps=["arr_summed_over_months", "two_revenue_streams"], split=H,
        margin=float((nn26.max() - nn26.nlargest(2).iloc[-1]) / abs(nn26.max())))

    # ---------------- ARR cuts (region, segment, distribution) ----------------
    em25 = sep25[sep25.customer_id.map(region) == "EMEA"].arr_usd.sum()
    em26 = sep[sep.customer_id.map(region) == "EMEA"].arr_usd.sum()
    add("x_emea_growth", "By what percent did ARR from customers in EMEA grow from the end of September 2025 to the "
        "end of September 2026?", round(100 * (em26 / em25 - 1), 2), kind="percent", tol=0.5,
        traps=["two_revenue_streams", "tcv_vs_arr"], split=H)
    sr = sep.assign(region=sep.customer_id.map(region))
    emea = sr[sr.region == "EMEA"]
    add("x_emea_ss_share", "What percent of EMEA ARR at the end of September 2026 came from self-serve customers?",
        round(100 * emea[emea.motion == "self_serve"].arr_usd.sum() / emea.arr_usd.sum(), 2), kind="percent",
        tol=0.5, traps=["two_revenue_streams", "invoice_double_count"], split=H)
    ent = e26
    add("x_median_ent_arr", "What was the median ARR per enterprise customer at the end of September 2026?",
        round(float(ent.median()), 2), traps=["tcv_vs_arr"], split=H)
    add("x_ss_avg_arr", "What was average ARR per self-serve customer at the end of September 2026?",
        round(sep[sep.motion == "self_serve"].arr_usd.sum() / sep[sep.motion == "self_serve"].customer_id.nunique(), 2),
        traps=["two_revenue_streams", "invoice_double_count"], split=H)
    add("x_cust_over_10k", "How many customers, self-serve and enterprise combined, had at least $10,000 of ARR at "
        "the end of September 2026?", int((s >= 10_000).sum()), tol=0,
        traps=["two_revenue_streams", "tcv_vs_arr", "customer_identity"], split=H)
    add("x_upgraded_count", "How many enterprise customers paying at the end of September 2026 originally started "
        "on the self-serve plan?", int(len(set(sep[sep.motion == "enterprise"].customer_id) & upgraded)), tol=0,
        traps=["customer_identity", "upgrade_is_not_churn"], split=H)
    apac_ent = sr[(sr.region == "APAC") & (sr.motion == "enterprise")].customer_id.nunique()
    add("x_apac_ent_count", "How many enterprise customers in APAC were paying at the end of September 2026?",
        int(apac_ent), tol=0, traps=["stale_status"], split=H)
    rg = (sr.groupby("region").arr_usd.sum() / sr.groupby("region").customer_id.nunique())
    add("x_region_arpc", "Which region had the highest average ARR per paying customer at the end of September 2026? "
        "Answer NA, EMEA, APAC, or LATAM.", rg.idxmax(), kind="category",
        traps=["two_revenue_streams", "customer_identity"], split=H,
        margin=float((rg.max() - rg.nlargest(2).iloc[-1]) / rg.max()))

    # ---------------- Contracts (TCV vs ARR) ----------------
    con = pd.read_parquet(data / "truth" / "truth_contracts.parquet")
    con["start"] = pd.to_datetime(con["start"]); con["end"] = pd.to_datetime(con["end"])
    c25 = con[con.start.dt.year == 2025]
    add("x_contract_arr_2025", "What was the total annualized value (ARR, not total contract value) of enterprise "
        "contracts that started in 2025, counting new business, expansions, and renewals?",
        round(c25.arr.sum(), 2), traps=["tcv_vs_arr"], split=H)
    nb26 = con[(con.start >= "2026-01-01") & (con.start <= "2026-09-30") & (con.type == "New Business")]
    add("x_nb_arr_2026", "What was the total ARR of new-business enterprise contracts that started between January 1 "
        "and September 30, 2026?", round(nb26.arr.sum(), 2), traps=["tcv_vs_arr"], split=H)
    first = con.groupby("account_id").start.min()
    plus_first = orgs[orgs.upgraded_to_enterprise & ~orgs.is_internal].groupby("customer_id").plus_start.min()
    days = (first.reindex(plus_first.index) - plus_first).dt.days.dropna()
    add("x_days_upgrade", "For enterprise customers that started on the self-serve plan, what is the median number of "
        "days from their first self-serve payment to the start of their first enterprise contract?",
        float(days.median()), tol=0.02, traps=["customer_identity"], split=H)

    # ---------------- Usage (internal usage, self-hosted telemetry gap, balances) ----------------
    d = daily[~daily.is_internal]
    sep_d = d[(d.date >= "2026-09-01") & (d.date <= "2026-09-30")]
    aug_d = d[(d.date >= "2026-08-01") & (d.date <= "2026-08-31")]
    add("x_traces_mom", "By what percent did base traces grow from August 2026 to September 2026, excluding internal "
        "usage?", round(100 * (sep_d.traces.sum() / aug_d.traces.sum() - 1), 2), kind="percent", tol=0.5,
        traps=["internal_usage"], split=H)
    add("x_sh_trace_share", "What percent of base traces ingested in September 2026 came from self-hosted orgs, "
        "excluding internal usage?", round(100 * sep_d[sep_d.deployment == "self_hosted"].traces.sum()
                                         / sep_d.traces.sum(), 2), kind="percent", tol=0.5,
        traps=["self_hosted_no_telemetry", "sf_deployment_stale", "internal_usage"], split=H)
    q3 = d[(d.date >= "2026-07-01") & (d.date <= "2026-09-30")]
    sandbox = set(orgs[orgs.is_sandbox].org_id)
    eq3 = q3[(q3.motion == "enterprise") & ~q3.org_id.astype(str).isin(sandbox)]
    add("x_ent_traces_q3", "How many base traces did orgs on the enterprise plan ingest in Q3 2026? Exclude internal "
        "usage and enterprise sandbox orgs.", int(eq3.traces.sum()),
        traps=["internal_usage", "self_hosted_no_telemetry"], split=H)
    add("x_avg_dau_sep", "What was the average number of daily active users per day in September 2026, summed across "
        "all non-internal orgs?", round(float(sep_d.groupby("date").active_users.sum().mean()), 2),
        traps=["internal_usage", "segment_duplicates"], split=H)
    ev_q3 = q3[q3.motion == "plus"]
    add("x_plus_events_per_dau", "In Q3 2026, how many product events per active user-day did Plus orgs generate? "
        "Divide total product events by total daily active users, excluding internal usage.",
        round(ev_q3.events.sum() / ev_q3.active_users.sum(), 3), kind="abs", tol=0.02,
        traps=["segment_duplicates", "internal_usage"],
        split=H)
    s30 = d[d.date == "2026-09-30"]
    plus30 = s30[s30.motion == "plus"]
    add("x_plus_10_seats", "How many Plus orgs had more than 10 billed seats on September 30, 2026?",
        int((plus30.groupby("org_id", observed=True).seats.sum() > 10).sum()), tol=0,
        traps=["seats_are_a_balance"], split=H)
    seat_m = d[(d.motion == "plus") & (d.date >= "2026-07-01") & (d.date <= "2026-09-30")]
    add("x_avg_plus_seats_q3", "What was the average total number of billed Plus seats per day in Q3 2026?",
        round(float(seat_m.groupby("date").seats.sum().mean()), 2), traps=["seats_are_a_balance"], split=H)

    # ---------------- Funnel ----------------
    o = orgs[~orgs.is_internal].copy()
    o["signup_date"] = pd.to_datetime(o.signup_date)
    h1 = o[(o.signup_date >= "2026-01-01") & (o.signup_date <= "2026-06-30") & o.activation_date.notna()]
    add("x_days_to_activate", "For orgs that signed up in the first half of 2026 and activated, what is the median "
        "number of days from signup to activation?",
        float((pd.to_datetime(h1.activation_date) - h1.signup_date).dt.days.median()), tol=0.02, split=H,
        traps=["internal_usage"])
    q4 = o[(o.signup_date >= "2025-10-01") & (o.signup_date <= "2025-12-31")]
    add("x_activation_q4_25", "What share of orgs that signed up in Q4 2025 have activated? Give a percent.",
        round(100 * q4.activation_date.notna().mean(), 2), kind="percent", tol=0.5, split=H, traps=["internal_usage"])
    q1 = o[(o.signup_date >= "2026-01-01") & (o.signup_date <= "2026-03-31")]
    act = q1[q1.activation_date.notna()]
    add("x_paid_given_active", "Of the orgs that signed up in Q1 2026 and activated, what percent have become paying "
        "customers?", round(100 * act.first_paid_date.notna().mean(), 2), kind="percent", tol=0.5, split=H,
        traps=["internal_usage"])

    # ---------------- Support (customer identity, internal orgs) ----------------
    tk = r("raw_support", "tickets")
    tk["created_at"] = pd.to_datetime(tk.created_at)
    internal = set(orgs[orgs.is_internal].org_id)
    tk = tk[~tk.org_id.isin(internal)]
    tq3 = tk[(tk.created_at >= "2026-07-01") & (tk.created_at < "2026-10-01")]
    urg = tq3[(tq3.priority == "urgent") & tq3.solved_at.notna()]
    add("x_urgent_hours_q3", "What was the median time to resolution, in hours, for urgent support tickets created in "
        "Q3 2026 that have been solved? Exclude internal orgs.",
        round(float(((pd.to_datetime(urg.solved_at) - urg.created_at).dt.total_seconds() / 3600).median()), 2),
        kind="abs", tol=0.05, traps=["internal_usage"], split=H)
    org_cust = orgs.set_index("org_id").customer_id
    tq3c = tq3.assign(customer_id=tq3.org_id.map(org_cust))
    ent_ids = set(sep[sep.motion == "enterprise"].customer_id)
    add("x_ent_tickets_q3", "How many support tickets did enterprise customers that were paying at the end of "
        "September 2026 open in Q3 2026, counting tickets from all of their orgs?",
        int(tq3c.customer_id.isin(ent_ids).sum()), tol=0, traps=["customer_identity", "stale_status"], split=H)
    urg_cust = set(tq3c[tq3c.priority == "urgent"].customer_id)
    add("x_arr_urgent_q3", "How much ARR at the end of September 2026 belonged to customers that opened at least one "
        "urgent support ticket in Q3 2026?", round(s.reindex(list(urg_cust & set(s.index))).sum(), 2),
        traps=["customer_identity", "two_revenue_streams"], split=H)
    cats = tq3.groupby("category").size()
    add("x_top_category_q3", "Which support ticket category had the most tickets created in Q3 2026, excluding "
        "internal orgs? Answer with the category name exactly as stored.", cats.idxmax(), kind="category",
        traps=["internal_usage"], split=H, margin=float((cats.max() - cats.nlargest(2).iloc[-1]) / cats.max()))

    # ---------------- Billing (invoices are not ARR; price change) ----------------
    inv = r("raw_metronome", "invoices")
    inv["period_start"] = pd.to_datetime(inv.period_start)
    add("x_ent_invoiced_2025", "How much was invoiced to enterprise customers for service periods starting in 2025? "
        "This is billed revenue, not ARR.",
        round(inv[(inv.plan == "enterprise") & (inv.period_start.dt.year == 2025)].amount_usd.sum(), 2),
        traps=["invoice_double_count", "tcv_vs_arr"], split=H)
    pi = inv[inv.plan == "plus"]
    h1_25 = pi[(pi.period_start >= "2025-01-01") & (pi.period_start <= "2025-06-30")].amount_usd.sum()
    h2_25 = pi[(pi.period_start >= "2025-07-01") & (pi.period_start <= "2025-12-31")].amount_usd.sum()
    add("x_plus_h2_vs_h1", "By what percent did Plus revenue invoiced for service periods in the second half of 2025 "
        "differ from the first half of 2025?", round(100 * (h2_25 / h1_25 - 1), 2), kind="percent", tol=0.5,
        traps=["price_book_change"], split=H)
