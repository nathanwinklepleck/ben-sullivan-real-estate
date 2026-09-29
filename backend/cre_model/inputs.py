from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UseAssumptions(StrictModel):
    land: float = Field(default=0, ge=0)
    hard_costs: float = Field(default=0, ge=0)
    soft_costs: float = Field(default=0, ge=0)
    developer_fee: float = Field(default=0, ge=0)
    financing_closing_costs: float = Field(default=0, ge=0)
    capitalized_reserves: float = Field(default=0, ge=0)
    contingency: float = Field(default=0, ge=0)

    @property
    def total(self) -> float:
        return sum(self.model_dump().values())


class SourceAssumptions(StrictModel):
    equity: float = Field(default=0, ge=0)
    tif_grants: float = Field(default=0, ge=0)
    other_subsidy: float = Field(default=0, ge=0)

    @property
    def subsidy_total(self) -> float:
        return self.tif_grants + self.other_subsidy


class ExpenseAssumptions(StrictModel):
    property_taxes: float = Field(default=0, ge=0)
    insurance: float = Field(default=0, ge=0)
    cam: float = Field(default=0, ge=0)
    utilities: float = Field(default=0, ge=0)
    payroll: float = Field(default=0, ge=0)
    repairs: float = Field(default=0, ge=0)
    general_admin: float = Field(default=0, ge=0)
    advertising: float = Field(default=0, ge=0)
    management_rate: float = Field(default=0, ge=0, le=1)

    @property
    def recoverable_annual(self) -> float:
        return self.property_taxes + self.insurance + self.cam

    @property
    def fixed_annual(self) -> float:
        return sum(
            value
            for key, value in self.model_dump().items()
            if key != "management_rate"
        )


class UnitMixRow(StrictModel):
    unit_type: str = Field(min_length=1)
    count: int = Field(gt=0)
    average_sf: float = Field(gt=0)
    current_rent_monthly: float = Field(ge=0)
    stabilized_rent_monthly: float = Field(ge=0)


class RentStep(StrictModel):
    effective_date: date
    rent: float = Field(ge=0)


