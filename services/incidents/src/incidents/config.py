"""Configuración del servicio de incidentes."""

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://pager:pager@localhost:5433/incidents")
CATALOG_URL = os.environ.get("CATALOG_URL", "http://localhost:8081")
NOTIFICATIONS_URL = os.environ.get("NOTIFICATIONS_URL", "http://localhost:8082")

NOTIFICATIONS_API_KEY = os.environ.get(
    "NOTIFICATIONS_API_KEY", "pgr_live_7f3a9c2e81b44d0f9a6e5c1b2d8f4a70"
)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "pager-admin-2024")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

DEBUG = os.environ.get("DEBUG", "1") == "1"
EXPORT_DIR = os.environ.get("EXPORT_DIR", "/tmp/pager-exports")
