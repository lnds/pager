"""Punto de entrada: arma la aplicación con la configuración del environment."""

import logging
import os

from incidents import config
from incidents.api import create_app
from incidents.clients import HttpCatalog, HttpNotifications
from incidents.repository import PostgresRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = create_app(
    repo=PostgresRepository(config.DATABASE_URL),
    catalog=HttpCatalog(os.environ.get("CATALOG_URL", config.CATALOG_URL)),
    notifications=HttpNotifications(config.NOTIFICATIONS_URL),
)
