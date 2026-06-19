# Daba.Dar — AI Financial Simulation Engine

A hyper-localized, AI-assisted **real-estate development financial simulator** for
Casablanca, Morocco. Built as an isolated microservice that plugs into Daba.Dar's
property listing cards (a Daba.Cities product).

Given a piece of land, the engine autonomously designs a **legally-compliant building**
under Casablanca urban-planning law, costs it out (Capex), estimates its **Gross
Development Value (GDV)**, and reports the **net profit and margin** — turning complex
developer math into an instant answer for non-specialist micro-investors.

---

## 1. The Problem & The Solution

- **Problem:** Real-estate development economics are complex, exclusive, and built for
  professional developers. There is no fast, localized tool to show ordinary investors
  whether building on a given plot is financially viable.
- **Solution:** Input a plot (size, location, zoning, land price) → get instant,
  scenario-based projections (acquisition + demolition + construction cost, GDV, profit
  margin), with all the math hidden from the user.

---

## 2. Architecture & Submodels

The system is decomposed into four submodels (think of them as a pipeline):

| Submodel | Name | Status | What it does |
|----------|------|--------|--------------|
| **A** | Data Ingestion | ✅ Done | Loads & cleans the Casablanca housing dataset (`app/scraper/cleaner.py`). |
| **B** | Capex (Cost) Engine | ✅ Done | Designs a zoning-compliant building and itemizes all costs (`app/engine/capex.py`). |
| **C** | GDV Valuation | ✅ Done (v1) | Estimates resale value per m² to compute GDV (`app/engine/gdv.py`). |
| **D** | API Gateway + Validation | ⬜ Not started | FastAPI endpoint wrapping B+C, validated vs. 3 real listings. |

Composition layer: `app/engine/valuation.py` ties **B + C** together into a full
cost → GDV → profit breakdown.

### Domain logic: Casablanca zoning law
The Capex engine strictly enforces legal limits from the *Agence Urbaine de Casablanca*,
encoded as a data-driven matrix in `app/engine/matrix.py`:

