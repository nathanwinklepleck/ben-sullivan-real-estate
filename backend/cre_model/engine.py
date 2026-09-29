from __future__ import annotations

import calendar
from datetime import date

import numpy_financial as npf

from cre_model.inputs import (
    AnnualCashFlow,
    CashFlowRow,
    DealAssumptions,
    DealResults,
    InvestorAssumptions,
    InvestorCashFlow,
    SensitivityPoint,
    TenantAssumptions,
    WaterfallPeriod,
    WaterfallResults,
)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def annualized_monthly_irr(cash_flows: list[float]) -> float | None:
    if not any(value < 0 for value in cash_flows) or not any(
        value > 0 for value in cash_flows
    ):
        return None
    monthly_irr = float(npf.irr(cash_flows))
    if monthly_irr <= -1:
        return None
    return (1 + monthly_irr) ** 12 - 1


def xirr(cash_flows: list[float], dates: list[date]) -> float | None:
    if len(cash_flows) != len(dates):
        raise ValueError("cash_flows and dates must have the same length")
    if not any(value < 0 for value in cash_flows) or not any(
        value > 0 for value in cash_flows
    ):
        return None

    start_date = dates[0]
    year_fractions = [(current_date - start_date).days / 365 for current_date in dates]

    def npv(rate: float) -> float:
        return sum(
            amount / (1 + rate) ** year_fraction
            for amount, year_fraction in zip(cash_flows, year_fractions, strict=True)
        )

    lower = -0.9999
    upper = 1.0
    lower_value = npv(lower)
    upper_value = npv(upper)
    while lower_value * upper_value > 0 and upper < 1_000_000:
        upper = upper * 2 + 1
        upper_value = npv(upper)
    if lower_value * upper_value > 0:
        return None

    for _ in range(200):
        midpoint = (lower + upper) / 2
        midpoint_value = npv(midpoint)
        if abs(midpoint_value) < 1e-8:
            return midpoint
        if lower_value * midpoint_value <= 0:
            upper = midpoint
            upper_value = midpoint_value
        else:
            lower = midpoint
            lower_value = midpoint_value
    return (lower + upper) / 2


def _gross_distribution_to_hurdle(
    lp_cash_flows: list[float],
    dates: list[date],
    available: float,
    lp_split: float,
    hurdle_irr: float,
) -> float:
    if available <= 0 or lp_split <= 0:
        return 0.0
    current_irr = xirr(lp_cash_flows, dates)
    if current_irr is not None and current_irr >= hurdle_irr:
        return 0.0

    full_irr = xirr(
        [*lp_cash_flows[:-1], lp_cash_flows[-1] + available * lp_split], dates
    )
    if full_irr is None or full_irr < hurdle_irr:
        return available

    lower = 0.0
    upper = available
    for _ in range(100):
        midpoint = (lower + upper) / 2
        candidate_irr = xirr(
            [*lp_cash_flows[:-1], lp_cash_flows[-1] + midpoint * lp_split], dates
        )
        if candidate_irr is not None and candidate_irr >= hurdle_irr:
            upper = midpoint
        else:
            lower = midpoint
    return upper


