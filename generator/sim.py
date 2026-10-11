"""Simulation: entities, lifecycles, daily activity, and every emitted table.

Time is handled as integer day indexes (day 0 = cfg.start) and converted to dates on output.
Every random draw comes from one seeded numpy Generator, so a run is fully reproducible.
"""
from __future__ import annotations

import string
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from faker import Faker

from .config import Config

COUNTRIES = {  # country -> (weight, region); region mapping is also a dbt seed
    "US": (0.45, "NA"), "CA": (0.04, "NA"), "GB": (0.08, "EMEA"), "DE": (0.06, "EMEA"),
    "FR": (0.04, "EMEA"), "NL": (0.02, "EMEA"), "SE": (0.02, "EMEA"), "IL": (0.02, "EMEA"),
    "ES": (0.02, "EMEA"), "IN": (0.08, "APAC"), "JP": (0.03, "APAC"), "AU": (0.03, "APAC"),
    "SG": (0.02, "APAC"), "KR": (0.02, "APAC"), "BR": (0.03, "LATAM"), "MX": (0.02, "LATAM"),
}
INDUSTRIES = ["Software", "Financial Services", "Healthcare", "Retail", "Media",
              "Manufacturing", "Professional Services", "Education", "Telecom", "Insurance"]
EVENTS = {"Trace Viewed": .30, "Project Viewed": .18, "Experiment Run": .12, "Dataset Created": .06,
          "Prompt Saved": .10, "Annotation Submitted": .08, "Dashboard Viewed": .12,
          "Deployment Created": .04}
B62 = np.array(list(string.digits + string.ascii_letters))
HEX = np.array(list("0123456789abcdef"))


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year
    mo += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, mo, day)
        except ValueError:
            continue
    raise ValueError(d)


def bq_month_diff(a: date, b: date) -> int:
    """Mirror of BigQuery DATE_DIFF(b, a, MONTH): month boundaries crossed."""
    return (b.year - a.year) * 12 + (b.month - a.month)


@dataclass
class Org:
    idx: int
    org_id: str
    name: str
    created: int
    country: str
    domain: str
    deployment: str = "cloud"            # current (true) deployment
    deployment_history: list = field(default_factory=list)  # [(from_day, type)]
    is_internal: bool = False
    account_id: str | None = None
    metronome_id: str = ""
    plus_start: int | None = None
    plus_end: int | None = None          # inclusive last day; None = still active
    plus_archetype: str | None = None
    ent_start: int | None = None
    activated: bool = False
    is_sandbox: bool = False
    users: list = field(default_factory=list)  # [(user_id, created_day)]


