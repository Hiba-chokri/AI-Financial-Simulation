"""
Daba.Dar — local TESTING interface (not the production frontend).

Drives the Cost (Capex) engine and BOTH GDV valuators:
  - ML model (app/ml/predict.py)  : trained KC pipeline (primary)
  - Lookup   (app/engine/gdv.py)  : Casablanca median MAD/m² (fallback when ML bundle missing)

Run from the project root:
    streamlit run streamlit_app.py
"""
import pandas as pd
import streamlit as st

from app.engine.capex import ProjectFinancialInputs, compute_returns, generate_financial_model
from app.engine.currency import Currency, convert
from app.engine.gdv import load_lookup, predict_price_per_m2, train_from_dataset
from app.engine.matrix import CASABLANCA_ZONING_RULES, ZoningCategory
from app.ml import predict as ml_predict
from app.ml.config import MLConfig

_ml_config = MLConfig()

ZONE_LABELS = {
    "Zone A/B: Dense residential (R+5)": ZoningCategory.ZONE_AB_DENSE,
    "Zone D: Villa (R+1)": ZoningCategory.ZONE_D_VILLA,
    "Zone E: Commercial (R+6)": ZoningCategory.ZONE_E_COMMERCIAL,
}

CURRENCY_LABELS = {
    "Moroccan Dirham (MAD)": Currency.MAD,
    "US Dollar (USD)": Currency.USD,
    "Euro (EUR)": Currency.EUR,
}


@st.cache_resource
def get_lookup():
    try:
        return load_lookup()
    except FileNotFoundError:
        return train_from_dataset()


@st.cache_resource
def get_ml_bundle():
    try:
        return ml_predict.load_model()
    except FileNotFoundError:
        return None


st.set_page_config(page_title="Daba.Dar Simulator", page_icon="🏗️", layout="wide")
st.title("🏗️ Daba.Dar Financial Simulator")
st.caption("Testing interface: Capex · GDV · NDV · currency conversion.")

lookup = get_lookup()
ml_bundle = get_ml_bundle()

if ml_bundle and ml_bundle.get("training_neighborhoods"):
    neighborhoods = sorted(ml_bundle["training_neighborhoods"])
    using_ml = True
else:
    neighborhoods = sorted(lookup["neighborhoods"].keys())
    using_ml = False


