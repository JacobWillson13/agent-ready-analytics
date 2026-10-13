"""Build evals/golden.jsonl from the generator's answer key (data/truth) plus untrapped raw tables.

Answers never come from dbt. Rerun after every regeneration:  uv run python evals/build_golden.py --data data
"""
import argparse
import json
from pathlib import Path

import pandas as pd

AS_OF = pd.Timestamp("2026-10-14")


def load(data: Path):
    t = lambda n: pd.read_parquet(data / "truth" / f"{n}.parquet")
    r = lambda ds, n: pd.read_parquet(data / "raw" / ds / f"{n}.parquet")
    arr = t("truth_arr_monthly"); arr["month_start"] = pd.to_datetime(arr["month_start"])
    daily = t("truth_org_daily"); daily["date"] = pd.to_datetime(daily["date"])
    orgs = t("truth_orgs")
    cust = t("truth_customers")
    return arr, daily, orgs, cust, r


def build(data: Path):
    arr, daily, orgs, cust, r = load(data)
    q = []

    def add(qid, question, answer, kind="number", tol=0.01, traps=(), split="core"):
        q.append(dict(id=qid, question=question, answer=answer, kind=kind, tol=tol, traps=list(traps), split=split))

    m = lambda d: arr[arr.month_start == pd.Timestamp(d)]
    sep, jun, sep25 = m("2026-09-01"), m("2026-06-01"), m("2025-09-01")
    add("arr_total_sep26", "What was total ARR at the end of September 2026?", round(sep.arr_usd.sum(), 2),
        traps=["tcv_vs_arr", "two_revenue_streams", "invoice_double_count"])
    add("arr_ent_sep26", "What was enterprise ARR at the end of September 2026?",
        round(sep[sep.motion == "enterprise"].arr_usd.sum(), 2), traps=["tcv_vs_arr"])
    add("arr_ss_sep26", "What was self-serve ARR at the end of September 2026?",
        round(sep[sep.motion == "self_serve"].arr_usd.sum(), 2), traps=["two_revenue_streams"])
    add("paying_sep26", "How many paying customers did we have at the end of September 2026?",
        int(sep.customer_id.nunique()), tol=0, traps=["stale_status", "customer_identity"])
    add("paying_ent_sep26", "How many enterprise customers were paying at the end of September 2026?",
        int(sep[sep.motion == "enterprise"].customer_id.nunique()), tol=0, traps=["stale_status"])
    add("arr_q2_26", "What was total ARR for Q2 2026?", round(jun.arr_usd.sum(), 2),
        traps=["arr_summed_over_months"])
    add("arr_yoy_sep", "By what percent did total ARR grow from the end of September 2025 to the end of September 2026?",
        round(100 * (sep.arr_usd.sum() / sep25.arr_usd.sum() - 1), 2), kind="percent", tol=0.5)
    add("nnarr_q3_26", "What was net new ARR in Q3 2026?", round(sep.arr_usd.sum() - jun.arr_usd.sum(), 2))
    ent_dec = set(m("2025-12-01").query("motion == 'enterprise'").customer_id)
    now = set(m("2026-10-01").customer_id)
    add("ent_churn_2026", "How many enterprise customers had ARR at the end of December 2025 but have no ARR as of October 14, 2026?",
        len(ent_dec - now), tol=0, traps=["stale_status"])
    acc = r("raw_salesforce", "account")
    acc = acc[(~acc.is_deleted) & (acc.account_status__c == "Active") & (~acc.name.str.contains("Internal"))]
    add("stale_active", "How many Salesforce customer accounts are marked Active but have no ARR as of October 14, 2026? Exclude Lanternfly's internal account.",
        int((~acc.id.isin(now)).sum()), tol=0, traps=["stale_status"])
    pe = pd.to_datetime(orgs.plus_end)
    add("ss_churn_q3", "How many self-serve customers churned in Q3 2026? Do not count customers who upgraded to enterprise.",
        int(((pe >= "2026-07-01") & (pe <= "2026-09-30") & (~orgs.upgraded_to_enterprise)).sum()), tol=0,
        traps=["upgrade_is_not_churn"])
    d9 = daily[(daily.date >= "2026-09-01") & (daily.date <= "2026-09-30") & (~daily.is_internal)]
    dep = orgs.set_index("org_id").deployment_now
    add("sh_traces_sep", "How many base traces did self-hosted orgs ingest in September 2026?",
        int(d9[d9.org_id.map(dep) == "self_hosted"].traces.sum()), traps=["self_hosted_no_telemetry", "sf_deployment_stale"])
    add("events_sep", "How many product events were recorded in September 2026, excluding internal usage?",
        int(d9.events.sum()), traps=["internal_usage", "segment_duplicates"])
    add("traces_sep", "How many base traces were ingested in September 2026, excluding internal usage?",
        int(d9.traces.sum()), traps=["internal_usage"])
    s30 = daily[(daily.date == "2026-09-30") & (daily.motion == "plus") & (~daily.is_internal)]
    add("plus_seats_sep30", "How many billed seats did Plus customers have in total on September 30, 2026?",
        int(s30.seats.sum()), traps=["seats_are_a_balance"])
    inv = r("raw_metronome", "invoices"); inv["period_start"] = pd.to_datetime(inv.period_start)
    add("ss_billed_2025", "How much self-serve (Plus) revenue was invoiced for service periods in 2025?",
        round(inv[(inv.plan == "plus") & (inv.period_start.dt.year == 2025)].amount_usd.sum(), 2),
        traps=["price_book_change"])
    o = orgs[~orgs.is_internal].copy(); o["signup_date"] = pd.to_datetime(o.signup_date)
    q3 = o[(o.signup_date >= "2026-07-01") & (o.signup_date <= "2026-09-30")]
    add("signups_q3", "How many orgs signed up in Q3 2026?", int(len(q3)), tol=0)
    q2 = o[(o.signup_date >= "2026-04-01") & (o.signup_date <= "2026-06-30")]
    add("activation_q2", "What share of orgs that signed up in Q2 2026 have activated? Give a percent.",
        round(100 * q2.activation_date.notna().mean(), 2), kind="percent", tol=0.5)
    c25 = o[o.signup_date.dt.year == 2025]
    add("paid_rate_2025", "What percent of orgs that signed up in 2025 have become paying customers?",
        round(100 * c25.first_paid_date.notna().mean(), 2), kind="percent", tol=0.5)
    paid25 = c25[c25.first_paid_date.notna()]
    add("days_to_paid_2025", "For orgs that signed up in 2025 and became paying, what is the median number of days from signup to first payment?",
        float((pd.to_datetime(paid25.first_paid_date) - paid25.signup_date).dt.days.median()), tol=0.02)
    ent_sep = sep[sep.motion == "enterprise"]
    add("ent_over_100k", "How many enterprise customers had more than $100,000 of ARR at the end of September 2026?",
        int((ent_sep.groupby("customer_id").arr_usd.sum() > 100_000).sum()), tol=0, traps=["tcv_vs_arr"])
    add("avg_ent_arr", "What was average ARR per enterprise customer at the end of September 2026?",
        round(ent_sep.arr_usd.sum() / ent_sep.customer_id.nunique(), 2), traps=["tcv_vs_arr"])
    tk = r("raw_support", "tickets"); tk["created_at"] = pd.to_datetime(tk.created_at)
    add("urgent_sep", "How many urgent support tickets were created in September 2026?",
        int(((tk.priority == "urgent") & (tk.created_at >= "2026-09-01") & (tk.created_at < "2026-10-01")).sum()), tol=0)
    reg = sep.merge(cust[["customer_id", "region"]].drop_duplicates("customer_id"), on="customer_id")
    add("top_region", "Which region had the most total ARR at the end of September 2026? Answer NA, EMEA, APAC, or LATAM.",
        reg.groupby("region").arr_usd.sum().idxmax(), kind="category")
    up = set(cust[cust.upgraded_from_self_serve].customer_id)
    add("upgraded_arr", "How much ARR at the end of September 2026 came from enterprise customers who started on self-serve?",
        round(sep[sep.customer_id.isin(up)].arr_usd.sum(), 2), traps=["customer_identity"])

    # ---- holdout: written after the guides, same rules, new wording. Never used for tuning. ----
    H = "holdout"
    region = cust.drop_duplicates("customer_id").set_index("customer_id")["region"]
    mar26 = m("2026-03-01")
    add("h_emea_arr_mar26", "What was ARR at the end of March 2026 for customers in EMEA?",
        round(mar26[mar26.customer_id.map(region) == "EMEA"].arr_usd.sum(), 2),
        traps=["two_revenue_streams", "tcv_vs_arr"], split=H)
    add("h_arr_change_ytd", "How much did ARR grow between December 31, 2025 and September 30, 2026?",
        round(sep.arr_usd.sum() - m("2025-12-01").arr_usd.sum(), 2),
        traps=["two_revenue_streams", "arr_summed_over_months"], split=H)
    add("h_ss_share", "What percent of ARR at the end of September 2026 came from the self-serve business?",
        round(100 * sep[sep.motion == "self_serve"].arr_usd.sum() / sep.arr_usd.sum(), 2), kind="percent", tol=0.5,
        traps=["two_revenue_streams", "invoice_double_count"], split=H)
    add("h_h1_arr", "What was our ARR for the first half of 2026?", round(jun.arr_usd.sum(), 2),
        traps=["arr_summed_over_months"], split=H)
    sep25_c = set(sep25.customer_id)
    add("h_logo_churn", "Of the customers paying at the end of September 2025, how many were no longer paying as of "
        "October 14, 2026? A customer that moved from self-serve to enterprise counts as retained.",
        len(sep25_c - now), tol=0, traps=["upgrade_is_not_churn", "customer_identity"], split=H)
    d9d = d9.assign(dep=d9.org_id.map(dep))
    add("h_top_deployment", "Which deployment type ingested the most base traces in September 2026, excluding "
        "internal usage? Answer cloud, hybrid, or self_hosted.",
        d9d.groupby("dep").traces.sum().idxmax(), kind="category", traps=["sf_deployment_stale"], split=H)
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "golden.jsonl")
    a = ap.parse_args()
    qs = build(a.data)
    a.out.write_text("\n".join(json.dumps(x, default=str) for x in qs) + "\n")
    print(f"wrote {len(qs)} questions to {a.out}")


if __name__ == "__main__":
    main()
