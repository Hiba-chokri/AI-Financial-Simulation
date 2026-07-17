"""
verification of the Capex engine — every expected number below was
hand-calculated from the formulas first, then asserted against the engine.

Reference scenario (used throughout): 500 m2 plot, 4,500,000 MAD land,
demolition 150,000 MAD, default rates (parking 3500 / ground 4500 /
upper 4300 / penthouse 5000 MAD/m2) and default percentages.

Zone E (CES 0.50, COS 4.0, R+6, no penthouse) hand math:
    parking       500*0.80 = 400 m2 @ 3500 = 1,400,000
    ground        500*0.50 = 250 m2 @ 4500 = 1,125,000
    G+1..G+6      6 x (250 @ 4300 = 1,075,000) = 6,450,000   (COS cap 2000 not hit)
    construction subtotal                       = 8,975,000
    soft base = constr + demo                   = 9,125,000
        feasibility  0.5%  =  45,625      architecture 3.0% = 273,750
        landscaping  0.3%  =  27,375      structural  1.2%  = 109,500
        pm+marketing 2.5%  = 228,125      total 7.5%        = 684,375
    overheads = (land+demo+constr+soft) * 0.5%
              = 14,309,375 * 0.005                          = 71,546.88
    contingency = constr * 5%                               = 448,750
    TDC = 4.5M + 8,975,000 + 150,000 + 684,375
          + 71,546.88 + 448,750                             = 14,829,671.88
"""
import pytest

from app.engine.capex import (
    NON_SELLABLE_LEVELS,
    ProjectFinancialInputs,
    compute_returns,
    generate_financial_model,
)
from app.engine.matrix import ZoningCategory


@pytest.fixture()
def inputs() -> ProjectFinancialInputs:
    return ProjectFinancialInputs(
        underground_parking_mad=3500.0,
        ground_floor_mad=4500.0,
        upper_floors_mad=4300.0,
        penthouse_mad=5000.0,
        demolition_cost_mad=150_000.0,
    )


@pytest.fixture()
def zone_e(inputs: ProjectFinancialInputs) -> dict:
    return generate_financial_model(
        raw_plot_m2=500.0,
        land_price_mad=4_500_000.0,
        zone=ZoningCategory.ZONE_E_COMMERCIAL,
        inputs=inputs,
        requires_demolition=True,
    )


# ── Construction: level-by-level ──────────────────────────────────────────────

def test_zone_e_builds_exactly_the_legal_stack(zone_e):
    levels = [item["level"] for item in zone_e["construction_details"]]
    assert levels == [
        "Underground Parking", "Ground Floor",
        "Floor G+1", "Floor G+2", "Floor G+3", "Floor G+4", "Floor G+5", "Floor G+6",
    ]


def test_zone_e_surfaces_per_level(zone_e):
    by_level = {i["level"]: i["surface_m2"] for i in zone_e["construction_details"]}
    assert by_level["Underground Parking"] == 400.0   # 500 * 0.80
    assert by_level["Ground Floor"] == 250.0          # 500 * CES 0.50
    assert by_level["Floor G+6"] == 250.0             # upper floors repeat the footprint


def test_zone_e_cost_per_level_is_surface_times_rate(zone_e):
    for item in zone_e["construction_details"]:
        assert item["total_mad"] == pytest.approx(item["surface_m2"] * item["cost_m2"])


def test_zone_e_construction_subtotal(zone_e):
    # 1,400,000 + 1,125,000 + 6 * 1,075,000
    assert zone_e["construction_subtotal_mad"] == pytest.approx(8_975_000.0)


def test_zone_e_total_built_surface(zone_e):
    # 400 parking + 7 x 250 above ground
    assert zone_e["total_built_surface_m2"] == pytest.approx(2_150.0)


# ── Zoning law enforcement ────────────────────────────────────────────────────

def test_zone_ab_cos_ceiling_stops_construction_before_height_cap(inputs):
    """Zone A/B allows R+5, but COS 3.0 on a 500 m2 plot caps GFA at 1500 m2:
    ground(275) + 4 floors = 1375; a 5th floor (1650) would be illegal."""
    cost = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_AB_DENSE, inputs, True
    )
    levels = [i["level"] for i in cost["construction_details"]]
    assert "Floor G+4" in levels
    assert "Floor G+5" not in levels           # blocked by COS, not by height


def test_zone_ab_penthouse_blocked_by_cos(inputs):
    """Penthouse is allowed in Zone A/B, but 1375 + 137.5 > 1500 -> must not build."""
    cost = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_AB_DENSE, inputs, True
    )
    levels = [i["level"] for i in cost["construction_details"]]
    assert "Penthouse" not in levels


def test_zone_d_villa_builds_to_exact_cos_limit(inputs):
    """Zone D: CES 0.30 -> ground 150; COS 0.6 -> cap 300. Ground + G+1 == 300,
    exactly at the cap — the boundary case must be allowed, not rejected."""
    cost = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_D_VILLA, inputs, True
    )
    levels = [i["level"] for i in cost["construction_details"]]
    assert levels == ["Underground Parking", "Ground Floor", "Floor G+1"]
    above_ground = sum(
        i["surface_m2"] for i in cost["construction_details"]
        if i["level"] not in NON_SELLABLE_LEVELS
    )
    assert above_ground == pytest.approx(300.0)


# ── Soft costs, overheads, contingency, TDC ───────────────────────────────────

