"""
 tests for the deterministic financial engine.

"""
import pytest

from app.engine.capex import (
    NON_SELLABLE_LEVELS,
    ProjectFinancialInputs,
    compute_returns,
    generate_financial_model,
)
from app.engine.currency import Currency, convert
from app.engine.matrix import ZoningCategory


@pytest.fixture()
def inputs() -> ProjectFinancialInputs:
    return ProjectFinancialInputs(
        underground_parking_mad=3500.0,
        ground_floor_mad=4500.0,
        upper_floors_mad=4300.0,
        penthouse_mad=5000.0,
        demolition_cost_mad=150000.0,
    )


@pytest.fixture()
def cost(inputs: ProjectFinancialInputs) -> dict:
    return generate_financial_model(
        raw_plot_m2=500.0,
        land_price_mad=4_500_000.0,
        zone=ZoningCategory.ZONE_E_COMMERCIAL,
        inputs=inputs,
        requires_demolition=True,
    )


def test_cost_model_has_expected_shape(cost: dict):
    for key in (
        "land_acquisition",
        "construction_details",
        "construction_subtotal_mad",
        "other_costs",
        "TOTAL_NEEDED_INVESTMENT_MAD",
    ):
        assert key in cost


def test_soft_cost_lines_sum_to_total(cost: dict):
    lines = cost["other_costs"]["soft_cost_lines"]
    assert len(lines) == 5
    assert round(sum(lines.values()), 2) == cost["other_costs"]["soft_costs_mad"]


def test_tdc_is_sum_of_its_parts(cost: dict):
    expected = (
        cost["land_acquisition"]["total_mad"]
        + cost["construction_subtotal_mad"]
        + cost["other_costs"]["subtotal_other_mad"]
    )
    assert round(cost["TOTAL_NEEDED_INVESTMENT_MAD"], 2) == round(expected, 2)


def test_overheads_present_in_tdc(cost: dict):
    assert cost["other_costs"]["overheads_mad"] > 0


def test_returns_ndv_below_gdv_and_profit_formula(cost: dict):
    r = compute_returns(cost, price_per_m2=20_000.0, selling_cost_pct=0.01)
    assert r["ndv"] < r["gdv"]                       # selling cost was deducted
    tdc = cost["TOTAL_NEEDED_INVESTMENT_MAD"]
    assert round(r["net_profit"], 2) == round(r["ndv"] - tdc, 2)


def test_parking_excluded_from_sellable_area(cost: dict):
    r = compute_returns(cost, price_per_m2=20_000.0)
    sellable = sum(
        item["surface_m2"]
        for item in cost["construction_details"]
        if item["level"] not in NON_SELLABLE_LEVELS
    )
    assert r["sellable_m2"] == sellable
    assert r["sellable_m2"] < cost["total_built_surface_m2"]  # parking was removed


def test_zoning_binds_building_height(inputs: ProjectFinancialInputs):
    """A villa zone (R+1) must produce fewer levels than a commercial zone (R+6)."""
    villa = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_D_VILLA, inputs, True
    )
    commercial = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_E_COMMERCIAL, inputs, True
    )
    assert len(villa["construction_details"]) < len(commercial["construction_details"])


def test_currency_conversion():
    assert convert(100.0, Currency.MAD) == 100.0            # MAD is the identity
    assert convert(100.0, Currency.USD) < 100.0             # USD worth more than MAD
    assert convert(0.0, Currency.EUR) == 0.0
