from datetime import date

import pytest

from cre_model.engine import add_months, annualized_monthly_irr, calculate_deal, run_waterfall, xirr
from cre_model.inputs import DealAssumptions, InvestorAssumptions


def sample_deal(**overrides: object) -> DealAssumptions:
    values: dict[str, object] = {
        "property_name": "Test Apartments",
        "property_type": "multifamily",
        "closing_date": date(2026, 1, 1),
        "analysis_start_date": date(2026, 1, 1),
        "hold_years": 5,
        "exit_cap_rate": 0.05,
        "units": 1,
        "uses": {"land": 100000},
        "unit_mix": [
            {
                "unit_type": "One bedroom",
                "count": 1,
                "average_sf": 700,
                "current_rent_monthly": 1000,
                "stabilized_rent_monthly": 1000,
            }
        ],
        "vacancy_rate": 0,
        "revenue_growth_rate": 0,
        "expense_growth_rate": 0,
        "stabilization_month": 12,
    }
    values.update(overrides)
    return DealAssumptions.model_validate(values)


def test_periodic_irr_annualizes_monthly_cash_flows() -> None:
    cash_flows = [-100.0] + [0.0] * 11 + [110.0]

    assert annualized_monthly_irr(cash_flows) == pytest.approx(0.10, abs=1e-7)


def test_xirr_uses_actual_dates() -> None:
    result = xirr([-100.0, 110.0], [date(2025, 1, 1), date(2026, 1, 1)])

    assert result == pytest.approx(0.10, abs=1e-7)


def test_five_year_monthly_model_has_exact_hold_length_and_positive_exit() -> None:
    result = calculate_deal(sample_deal())

    assert len(result.monthly_cash_flows) == 60
    assert len(result.annual_cash_flows) == 5
    assert result.exit_value == pytest.approx(240000)
    assert result.unlevered_irr is not None
    assert len(result.exit_cap_sensitivity) == 7
    assert [row.hold_years for row in result.hold_period_sensitivity] == [5, 6, 7, 8, 9, 10]


def test_nnn_reimbursement_increases_egi_but_gross_does_not() -> None:
    base = {
        "property_name": "Retail Suite",
        "property_type": "retail",
        "closing_date": date(2026, 1, 1),
        "analysis_start_date": date(2026, 1, 1),
        "hold_years": 5,
        "exit_cap_rate": 0.06,
        "total_nra_sf": 1000,
        "vacancy_rate": 0,
        "uses": {"land": 100000},
        "expenses": {
            "property_taxes": 12000,
            "insurance": 6000,
            "cam": 12000,
        },
        "rent_roll": [
            {
                "name": "Tenant",
                "area_sf": 1000,
                "lease_start": date(2025, 1, 1),
                "lease_end": date(2030, 1, 1),
                "current_rent": 24,
                "lease_structure": "nnn",
            }
        ],
    }
    nnn_result = calculate_deal(DealAssumptions.model_validate(base))
    nn_inputs = {
        **base,
        "rent_roll": [{**base["rent_roll"][0], "lease_structure": "nn"}],
    }
    nn_result = calculate_deal(DealAssumptions.model_validate(nn_inputs))
    gross_inputs = {
        **base,
        "rent_roll": [{**base["rent_roll"][0], "lease_structure": "gross"}],
    }
    gross_result = calculate_deal(DealAssumptions.model_validate(gross_inputs))

    assert nnn_result.monthly_cash_flows[0].effective_gross_income == pytest.approx(4500)
    assert nn_result.monthly_cash_flows[0].effective_gross_income == pytest.approx(4000)
    assert gross_result.monthly_cash_flows[0].effective_gross_income == pytest.approx(2000)


def test_modified_gross_recovers_expense_amount_above_stop() -> None:
    deal = DealAssumptions.model_validate(
        {
            "property_name": "Modified Gross Center",
            "property_type": "retail",
            "closing_date": date(2026, 1, 1),
            "analysis_start_date": date(2026, 1, 1),
            "hold_years": 5,
            "exit_cap_rate": 0.06,
            "total_nra_sf": 1000,
            "vacancy_rate": 0,
            "modified_gross_expense_stop_per_sf": 20,
            "expenses": {"property_taxes": 12000, "insurance": 6000, "cam": 12000},
            "rent_roll": [
                {
                    "name": "Tenant",
                    "area_sf": 1000,
                    "lease_start": date(2025, 1, 1),
                    "lease_end": date(2030, 1, 1),
                    "current_rent": 24,
                    "lease_structure": "modified_gross",
                }
            ],
        }
    )
    result = calculate_deal(deal)

    assert result.monthly_cash_flows[0].effective_gross_income == pytest.approx(
        2000 + (deal.expenses.fixed_annual - 20000) / 12
    )


