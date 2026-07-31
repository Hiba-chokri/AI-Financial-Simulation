"""
Request / response contracts for the public API.

Pydantic validates every incoming request and documents the JSON shape in the
auto-generated Swagger UI (/docs).
it just describes what goes in and what comes out.
"""
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator

from app.engine.currency import Currency
from app.engine.matrix import ZoningCategory

# Every float on the public API — in requests and in responses — is reported
# to this many decimal places. One rule, enforced in one place, rather than
# each field picking its own precision.
DECIMAL_PLACES = 3


class RoundedModel(BaseModel):
    """
    Base class: rounds every float field to DECIMAL_PLACES after validation.

    Applies uniformly to inputs (a caller sending land_price_mad=4500000.123456
    gets it normalized before it reaches the engine) and outputs (currency
    conversion and division produce long float tails; this is where they get
    cleaned up for display). Nested models validate first, so a list of
    ConstructionItem or a nested UnitFeatures is rounded automatically too.
    """

    @model_validator(mode="after")
    def _round_floats(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, float):
                setattr(self, name, round(value, DECIMAL_PLACES))
        return self


class GDVMethod(str, Enum):
    """Which valuator to use for the revenue (GDV) side."""
    ml = "ml"          # trained pipeline (app/ml) — prices from the typical unit
    lookup = "lookup"  # neighborhood median (app/engine/gdv)


class UnitFeatures(RoundedModel):
    """
    Describes a "typical unit" for the project — the ML model prices per m²
    from these attributes. Only used when `gdv_method="ml"`; ignored for
    `gdv_method="lookup"`. Field names must match MLConfig.numeric_features
    exactly — if you change the dataset, update config.py and this class
    together; nowhere else.
    """
    bedrooms: int = Field(3, description="Bedroom count")
    bathrooms: float = Field(1.75, description="Bathroom count (0.75 = a half-bath, etc.)")
    floors: float = Field(1.0, description="Floors within the unit itself")
    waterfront: int = Field(0, ge=0, le=1, description="1 if waterfront-adjacent, else 0")
    view: int = Field(0, ge=0, le=4, description="View quality, 0 (none) to 4 (best)")
    condition: int = Field(3, ge=1, le=5, description="Physical condition, 1 (poor) to 5 (excellent)")
    grade: int = Field(7, ge=1, le=13, description="Construction/design grade, 1 (low) to 13 (luxury)")
    sqft_above: float = Field(1180.0, ge=0, description="Living area above grade (sqft)")
    sqft_basement: float = Field(0.0, ge=0, description="Basement living area (sqft), 0 if none")
    yr_built: int = Field(1990, ge=1900, le=2030, description="Year the unit was/will be built")
    sqft_living15: float = Field(1340.0, ge=0, description="Average living area of the 15 nearest comparable units (sqft)")


class SimulationRequest(RoundedModel):
    """Everything needed to value a development project end to end."""
    # Site
    plot_m2: float = Field(..., gt=0, description="Raw plot size in m²")
    land_price_mad: float = Field(..., ge=0, description="Land acquisition price (MAD)")
    zone: ZoningCategory = Field(..., description="Casablanca zoning category")
    neighborhood: str = Field(..., description="Location identifier — maps to the categorical feature in MLConfig (e.g. zipcode)")

    # Construction rates (MAD/m²) — fully dynamic, no hardcoded prices
    underground_parking_mad: float = Field(3500.0, ge=0, description="Build cost, underground parking (MAD/m²)")
    ground_floor_mad: float = Field(4500.0, ge=0, description="Build cost, ground floor (MAD/m²)")
    upper_floors_mad: float = Field(4300.0, ge=0, description="Build cost, upper floors (MAD/m²)")
    penthouse_mad: float = Field(5000.0, ge=0, description="Build cost, penthouse (MAD/m²), if the zone allows one")

    # Other costs
    contingency_percentage: float = Field(0.05, ge=0, le=1, description="Contingency reserve, as a fraction of construction cost")
    demolition_cost_mad: float = Field(150000.0, ge=0, description="Demolition cost (MAD); only charged if requires_demolition is true")
    requires_demolition: bool = Field(True, description="Whether the plot needs demolition before building")
    # Soft costs — 5 sub-lines (base = construction + demolition)
    feasibility_pct: float = Field(0.005, ge=0, le=1, description="Feasibility studies, as a fraction of (construction + demolition)")
    architecture_pct: float = Field(0.030, ge=0, le=1, description="Architecture fees, as a fraction of (construction + demolition)")
    landscaping_env_pct: float = Field(0.003, ge=0, le=1, description="Landscaping & environmental studies, as a fraction of (construction + demolition)")
    structural_pct: float = Field(0.012, ge=0, le=1, description="Structural engineering, as a fraction of (construction + demolition)")
    pm_marketing_pct: float = Field(0.025, ge=0, le=1, description="Project management + marketing, as a fraction of (construction + demolition)")
    # Overheads (base = land + demo + construction + soft costs)
    overheads_pct: float = Field(0.005, ge=0, le=1, description="Overheads, as a fraction of (land + demolition + construction + soft costs)")
    # Selling cost deducted from GDV to produce NDV
    selling_cost_pct: float = Field(0.01, ge=0, le=1, description="Agent fees + selling costs deducted from GDV to arrive at NDV")

    # GDV configuration
    gdv_method: GDVMethod = Field(GDVMethod.ml, description="Which valuator prices the revenue side — 'ml' (falls back to 'lookup' automatically if no model is loaded) or 'lookup' directly")
    unit: UnitFeatures = Field(default_factory=UnitFeatures, description="Typical-unit attributes, used only when gdv_method='ml'")

    # Output currency — all monetary outputs are converted to this.
    # Inputs (construction rates, land price) are always provided in MAD.
    currency: Currency = Field(Currency.USD, description="Currency for every monetary field in the response. Inputs above are always MAD regardless of this setting")

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


