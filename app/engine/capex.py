"""
Capex — the deterministic cost engine (Submodel B).

Given a plot, its zoning category, and market rates, this module autonomously
designs a legally-compliant building (enforcing Casablanca CES/COS/height limits
from matrix.py) and itemizes the full Total Development Cost (TDC):

    land + demolition + construction + soft costs (5 lines) + overheads + contingency

`compute_returns` then joins the cost side to a price/m2 (from the ML model or the
lookup) to produce GDV, NDV, net profit, margin, and ROI.

Everything is priced from injected inputs (ProjectFinancialInputs) — there are no
hardcoded prices, and all amounts are in MAD (currency conversion happens at the
API boundary, not here).
"""
from typing import Any, Dict

from pydantic import BaseModel

from app.engine.matrix import ZoningCategory, CASABLANCA_ZONING_RULES

class ProjectFinancialInputs(BaseModel):
    underground_parking_mad: float
    ground_floor_mad: float
    upper_floors_mad: float
    penthouse_mad: float
    # Soft costs — 5 sub-lines; base = construction + demolition
    feasibility_pct: float = 0.005
    architecture_pct: float = 0.030
    landscaping_env_pct: float = 0.003
    structural_pct: float = 0.012
    pm_marketing_pct: float = 0.025
    # Overheads — base = land + demo + construction + soft costs
    overheads_pct: float = 0.005
    contingency_percentage: float = 0.05
    demolition_cost_mad: float = 0.0

def generate_financial_model(
    raw_plot_m2: float, 
    land_price_mad: float, 
    zone: ZoningCategory, 
    inputs: ProjectFinancialInputs,
    requires_demolition: bool = True
) -> Dict[str, Any]:
    """
    Autonomously generates a vertical building based on Casablanca zoning laws, 
    enforcing COS limits and using 100% dynamically injected market rates.
    """
    rules = CASABLANCA_ZONING_RULES[zone]
    ces = rules["ces"]
    cos = rules["cos"]
    
    #1. LAND ACQUISITION ---
    land_costs = {
        "surface_m2": raw_plot_m2,
        "total_mad": land_price_mad
    }
    
    construction_items = []
    
    # The COS ceiling: Maximum legally allowed vertical volume (above ground)
    max_gross_floor_area = raw_plot_m2 * cos
    current_gross_area = 0.0
    
    #VERTICAL CONSTRUCTION ---
    
    # Underground Parking (Usually exempt from COS limits)
    parking_m2 = round(raw_plot_m2 * 0.80, 4)
    construction_items.append({
        "level": "Underground Parking", 
        "surface_m2": parking_m2, 
        "cost_m2": inputs.underground_parking_mad, 
        "total_mad": parking_m2 * inputs.underground_parking_mad
    })
    
    # Ground Floor
    ground_m2 = round(raw_plot_m2 * ces, 4)
    if current_gross_area + ground_m2 <= max_gross_floor_area:
        construction_items.append({
            "level": "Ground Floor", 
            "surface_m2": ground_m2, 
            "cost_m2": inputs.ground_floor_mad, 
            "total_mad": ground_m2 * inputs.ground_floor_mad
        })
        current_gross_area += ground_m2
    
    # Upper Floors (Loops until it hits the max floors OR the COS ceiling)
    for floor in range(1, rules["max_upper_floors"] + 1):
        if current_gross_area + ground_m2 <= max_gross_floor_area:
            construction_items.append({
                "level": f"Floor G+{floor}", 
                "surface_m2": ground_m2, 
                "cost_m2": inputs.upper_floors_mad, 
                "total_mad": ground_m2 * inputs.upper_floors_mad
            })
            current_gross_area += ground_m2
        else:
            break  # Stops the engine from building illegally over the COS limit
            
    # Penthouse
    if rules["allows_penthouse"]:
        penthouse_m2 = ground_m2 * 0.50
        if current_gross_area + penthouse_m2 <= max_gross_floor_area:
            construction_items.append({
                "level": "Penthouse", 
                "surface_m2": penthouse_m2, 
                "cost_m2": inputs.penthouse_mad, 
                "total_mad": penthouse_m2 * inputs.penthouse_mad
            })
            current_gross_area += penthouse_m2

    subtotal_construction = sum(item["total_mad"] for item in construction_items)

    total_built_surface = sum(item["surface_m2"] for item in construction_items)

    # --- 3. OTHER COSTS ---
    active_demolition_cost = inputs.demolition_cost_mad if requires_demolition else 0.0

    # Soft costs split into 5 sub-lines; base = construction + demolition
    soft_base = subtotal_construction + active_demolition_cost
    soft_cost_lines = {
        "feasibility_mad": round(soft_base * inputs.feasibility_pct, 2),
        "architecture_mad": round(soft_base * inputs.architecture_pct, 2),
        "landscaping_env_mad": round(soft_base * inputs.landscaping_env_pct, 2),
        "structural_mad": round(soft_base * inputs.structural_pct, 2),
        "pm_marketing_mad": round(soft_base * inputs.pm_marketing_pct, 2),
    }
    soft_costs = sum(soft_cost_lines.values())

    # Overheads; base = land + demo + construction + soft costs
    overhead_base = land_price_mad + active_demolition_cost + subtotal_construction + soft_costs
    overheads = round(overhead_base * inputs.overheads_pct, 2)

    contingency = round(subtotal_construction * inputs.contingency_percentage, 2)

    other_costs = {
        "demolition_mad": active_demolition_cost,
        "soft_cost_lines": soft_cost_lines,
        "soft_costs_mad": soft_costs,
        "overheads_mad": overheads,
        "contingency_mad": contingency,
        "subtotal_other_mad": active_demolition_cost + soft_costs + overheads + contingency,
    }

    # --- 4. THE GRAND TOTAL ---
    needed_investment = land_costs["total_mad"] + subtotal_construction + other_costs["subtotal_other_mad"]

    return {
        "land_acquisition": land_costs,
        "construction_details": construction_items,
        "construction_subtotal_mad": subtotal_construction,
        "total_built_surface_m2": total_built_surface,
        "other_costs": other_costs,
        "TOTAL_NEEDED_INVESTMENT_MAD": needed_investment
    }