def test_zone_e_soft_cost_lines_exact(zone_e):
    lines = zone_e["other_costs"]["soft_cost_lines"]
    assert lines["feasibility_mad"] == pytest.approx(45_625.00)
    assert lines["architecture_mad"] == pytest.approx(273_750.00)
    assert lines["landscaping_env_mad"] == pytest.approx(27_375.00)
    assert lines["structural_mad"] == pytest.approx(109_500.00)
    assert lines["pm_marketing_mad"] == pytest.approx(228_125.00)
    assert zone_e["other_costs"]["soft_costs_mad"] == pytest.approx(684_375.00)


def test_zone_e_overheads_exact(zone_e):
    # (4,500,000 + 150,000 + 8,975,000 + 684,375) * 0.005
    assert zone_e["other_costs"]["overheads_mad"] == pytest.approx(71_546.88)


def test_zone_e_contingency_exact(zone_e):
    assert zone_e["other_costs"]["contingency_mad"] == pytest.approx(448_750.00)


def test_zone_e_tdc_exact(zone_e):
    assert zone_e["TOTAL_NEEDED_INVESTMENT_MAD"] == pytest.approx(14_829_671.88)


def test_tdc_equals_sum_of_its_parts(zone_e):
    """The grand total must be exactly land + construction + other costs."""
    oc = zone_e["other_costs"]
    expected = (
        zone_e["land_acquisition"]["total_mad"]
        + zone_e["construction_subtotal_mad"]
        + oc["subtotal_other_mad"]
    )
    assert zone_e["TOTAL_NEEDED_INVESTMENT_MAD"] == pytest.approx(expected)
    assert oc["subtotal_other_mad"] == pytest.approx(
        oc["demolition_mad"] + oc["soft_costs_mad"]
        + oc["overheads_mad"] + oc["contingency_mad"]
    )


def test_demolition_off_shrinks_soft_base_and_overhead_base(inputs):
    """requires_demolition=False must zero the demo line AND remove it from the
    soft-cost and overhead bases (not just hide the line)."""
    cost = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_E_COMMERCIAL, inputs,
        requires_demolition=False,
    )
    oc = cost["other_costs"]
    assert oc["demolition_mad"] == 0.0
    # soft base drops from 9,125,000 to 8,975,000
    assert oc["soft_costs_mad"] == pytest.approx(8_975_000.0 * 0.075)
    expected_ovh = round((4_500_000 + 8_975_000 + oc["soft_costs_mad"]) * 0.005, 2)
    assert oc["overheads_mad"] == pytest.approx(expected_ovh)


def test_custom_percentages_flow_through_not_hardcoded(inputs):
    """Overriding any percentage must change the output — guards against
    re-introducing hardcoded rates."""
    custom = inputs.model_copy(update={
        "architecture_pct": 0.05, "overheads_pct": 0.01,
        "contingency_percentage": 0.10,
    })
    cost = generate_financial_model(
        500.0, 4_500_000.0, ZoningCategory.ZONE_E_COMMERCIAL, custom, True
    )
    oc = cost["other_costs"]
    soft_base = 8_975_000.0 + 150_000.0
    assert oc["soft_cost_lines"]["architecture_mad"] == pytest.approx(soft_base * 0.05)
    assert oc["contingency_mad"] == pytest.approx(8_975_000.0 * 0.10)
    ovh_base = 4_500_000 + 150_000 + 8_975_000 + oc["soft_costs_mad"]
    assert oc["overheads_mad"] == pytest.approx(round(ovh_base * 0.01, 2))


# ── Returns: GDV -> NDV -> profit ─────────────────────────────────────────────

def test_returns_chain_exact(zone_e):
    """At 20,000 MAD/m2 and 1% selling cost (default)."""
    r = compute_returns(zone_e, price_per_m2=20_000.0)
    assert r["sellable_m2"] == pytest.approx(1_750.0)        # parking excluded
    assert r["gdv"] == pytest.approx(35_000_000.0)
    assert r["ndv"] == pytest.approx(34_650_000.0)           # GDV * 0.99
    assert r["net_profit"] == pytest.approx(19_820_328.12)   # NDV - TDC
    assert r["margin_pct"] == pytest.approx(57.2015, abs=1e-3)
    assert r["roi_pct"] == pytest.approx(133.6532, abs=1e-3)


def test_parking_never_counts_as_sellable(zone_e):
    r = compute_returns(zone_e, price_per_m2=20_000.0)
    total_built = zone_e["total_built_surface_m2"]
    parking = next(
        i["surface_m2"] for i in zone_e["construction_details"]
        if i["level"] == "Underground Parking"
    )
    assert r["sellable_m2"] == pytest.approx(total_built - parking)


def test_zero_selling_cost_means_ndv_equals_gdv(zone_e):
    r = compute_returns(zone_e, price_per_m2=20_000.0, selling_cost_pct=0.0)
    assert r["ndv"] == pytest.approx(r["gdv"])


def test_selling_cost_scales_ndv_linearly(zone_e):
    r = compute_returns(zone_e, price_per_m2=20_000.0, selling_cost_pct=0.05)
    assert r["ndv"] == pytest.approx(r["gdv"] * 0.95)


def test_zero_price_does_not_divide_by_zero(zone_e):
    r = compute_returns(zone_e, price_per_m2=0.0)
    assert r["gdv"] == 0.0
    assert r["margin_pct"] == 0.0
    assert r["net_profit"] == pytest.approx(-zone_e["TOTAL_NEEDED_INVESTMENT_MAD"])
