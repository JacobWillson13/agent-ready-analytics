"""All generator knobs in one place. Counts are full scale; --scale shrinks them."""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Config:
    seed: int = 42
    start: date = date(2024, 1, 1)           # paid product GA window starts here
    end: date = date(2026, 10, 14)           # snapshot date; also the dbt as_of_date
    scale: float = 1.0

    # funnel volumes (full scale)
    free_signups: int = 80_000
    p_activate: float = 0.50                 # share of signups that really use the product
    p_plus_given_active: float = 0.22
    p_enterprise_from_plus: float = 0.035
    sales_led_enterprise: int = 200
    prospects: int = 1_500
    owners: int = 15
    internal_orgs: int = 6
    signup_growth: float = 4.0               # daily signup rate at end vs start

    # fictional price book (seat price flat, overage price drops once)
    seat_price: float = 39.0
    plus_included_traces: int = 10_000
    price_change_date: date = date(2025, 7, 1)
    overage_per_1k_before: float = 5.00
    overage_per_1k_after: float = 2.50
    extended_upgrade_per_1k: float = 2.50

    # enterprise contracts
    ent_arr_median: float = 48_000
    ent_arr_sigma: float = 0.8
    ent_mix: dict = field(default_factory=lambda: {
        "grower": 0.25, "steady": 0.40, "at_risk_saved": 0.12, "churner": 0.23})
    plus_mix: dict = field(default_factory=lambda: {
        "grower": 0.20, "steady": 0.40, "at_risk_saved": 0.10, "churner": 0.30})
    deployment_mix: dict = field(default_factory=lambda: {
        "cloud": 0.55, "hybrid": 0.25, "self_hosted": 0.20})

    # behavior
    events_per_active_user_day: float = 2.5
    hybrid_telemetry_share: float = 0.40

    # traps (see docs/DATA_GENERATION_PLAN.md)
    traps_enabled: bool = True
    segment_dup_rate: float = 0.015
    stale_status_rate: float = 0.40          # share of churned accounts still marked Active
    deployment_migration_rate: float = 0.10  # cloud enterprise orgs that move to self-hosted
    sf_soft_delete_rate: float = 0.03
    sandbox_org_rate: float = 0.12

    def n(self, full: int, minimum: int = 1) -> int:
        return max(minimum, int(round(full * self.scale)))
