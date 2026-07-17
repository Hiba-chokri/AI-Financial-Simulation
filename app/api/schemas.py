"""
Request / response contracts for the public API.

Pydantic validates every incoming request and documents the JSON shape in the
auto-generated Swagger UI (/docs).
it just describes what goes in and what comes out.
"""
from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from app.engine.currency import Currency
from app.engine.matrix import ZoningCategory


class GDVMethod(str, Enum):
    """Which valuator to use for the revenue (GDV) side."""
    ml = "ml"          # trained pipeline (app/ml) — prices from the typical unit
    lookup = "lookup"  # neighborhood median (app/engine/gdv)


class UnitFeatures(BaseModel):
    """
    Numeric features for the ML price prediction.
    Field names must match MLConfig.numeric_features exactly — if you change
    the dataset, update config.py and this class together; nowhere else.
    """
    bedrooms: int = 3
    bathrooms: float = 1.75
    floors: float = 1.0
    waterfront: int = Field(0, ge=0, le=1)
    view: int = Field(0, ge=0, le=4)
    condition: int = Field(3, ge=1, le=5)
    grade: int = Field(7, ge=1, le=13)
    sqft_above: float = Field(1180.0, ge=0)
    sqft_basement: float = Field(0.0, ge=0)
    yr_built: int = Field(1990, ge=1900, le=2030)
    sqft_living15: float = Field(1340.0, ge=0)


class SimulationRequest(BaseModel):
    """Everything needed to value a development project end to end."""
    # Site
    plot_m2: float = Field(..., gt=0, description="Raw plot size in m²")
    land_price_mad: float = Field(..., ge=0, description="Land acquisition price (MAD)")
    zone: ZoningCategory = Field(..., description="Casablanca zoning category")
    neighborhood: str = Field(..., description="Location identifier — maps to the categorical feature in MLConfig (e.g. zipcode)")

    # Construction rates (MAD/m²) — fully dynamic, no hardcoded prices
    underground_parking_mad: float = Field(3500.0, ge=0)
    ground_floor_mad: float = Field(4500.0, ge=0)
    upper_floors_mad: float = Field(4300.0, ge=0)
    penthouse_mad: float = Field(5000.0, ge=0)

    # Other costs
    contingency_percentage: float = Field(0.05, ge=0, le=1)
    demolition_cost_mad: float = Field(150000.0, ge=0)
    requires_demolition: bool = True
    # Soft costs — 5 sub-lines (base = construction + demolition)
    feasibility_pct: float = Field(0.005, ge=0, le=1)
    architecture_pct: float = Field(0.030, ge=0, le=1)
    landscaping_env_pct: float = Field(0.003, ge=0, le=1)
    structural_pct: float = Field(0.012, ge=0, le=1)
    pm_marketing_pct: float = Field(0.025, ge=0, le=1)
    # Overheads (base = land + demo + construction + soft costs)
    overheads_pct: float = Field(0.005, ge=0, le=1)
    # Selling cost deducted from GDV to produce NDV
    selling_cost_pct: float = Field(0.01, ge=0, le=1)

    # GDV configuration
    gdv_method: GDVMethod = GDVMethod.ml
    unit: UnitFeatures = Field(default_factory=UnitFeatures)

    # Output currency — all monetary outputs are converted to this.
    # Inputs (construction rates, land price) are always provided in MAD.
    currency: Currency = Currency.USD

    model_config = {
        "json_schema_extra": {
            "example": {
                "plot_m2": 500, "land_price_mad": 4500000, "zone": "zone_ab",
                "neighborhood": "98052",
                "underground_parking_mad": 3500, "ground_floor_mad": 4500,
                "upper_floors_mad": 4300, "penthouse_mad": 5000,
                "contingency_percentage": 0.05,
                "feasibility_pct": 0.005, "architecture_pct": 0.030,
                "landscaping_env_pct": 0.003, "structural_pct": 0.012, "pm_marketing_pct": 0.025,
                "overheads_pct": 0.005, "selling_cost_pct": 0.01,
                "demolition_cost_mad": 150000, "requires_demolition": True,
                "gdv_method": "ml",
                "unit": {
                    "bedrooms": 3, "bathrooms": 1.75, "floors": 1.0,
                    "waterfront": 0, "view": 0, "condition": 3, "grade": 7,
                    "sqft_above": 1180, "sqft_basement": 0,
                    "yr_built": 1990, "sqft_living15": 1340,
                },
            }
        }
    }


class ConstructionItem(BaseModel):
    level: str
    surface_m2: float
    cost_m2: float
    total_mad: float


class SimulationResponse(BaseModel):
    """The full cost → GDV → profit breakdown."""
    # Currency used for all monetary fields below
    currency: str
    # Cost side
    total_investment_mad: float
    construction_subtotal_mad: float
    total_built_surface_m2: float
    construction_details: List[ConstructionItem]
    # Revenue side
    gdv_method: str
    sellable_surface_m2: float
    price_per_m2: float
    gdv_mad: float
    ndv_mad: float
    soft_costs_mad: float
    overheads_mad: float
    # percentages are never converted, they are dimensionless
    net_profit_mad: float
    margin_pct: float
    roi_pct: float