def test_hold_period_and_tenant_limit_are_validated() -> None:
    with pytest.raises(ValueError):
        sample_deal(hold_years=4)
    with pytest.raises(ValueError):
        DealAssumptions.model_validate(
            {
                "property_name": "Retail",
                "property_type": "retail",
                "closing_date": date(2026, 1, 1),
                "analysis_start_date": date(2026, 1, 1),
                "hold_years": 5,
                "exit_cap_rate": 0.06,
                "rent_roll": [
                    {
                        "name": f"Tenant {index}",
                        "area_sf": 100,
                        "lease_start": date(2026, 1, 1),
                        "lease_end": date(2030, 1, 1),
                        "current_rent": 20,
                    }
                    for index in range(501)
                ],
            }
        )


def test_vacant_space_uses_market_potential_without_double_vacancy() -> None:
    base = sample_deal(
        property_type="retail", unit_mix=[], units=0, total_nra_sf=1000,
        vacancy_rate=0.05, revenue_growth_rate=0,
        rent_roll=[
            {"name": "Occupied", "area_sf": 900, "lease_start": date(2025, 1, 1),
             "lease_end": date(2032, 1, 1), "current_rent": 24},
            {"name": "Vacant", "area_sf": 100, "lease_start": date(2026, 1, 1),
             "lease_end": date(2032, 1, 1), "current_rent": 0,
             "vacant": True, "market_rent_per_sf": 24, "lease_structure": "gross"},
        ],
    )
    first = calculate_deal(base).monthly_cash_flows[0]
    assert first.potential_rent == pytest.approx(2000)
    assert first.effective_gross_income == pytest.approx(1800)

    almost_full = base.model_copy(update={"rent_roll": [
        base.rent_roll[0].model_copy(update={"area_sf": 950}),
        base.rent_roll[1].model_copy(update={"area_sf": 50}),
    ]})
    first = calculate_deal(almost_full).monthly_cash_flows[0]
    assert first.potential_rent == pytest.approx(2000)
    assert first.effective_gross_income == pytest.approx(1900)


def test_vacant_suite_lease_up_charges_ti_and_commission_once() -> None:
    deal = sample_deal(
        property_type="industrial", unit_mix=[], units=0, total_nra_sf=1000,
        vacancy_rate=0.05,
        rent_roll=[{"name": "Suite A", "area_sf": 1000, "lease_start": date(2026, 1, 1),
                    "lease_end": date(2031, 1, 1), "current_rent": 0, "vacant": True,
                    "lease_up_date": date(2026, 3, 1), "market_rent_per_sf": 12,
                    "new_lease_ti_per_sf": 2, "new_lease_commission_rate": 0.05,
                    "lease_structure": "gross"}],
    )
    rows = calculate_deal(deal).monthly_cash_flows
    assert rows[0].effective_gross_income == 0
    assert rows[1].leasing_costs == pytest.approx(5000)
    assert rows[1].effective_gross_income == pytest.approx(950)
    assert rows[2].leasing_costs == 0


def test_expiring_tenant_has_expected_downtime_and_new_lease_cost_at_reletting() -> None:
    deal = sample_deal(
        property_type="office", unit_mix=[], units=0, total_nra_sf=1000,
        rent_roll=[{"name": "Suite", "area_sf": 1000, "lease_start": date(2025, 1, 1),
                    "lease_end": date(2026, 2, 1), "current_rent": 24,
                    "market_rent_per_sf": 24, "renewal_probability": 0.5,
                    "downtime_months": 2, "new_lease_ti_per_sf": 2,
                    "new_lease_commission_rate": 0.1, "lease_structure": "gross"}],
    )
    rows = calculate_deal(deal).monthly_cash_flows
    assert rows[1].effective_gross_income == pytest.approx(1000)
    assert rows[2].effective_gross_income == pytest.approx(1000)
    assert rows[3].effective_gross_income == pytest.approx(2000)
    assert rows[3].leasing_costs == pytest.approx(7000)
    assert rows[4].leasing_costs == 0