- **CES** (*Coefficient d'Emprise au Sol*) — max ground footprint as a fraction of the plot.
- **COS** (*Coefficient d'Occupation du Sol*) — max total floor area (vertical volume).
- **Height caps** — e.g. Zone A/B dense → R+5, Zone D villa → R+1, Zone E commercial → R+6.

The engine builds floors upward and **stops at whichever binds first** — the height cap or
the COS ceiling — so it never proposes an illegal structure.

---

## 3. Tech Stack

- **Language:** Python 3.9
- **Validation:** Pydantic (strict, fully dynamic financial inputs — zero hardcoded prices)
- **Data:** Pandas
- **Planned:** FastAPI + Uvicorn (Submodel D), PostgreSQL (production GIS zoning data)
- **Installed but currently unused:** scikit-learn, xgboost — see the [data reality](#5-important-the-data-reality) note below.

---

## 4. Project Structure

```
AI-Financial-Simulation/
├── app/
│   ├── api/                 # Submodel D — FastAPI layer (STUBS, not built yet)
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── database/            # PostgreSQL layer (STUBS, not built yet)
│   │   ├── database.py
│   │   └── models.py
│   ├── engine/              # The financial core
│   │   ├── matrix.py        # Casablanca CES/COS/height zoning rules
│   │   ├── capex.py         # Submodel B — cost engine + building generator
│   │   ├── gdv.py           # Submodel C — GDV price/m² valuation
│   │   └── valuation.py     # Composition: Capex + GDV -> profit/margin
│   └── scraper/
│       ├── cleaner.py       # Submodel A — dataset ingestion + feature prep
│       └── sarouty.py       # Legacy live scraper (superseded, see below)
├── data/
│   ├── raw/                 # Housing_data.csv lives here (gitignored)
│   └── models/              # Generated GDV lookup artifact (gitignored)
├── main.py                  # FastAPI entrypoint (empty — not built yet)
├── requirements.txt
└── .env.example
```

---

## 5. IMPORTANT: The Data Reality

This is the single most important thing for a teammate to understand before trusting any
output:

- The data source is a **static Kaggle "Moroccan Housing" dataset** of **resale listings**
  (existing finished apartments/villas), *not* land plots or new-build sales. This was a
  deliberate **Phase-1 pivot** away from live scraping (`sarouty.py`) after Cloudflare
  blocked the scrapers — it decouples the engine from network blockers so the math could be
  built today.
- After filtering to Casablanca, the dataset is **~3,179 rows but only 17 unique data
  points** (each duplicated ~187× with different marketing text), spanning **12
  neighborhoods**.
- **Because of this, Submodel C is NOT a machine-learning model.** A regressor on 17 points
  would just memorize and leak across a train/test split (fake R²≈1.0). Instead, Submodel C
  is an honest, transparent **price-per-m² lookup table** (median MAD/m² per neighborhood,
  with a city-wide median fallback). The `estimate_gdv()` interface is identical to what a
  real model would expose, so the internals can be swapped for ML once real data arrives.

### Consequences (treat outputs as a directional skeleton, not a calibrated valuation)
- **Land price** has no data source — it is a **manual user input** (the listing's asking
  price), by design.
- GDV applies a generic neighborhood *resale* price to *new* build area with no new-build
  premium adjustment, so margins skew optimistic.
- **Submodel D's validation against 3 real listings (<10% variance) is the real test** of
  whether the proxy holds.

---

## 6. Setup

```bash
# 1. Create & activate a virtual environment (the repo uses a `ven/` folder)
python3 -m venv ven
source ven/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Get the dataset (gitignored — not in the repo)
#    Place the Kaggle Moroccan Housing CSV at:
#    data/raw/Housing_data.csv

# 4. Configure environment
cp .env.example .env   # then fill in DB credentials when Submodel D/DB are built
```

> Note: `requirements.txt` version pins may drift from what's installed in an existing
> `ven/`. If you hit a `ModuleNotFoundError`, run `pip install -r requirements.txt` again.

---

## 7. Running the Modules

Each module is runnable standalone via its `__main__` block (there is no API server yet).
Run from the project root so the `app.` package imports resolve:

```bash
# Submodel A — ingest + clean + feature-prep the dataset
python -m app.scraper.cleaner

# Submodel B — Capex engine (designs a building + itemizes costs)
python -m app.engine.capex

# Submodel C — build the GDV price/m² lookup (writes data/models/gdv_price_per_m2.json)
python -m app.engine.gdv

# Full valuation — Capex + GDV -> net profit & margin (sell-on-completion)
python -m app.engine.valuation
```

Example output from `valuation.py` (500 m² plot, Zone A/B dense, Riviera):

```
GDV (revenue):    31,402,291 MAD
Total investment: 13,122,625 MAD
Net profit:       18,279,666 MAD
Development margin: 58.2%   ROI: 139.3%
```

---

## 8. Roadmap

- **Phase C — Revenue/scenario layer:** add the remaining exit strategies (short-term/Airbnb,
  long-term rental, hold-and-manage) with localized yields, beyond sell-on-completion.
- **Phase D — Submodel D:** wrap Capex + GDV in a single FastAPI endpoint with a validation
  guardrail against ≥3 real listed properties.
- **Phase 2 data:** swap the static dataset for a live B2B/API data pipeline, and (only then)
  reconsider a real ML valuation model.
- **Infra:** PostgreSQL for production GIS zoning data; Docker for dev/prod parity.

---

## 9. Deliverables (project goals)

1. Financial simulation API integrated into Daba.Dar.
2. Scenario comparison dashboard (rent / sell / hold).
3. Validation report on 3 real property cases.
4. Technical documentation & model-assumptions log.

> Current geographic and mathematical scope is **strictly Casablanca, Morocco**.
