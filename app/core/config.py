"""
Central runtime configuration.

Values are read from environment variables, optionally loaded from a `.env`
file at the project root. Never hardcode secrets here — `.env` is gitignored;
`.env.example` documents every variable the service reads.
"""
import os
from typing import List, Set

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from a .env file if one exists


def _csv_env(name: str) -> List[str]:
    """Parse a comma-separated env var into a clean list (empty if unset)."""
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


# API keys the service accepts (comma-separated in DABA_API_KEYS).
API_KEYS: Set[str] = set(_csv_env("DABA_API_KEYS"))

# Browser origins allowed to call the API (comma-separated in DABA_ALLOWED_ORIGINS).
# Empty list = no cross-origin browser access is permitted.
ALLOWED_ORIGINS: List[str] = _csv_env("DABA_ALLOWED_ORIGINS")

# Enforce API-key auth. Set DABA_AUTH_ENABLED=false to bypass it in local dev.
AUTH_ENABLED: bool = os.getenv("DABA_AUTH_ENABLED", "true").strip().lower() != "false"

# Largest request body the API will accept (bytes). Simulation payloads are tiny.
MAX_BODY_BYTES: int = int(os.getenv("DABA_MAX_BODY_BYTES", "100000"))
