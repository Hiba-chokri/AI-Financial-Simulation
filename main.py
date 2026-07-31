"""
Daba.Dar — Financial Simulation API (Submodel D).

FastAPI entrypoint that turns the isolated cost/GDV engines into a web service.
Interactive docs are auto-generated at /docs (Swagger) and /redoc.

Run:
    uvicorn main:app --reload
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core import config

app = FastAPI(
    title="Daba.Dar Financial Simulation API",
    description=(
        "Hyper-localized real-estate development valuation for Casablanca. Given a plot "
        "of land, autonomously designs a zoning-compliant building, prices the full "
        "construction cost, estimates its Gross Development Value (GDV), and returns "
        "net profit, margin, and ROI — a complete developer pro-forma in one call.\n\n"
        "All endpoints except `/health` require an API key — see the **Authorize** "
        "button above, header `X-API-Key`."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "meta",
            "description": "Service status and reference data — no financial computation.",
        },
        {
            "name": "valuation",
            "description": "The core financial simulation: cost, revenue, and profit for a development project.",
        },
    ],
)

# --- CORS: only the configured origins may call the API from a browser ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


@app.middleware("http")
async def security_hardening(request: Request, call_next):
    """Reject oversized bodies and stamp standard security headers on every response."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > config.MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body too large."})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Daba.Dar Financial Simulation API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/api/v1/simulate", "/api/v1/neighborhoods", "/api/v1/health"],
    }