class TenantAssumptions(StrictModel):
    name: str = Field(min_length=1)
    suite: str = ""
    area_sf: float = Field(gt=0)
    lease_start: date
    lease_end: date
    current_rent: float = Field(ge=0, description="Rent per SF per year, or monthly rent")
    vacant: bool = False
    lease_up_date: date | None = None
    extension_end: date | None = None
    renewal_ti_per_sf: float = Field(default=0, ge=0)
    new_lease_ti_per_sf: float = Field(default=0, ge=0)
    renewal_commission_rate: float = Field(default=0, ge=0, le=1)
    new_lease_commission_rate: float = Field(default=0, ge=0, le=1)
    rent_basis: Literal["per_sf_year", "per_month"] = "per_sf_year"
    lease_structure: Literal["gross", "modified_gross", "nn", "nnn"] = "nnn"
    recoverable_expenses: list[Literal["property_taxes", "insurance", "cam"]] = Field(
        default_factory=lambda: ["property_taxes", "cam"]
    )
    expense_stop_per_sf: float = Field(default=0, ge=0)
    renewal_probability: float = Field(default=0.7, ge=0, le=1)
    downtime_months: int = Field(default=3, ge=0)
    market_rent_per_sf: float = Field(default=0, ge=0)
    new_lease_term_months: int = Field(default=60, gt=0)
    renewal_rent_per_sf: float | None = Field(default=None, ge=0)
    rent_steps: list[RentStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def lease_dates_are_ordered(self) -> TenantAssumptions:
        if self.lease_end < self.lease_start:
            raise ValueError("lease_end must be on or after lease_start")
        if self.extension_end and self.extension_end < self.lease_end:
            raise ValueError("extension_end must be on or after lease_end")
        return self


class LoanAssumptions(StrictModel):
    name: str = Field(min_length=1)
    amount: float = Field(gt=0)
    rate: float = Field(ge=0, le=1)
    rate_type: Literal["fixed", "floating"] = "fixed"
    spread: float = Field(default=0, ge=0, le=1)
    interest_only_months: int = Field(default=0, ge=0)
    amortization_years: int = Field(default=0, ge=0)
    term_months: int = Field(default=120, gt=0)
    origination_fee_rate: float = Field(default=0, ge=0, le=1)


class WaterfallTier(StrictModel):
    name: str = Field(min_length=1)
    hurdle_irr: float | None = Field(default=None, ge=0, le=2)
    lp_split: float = Field(ge=0, le=1)
    gp_split: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_split(self) -> WaterfallTier:
        if abs(self.lp_split + self.gp_split - 1) > 1e-9:
            raise ValueError("LP and GP splits must sum to 100%")
        return self


class InvestorAssumptions(StrictModel):
    gp_coinvest_pct: float = Field(default=0, ge=0, le=1)
    minimum_investment: float = Field(default=0, ge=0)
    preferred_return_rate: float = Field(default=0, ge=0, le=1)
    gp_catch_up: bool = False
    tiers: list[WaterfallTier] = Field(
        default_factory=lambda: [
            WaterfallTier(name="Unpromoted", lp_split=1, gp_split=0)
        ],
        min_length=1,
    )


class InvestorCashFlow(StrictModel):
    date: date
    contribution: float
    distribution: float
    net_cash_flow: float


class WaterfallPeriod(StrictModel):
    date: date
    lp_contribution: float
    gp_contribution: float
    lp_distribution: float
    gp_distribution: float


class WaterfallResults(StrictModel):
    lp_irr: float | None
    gp_irr: float | None
    lp_equity_multiple: float
    gp_equity_multiple: float
    lp_contributions: float
    gp_contributions: float
    lp_distributions: float
    gp_distributions: float
    lp_cash_flows: list[InvestorCashFlow]
    gp_cash_flows: list[InvestorCashFlow]
    monthly_periods: list[WaterfallPeriod]


class DealAssumptions(StrictModel):
    property_name: str = Field(min_length=1)
    address: str = ""
    report_label: str = ""
    property_type: Literal["multifamily", "retail", "office", "industrial"]
    deal_type: Literal["acquisition", "development"] = "acquisition"
    closing_date: date
    analysis_start_date: date
    units: int = Field(default=0, ge=0)
    total_nra_sf: float = Field(default=0, ge=0)
    illustrative_investment_amount: float = Field(default=0, ge=0)
    hold_years: int = Field(ge=5, le=10)
    exit_cap_rate: float = Field(gt=0, le=1)
    sale_cost_rate: float = Field(default=0.02, ge=0, le=1)
    vacancy_rate: float = Field(default=0.05, ge=0, le=1)
    concessions_rate: float = Field(default=0, ge=0, le=1)
    bad_debt_rate: float = Field(default=0, ge=0, le=1)
    other_income_per_unit_monthly: float = Field(default=0, ge=0)
    revenue_growth_rate: float = Field(default=0.03, ge=-0.5, le=1)
    expense_growth_rate: float = Field(default=0.03, ge=-0.5, le=1)
    replacement_reserve_per_unit_annual: float = Field(default=0, ge=0)
    construction_months: int = Field(default=0, ge=0)
    lease_up_absorption_units_monthly: float = Field(default=0, ge=0)
    stabilization_month: int = Field(default=12, gt=0)
    modified_gross_expense_stop_per_sf: float = Field(default=0, ge=0)
    uses: UseAssumptions = Field(default_factory=UseAssumptions)
    sources: SourceAssumptions = Field(default_factory=SourceAssumptions)
    expenses: ExpenseAssumptions = Field(default_factory=ExpenseAssumptions)
    investor: InvestorAssumptions = Field(default_factory=InvestorAssumptions)
    unit_mix: list[UnitMixRow] = Field(default_factory=list)
    rent_roll: list[TenantAssumptions] = Field(default_factory=list, max_length=500)
    loans: list[LoanAssumptions] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_property_inputs(self) -> DealAssumptions:
        if self.analysis_start_date < self.closing_date:
            raise ValueError("analysis_start_date must be on or after closing_date")
        if self.property_type == "multifamily":
            if not self.unit_mix:
                raise ValueError("multifamily deals require at least one unit_mix row")
            if self.units and sum(row.count for row in self.unit_mix) != self.units:
                raise ValueError("unit_mix counts must equal units")
        elif not self.rent_roll:
            raise ValueError("commercial deals require at least one rent_roll tenant")
        return self

    @property
    def total_units(self) -> int:
        return self.units or sum(row.count for row in self.unit_mix)

    @property
    def rentable_area(self) -> float:
        if self.total_nra_sf:
            return self.total_nra_sf
        assumptions = self.model_dump()
        if assumptions["unit_mix"]:
            return sum(
                row["count"] * row["average_sf"]
                for row in assumptions["unit_mix"]
            )
        return sum(tenant["area_sf"] for tenant in assumptions["rent_roll"])

    @property
    def total_uses(self) -> float:
        assumptions = self.model_dump()
        fees = sum(
            loan["amount"] * loan["origination_fee_rate"]
            for loan in assumptions["loans"]
        )
        return sum(assumptions["uses"].values()) + fees


class CashFlowRow(StrictModel):
    month: int
    date: date
    potential_rent: float
    effective_gross_income: float
    operating_expenses: float
    net_operating_income: float
    reserves: float
    leasing_costs: float = 0
    debt_service: float
    debt_payoff: float
    unlevered_cash_flow: float
    levered_cash_flow: float
    sale_proceeds: float


class AnnualCashFlow(StrictModel):
    year: int
    effective_gross_income: float
    operating_expenses: float
    net_operating_income: float
    leasing_costs: float = 0
    debt_service: float
    debt_payoff: float
    unlevered_cash_flow: float
    levered_cash_flow: float


class SensitivityPoint(StrictModel):
    exit_cap_rate: float | None = None
    hold_years: int | None = None
    levered_irr: float | None
    equity_multiple: float


class DealResults(StrictModel):
    property_name: str
    total_uses: float
    total_debt: float
    required_equity: float
    unlevered_irr: float | None
    levered_irr: float | None
    unlevered_equity_multiple: float
    levered_equity_multiple: float
    average_cash_on_cash: float
    stabilized_yield_on_cost: float
    development_spread: float
    exit_value: float
    monthly_cash_flows: list[CashFlowRow]
    annual_cash_flows: list[AnnualCashFlow]
    exit_cap_sensitivity: list[SensitivityPoint] = Field(default_factory=list)
    hold_period_sensitivity: list[SensitivityPoint] = Field(default_factory=list)
    waterfall: WaterfallResults | None = None