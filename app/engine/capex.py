from typing import Dict, Any, List
from pydantic import BaseModel
from app.engine.matrix import ZoningCategory, CASABLANCA_ZONING_RULES

class ProjectFinancialInputs(BaseModel):
    underground_parking_mad: float
    ground_floor_mad: float
    upper_floors_mad: float
    penthouse_mad: float
    soft_costs_percentage: float      
    contingency_percentage: float     
    demolition_cost_mad: float        

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
    parking_m2 = raw_plot_m2 * 0.80
    construction_items.append({
        "level": "Underground Parking", 
        "surface_m2": parking_m2, 
        "cost_m2": inputs.underground_parking_mad, 
        "total_mad": parking_m2 * inputs.underground_parking_mad
    })
    
    # Ground Floor
    ground_m2 = raw_plot_m2 * ces
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
    soft_costs = subtotal_construction * inputs.soft_costs_percentage
    contingency = subtotal_construction * inputs.contingency_percentage
    
    other_costs = {
        "demolition_mad": active_demolition_cost,
        "soft_costs_mad": soft_costs,
        "contingency_mad": contingency,
        "subtotal_other_mad": active_demolition_cost + soft_costs + contingency
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

if __name__ == "__main__":
    # Testing the engine using Commercial Zone
    test_inputs = ProjectFinancialInputs(
        underground_parking_mad=3500.0,
        ground_floor_mad=4500.0,
        upper_floors_mad=4300.0,
        penthouse_mad=5000.0,
        soft_costs_percentage=0.10,
        contingency_percentage=0.05,
        demolition_cost_mad=150000.0
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
    
    print("\nOther Costs Breakdown:")
    print(f" - Demolition: {financial_output['other_costs']['demolition_mad']:,.2f} MAD")
    print(f" - Soft Costs (10%): {financial_output['other_costs']['soft_costs_mad']:,.2f} MAD")
    print(f" - Contingency (5%): {financial_output['other_costs']['contingency_mad']:,.2f} MAD\n")