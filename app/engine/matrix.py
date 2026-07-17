"""
Casablanca zoning rules — the legal envelope the cost engine must respect.

Encodes the urban-planning limits (Agence Urbaine de Casablanca) as a data-driven
matrix so the Capex engine never proposes an illegal building:

  - CES (Coefficient d'Emprise au Sol): max ground footprint as a fraction of the plot.
  - COS (Coefficient d'Occupation du Sol): max total floor area (vertical volume).
  - max_upper_floors / allows_penthouse: height caps per zone.

Adding or tuning a zone is a data edit here — the engine logic in capex.py is untouched.
"""
from enum import Enum


class ZoningCategory(str, Enum):
    ZONE_AB_DENSE = "zone_ab"
    ZONE_D_VILLA = "zone_d"
    ZONE_E_COMMERCIAL = "zone_e"

# Casablanca Urban Rules (Legal limits)
CASABLANCA_ZONING_RULES = {
    ZoningCategory.ZONE_AB_DENSE: {
        "ces": 0.55, 
        "cos": 3.0,  
        "max_upper_floors": 5, 
        "allows_penthouse": True
    },
    ZoningCategory.ZONE_D_VILLA: {
        "ces": 0.30, 
        "cos": 0.6, 
        "max_upper_floors": 1, 
        "allows_penthouse": False
    },
    ZoningCategory.ZONE_E_COMMERCIAL: {
        "ces": 0.50,         
        "cos": 4.0,          
        "max_upper_floors": 6, 
        "allows_penthouse": False
    }
}