def test_reimbursements_during_rollover_track_occupied_share() -> None:
    deal = sample_deal(
        property_type="office", unit_mix=[], units=0, total_nra_sf=1000,
        expenses={"property_taxes": 12000},
        rent_roll=[{"name": "Office", "area_sf": 1000, "lease_start": date(2025, 1, 1),
                    "lease_end": date(2026, 2, 1), "current_rent": 24,
                    "market_rent_per_sf": 24, "renewal_probability": 0.5,
                    "downtime_months": 2}],
    )
    rows = calculate_deal(deal).monthly_cash_flows
    assert rows[1].potential_rent == pytest.approx(2000)
    assert rows[1].effective_gross_income == pytest.approx(1500)


def test_agreed_early_extension_step_continues_past_original_expiration() -> None:
    deal = sample_deal(
        property_type="retail", unit_mix=[], units=0, total_nra_sf=1000,
        rent_roll=[{"name": "Suite", "area_sf": 1000, "lease_start": date(2025, 1, 1),
                    "lease_end": date(2026, 9, 1), "extension_end": date(2028, 9, 1),
                    "current_rent": 12, "rent_steps": [{"effective_date": date(2026, 6, 1), "rent": 24}],
                    "renewal_ti_per_sf": 2, "lease_structure": "gross"}],
    )
    rows = calculate_deal(deal).monthly_cash_flows
    assert rows[3].effective_gross_income == pytest.approx(1000)
    assert rows[4].effective_gross_income == pytest.approx(2000)
    assert rows[4].leasing_costs == pytest.approx(2000)
    assert rows[8].effective_gross_income == pytest.approx(2000)


def test_contractual_rent_step_is_not_double_escalated_by_market_growth() -> None:
    deal = sample_deal(
        property_type="retail", unit_mix=[], units=0, total_nra_sf=1000,
        revenue_growth_rate=0.1,
        rent_roll=[{"name": "Store", "area_sf": 1000, "lease_start": date(2025, 1, 1),
                    "lease_end": date(2032, 1, 1), "current_rent": 24,
                    "rent_steps": [{"effective_date": date(2027, 1, 1), "rent": 25.2}],
                    "lease_structure": "gross"}],
    )
    rows = calculate_deal(deal).monthly_cash_flows
    assert rows[11].effective_gross_income == pytest.approx(2100)
    assert rows[12].effective_gross_income == pytest.approx(2100)


def test_loan_balloon_is_paid_when_maturity_precedes_sale() -> None:
    result = calculate_deal(
        sample_deal(
            loans=[
                {
                    "name": "Bridge",
                    "amount": 40000,
                    "rate": 0,
                    "term_months": 12,
                    "amortization_years": 0,
                }
            ]
        )
    )

    assert result.monthly_cash_flows[11].debt_payoff == pytest.approx(40000)
    assert result.monthly_cash_flows[11].levered_cash_flow < 0
    assert result.monthly_cash_flows[-1].debt_payoff == 0


def test_waterfall_hurdle_splits_conserve_distributions() -> None:
    assumptions = InvestorAssumptions.model_validate(
        {
            "gp_coinvest_pct": 0.2,
            "preferred_return_rate": 0,
            "tiers": [
                {"name": "First promote", "hurdle_irr": 0.17, "lp_split": 0.8, "gp_split": 0.2},
                {"name": "Residual", "lp_split": 0.5, "gp_split": 0.5},
            ],
        }
    )

    result = run_waterfall(
        [-100, 300], [date(2025, 1, 1), date(2026, 1, 1)], assumptions
    )

    assert result.lp_contributions == pytest.approx(80)
    assert result.gp_contributions == pytest.approx(20)
    assert result.lp_distributions == pytest.approx(185.1)
    assert result.gp_distributions == pytest.approx(114.9)
    assert result.lp_distributions + result.gp_distributions == pytest.approx(300)
    assert result.monthly_periods[-1].lp_distribution + result.monthly_periods[-1].gp_distribution == pytest.approx(300)


def test_waterfall_monthly_pref_and_gp_catch_up_conserve_cash() -> None:
    start_date = date(2025, 1, 1)
    dates = [start_date, *[add_months(start_date, month) for month in range(1, 13)]]
    assumptions = InvestorAssumptions.model_validate(
        {
            "gp_coinvest_pct": 0.2,
            "preferred_return_rate": 0.07,
            "gp_catch_up": True,
            "tiers": [{"name": "Residual", "lp_split": 0.8, "gp_split": 0.2}],
        }
    )

    result = run_waterfall([-100, *([0] * 11), 110], dates, assumptions)
    expected_pref = 100 * ((1 + 0.07 / 12) ** 12 - 1)

    assert result.monthly_periods[-1].lp_distribution >= 80 + expected_pref
    assert result.monthly_periods[-1].gp_distribution > 20
    assert result.lp_distributions + result.gp_distributions == pytest.approx(110)