def run_waterfall(
    project_cash_flows: list[float],
    dates: list[date],
    assumptions: InvestorAssumptions,
) -> WaterfallResults:
    if len(project_cash_flows) != len(dates):
        raise ValueError("project_cash_flows and dates must have the same length")
    if not project_cash_flows:
        raise ValueError("at least one project cash flow is required")

    gp_fraction = assumptions.gp_coinvest_pct
    lp_fraction = 1 - gp_fraction
    initial_contribution = max(0.0, -project_cash_flows[0])
    lp_capital = initial_contribution * lp_fraction
    gp_capital = initial_contribution * gp_fraction
    lp_cash_flows = [project_cash_flows[0] * lp_fraction]
    gp_cash_flows = [project_cash_flows[0] * gp_fraction]
    lp_contributions = [initial_contribution * lp_fraction]
    gp_contributions = [initial_contribution * gp_fraction]
    lp_distributions = [0.0]
    gp_distributions = [0.0]
    periods = [
        WaterfallPeriod(
            date=dates[0],
            lp_contribution=lp_contributions[0],
            gp_contribution=gp_contributions[0],
            lp_distribution=0,
            gp_distribution=0,
        )
    ]
    preferred_due = 0.0
    preferred_paid = 0.0
    gp_catch_up_paid = 0.0
    monthly_pref = assumptions.preferred_return_rate / 12

    for index, project_cash_flow in enumerate(project_cash_flows[1:], start=1):
        current_date = dates[index]
        preferred_due += (lp_capital + preferred_due) * monthly_pref
        lp_cash_flows.append(0.0)
        gp_cash_flows.append(0.0)
        lp_contribution = 0.0
        gp_contribution = 0.0
        lp_distribution = 0.0
        gp_distribution = 0.0

        if project_cash_flow < 0:
            lp_contribution = -project_cash_flow * lp_fraction
            gp_contribution = -project_cash_flow * gp_fraction
            lp_capital += lp_contribution
            gp_capital += gp_contribution
            lp_cash_flows[index] -= lp_contribution
            gp_cash_flows[index] -= gp_contribution
            lp_contributions.append(lp_contribution)
            gp_contributions.append(gp_contribution)
            lp_distributions.append(0.0)
            gp_distributions.append(0.0)
            periods.append(
                WaterfallPeriod(
                    date=current_date,
                    lp_contribution=lp_contribution,
                    gp_contribution=gp_contribution,
                    lp_distribution=0,
                    gp_distribution=0,
                )
            )
            continue

        lp_contributions.append(0.0)
        gp_contributions.append(0.0)
        lp_distributions.append(0.0)
        gp_distributions.append(0.0)
        available = project_cash_flow

        contributed_capital = lp_capital + gp_capital
        returned_capital = min(available, contributed_capital)
        if returned_capital and contributed_capital:
            lp_return = min(lp_capital, returned_capital * lp_capital / contributed_capital)
            gp_return = min(gp_capital, returned_capital - lp_return)
            lp_capital -= lp_return
            gp_capital -= gp_return
            available -= lp_return + gp_return
            lp_distribution += lp_return
            gp_distribution += gp_return

        preferred_distribution = min(available, preferred_due)
        preferred_due -= preferred_distribution
        preferred_paid += preferred_distribution
        available -= preferred_distribution
        lp_distribution += preferred_distribution

        if assumptions.gp_catch_up and assumptions.tiers:
            lead_tier = assumptions.tiers[0]
            if lead_tier.lp_split > 0 and lead_tier.gp_split > 0:
                catch_up_target = preferred_paid * lead_tier.gp_split / lead_tier.lp_split
                catch_up = min(available, max(0.0, catch_up_target - gp_catch_up_paid))
                gp_catch_up_paid += catch_up
                available -= catch_up
                gp_distribution += catch_up

        active_dates = dates[: index + 1]
        for tier in assumptions.tiers:
            if available <= 1e-8:
                break
            if tier.hurdle_irr is None:
                tier_distribution = available
            else:
                tier_distribution = _gross_distribution_to_hurdle(
                    [
                        *lp_cash_flows[:index],
                        lp_cash_flows[index] + lp_distribution,
                    ],
                    active_dates,
                    available,
                    tier.lp_split,
                    tier.hurdle_irr,
                )
            lp_share = tier_distribution * tier.lp_split
            gp_share = tier_distribution * tier.gp_split
            lp_distribution += lp_share
            gp_distribution += gp_share
            available -= tier_distribution

        if available > 1e-8:
            final_tier = assumptions.tiers[-1]
            lp_distribution += available * final_tier.lp_split
            gp_distribution += available * final_tier.gp_split

        lp_cash_flows[index] += lp_distribution
        gp_cash_flows[index] += gp_distribution
        lp_distributions[index] = lp_distribution
        gp_distributions[index] = gp_distribution
        periods.append(
            WaterfallPeriod(
                date=current_date,
                lp_contribution=0,
                gp_contribution=0,
                lp_distribution=lp_distribution,
                gp_distribution=gp_distribution,
            )
        )

    lp_dates = [InvestorCashFlow(date=dates[index], contribution=lp_contributions[index], distribution=lp_distributions[index], net_cash_flow=lp_cash_flows[index]) for index in range(len(dates))]
    gp_dates = [InvestorCashFlow(date=dates[index], contribution=gp_contributions[index], distribution=gp_distributions[index], net_cash_flow=gp_cash_flows[index]) for index in range(len(dates))]
    total_lp_contributions = sum(lp_contributions)
    total_gp_contributions = sum(gp_contributions)
    total_lp_distributions = sum(lp_distributions)
    total_gp_distributions = sum(gp_distributions)
    return WaterfallResults(
        lp_irr=xirr(lp_cash_flows, dates),
        gp_irr=xirr(gp_cash_flows, dates),
        lp_equity_multiple=total_lp_distributions / max(total_lp_contributions, 1),
        gp_equity_multiple=total_gp_distributions / max(total_gp_contributions, 1),
        lp_contributions=total_lp_contributions,
        gp_contributions=total_gp_contributions,
        lp_distributions=total_lp_distributions,
        gp_distributions=total_gp_distributions,
        lp_cash_flows=lp_dates,
        gp_cash_flows=gp_dates,
        monthly_periods=periods,
    )