class PaginatedNeighborhoods(BaseModel):
    """One page of location identifiers, e.g. from GET /neighborhoods?page=2."""
    items: List[str] = Field(description="Location identifiers on this page")
    total: int = Field(description="Total matching neighborhoods across all pages")
    page: int = Field(description="Current page (1-indexed)")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether a next page exists")
    has_previous: bool = Field(description="Whether a previous page exists")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": ["98052", "98053", "98055"],
                "total": 70, "page": 1, "page_size": 50,
                "total_pages": 2, "has_next": True, "has_previous": False,
            }
        }
    }


class ConstructionItem(RoundedModel):
    """One level of the generated building (e.g. "Ground Floor", "Floor G+2")."""
    level: str = Field(description="Level name — parking, ground floor, an upper floor, or penthouse")
    surface_m2: float = Field(description="Built surface at this level (m²)")
    cost_m2: float = Field(description="Construction rate applied to this level, in the response currency")
    total_mad: float = Field(description="surface_m2 × cost_m2, converted to the response currency")


class SimulationResponse(RoundedModel):
    """The full cost → GDV → profit breakdown for one simulated project."""

    currency: str = Field(description="Currency every monetary field below is expressed in (MAD, USD, or EUR)")

    # --- Cost side (Total Development Cost) ---
    total_investment_mad: float = Field(description="TDC — land + demolition + construction + soft costs + overheads + contingency")
    construction_subtotal_mad: float = Field(description="Construction cost only, summed across all levels")
    total_built_surface_m2: float = Field(description="Total built area across all levels, including underground parking")
    construction_details: List[ConstructionItem] = Field(description="Per-level breakdown of the generated building")

    # --- Revenue side ---
    gdv_method: str = Field(description="Valuator that actually priced this project — 'ml', 'lookup', or 'lookup (ml_unavailable)' if the requested ML model wasn't loaded")
    sellable_surface_m2: float = Field(description="Above-ground built area (excludes underground parking, which isn't sold at residential rates)")
    price_per_m2: float = Field(description="Predicted or looked-up sale price per m²")
    gdv_mad: float = Field(description="Gross Development Value = sellable_surface_m2 × price_per_m2")
    ndv_mad: float = Field(description="Net Distributable Value = GDV × (1 − selling_cost_pct) — what the developer actually nets from sales")
    soft_costs_mad: float = Field(description="Sum of the 5 soft-cost sub-lines (feasibility, architecture, landscaping, structural, PM/marketing)")
    overheads_mad: float = Field(description="Overheads, computed on land + demolition + construction + soft costs")

    # --- Bottom line — percentages are dimensionless and never currency-converted ---
    net_profit_mad: float = Field(description="NDV − TDC")
    margin_pct: float = Field(description="net_profit ÷ NDV, as a percentage")
    roi_pct: float = Field(description="net_profit ÷ TDC, as a percentage")
