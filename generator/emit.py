"""Turn entities into daily activity and emitted source tables (usage, events, invoices, tickets)."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .sim import EVENTS, Org, Sim, add_months

METRICS = ["base_traces", "extended_traces", "seats"]
DEPLOYMENTS = ["cloud", "hybrid", "self_hosted"]
MOTIONS = ["", "free", "plus", "enterprise", "internal"]
TICKET_CATS = ["tracing", "evaluations", "deployment", "billing", "sso_access", "performance", "sdk_bug"]
PRIORITIES = np.array(["low", "normal", "high", "urgent"])


def _curve(sim: Sim, n: int, arch: str, ends: bool) -> np.ndarray:
    t = np.arange(n, dtype=float)
    if arch == "grower":
        c = 1 + 1.5 * t / max(n - 1, 1)
    elif arch == "at_risk_saved":
        mid = sim.rng.uniform(0.3, 0.8) * n
        c = 1 - 0.65 * np.exp(-((t - mid) / 35) ** 2)
    elif arch == "churner" and ends:
        c = np.ones(n)
        k = min(n, 100)
        c[n - k:] = np.linspace(1, 0.2, k)
    elif arch == "free":
        c = np.exp(-t / sim.rng.uniform(20, 120))
    else:
        c = np.ones(n)
    return c


class Emitter:
    def __init__(self, sim: Sim, out_dir, events_writer_rows: int = 2_000_000):
        self.sim, self.out = sim, out_dir
        self.usage, self.invoices, self.subs, self.tickets, self.truth_daily = [], [], [], [], []
        self._ev_buf, self._ev_rows, self._ev_writer = [], 0, None
        self._chunk = events_writer_rows
        self._usage_seq = 0

    # ------------- phases -------------
    def phases(self, o: Org):
        """Return list of (motion, lo, hi, archetype) in day indexes, inclusive."""
        s, D = self.sim, self.sim.D
        out = []
        if o.is_internal:
            return [("internal", 0, D - 1, "steady")]
        acct_state = s.ent.get(o.account_id) if o.account_id else None
        first_paid = o.plus_start if o.plus_start is not None else (o.ent_start if not o.is_sandbox else None)
        free_hi = (first_paid - 1) if first_paid is not None else D - 1
        if o.is_sandbox:
            free_hi = o.created - 1
        if free_hi >= o.created:
            out.append(("free", o.created, free_hi, "free"))
        if o.plus_start is not None:
            hi = o.plus_end if o.plus_end is not None else D - 1
            out.append(("plus", o.plus_start, hi, o.plus_archetype))
        if acct_state is not None:
            lo = o.created if o.is_sandbox else o.ent_start
            churn = acct_state["churn_date"]
            hi = (s.idx(churn) - 1) if churn else D - 1
            if lo <= hi:
                out.append(("enterprise", lo, hi, acct_state["archetype"]))
        return out

    def dep_by_day(self, o: Org) -> np.ndarray:
        dep = np.empty(self.sim.D, dtype=object)
        for i, (d, t) in enumerate(o.deployment_history):
            dep[max(0, d):] = t
        return dep

    # ------------- per org -------------
    def run(self):
        s = self.sim
        for o in s.orgs:
            self._org(o)
        self._flush_events(final=True)

    def _org(self, o: Org):
        s, rng, D = self.sim, self.sim.rng, self.sim.D
        traces = np.zeros(D)
        seats = np.zeros(D, dtype=np.int32)
        curve = np.zeros(D)
        motion = np.full(D, "", dtype=object)
        base_p = np.zeros(D)
        acct = s.ent.get(o.account_id) if o.account_id else None

        for m, lo, hi, arch in self.phases(o):
            n = hi - lo + 1
            ends = (m == "plus" and o.plus_end is not None and o.ent_start is None) or \
                   (m == "enterprise" and acct and acct["churn_date"] is not None)
            c = _curve(s, n, arch, ends)
            curve[lo:hi + 1] = c
            motion[lo:hi + 1] = m
            noise = rng.lognormal(0, 0.45, n) * s.weekday[lo:hi + 1]
            if m == "free":
                if o.activated:
                    traces[lo:hi + 1] = np.minimum(60 * c * noise, 400)
                    base_p[lo:hi + 1] = 0.35
                else:
                    k = min(n, 3)
                    pick = rng.choice(n, k, replace=False)
                    traces[lo + pick] = rng.integers(3, 60, k)
                    base_p[lo + pick] = 0.5
            elif m == "plus":
                sp = np.full(n, int(rng.integers(1, 4)))
                if arch == "grower":
                    bumps = np.cumsum(rng.random(n) < 1 / 60)
                    sp = np.minimum(sp + bumps, 25)
                seats[lo:hi + 1] = sp
                traces[lo:hi + 1] = 650 * sp ** 0.6 * c * noise
                base_p[lo:hi + 1] = 0.25
            elif m == "enterprise":
                if o.is_sandbox:
                    traces[lo:hi + 1] = 2_000 * c * noise
                else:
                    seats[lo:hi + 1] = acct["seats_by_day"][lo:hi + 1]
                    arr_proxy = np.maximum(seats[lo:hi + 1], 5) * 1500
                    traces[lo:hi + 1] = arr_proxy * 0.4 * c * noise
                base_p[lo:hi + 1] = 0.20
            elif m == "internal":
                traces[lo:hi + 1] = 40_000 * noise
                base_p[lo:hi + 1] = 0.5
        traces = np.round(traces).astype(np.int64)
        paid = np.isin(motion, ["plus", "enterprise", "internal"])
        extended = np.where(paid, rng.binomial(np.maximum(traces, 0), 0.08), 0)

        # ---- usage rows (Metronome) ----
        days = np.nonzero(traces > 0)[0]
        self._usage(o, days, 0, traces[days])
        ed = np.nonzero(extended > 0)[0]
        self._usage(o, ed, 1, extended[ed])
        sd = np.nonzero(seats > 0)[0]
        self._usage(o, sd, 2, seats[sd])

        # ---- Segment events ----
        dep = self.dep_by_day(o)
        tele = np.where(dep == "cloud", 1.0, np.where(dep == "hybrid", s.cfg.hybrid_telemetry_share, 0.0))
        created = np.array([u[1] for u in o.users])
        n_users = np.searchsorted(np.sort(created), np.arange(D), side="right")
        p = np.clip(base_p * np.clip(curve, 0.05, 2), 0, 0.9) * (traces > 0)
        k = rng.binomial(n_users, p)
        n_ev = k + rng.poisson(1.5 * k)
        n_ev = rng.binomial(n_ev, tele)                  # hybrid partial, self-hosted none
        events_true = n_ev.copy()
        dau = np.zeros(D, dtype=np.int32)
        if n_ev.sum() > 0:
            ev_days = np.repeat(np.arange(D), n_ev)
            uidx = (rng.random(ev_days.size) * n_users[ev_days]).astype(int)
            user_ids = np.array([u[0] for u in o.users])[uidx]
            # distinct users per day (truth)
            key = ev_days.astype(np.int64) * 100_000 + uidx
            ud = np.unique(key) // 100_000
            np.add.at(dau, ud, 1)
            self._events(o, ev_days, user_ids)

        # ---- invoices and subscriptions ----
        self._billing(o, traces, extended, seats, motion, acct)
        # ---- tickets ----
        self._tickets(o, motion, curve)
        # ---- truth ----
        active = np.nonzero((traces > 0) | (events_true > 0) | (seats > 0))[0]
        if active.size:
            dep_code = np.array([DEPLOYMENTS.index(x) for x in dep[active]], dtype=np.int8)
            mot_code = np.array([MOTIONS.index(x) for x in motion[active]], dtype=np.int8)
            self.truth_daily.append(dict(
                org=np.full(active.size, o.idx, dtype=np.int32), day=active.astype(np.int16),
                traces=traces[active], extended_traces=extended[active].astype(np.int64),
                events=events_true[active].astype(np.int32), active_users=dau[active],
                seats=seats[active], deployment=dep_code, motion=mot_code))

    def _usage(self, o, days, metric_code, qty):
        if days.size == 0:
            return
        self._usage_seq += days.size
        self.usage.append(dict(org=np.full(days.size, o.idx, dtype=np.int32),
                               metric=np.full(days.size, metric_code, dtype=np.int8),
                               day=days.astype(np.int16), quantity=np.asarray(qty, dtype=np.int64)))

    def _events(self, o, ev_days, user_ids):
        rng = self.sim.rng
        n = ev_days.size
        secs = np.clip(rng.normal(15 * 3600, 3.5 * 3600, n), 0, 86_399).astype(np.int64)
        names = rng.choice(list(EVENTS), n, p=np.array(list(EVENTS.values())))
        ids = rng.integers(0, 2**62, n, dtype=np.int64)
        self._ev_buf.append(dict(id=ids, user_id=user_ids, org_id=np.full(n, o.org_id),
                                 event=names, day=ev_days, sec=secs))
        self._ev_rows += n
        if self._ev_rows >= self._chunk:
            self._flush_events()

    def _flush_events(self, final=False):
        if not self._ev_buf:
            if final and self._ev_writer:
                self._ev_writer.close()
            return
        s, rng = self.sim, self.sim.rng
        cols = {k: np.concatenate([b[k] for b in self._ev_buf]) for k in self._ev_buf[0]}
        if s.cfg.traps_enabled:   # trap: at-least-once delivery duplicates
            dup = rng.random(cols["id"].size) < s.cfg.segment_dup_rate
            for k in cols:
                cols[k] = np.concatenate([cols[k], cols[k][dup]])
            extra = np.zeros(cols["id"].size, dtype=np.int64)
            extra[-dup.sum():] = rng.integers(1, 600, dup.sum()) if dup.sum() else 0
        else:
            extra = np.zeros(cols["id"].size, dtype=np.int64)
        start = np.datetime64(s.cfg.start, "s")
        ts = start + (cols["day"].astype(np.int64) * 86_400 + cols["sec"]).astype("timedelta64[s]")
        recv = ts + (rng.integers(1, 20, ts.size) + extra).astype("timedelta64[s]")
        table = pa.table({
            "id": pa.array(np.char.add("evt_", np.char.mod("%016x", cols["id"]))),
            "user_id": pa.array(cols["user_id"].astype(str)),
            "org_id": pa.array(cols["org_id"].astype(str)),
            "event": pa.array(cols["event"].astype(str)),
            "timestamp": pa.array(ts, type=pa.timestamp("us", tz="UTC")),
            "received_at": pa.array(recv, type=pa.timestamp("us", tz="UTC")),
        })
        path = self.out / "raw" / "raw_segment"
        path.mkdir(parents=True, exist_ok=True)
        if self._ev_writer is None:
            self._ev_writer = pq.ParquetWriter(path / "tracks.parquet", table.schema)
        self._ev_writer.write_table(table)
        self._ev_buf, self._ev_rows = [], 0
        if final:
            self._ev_writer.close()

    def _billing(self, o, traces, extended, seats, motion, acct):
        s, c = self.sim, self.sim.cfg
        cust = o.metronome_id
        # plan subscriptions
        for m, lo, hi, _ in self.phases(o):
            plan = {"free": "developer", "plus": "plus", "enterprise": "enterprise", "internal": "internal"}[m]
            if o.is_sandbox and m == "enterprise":
                plan = "enterprise_sandbox"
            self.subs.append(dict(subscription_id=s.hex_id("sub_", 12), customer_id=cust, plan=plan,
                                  start_date=s.day(lo), end_date=None if hi >= s.D - 1 else s.day(hi)))
        # plus: calendar-month invoices issued after period end, only for closed periods
        if o.plus_start is not None:
            plo = o.plus_start
            phi = o.plus_end if o.plus_end is not None else s.D - 1
            m0 = s.day(plo).replace(day=1)
            while m0 <= s.day(phi):
                p_end = add_months(m0, 1) - timedelta(days=1)
                if p_end >= c.end:
                    break
                a, b = max(plo, s.idx(m0)), min(phi, s.idx(p_end))
                used = int(traces[a:b + 1].sum())
                ext = int(extended[a:b + 1].sum())
                st = int(seats[a:b + 1].max())
                price = c.overage_per_1k_before if m0 < c.price_change_date else c.overage_per_1k_after
                over = max(0, used - c.plus_included_traces)
                inv = s.hex_id("inv_", 14)
                for li, q, unit in (("seats", st, c.seat_price), ("base_trace_overage", over, price / 1000),
                                    ("extended_retention_upgrade", ext, c.extended_upgrade_per_1k / 1000)):
                    self.invoices.append(dict(invoice_id=inv, customer_id=cust, plan="plus", period_start=m0,
                                              period_end=p_end, line_item=li, quantity=q, unit_price=round(unit, 6),
                                              amount_usd=round(q * unit, 2), issued_at=p_end + timedelta(days=1)))
                m0 = add_months(m0, 1)
        # enterprise: commit invoiced annually per contract year, expansions invoiced once (trap: overlaps SFDC ARR)
        if acct is not None and not o.is_sandbox:
            for k in [k for k in s.contracts if k["account_id"] == o.account_id]:
                if k["type"] == "Expansion":
                    chunks = [(k["start"], k["end"])]
                else:
                    chunks, y = [], k["start"]
                    while y <= k["end"]:
                        chunks.append((y, min(k["end"], add_months(y, 12) - timedelta(days=1))))
                        y = add_months(y, 12)
                for a, b in chunks:
                    if a > c.end:
                        continue
                    months = (b.year - a.year) * 12 + (b.month - a.month) + 1
                    amt = round(k["arr"] * min(12, months) / 12, 2) if k["type"] != "Expansion" else \
                        round(k["arr"] * months / 12, 2)
                    self.invoices.append(dict(invoice_id=s.hex_id("inv_", 14), customer_id=cust, plan="enterprise",
                                              period_start=a, period_end=b, line_item="platform_commit", quantity=1,
                                              unit_price=amt, amount_usd=amt, issued_at=a))

    def _tickets(self, o, motion, curve):
        s, rng = self.sim, self.sim.rng
        rate = np.where(motion == "enterprise", 0.02, np.where(motion == "plus", 0.004, 0.0))
        rate = rate * (1 + 3 * np.clip(0.8 - curve, 0, None)) * s.weekday
        n = rng.poisson(rate)
        days = np.repeat(np.arange(s.D), n)
        for d in days:
            stressed = curve[d] < 0.6
            pr = rng.choice(PRIORITIES, p=[.15, .35, .3, .2] if stressed else [.35, .45, .15, .05])
            med = {"low": 40, "normal": 24, "high": 10, "urgent": 4}[pr]
            created = np.datetime64(s.day(d)) + np.timedelta64(int(rng.integers(0, 86_400)), "s")
            solved = created + np.timedelta64(int(rng.lognormal(np.log(med * 3600), 0.8)), "s")
            is_open = solved > np.datetime64(s.cfg.end) + np.timedelta64(1, "D")
            self.tickets.append(dict(id=s.hex_id("tkt_", 10), org_id=o.org_id,
                                     sf_account_id=o.account_id if motion[d] == "enterprise" else None,
                                     priority=str(pr), status="open" if is_open else "solved",
                                     category=str(rng.choice(TICKET_CATS)), created_at=created,
                                     solved_at=None if is_open else solved))