class Sim:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.fake = Faker()
        Faker.seed(cfg.seed)
        self.D = (cfg.end - cfg.start).days + 1
        self.dates = np.array([cfg.start + timedelta(days=i) for i in range(self.D)])
        wd = np.array([(cfg.start.weekday() + i) % 7 for i in range(self.D)])
        self.weekday = np.where(wd >= 5, 0.35, 1.0)
        self.first_names = [self.fake.first_name().lower() for _ in range(800)]
        self.last_names = [self.fake.last_name().lower() for _ in range(800)]
        self.cc = list(COUNTRIES)
        self.cw = np.array([COUNTRIES[c][0] for c in self.cc])
        self.cw /= self.cw.sum()
        self._ids: set[str] = set()

        self.orgs: list[Org] = []
        self.accounts: list[dict] = []
        self.opps: list[dict] = []
        self.contracts: list[dict] = []      # truth: won contracts with exact ARR
        self.owners: list[dict] = []
        self.ent: dict[str, dict] = {}       # account_id -> enterprise state (truth)
        # daily arrays per org index, filled by activity()
        self.daily: dict[int, dict] = {}

    # ---------------- ids and helpers ----------------
    def _uniq(self, make):
        while True:
            s = make()
            if s not in self._ids:
                self._ids.add(s)
                return s

    def sf_id(self, prefix: str) -> str:
        return self._uniq(lambda: prefix + "".join(self.rng.choice(B62, 15)))

    def hex_id(self, prefix: str, n: int = 12) -> str:
        return self._uniq(lambda: prefix + "".join(self.rng.choice(HEX, n)))

    def day(self, i: int) -> date:
        return self.cfg.start + timedelta(days=int(i))

    def idx(self, d: date) -> int:
        return (d - self.cfg.start).days

    def country(self) -> str:
        return str(self.rng.choice(self.cc, p=self.cw))

    def company(self):
        name = self.fake.unique.company()
        slug = "".join(ch for ch in name.lower() if ch.isalnum())[:20]
        return name, f"{slug}.com"

    def pick(self, mix: dict) -> str:
        k = list(mix)
        return str(self.rng.choice(k, p=np.array([mix[x] for x in k])))

    def add_users(self, org: Org, n: int, first_day: int, last_day: int):
        have = len(org.users)
        for j in range(have, n):
            d = first_day if j == 0 else int(self.rng.integers(first_day, max(first_day + 1, last_day + 1)))
            fn, ln = self.rng.choice(self.first_names), self.rng.choice(self.last_names)
            dom = org.domain if org.domain else str(self.rng.choice(["gmail.com", "outlook.com", "proton.me"]))
            uid = self.hex_id("usr_", 10)
            org.users.append((uid, d, f"{fn}.{ln}{j}@{dom}"))
        org.users.sort(key=lambda u: u[1])

    def new_org(self, created: int, name=None, domain=None, internal=False, country=None) -> Org:
        if name is None:
            name, domain = self.company()
            if self.rng.random() < 0.6:          # many free signups are individuals
                domain = ""
        o = Org(idx=len(self.orgs), org_id=self.hex_id("org_"), name=name, created=created,
                country=country or self.country(), domain=domain or "", is_internal=internal)
        o.metronome_id = self.hex_id("mc_", 16)
        o.deployment_history = [(created, "cloud")]
        self.orgs.append(o)
        return o

    # ---------------- entities ----------------
    def build(self):
        c = self.cfg
        for i in range(c.owners):
            self.owners.append({"id": self.sf_id("005"), "name": self.fake.name(),
                                "email": f"owner{i}@lanternfly.dev", "title": "Account Executive"})
        self._internal()
        self._self_serve_funnel()
        self._sales_led_enterprise()
        self._prospects()

    def _internal(self):
        acct = self.sf_id("001")
        self.accounts.append(dict(id=acct, name="Lanternfly Labs (Internal)", website="lanternfly.dev",
                                  industry="Software", billing_country="US", employee_count=300,
                                  deployment_type__c="Cloud", account_status__c="Active",
                                  owner_id=self.owners[0]["id"], is_deleted=False,
                                  created_date=self.day(0)))
        for k in range(self.cfg.internal_orgs):
            o = self.new_org(0, name=f"lanternfly-internal-{k}", domain="lanternfly.dev", internal=True, country="US")
            o.account_id = acct
            o.activated = True
            self.add_users(o, 30, 0, self.D - 1)

    def _signup_days(self, n):
        g = np.log(self.cfg.signup_growth) / self.D
        u = self.rng.random(n)
        t = np.log1p(u * (np.exp(g * self.D) - 1)) / g      # inverse CDF of exp growth
        return np.sort(t.astype(int).clip(0, self.D - 1))

    def _self_serve_funnel(self):
        c = self.cfg
        for d in self._signup_days(c.n(c.free_signups, 50)):
            o = self.new_org(int(d))
            o.activated = self.rng.random() < c.p_activate
            self.add_users(o, 1 if self.rng.random() < 0.8 else 2, o.created, min(self.D - 1, o.created + 30))
            if not o.activated or self.rng.random() >= c.p_plus_given_active:
                continue
            ps = o.created + 3 + int(self.rng.exponential(40))
            if ps >= self.D:
                continue
            o.plus_start, o.plus_archetype = ps, self.pick(c.plus_mix)
            if o.domain == "":
                o.name, o.domain = self.company()    # paying teams register a company
            hazard = {"grower": 0.008, "steady": 0.015, "at_risk_saved": 0.025, "churner": 0.09}[o.plus_archetype]
            life = int(self.rng.geometric(hazard) * 30.4)
            if self.rng.random() < c.p_enterprise_from_plus and o.plus_archetype in ("grower", "steady"):
                es = ps + int(self.rng.integers(120, 540))
                if es < self.D and es < ps + life:
                    o.plus_end = es - 1
                    self._enterprise(o, es, upgraded=True)
                    continue
            if ps + life < self.D:
                o.plus_end = ps + life

    def _sales_led_enterprise(self):
        c = self.cfg
        days = self.rng.integers(30, self.D - 20, c.n(c.sales_led_enterprise, 6))
        for es in sorted(days):
            name, domain = self.company()
            o = self.new_org(int(es) - 30, name=name, domain=domain)
            o.activated = True
            self._enterprise(o, int(es), upgraded=False)

    def _enterprise(self, org: Org, start_day: int, upgraded: bool):
        """Create the Salesforce account, contract history, and deployment for one enterprise customer."""
        c = self.cfg
        acct = self.sf_id("001")
        org.account_id, org.ent_start = acct, start_day
        arch = self.pick(c.ent_mix)
        dep = self.pick(c.deployment_mix)
        org.deployment_history.append((start_day, dep))
        migrated_day = None
        if c.traps_enabled and dep == "cloud" and self.rng.random() < c.deployment_migration_rate:
            md = start_day + int(self.rng.integers(60, 400))
            if md < self.D:
                migrated_day = md
                org.deployment_history.append((md, "self_hosted"))
        org.deployment = org.deployment_history[-1][1]

        start = self.day(start_day)
        first_term = int(self.rng.choice([12, 24, 36], p=[0.75, 0.15, 0.10]))
        arr = float(np.clip(self.rng.lognormal(np.log(c.ent_arr_median), c.ent_arr_sigma), 20_000, 1_500_000))
        arr = round(arr / 500) * 500
        owner = self.owners[int(self.rng.integers(len(self.owners)))]["id"]
        emp = int(np.clip(self.rng.lognormal(np.log(800), 1.2), 50, 200_000))
        churn_at_renewal = 1 if self.rng.random() < 0.7 else 2
        st = dict(account_id=acct, archetype=arch, deployment_initial=dep, migrated_day=migrated_day,
                  upgraded=upgraded, org_index=org.idx, churn_date=None, region_country=org.country,
                  seats_by_day=np.zeros(self.D, dtype=np.int32))
        self.ent[acct] = st

        cur_start, cur_arr, term, k = start, arr, first_term, 0
        while True:
            cend = add_months(cur_start, term) - timedelta(days=1)
            close = cur_start - timedelta(days=int(self.rng.integers(3, 30)))
            typ = "New Business" if k == 0 else "Renewal"
            if close > c.end:          # renewal not yet closed: open pipeline
                self._opp(acct, typ, cur_arr * term / 12, cur_start, cend, close, won=False, open_=True)
                break
            self._opp(acct, typ, cur_arr * term / 12, cur_start, cend, close, won=True, arr=cur_arr)
            self._seats(st, cur_start, cend, cur_arr)
            if arch == "grower" and term >= 12:
                es = add_months(cur_start, int(self.rng.integers(3, term - 1))).replace(day=1)
                if cur_start < es <= cend:
                    exp_arr = round(cur_arr * self.rng.uniform(0.3, 0.6) / 500) * 500
                    months = bq_month_diff(es, cend + timedelta(days=1))
                    ec = es - timedelta(days=int(self.rng.integers(2, 15)))
                    if ec <= c.end and months >= 1:
                        self._opp(acct, "Expansion", exp_arr * months / 12, es, cend, ec, won=True, arr=exp_arr)
                        self._seats(st, es, cend, cur_arr + exp_arr)
                        cur_arr += exp_arr
            renewal_start = cend + timedelta(days=1)
            k += 1
            if arch == "churner" and k >= churn_at_renewal:
                lc = cend - timedelta(days=int(self.rng.integers(0, 25)))
                if lc <= c.end:
                    self._opp(acct, "Renewal", cur_arr, renewal_start, add_months(renewal_start, 12) - timedelta(days=1),
                              lc, won=False)
                    if renewal_start <= c.end:
                        st["churn_date"] = renewal_start
                else:
                    self._opp(acct, "Renewal", cur_arr, renewal_start, add_months(renewal_start, 12) - timedelta(days=1),
                              lc, won=False, open_=True)
                break
            if renewal_start > c.end + timedelta(days=200):
                break
            mult = {"steady": self.rng.uniform(1.0, 1.08), "grower": 1.05,
                    "at_risk_saved": 0.85, "churner": 1.0}[arch]
            cur_arr = round(cur_arr * mult / 500) * 500
            cur_start = renewal_start
            term = 12 if self.rng.random() < 0.8 else term

        status = "Churned" if st["churn_date"] else "Active"
        if status == "Churned" and c.traps_enabled and self.rng.random() < c.stale_status_rate:
            status = "Active"        # trap: owner never updated the field
        self.accounts.append(dict(
            id=acct, name=org.name, website=org.domain, industry=str(self.rng.choice(INDUSTRIES)),
            billing_country=org.country, employee_count=emp,
            deployment_type__c={"cloud": "Cloud", "hybrid": "Hybrid", "self_hosted": "Self-Hosted"}[dep],
            account_status__c=status, owner_id=owner, is_deleted=False,
            created_date=start - timedelta(days=int(self.rng.integers(45, 160)))))
        seats = int(st["seats_by_day"].max()) or 5
        self.add_users(org, min(seats, 150), org.created, self.D - 1)
        if self.rng.random() < self.cfg.sandbox_org_rate:
            sb = self.new_org(min(self.D - 1, start_day + int(self.rng.integers(10, 200))),
                              name=f"{org.name} Sandbox", domain=org.domain, country=org.country)
            sb.account_id, sb.is_sandbox, sb.activated = acct, True, True
            sb.deployment_history = [(sb.created, org.deployment_history[1][1])]
            sb.deployment = sb.deployment_history[-1][1]
            self.add_users(sb, 3, sb.created, self.D - 1)

    def _seats(self, st, a: date, b: date, arr: float):
        lo, hi = max(0, self.idx(a)), min(self.D - 1, self.idx(b))
        if lo <= hi:
            st["seats_by_day"][lo:hi + 1] = max(5, int(arr / 1500))

    def _opp(self, acct, typ, amount, cs, ce, close, won, open_=False, arr=None):
        oid = self.sf_id("006")
        stage = "Closed Won" if won else ("Negotiation" if open_ else "Closed Lost")
        self.opps.append(dict(id=oid, account_id=acct, name=f"{typ} {cs:%Y-%m}", type=typ, stage_name=stage,
                              is_closed=not open_, is_won=won, amount=round(float(amount), 2),
                              contract_start_date__c=cs if (won or open_) else None,
                              contract_end_date__c=ce if (won or open_) else None,
                              close_date=close, is_deleted=False,
                              created_date=close - timedelta(days=int(self.rng.integers(20, 120)))))
        if won:
            self.contracts.append(dict(contract_id=oid, account_id=acct, type=typ, start=cs, end=ce, arr=float(arr)))

    def _prospects(self):
        c = self.cfg
        for _ in range(c.n(c.prospects, 10)):
            name, domain = self.company()
            acct = self.sf_id("001")
            created = int(self.rng.integers(0, self.D - 1))
            self.accounts.append(dict(id=acct, name=name, website=domain, industry=str(self.rng.choice(INDUSTRIES)),
                                      billing_country=self.country(),
                                      employee_count=int(np.clip(self.rng.lognormal(np.log(600), 1.2), 20, 100_000)),
                                      deployment_type__c=None, account_status__c="Prospect",
                                      owner_id=self.owners[int(self.rng.integers(len(self.owners)))]["id"],
                                      is_deleted=False, created_date=self.day(created)))
            if self.rng.random() < 0.6:
                close = self.day(min(self.D + 60, created + int(self.rng.integers(30, 200))))
                open_ = close > c.end
                amt = round(float(self.rng.lognormal(np.log(50_000), 0.7)), -2)
                self._opp(acct, "New Business", amt, close + timedelta(days=7), None, close, won=False, open_=open_)
                if open_:
                    self.opps[-1]["contract_end_date__c"] = add_months(close + timedelta(days=7), 12) - timedelta(days=1)