def _tenant_rent(tenant: TenantAssumptions, current_date: date) -> float:
    if tenant.vacant:
        return (
            tenant.market_rent_per_sf * tenant.area_sf / 12
            if tenant.lease_up_date and current_date >= tenant.lease_up_date
            else 0
        )
    if current_date < tenant.lease_start:
        return 0

    rent = tenant.current_rent
    for step in sorted(tenant.rent_steps, key=lambda row: row.effective_date):
        if step.effective_date <= current_date:
            rent = step.rent

    if current_date <= (tenant.extension_end or tenant.lease_end):
        return rent * tenant.area_sf / 12 if tenant.rent_basis == "per_sf_year" else rent

    expiration = tenant.extension_end or tenant.lease_end
    months_after_expiration = (
        (current_date.year - expiration.year) * 12
        + current_date.month
        - expiration.month
    )
    renewal_rent = tenant.renewal_rent_per_sf or tenant.market_rent_per_sf
    renewal_monthly = renewal_rent * tenant.area_sf / 12
    if months_after_expiration <= tenant.downtime_months:
        return renewal_monthly * tenant.renewal_probability
    if months_after_expiration <= tenant.downtime_months + tenant.new_lease_term_months:
        market_monthly = tenant.market_rent_per_sf * tenant.area_sf / 12
        return (
            renewal_monthly * tenant.renewal_probability
            + market_monthly * (1 - tenant.renewal_probability)
        )
    return renewal_monthly * tenant.renewal_probability