with st.sidebar:
    st.header("Project inputs")

    cur_label = st.selectbox("Output currency", list(CURRENCY_LABELS.keys()))
    currency = CURRENCY_LABELS[cur_label]
    sym = currency.value

    st.divider()

    zone_label = st.selectbox("Zoning category", list(ZONE_LABELS.keys()))
    zone = ZONE_LABELS[zone_label]
    rules = CASABLANCA_ZONING_RULES[zone]
    st.caption(
        f"CES {rules['ces']} · COS {rules['cos']} · "
        f"max {rules['max_upper_floors']} upper floors · "
        f"penthouse: {'yes' if rules['allows_penthouse'] else 'no'}"
    )

    plot_m2 = st.number_input("Plot size (m²)", min_value=1.0, value=500.0, step=10.0)
    land_price = st.number_input("Land price (MAD)", min_value=0.0, value=4_500_000.0, step=50_000.0)

    hood_default = "98052" if "98052" in neighborhoods else neighborhoods[0]
    neighborhood = st.selectbox(
        "Neighborhood / Zipcode",
        neighborhoods,
        index=neighborhoods.index(hood_default),
        help="KC zipcodes (ML bundle)" if using_ml else "Casablanca lookup (ML bundle not loaded)",
    )

    st.divider()
    if using_ml:
        st.subheader("Typical unit: KC features")
        u1, u2 = st.columns(2)
        bedrooms = u1.number_input("Bedrooms", min_value=0, value=3, step=1)
        bathrooms = u2.number_input("Bathrooms", min_value=0.0, value=1.75, step=0.25)
        u3, u4 = st.columns(2)
        sqft_above = u3.number_input("Sqft above grade", min_value=0.0, value=1180.0, step=50.0)
        sqft_basement = u4.number_input("Sqft basement", min_value=0.0, value=0.0, step=50.0)
        u5, u6 = st.columns(2)
        yr_built = u5.number_input("Year built", min_value=1900, max_value=2030, value=1990, step=1)
        sqft_living15 = u6.number_input("Neighbor avg sqft", min_value=0.0, value=1340.0, step=50.0)
        u7, u8 = st.columns(2)
        floors = u7.number_input("Floors", min_value=1.0, value=1.0, step=0.5)
        grade = u8.slider("Grade (1–13)", 1, 13, 7)
        u9, u10 = st.columns(2)
        condition = u9.slider("Condition (1–5)", 1, 5, 3)
        view = u10.slider("View (0–4)", 0, 4, 0)
        waterfront = st.checkbox("Waterfront", value=False)
    else:
        st.warning("ML bundle not loaded. Run `python -m app.ml.train` to enable ML GDV. Using Casablanca lookup for now.")

    st.divider()
    st.subheader(f"Construction rates ({sym}/m²)")
    parking_rate = st.number_input("Underground parking", min_value=0.0, value=3_500.0, step=100.0)
    ground_rate = st.number_input("Ground floor", min_value=0.0, value=4_500.0, step=100.0)
    upper_rate = st.number_input("Upper floors", min_value=0.0, value=4_300.0, step=100.0)
    penthouse_rate = st.number_input("Penthouse", min_value=0.0, value=5_000.0, step=100.0)

    st.divider()
    st.subheader("Other costs")
    contingency_pct = st.slider("Contingency (%)", 0.0, 20.0, 5.0, step=0.5) / 100
    requires_demolition = st.checkbox("Requires demolition", value=True)
    demolition_cost = st.number_input(
        "Demolition cost (MAD)", min_value=0.0, value=150_000.0, step=10_000.0,
        disabled=not requires_demolition,
    )

    with st.expander("Soft Costs & Overheads"):
        st.caption("Base for soft costs = construction + demolition")
        feasibility_pct = st.slider("Feasibility (%)", 0.0, 5.0, 0.5, step=0.1) / 100
        architecture_pct = st.slider("Architecture (%)", 0.0, 10.0, 3.0, step=0.5) / 100
        landscaping_pct = st.slider("Landscaping & Env (%)", 0.0, 5.0, 0.3, step=0.1) / 100
        structural_pct = st.slider("Structural (%)", 0.0, 5.0, 1.2, step=0.1) / 100
        pm_marketing_pct = st.slider("PM & Marketing (%)", 0.0, 10.0, 2.5, step=0.5) / 100
        st.caption("Base for overheads = land + demo + construction + soft costs")
        overheads_pct = st.slider("Overheads (%)", 0.0, 5.0, 0.5, step=0.1) / 100
        st.caption("Selling cost deducted from GDV to get NDV")
        selling_cost_pct = st.slider("Selling cost (%)", 0.0, 5.0, 1.0, step=0.1) / 100

    run = st.button("Calculate", type="primary", use_container_width=True)