# Levels built for structural/cost purposes but not sold at residential price/m².
NON_SELLABLE_LEVELS = {"Underground Parking"}


def compute_returns(cost: dict, price_per_m2: float, selling_cost_pct: float = 0.01) -> dict:
    """
    Given the output of generate_financial_model and a price/m²,
    compute the revenue side and bottom line.

    NDV = GDV × (1 − selling_cost_pct). Net profit = NDV − TDC.
    """
    total_investment = cost["TOTAL_NEEDED_INVESTMENT_MAD"]

    sellable_m2 = sum(
        item["surface_m2"]
        for item in cost["construction_details"]
        if item["level"] not in NON_SELLABLE_LEVELS
    )

    gdv = sellable_m2 * price_per_m2
    ndv = gdv * (1.0 - selling_cost_pct)
    net_profit = ndv - total_investment
    margin_pct = (net_profit / ndv * 100) if ndv else 0.0
    roi_pct = (net_profit / total_investment * 100) if total_investment else 0.0

    return {
        "sellable_m2": sellable_m2,
        "gdv": gdv,
        "ndv": ndv,
        "net_profit": net_profit,
        "margin_pct": margin_pct,
        "roi_pct": roi_pct,
    }


if __name__ == "__main__":
    # Testing the engine using Commercial Zone
    test_inputs = ProjectFinancialInputs(
        underground_parking_mad=3500.0,
        ground_floor_mad=4500.0,
        upper_floors_mad=4300.0,
        penthouse_mad=5000.0,
        demolition_cost_mad=150000.0,
        # soft cost sub-lines, overheads and contingency use the field defaults
    )
    
    # 2. Run the engine for a 500 sqm commercial plot
    financial_output = generate_financial_model(
        raw_plot_m2=500.0, 
        land_price_mad=4500000.0, 
        zone=ZoningCategory.ZONE_E_COMMERCIAL,
        inputs=test_inputs,
        requires_demolition=True
    )
    
    # 3. Print the Spreadsheet-style output
    print("\n--- DABA.DAR SPREADSHEET ENGINE TEST ---")
    print(f"Total Needed Investment: {financial_output['TOTAL_NEEDED_INVESTMENT_MAD']:,.2f} MAD")
    print("\nConstruction Breakdown:")
    for item in financial_output["construction_details"]:
        print(f" - {item['level']}: {item['surface_m2']} m2 @ {item['cost_m2']} MAD/m2 -> {item['total_mad']:,.2f} MAD")
    print(f"Subtotal Construction: {financial_output['construction_subtotal_mad']:,.2f} MAD")
    
    oc = financial_output["other_costs"]
    total_soft_pct = (
        test_inputs.feasibility_pct + test_inputs.architecture_pct
        + test_inputs.landscaping_env_pct + test_inputs.structural_pct
        + test_inputs.pm_marketing_pct
    )
    print("\nOther Costs Breakdown:")
    print(f" - Demolition: {oc['demolition_mad']:,.2f} MAD")
    print(f" - Soft Costs ({total_soft_pct:.2%} across {len(oc['soft_cost_lines'])} lines):")
    for name, value in oc["soft_cost_lines"].items():
        print(f"     {name:<22} {value:>14,.2f} MAD")
    print(f"     {'Total soft costs':<22} {oc['soft_costs_mad']:>14,.2f} MAD")
    print(f" - Overheads ({test_inputs.overheads_pct:.2%}): {oc['overheads_mad']:,.2f} MAD")
    print(f" - Contingency ({test_inputs.contingency_percentage:.2%}): {oc['contingency_mad']:,.2f} MAD")

    # Revenue side demo (arbitrary price/m2, since this script has no ML model loaded)
    returns = compute_returns(financial_output, price_per_m2=20000.0)
    print("\nReturns (demo price 20,000 MAD/m2):")
    print(f" - Sellable area: {returns['sellable_m2']:,.0f} m2 (parking excluded)")
    print(f" - GDV: {returns['gdv']:,.2f} MAD  |  NDV: {returns['ndv']:,.2f} MAD")
    print(f" - Net profit: {returns['net_profit']:,.2f} MAD  |  "
          f"Margin: {returns['margin_pct']:.1f}%  |  ROI: {returns['roi_pct']:.1f}%\n")