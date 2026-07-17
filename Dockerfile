# Daba.Dar Financial Simulation API — production image.
#
# Build:  docker build -t daba-dar-api .
# Run:    docker run --env-file .env -p 8000:8000 -v ./data:/app/data:ro daba-dar-api
#         (or simply: docker compose up)
#
# Model artifacts (data/models/*) are NOT baked into the image — mount ./data as a
# volume so the same image serves any trained model without a rebuild.

FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime dependencies first — this layer is cached until requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only the code the service needs (see .dockerignore for what stays out).
COPY main.py ./
COPY app/ ./app/

# Run as a non-root user — standard container hardening.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Container-level liveness probe against the public /health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; \
      r=urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=2); \
      sys.exit(0 if r.status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
