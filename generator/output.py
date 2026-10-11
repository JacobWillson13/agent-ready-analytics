"""Write raw source tables and ground-truth tables to parquet."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .emit import DEPLOYMENTS, METRICS, MOTIONS, Emitter
from .sim import COUNTRIES, Sim, add_months


def _write(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _soft_deletes(sim: Sim, df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Trap: Salesforce keeps soft-deleted duplicate records."""
    if not sim.cfg.traps_enabled:
        return df
    dup = df.sample(frac=sim.cfg.sf_soft_delete_rate, random_state=sim.cfg.seed).copy()
    dup["id"] = [sim.sf_id(prefix) for _ in range(len(dup))]
    dup["is_deleted"] = True
    return pd.concat([df, dup], ignore_index=True)


def write_raw(sim: Sim, em: Emitter, out: Path) -> dict:
    r = out / "raw"
    counts = {}

    def put(ds, name, df):
        _write(df, r / ds / f"{name}.parquet")
        counts[f"{ds}.{name}"] = len(df)

    # Salesforce
    put("raw_salesforce", "account", _soft_deletes(sim, pd.DataFrame(sim.accounts), "001"))
    put("raw_salesforce", "opportunity", _soft_deletes(sim, pd.DataFrame(sim.opps), "006"))
    put("raw_salesforce", "user", pd.DataFrame(sim.owners))
    # App
    orgs = pd.DataFrame([dict(org_id=o.org_id, sf_account_id=o.account_id, org_name=o.name,
                              deployment_type=o.deployment, country=o.country, is_internal=o.is_internal,
                              created_at=pd.Timestamp(sim.day(o.created)) + pd.Timedelta(hours=9))
                         for o in sim.orgs])
    put("raw_app", "organizations", orgs)
    users = pd.DataFrame([dict(user_id=u[0], org_id=o.org_id, email=u[2],
                               role="admin" if j == 0 else "member",
                               created_at=pd.Timestamp(sim.day(u[1])) + pd.Timedelta(hours=10))
                          for o in sim.orgs for j, u in enumerate(o.users)])
    put("raw_app", "users", users)
    # Metronome
    put("raw_metronome", "customers", pd.DataFrame([dict(
        customer_id=o.metronome_id, org_id=o.org_id, salesforce_account_id=o.account_id, name=o.name,
        created_at=pd.Timestamp(sim.day(o.created))) for o in sim.orgs]))
    put("raw_metronome", "plan_subscriptions", pd.DataFrame(em.subs))
    u = {k: np.concatenate([b[k] for b in em.usage]) for k in em.usage[0]}
    em.usage = []
    mc_ids = np.array([o.metronome_id for o in sim.orgs])
    usage = pd.DataFrame(dict(
        usage_id=np.arange(len(u["org"]), dtype=np.int64),
        customer_id=pd.Categorical.from_codes(u["org"], categories=mc_ids),
        billable_metric_name=pd.Categorical.from_codes(u["metric"], categories=METRICS),
        usage_date=pd.to_datetime(sim.cfg.start) + pd.to_timedelta(u["day"].astype(np.int64), unit="D"),
        quantity=u["quantity"]))
    usage["usage_date"] = usage["usage_date"].dt.date
    put("raw_metronome", "usage", usage)
    del u, usage
    put("raw_metronome", "invoices", pd.DataFrame(em.invoices))
    put("raw_metronome", "price_book", pd.DataFrame([
        dict(plan="plus", item="seat", unit="seat_month", price_usd=sim.cfg.seat_price,
             effective_from=sim.cfg.start, effective_to=None),
        dict(plan="plus", item="base_trace_overage", unit="per_1k", price_usd=sim.cfg.overage_per_1k_before,
             effective_from=sim.cfg.start, effective_to=sim.cfg.price_change_date - timedelta(days=1)),
        dict(plan="plus", item="base_trace_overage", unit="per_1k", price_usd=sim.cfg.overage_per_1k_after,
             effective_from=sim.cfg.price_change_date, effective_to=None),
        dict(plan="plus", item="extended_retention_upgrade", unit="per_1k", price_usd=sim.cfg.extended_upgrade_per_1k,
             effective_from=sim.cfg.start, effective_to=None),
        dict(plan="plus", item="included_base_traces", unit="traces_month", price_usd=0.0,
             effective_from=sim.cfg.start, effective_to=None)]))
    # Support
    t = pd.DataFrame(em.tickets)
    put("raw_support", "tickets", t)
    return counts


