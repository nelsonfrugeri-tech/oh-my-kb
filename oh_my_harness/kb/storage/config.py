"""Storage configuration.

A thin layer over environment variables so the rest of the codebase doesn't
read ``os.environ`` directly. Reading the URL is centralized here so the
default and the env var name are defined once.
"""

from __future__ import annotations

import os

DEFAULT_QDRANT_URL = "http://localhost:6333"
QDRANT_URL_ENV = "KB_QDRANT_URL"


def get_qdrant_url() -> str:
    """Return the Qdrant URL from ``$KB_QDRANT_URL`` or the default."""
    return os.environ.get(QDRANT_URL_ENV, DEFAULT_QDRANT_URL)