# ── COMPUTE + DISPLAY ─────────────────────────────────────────────────────────
if run:
    inputs = ProjectFinancialInputs(
        underground_parking_mad=parking_rate,
        ground_floor_mad=ground_rate,
        upper_floors_mad=upper_rate,
        penthouse_mad=penthouse_rate,
        feasibility_pct=feasibility_pct,
        architecture_pct=architecture_pct,
        landscaping_env_pct=landscaping_pct,
        structural_pct=structural_pct,
        pm_marketing_pct=pm_marketing_pct,
        overheads_pct=overheads_pct,
        contingency_percentage=contingency_pct,
        demolition_cost_mad=demolition_cost,
    )

    cost = generate_financial_model(
        raw_plot_m2=plot_m2,
        land_price_mad=land_price,
        zone=zone,
        inputs=inputs,
        requires_demolition=requires_demolition,
    )

    # GDV: ML (primary) or lookup (fallback)
    if using_ml:
        unit_features = {
            _ml_config.categorical_features[0]: neighborhood,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "floors": floors,
            "waterfront": int(waterfront),
            "view": view,
            "condition": condition,
            "grade": grade,
            "sqft_above": sqft_above,
            "sqft_basement": sqft_basement,
            "yr_built": yr_built,
            "sqft_living15": sqft_living15,
        }
        price_per_m2 = ml_predict.predict_price_per_m2(unit_features, ml_bundle)
        gdv_label = "ML model (KC)"
    else:
        price_per_m2 = predict_price_per_m2(neighborhood, lookup)
        gdv_label = "Casablanca lookup"

    returns = compute_returns(cost, price_per_m2, selling_cost_pct)
    fx = lambda amt: convert(amt, currency)

    # ── Headline metrics ──────────────────────────────────────────────────────
    st.subheader("Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"TDC ({sym})", f"{fx(cost['TOTAL_NEEDED_INVESTMENT_MAD']):,.0f}")
    c2.metric(f"GDV ({sym})", f"{fx(returns['gdv']):,.0f}")
    c3.metric(f"NDV ({sym})", f"{fx(returns['ndv']):,.0f}", f"after {selling_cost_pct*100:.1f}% selling cost")
    c4.metric(
        f"Net Profit ({sym})",
        f"{fx(returns['net_profit']):,.0f}",
        f"Margin {returns['margin_pct']:.1f}%  ·  ROI {returns['roi_pct']:.1f}%",
    )

    st.divider()
    left, right = st.columns(2)

    # ── Construction breakdown ────────────────────────────────────────────────
    with left:
        st.subheader("🏢 Construction breakdown")
        build_rows = [
            {
                "Level": item["level"],
                "Surface (m²)": item["surface_m2"],
                f"Rate ({sym}/m²)": fx(item["cost_m2"]),
                f"Total ({sym})": fx(item["total_mad"]),
            }
            for item in cost["construction_details"]
        ]
        build_df = pd.DataFrame(build_rows)
        st.dataframe(
            build_df.style.format({
                "Surface (m²)": "{:,.0f}",
                f"Rate ({sym}/m²)": "{:,.0f}",
                f"Total ({sym})": "{:,.0f}",
            }),
            hide_index=True, use_container_width=True,
        )
        st.write(f"**Construction subtotal:** {fx(cost['construction_subtotal_mad']):,.0f} {sym}")
        st.write(f"**Total built surface:** {cost['total_built_surface_m2']:,.0f} m²")

    # ── Full TDC breakdown ────────────────────────────────────────────────────
    with right:
        st.subheader(f"💰 Full cost breakdown: TDC ({sym})")
        oc = cost["other_costs"]
        sc = oc["soft_cost_lines"]
        rows = [
            ("Land acquisition", cost["land_acquisition"]["total_mad"]),
            ("Construction subtotal", cost["construction_subtotal_mad"]),
            ("Demolition", oc["demolition_mad"]),
            (f"  → Feasibility ({feasibility_pct:.2%})", sc["feasibility_mad"]),
            (f"  → Architecture ({architecture_pct:.2%})", sc["architecture_mad"]),
            (f"  → Landscaping & Env ({landscaping_pct:.2%})", sc["landscaping_env_mad"]),
            (f"  → Structural ({structural_pct:.2%})", sc["structural_mad"]),
            (f"  → PM & Marketing ({pm_marketing_pct:.2%})", sc["pm_marketing_mad"]),
            ("Soft Costs Total", oc["soft_costs_mad"]),
            (f"Overheads ({overheads_pct:.2%})", oc["overheads_mad"]),
            (f"Contingency ({contingency_pct:.2%})", oc["contingency_mad"]),
            ("TOTAL INVESTMENT (TDC)", cost["TOTAL_NEEDED_INVESTMENT_MAD"]),
        ]
        summary_df = pd.DataFrame(rows, columns=["Item", sym])
        summary_df[sym] = summary_df[sym].apply(fx)
        st.dataframe(
            summary_df.style.format({sym: "{:,.0f}"}),
            hide_index=True, use_container_width=True,
        )

    st.divider()

    # ── GDV / NDV detail ──────────────────────────────────────────────────────
    st.subheader(f"📈 Revenue: {gdv_label}")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Sellable area", f"{returns['sellable_m2']:,.0f} m²", "parking excluded")
    g2.metric(f"Price/m² ({sym})", f"{fx(price_per_m2):,.0f}")
    g3.metric(f"GDV ({sym})", f"{fx(returns['gdv']):,.0f}")
    g4.metric(f"NDV ({sym})", f"{fx(returns['ndv']):,.0f}")

else:
    st.info("👈 Set your inputs in the sidebar and click **Calculate**.")