def _rent_and_reimbursements(
    deal: DealAssumptions, current_date: date, month: int
) -> tuple[float, float, float]:
    growth_factor = (1 + deal.revenue_growth_rate) ** ((month - 1) // 12)
    if deal.property_type == "multifamily":
        gross_rent = 0.0
        for row in deal.unit_mix:
            if deal.deal_type == "development":
                occupied = min(
                    row.count,
                    max(
                        0,
                        (month - deal.construction_months)
                        * deal.lease_up_absorption_units_monthly,
                    ),
                )
                rent = row.stabilized_rent_monthly
            else:
                occupied = row.count
                rent = row.current_rent_monthly
            gross_rent += occupied * rent * growth_factor
        unit_count = deal.total_units
    else:
        gross_rent = 0.0
        physical_vacancy = 0.0
        occupied_area = 0.0
        for tenant in deal.rent_roll:
            market_growth = growth_factor if tenant.vacant or current_date > (tenant.extension_end or tenant.lease_end) else 1
            rent = _tenant_rent(tenant, current_date) * market_growth
            if tenant.vacant and (not tenant.lease_up_date or current_date < tenant.lease_up_date):
                vacancy = tenant.market_rent_per_sf * tenant.area_sf / 12 * growth_factor
                occupied_share = 0.0
            elif not tenant.vacant and current_date < tenant.lease_start:
                vacancy = tenant.market_rent_per_sf * tenant.area_sf / 12 * growth_factor
                occupied_share = 0.0
            elif not tenant.vacant and current_date > (tenant.extension_end or tenant.lease_end) and (
                (current_date.year - (tenant.extension_end or tenant.lease_end).year) * 12
                + current_date.month - (tenant.extension_end or tenant.lease_end).month
            ) <= tenant.downtime_months:
                vacancy = tenant.market_rent_per_sf * tenant.area_sf / 12 * (1 - tenant.renewal_probability) * growth_factor
                occupied_share = tenant.renewal_probability
            else:
                vacancy = 0.0
                occupied_share = 1.0
            physical_vacancy += vacancy
            occupied_area += tenant.area_sf * occupied_share
            gross_rent += rent + vacancy
        unit_count = 0

    if deal.property_type == "multifamily":
        vacancy_loss = gross_rent * deal.vacancy_rate
    else:
        occupancy = occupied_area / max(deal.rentable_area, 1)
        vacancy_loss = physical_vacancy
        if occupancy >= 0.95:
            vacancy_loss = max(vacancy_loss, gross_rent * deal.vacancy_rate)
    base_egi = max(0.0, gross_rent - vacancy_loss - gross_rent * (deal.concessions_rate + deal.bad_debt_rate))
    base_egi += unit_count * deal.other_income_per_unit_monthly

    if deal.property_type == "multifamily":
        return gross_rent, base_egi, 0.0

    recoveries = 0.0
    total_area = max(deal.rentable_area, 1)
    expense_growth = (1 + deal.expense_growth_rate) ** ((month - 1) // 12)
    for tenant in deal.rent_roll:
        if tenant.vacant and (not tenant.lease_up_date or current_date < tenant.lease_up_date):
            continue
        tenant_rent = _tenant_rent(tenant, current_date)
        if tenant_rent <= 0:
            continue
        share = tenant.area_sf / total_area
        expiration = tenant.extension_end or tenant.lease_end
        months_after_expiration = (current_date.year - expiration.year) * 12 + current_date.month - expiration.month
        if not tenant.vacant and 0 < months_after_expiration <= tenant.downtime_months:
            share *= tenant.renewal_probability
        recoverable = deal.expenses.recoverable_annual * expense_growth
        if tenant.lease_structure == "gross":
            continue
        if tenant.lease_structure == "nnn":
            recoveries += recoverable * share / 12
        elif tenant.lease_structure == "nn":
            recoveries += sum(
                getattr(deal.expenses, category)
                for category in tenant.recoverable_expenses
            ) * share / 12
        elif tenant.lease_structure == "modified_gross":
            stop = tenant.expense_stop_per_sf or deal.modified_gross_expense_stop_per_sf
            current_per_sf = deal.expenses.fixed_annual * expense_growth / total_area
            recoveries += max(0.0, current_per_sf - stop) * tenant.area_sf / 12

    return gross_rent, base_egi + recoveries, recoveries


def _leasing_costs(deal: DealAssumptions, current_date: date) -> float:
    if deal.property_type == "multifamily":
        return 0
    costs = 0.0
    for tenant in deal.rent_roll:
        if tenant.vacant:
            if tenant.lease_up_date and current_date.year == tenant.lease_up_date.year and current_date.month == tenant.lease_up_date.month:
                costs += tenant.area_sf * (tenant.new_lease_ti_per_sf + tenant.market_rent_per_sf * tenant.new_lease_term_months / 12 * tenant.new_lease_commission_rate)
            continue
        if tenant.extension_end:
            extension = next((step for step in tenant.rent_steps if step.effective_date <= tenant.lease_end), None)
            if extension and current_date.year == extension.effective_date.year and current_date.month == extension.effective_date.month:
                annual_rent = extension.rent * tenant.area_sf if tenant.rent_basis == "per_sf_year" else extension.rent * 12
                costs += tenant.area_sf * tenant.renewal_ti_per_sf + annual_rent * (tenant.extension_end - tenant.lease_end).days / 365.25 * tenant.renewal_commission_rate
            continue
        if current_date.year == tenant.lease_end.year and current_date.month == tenant.lease_end.month:
            renewal_rent = tenant.renewal_rent_per_sf or tenant.market_rent_per_sf
            costs += tenant.renewal_probability * (tenant.area_sf * tenant.renewal_ti_per_sf + renewal_rent * tenant.area_sf * tenant.new_lease_term_months / 12 * tenant.renewal_commission_rate)
        if current_date.year == add_months(tenant.lease_end, tenant.downtime_months + 1).year and current_date.month == add_months(tenant.lease_end, tenant.downtime_months + 1).month:
            costs += (1 - tenant.renewal_probability) * (tenant.area_sf * tenant.new_lease_ti_per_sf + tenant.market_rent_per_sf * tenant.area_sf * tenant.new_lease_term_months / 12 * tenant.new_lease_commission_rate)
    return costs


def _loan_schedule(deal: DealAssumptions) -> tuple[list[float], list[float]]:
    months = deal.hold_years * 12
    service = [0.0] * months
    payoff = [0.0] * months
    for loan in deal.loans:
        balance = loan.amount
        monthly_rate = (loan.rate + (loan.spread if loan.rate_type == "floating" else 0)) / 12
        amort_months = loan.amortization_years * 12
        amortizing_payment: float | None = None
        for index in range(months):
            loan_month = index + 1
            if loan_month > loan.term_months:
                payoff[index] += balance
                balance = 0
                continue
            if loan_month <= loan.interest_only_months or amort_months == 0:
                payment = balance * monthly_rate
            else:
                if amortizing_payment is None:
                    remaining = max(1, amort_months - loan.interest_only_months)
                    amortizing_payment = (
                        balance / remaining
                        if monthly_rate == 0
                        else -float(npf.pmt(monthly_rate, remaining, balance))
                    )
                payment = amortizing_payment
            principal = min(balance, max(0.0, payment - balance * monthly_rate))
            balance -= principal
            service[index] += payment
            if loan_month == loan.term_months or loan_month == months:
                payoff[index] += balance
                balance = 0
    return service, payoff


def _calculate_base(deal: DealAssumptions) -> DealResults:
    month_count = deal.hold_years * 12
    debt_service, debt_payoff = _loan_schedule(deal)
    months: list[CashFlowRow] = []
    unlevered = [-deal.total_uses]
    required_equity = max(
        0.0,
        deal.total_uses
        - sum(loan.amount for loan in deal.loans)
        - deal.sources.subsidy_total,
    )
    levered = [-required_equity]
    annual_groups: dict[int, list[CashFlowRow]] = {}
    trailing_noi: list[float] = []
    exit_value = 0.0

    for month in range(1, month_count + 1):
        current_date = add_months(deal.analysis_start_date, month)
        potential_rent, egi, _ = _rent_and_reimbursements(deal, current_date, month)
        expense_growth = (1 + deal.expense_growth_rate) ** ((month - 1) // 12)
        fixed_expenses = deal.expenses.fixed_annual * expense_growth / 12
        management = egi * deal.expenses.management_rate
        operating_expenses = fixed_expenses + management
        noi = egi - operating_expenses
        reserve = (deal.total_units if deal.property_type == "multifamily" else 0) * deal.replacement_reserve_per_unit_annual / 12
        leasing_costs = _leasing_costs(deal, current_date)
        unlevered_cf = noi - reserve - leasing_costs
        sale_proceeds = 0.0

        trailing_noi.append(noi)
        if len(trailing_noi) > 12:
            trailing_noi.pop(0)
        if month == month_count:
            exit_noi = sum(trailing_noi)
            exit_value = max(0.0, exit_noi / deal.exit_cap_rate)
            sale_proceeds = exit_value * (1 - deal.sale_cost_rate)

        levered_cf = unlevered_cf - debt_service[month - 1] - debt_payoff[month - 1]
        if sale_proceeds:
            levered_cf += sale_proceeds
            unlevered_cf += sale_proceeds
        unlevered.append(unlevered_cf)
        levered.append(levered_cf)
        row = CashFlowRow(
            month=month,
            date=current_date,
            potential_rent=potential_rent,
            effective_gross_income=egi,
            operating_expenses=operating_expenses,
            net_operating_income=noi,
            reserves=reserve,
            leasing_costs=leasing_costs,
            debt_service=debt_service[month - 1],
            debt_payoff=debt_payoff[month - 1],
            unlevered_cash_flow=unlevered_cf,
            levered_cash_flow=levered_cf,
            sale_proceeds=sale_proceeds,
        )
        months.append(row)
        annual_groups.setdefault((month - 1) // 12 + 1, []).append(row)

    annual = [
        AnnualCashFlow(
            year=year,
            effective_gross_income=sum(row.effective_gross_income for row in rows),
            operating_expenses=sum(row.operating_expenses for row in rows),
            net_operating_income=sum(row.net_operating_income for row in rows),
            leasing_costs=sum(row.leasing_costs for row in rows),
            debt_service=sum(row.debt_service for row in rows),
            debt_payoff=sum(row.debt_payoff for row in rows),
            unlevered_cash_flow=sum(row.unlevered_cash_flow for row in rows),
            levered_cash_flow=sum(row.levered_cash_flow for row in rows),
        )
        for year, rows in annual_groups.items()
    ]
    stabilized_index = min(max(deal.stabilization_month, 1), month_count) - 1
    stabilized_rows = months[max(0, stabilized_index - 11) : stabilized_index + 1]
    stabilized_yoc = (
        sum(row.net_operating_income for row in stabilized_rows) / deal.total_uses
        if deal.total_uses
        else 0.0
    )
    avg_coc = (
        sum(max(0, row.levered_cash_flow) for row in months[:-1])
        / max(required_equity, 1)
        / deal.hold_years
    )
    return DealResults(
        property_name=deal.property_name,
        total_uses=deal.total_uses,
        total_debt=sum(loan.amount for loan in deal.loans),
        required_equity=required_equity,
        unlevered_irr=xirr(unlevered, [deal.analysis_start_date, *[row.date for row in months]]),
        levered_irr=xirr(levered, [deal.analysis_start_date, *[row.date for row in months]]),
        unlevered_equity_multiple=sum(max(value, 0) for value in unlevered)
        / max(-sum(min(value, 0) for value in unlevered), 1),
        levered_equity_multiple=sum(max(value, 0) for value in levered)
        / max(-sum(min(value, 0) for value in levered), 1),
        average_cash_on_cash=avg_coc,
        stabilized_yield_on_cost=stabilized_yoc,
        development_spread=(stabilized_yoc - deal.exit_cap_rate) * 100,
        exit_value=exit_value,
        monthly_cash_flows=months,
        annual_cash_flows=annual,
    )


def calculate_deal(deal: DealAssumptions) -> DealResults:
    base = _calculate_base(deal)
    exit_cap_sensitivity = []
    for basis_points in (-75, -50, -25, 0, 25, 50, 75):
        exit_cap_rate = deal.exit_cap_rate + basis_points / 10000
        if exit_cap_rate <= 0:
            continue
        scenario = _calculate_base(deal.model_copy(update={"exit_cap_rate": exit_cap_rate}))
        exit_cap_sensitivity.append(
            SensitivityPoint(
                exit_cap_rate=exit_cap_rate,
                levered_irr=scenario.levered_irr,
                equity_multiple=scenario.levered_equity_multiple,
            )
        )

    hold_period_sensitivity = []
    for hold_years in range(5, 11):
        scenario = _calculate_base(deal.model_copy(update={"hold_years": hold_years}))
        hold_period_sensitivity.append(
            SensitivityPoint(
                hold_years=hold_years,
                levered_irr=scenario.levered_irr,
                equity_multiple=scenario.levered_equity_multiple,
            )
        )

    waterfall = run_waterfall(
        [-base.required_equity, *[row.levered_cash_flow for row in base.monthly_cash_flows]],
        [deal.analysis_start_date, *[row.date for row in base.monthly_cash_flows]],
        deal.investor,
    )
    return base.model_copy(
        update={
            "exit_cap_sensitivity": exit_cap_sensitivity,
            "hold_period_sensitivity": hold_period_sensitivity,
            "waterfall": waterfall,
        }
    )