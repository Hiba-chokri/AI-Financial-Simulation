# Daba.Dar — AI Financial Simulation API

[![CI](https://github.com/Hiba-chokri/AI-Financial-Simulation/actions/workflows/ci.yml/badge.svg)](https://github.com/Hiba-chokri/AI-Financial-Simulation/actions/workflows/ci.yml)

A hyper-localized **real-estate development financial simulator**, built as a stateless
**microservice** (a Daba.Cities product). Given a plot of land, it autonomously designs a
zoning-compliant building, costs it end to end, estimates its market value, and returns the
net profit and margin — as a single JSON API call any platform can consume.

```
plot + zoning + rates  ──►  [ Capex engine ]  ──►  Total Development Cost (TDC)
location + unit specs   ──►  [ ML valuation ]  ──►  price/m² ──► GDV ──► NDV
                                                              ──► net profit · margin · ROI
```

---

## 1. What it does

- **Designs a building** from a plot: enforces Casablanca CES/COS/height limits and stops at
  whichever binds first, so it never proposes an illegal structure.
- **Costs it fully** (TDC): land + demolition + construction (per level) + 5 soft-cost lines +
  overheads + contingency.
- **Values it**: predicts a price per m² (ML model), multiplies by the sellable area to get
  **GDV**, then deducts selling costs to get **NDV** (Net Distributable Value).
- **Reports the bottom line**: net profit (NDV − TDC), development margin, and ROI.
- **Speaks three currencies**: all monetary outputs convert to MAD, USD, or EUR on request.
- **Is secured**: API-key auth, CORS allowlist, and security headers on every response.

---

## 2. Architecture

The service is a thin HTTP layer over two independent engines. No business logic lives in the
API — it validates input, calls the engines, and serializes the result.

```
                       ┌─────────────────────────────┐
   HTTP request  ─────►│  app/api  (routes, schemas, │
                       │           security)         │
                       └───────────────┬─────────────┘
                                       │
                 ┌─────────────────────┴────────────────────┐
                 ▼                                           ▼
      ┌───────────────────────┐                 ┌───────────────────────────┐
      │  app/engine (Capex)   │                 │  app/ml  (price/m² model) │
      │  cost of building     │                 │  XGBoost pipeline         │
      │  matrix · capex ·     │                 │  + lookup fallback        │
      │  currency · gdv-lookup│                 │  (app/engine/gdv.py)      │
      └───────────────────────┘                 └───────────────────────────┘
```

### Folder map

| Folder | Responsibility |
|--------|----------------|
| `app/api/`      | HTTP layer — `routes.py`, `schemas.py` (request/response contracts), `security.py` (API-key auth). |
| `app/core/`     | Configuration — `config.py` reads keys / CORS origins / limits from the environment. |
| `app/engine/`   | Deterministic financial math — `capex.py` (cost engine), `matrix.py` (zoning rules), `currency.py` (MAD→USD/EUR, **live** rates), `gdv.py` (Casablanca lookup, the ML fallback). |
| `app/ml/`       | The price-per-m² model pipeline (ingest → validate → features → train → predict), driven entirely by `config.py`. |
| `tests/`        | Pytest smoke tests (engine math + API security). |
| `app/scraper/`  | **Legacy** — a superseded live scraper + Casablanca data prep. Not used by the live service (see §7). |
| `app/database/` | **Placeholder** — a persistence layer for later; empty by design (the service is stateless). |

---

## 3. Tech stack

- **Python 3.9**, **FastAPI** + **Uvicorn** (API), **Pydantic v2** (validation/contracts)
- **scikit-learn** + **XGBoost** + **joblib** (ML), **pandas**/**numpy** (data)
- **Streamlit** (local testing UI), **pytest** + **httpx** (tests)
- **Docker** + **docker compose** (packaging/deployment)

Dependencies are split: `requirements.txt` is the lean **runtime** set the Docker image
installs; `requirements-dev.txt` adds the local tooling (Streamlit, matplotlib, pytest,
legacy scraper).

---

## 4. Setup

```bash
# 1. Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies (dev set = runtime + tests/Streamlit/plots)
pip install -r requirements-dev.txt

# 3. Configure the environment
cp .env.example .env
#    then edit .env:
#      - generate an API key:  python -c "import secrets; print(secrets.token_urlsafe(32))"
#      - set DABA_API_KEYS and DABA_ALLOWED_ORIGINS

# 4. Datasets & model artifacts are gitignored (not in the repo). To train the model:
#    place the King County CSV at  data/raw/kc_house_data.csv  then:
python -m app.ml.train
```

> The trained model (`data/models/kc_pipeline.joblib`) and the Casablanca lookup
> (`data/models/gdv_price_per_m2.json`) are gitignored. The API serves whichever it finds
> and falls back gracefully; see §6.

---

## 5. Running

### The API — Docker (recommended for integration)

```bash
docker compose up --build
```

That's the whole deployment: it builds the image, injects `.env` (API keys, CORS), mounts
`./data` read-only (so retraining never requires a rebuild), and serves on port 8000 with a
container-level healthcheck. The image runs as a non-root user and contains no secrets, no
datasets, and no dev tooling.

### The API — bare Python (local development)

```bash
uvicorn main:app --reload          # or: ./run_api.sh
```

- Interactive docs (Swagger): **http://localhost:8000/docs** — click **Authorize**, paste your
  API key, then "Try it out".
- Alternative docs (ReDoc): **http://localhost:8000/redoc**

Every endpoint has a full description (what it does, how the ML fallback behaves, what each
status code means), and every request/response field has its own description — hover any field
in `/docs` to see what it means without reading the source. No need to ask what `ndv_mad` or
`margin_pct` is; it's documented inline.

### Example request

```bash
curl -s -X POST http://localhost:8000/api/v1/simulate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"plot_m2": 500, "land_price_mad": 4500000, "zone": "zone_e",
       "neighborhood": "98052", "currency": "MAD"}'
```

Every field except the five above has a sensible default (see `app/api/schemas.py`).

### The local testing UI

```bash
streamlit run streamlit_app.py
```

A dashboard that drives the engine directly (no API/key needed) — adjust any parameter and see
the full TDC → GDV → NDV → profit breakdown. For the team, not end users.

### The tests

```bash
pytest -q
```

The suite has three layers:

| File | What it proves |
|------|----------------|
| `tests/test_capex_calculations.py` | The financial math, against **hand-calculated expected values** — every construction line, soft-cost line, overheads, TDC to the dirham; zoning-law enforcement (COS ceiling, penthouse rules); the GDV → NDV → profit chain and its edge cases. |
| `tests/test_api_contract.py` | The HTTP contract an integrating platform codes against — validation (422s), full response schema, currency conversion on every monetary field, fallback behavior, and that the API returns *exactly* what a direct engine call computes. |
| `tests/test_api.py` / `tests/test_engine.py` | Smoke tests: auth (401/413), health, currency table sanity. |

Tests that need the gitignored ML artifact skip cleanly on a bare clone, so the suite
passes everywhere — locally with a trained model, and in CI without one.

### ML / data utilities

```bash
python -m app.ml.ingest         # preview the dataset (shape + first 10 rows)
python -m app.ml.train          # train + evaluate models, save the winner
python -m app.ml.quality_gate   # pass/fail check: is the trained model shippable?
python -m app.ml.plot_metrics   # bar-chart comparison of the candidate models
python -m app.ml.predict        # fallback-chain report across trained locations
```

---

## CI/CD (GitHub Actions)

Two deliberately **separate** pipelines — code changes never retrain the model, and
retraining never rebuilds the image (the container mounts `data/` at run time):

- **`ci.yml` — code pipeline.** Every push/PR: install → full test suite → Docker image
  build. A red ❌ blocks broken code from reaching `main`.
- **`train.yml` — model pipeline (MLOps).** Manual trigger (Actions → *Train model* →
  *Run workflow*), optional weekly schedule: trains the three candidate models, then a
  **quality gate** (`app/ml/quality_gate.py`) refuses to publish any model with R² < 0.70
  or MAPE > 20% — the pipeline cannot ship a degraded model. Passing artifacts
  (`.joblib` + metadata + metrics chart) are uploaded to the workflow run, ready to be
  dropped into `data/models/` of any deployment.

The KC training CSV (2.5 MB) and the Casablanca lookup JSON are committed specifically so
both pipelines work from a bare clone.

---

## 6. Endpoints & security

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/`                       | public  | Service metadata. |
| `GET`  | `/api/v1/health`          | public  | Liveness, ML model status, and FX rate freshness (`live`/`cached`/`bootstrap`). |
| `GET`  | `/api/v1/neighborhoods`   | **key** | Locations the model was trained on — paginated (see below). |
| `POST` | `/api/v1/simulate`        | **key** | Full valuation: cost → GDV → NDV → profit. |

### `/neighborhoods` pagination

The location list is paginated so the response stays flat regardless of dataset size —
today it's 70 King County zipcodes, but nothing about the endpoint assumes that ceiling.

```
GET /api/v1/neighborhoods?page=1&page_size=50&search=980
```

| Param | Default | Notes |
|-------|---------|-------|
| `page` | 1 | 1-indexed |
| `page_size` | 50 | max 500 |
| `search` | — | optional case-insensitive substring filter |

```json
{
  "items": ["98052", "98053", "98055"],
  "total": 70, "page": 1, "page_size": 50,
  "total_pages": 2, "has_next": true, "has_previous": false
}
```

A page past the end returns an empty `items` list, never an error.

**Security layers** (configured via `.env`, see `.env.example`):

- **API key** — send `X-API-Key: <key>`; missing/invalid → `401`. Keys are compared in constant
  time. `/health` stays public for monitoring.
- **CORS** — only origins in `DABA_ALLOWED_ORIGINS` may call the API from a browser. Server-to-
  server calls (recommended for integration) ignore CORS entirely.
- **Hardening** — security headers on every response (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`) and a request-body size cap.

**GDV fallback:** if `gdv_method=ml` but no model is loaded, the API silently falls back to the
Casablanca neighborhood lookup and reports `gdv_method: "lookup (ml_unavailable)"` in the
response, so the caller always knows which valuator produced the number.

**Live exchange rates:** MAD→USD/EUR rates are fetched from exchangerate-api.com and cached for
`DABA_FX_REFRESH_SECONDS` (default 6h) — not hardcoded, so a real-world rate move is reflected
without a deploy. If the provider is unreachable, the API keeps serving the **last successfully
fetched rate** rather than failing the request; only on a cold start with no prior fetch (or no
`DABA_EXCHANGE_RATE_API_KEY` configured) does it fall back to the fixed rates baked into
`currency.py`. Check `GET /api/v1/health` → `fx_rates_source` (`live` / `cached` / `bootstrap`)
to see which mode is active.

---

## 7. Important context for the team

**Data reality (read before trusting any number).** The ML model is currently trained on **King
County, WA** house data (`kc_house_data.csv`, ~21k rows) — a large, clean dataset used as a
**proxy** to build and validate the pipeline. It is *not* Moroccan data. Until it is replaced,
the *combined* profit/margin is directional plumbing, not a calibrated valuation: the cost side
is Casablanca MAD while the ML price side is King County USD/sqft. Swapping the dataset is a
config + retrain, not a code change (`app/ml/config.py`).

**Legacy code (kept, not live).**
- `app/scraper/sarouty.py` — a Playwright scraper, superseded by the static-data pivot after
  Cloudflare blocked live scraping. Nothing imports it; it's the only reason `playwright` is a
  dependency.
- `app/scraper/cleaner.py` — Casablanca-specific data prep, superseded by the config-driven
  `app/ml/` pipeline. Still used only to rebuild the Casablanca lookup from the legacy CSV.

**Placeholders.** `app/database/*` is intentionally empty — the service is stateless today.

---

## 8. Integration notes (for consuming microservices)

- **Ships as a container** — `docker compose up --build` is the entire deployment. The image is
  self-contained (code + dependencies); secrets come from the environment and model artifacts
  from a mounted volume, so neither ever requires a rebuild.
- **Stateless & horizontally scalable** — no DB, no session; the model loads into memory once
  per process (`@lru_cache`). Run as many replicas as you like behind a load balancer.
- **Call it server-to-server** with a shared API key. Keep the key server-side; never ship it to
  a browser.
- **The contract is the schema.** `app/api/schemas.py` is the single source of truth for the
  request/response shape, and `/docs` publishes it as OpenAPI — generate a typed client from it
  rather than hand-rolling one.
- **Versioned base path** (`/api/v1`) so future breaking changes don't disrupt existing callers.

---

## 9. Roadmap

- Replace the King County proxy with Moroccan price data (config + retrain).
- Typology engine (GFA/unit, efficiency %, unit mix) to break GDV down per unit type.
- Exit scenarios beyond sell-on-completion (long-term rent, short-term/Airbnb, hold) and their
  yield metrics (NOI, Yield-on-Cost, cap value).
- Rate limiting, and the persistence layer (`app/database/`) if saved simulations are needed.

> Current geographic scope for the **cost/zoning** side is **Casablanca, Morocco**.