def write_truth(sim: Sim, em: Emitter, out: Path) -> dict:
    """Ground truth computed from simulation state, never from emitted raw tables."""
    c = sim.cfg
    tdir = out / "truth"
    td = {k: np.concatenate([b[k] for b in em.truth_daily]) for k in em.truth_daily[0]}
    em.truth_daily = []
    org_ids = np.array([o.org_id for o in sim.orgs])
    cust = {o.org_id: (o.account_id if (o.account_id and not o.is_internal) else o.org_id) for o in sim.orgs}
    cust_arr = np.array([cust[x] for x in org_ids])
    internal = np.array([o.is_internal for o in sim.orgs])
    oc = td.pop("org")
    daily = pd.DataFrame(dict(
        org_id=pd.Categorical.from_codes(oc, categories=org_ids),
        date=(pd.to_datetime(sim.cfg.start) + pd.to_timedelta(td.pop("day").astype(np.int64), unit="D")),
        customer_id=pd.Categorical(cust_arr[oc]),
        is_internal=internal[oc],
        deployment=pd.Categorical.from_codes(td.pop("deployment"), categories=DEPLOYMENTS),
        motion=pd.Categorical.from_codes(td.pop("motion"), categories=MOTIONS), **td))
    daily["date"] = daily["date"].dt.date
    _write(daily, tdir / "truth_org_daily.parquet")

    # orgs + funnel (activation = first day cumulative base traces reach 1,000)
    rows = []
    for o in sim.orgs:
        rows.append(dict(org_id=o.org_id, customer_id=cust[o.org_id], is_internal=o.is_internal,
                         is_sandbox=o.is_sandbox, signup_date=sim.day(o.created),
                         plus_start=sim.day(o.plus_start) if o.plus_start is not None else None,
                         plus_end=sim.day(o.plus_end) if o.plus_end is not None else None,
                         upgraded_to_enterprise=o.plus_start is not None and o.ent_start is not None,
                         enterprise_start=sim.day(o.ent_start) if o.ent_start is not None else None,
                         deployment_now=o.deployment))
    orgs = pd.DataFrame(rows)
    for col in ("signup_date", "plus_start", "plus_end", "enterprise_start"):
        orgs[col] = pd.to_datetime(orgs[col])
    d = daily[["org_id", "date", "traces"]].astype({"org_id": str}).sort_values(["org_id", "date"])
    d["cum"] = d.groupby("org_id")["traces"].cumsum()
    act = pd.to_datetime(d[d["cum"] >= 1000].groupby("org_id")["date"].min()).rename("activation_date")
    orgs = orgs.merge(act, on="org_id", how="left")
    orgs["first_paid_date"] = orgs[["plus_start", "enterprise_start"]].min(axis=1)
    orgs.loc[orgs["is_sandbox"], "first_paid_date"] = pd.NaT
    _write(orgs, tdir / "truth_orgs.parquet")

    # customers
    crow = []
    for acct, st in sim.ent.items():
        o = sim.orgs[st["org_index"]]
        crow.append(dict(customer_id=acct, motion="enterprise", archetype=st["archetype"],
                         region=COUNTRIES[o.country][1], deployment_now=o.deployment,
                         churn_date=st["churn_date"], upgraded_from_self_serve=st["upgraded"]))
    for o in sim.orgs:
        if o.plus_start is not None and o.ent_start is None:
            crow.append(dict(customer_id=o.org_id, motion="self_serve", archetype=o.plus_archetype,
                             region=COUNTRIES[o.country][1], deployment_now="cloud",
                             churn_date=sim.day(o.plus_end + 1) if o.plus_end is not None else None,
                             upgraded_from_self_serve=False))
    customers = pd.DataFrame(crow)
    _write(customers, tdir / "truth_customers.parquet")

    # ARR monthly: enterprise = annualized contracts live on as_of; self-serve = 12 x latest closed plus invoice
    contracts = pd.DataFrame(sim.contracts)
    inv = pd.DataFrame(em.invoices)
    plus_inv = inv[inv["plan"] == "plus"].groupby(["customer_id", "period_end"], as_index=False)["amount_usd"].sum()
    mc_to_org = {o.metronome_id: o for o in sim.orgs}
    plus_inv["org_id"] = plus_inv["customer_id"].map(lambda m: mc_to_org[m].org_id)
    plus_orgs = [o for o in sim.orgs if o.plus_start is not None]
    out_rows = []
    m = c.start.replace(day=1)
    while m <= c.end:
        as_of = min(add_months(m, 1) - timedelta(days=1), c.end)
        live = contracts[(contracts["start"] <= as_of) & (contracts["end"] >= as_of)]
        for acct, arr in live.groupby("account_id")["arr"].sum().items():
            out_rows.append(dict(customer_id=acct, month_start=m, as_of_date=as_of, motion="enterprise",
                                 arr_usd=round(arr, 2)))
        closed = plus_inv[plus_inv["period_end"] <= as_of]
        latest = closed.sort_values("period_end").groupby("org_id").tail(1).set_index("org_id")["amount_usd"]
        ai = sim.idx(as_of)
        for o in plus_orgs:
            hi = o.plus_end if o.plus_end is not None else sim.D - 1
            if o.plus_start <= ai <= hi and o.org_id in latest.index:
                out_rows.append(dict(customer_id=cust[o.org_id], month_start=m, as_of_date=as_of,
                                     motion="self_serve", arr_usd=round(12 * latest[o.org_id], 2)))
        m = add_months(m, 1)
    arr = pd.DataFrame(out_rows)
    _write(arr, tdir / "truth_arr_monthly.parquet")
    _write(contracts, tdir / "truth_contracts.parquet")
    return dict(daily=len(daily), orgs=len(orgs), customers=len(customers), arr_rows=len(arr))
