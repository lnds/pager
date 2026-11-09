"""Clientes HTTP hacia catalog y notifications."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

import httpx

from incidents import config


class ServiceUnavailable(Exception):
    pass


class Catalog(Protocol):
    def list_services(self) -> list[dict[str, Any]]: ...

    def get_service(self, service_id: int) -> dict[str, Any] | None: ...

    def current_shift(self, service_id: int) -> dict[str, Any] | None: ...


class Notifications(Protocol):
    def notify(self, notification: dict[str, Any]) -> None: ...


class HttpCatalog:
    def __init__(self, base_url: str, timeout: float = 3.0):
        timeout = float(os.environ.get("CATALOG_TIMEOUT", timeout))
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    def list_services(self) -> list[dict[str, Any]]:
        return self._get("/services") or []

    def get_service(self, service_id: int) -> dict[str, Any] | None:
        return self._get(f"/services/{service_id}")

    def current_shift(self, service_id: int) -> dict[str, Any] | None:
        return self._get(f"/shifts/current/{service_id}")

    def _get(self, path: str) -> Any:
        try:
            response = self._http.get(path)
        except httpx.HTTPError as e:
            raise ServiceUnavailable("catalog") from e
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ServiceUnavailable("catalog")
        return response.json()


class HttpNotifications:
    def __init__(self, base_url: str, timeout: float = 2.0):
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Api-Key": config.NOTIFICATIONS_API_KEY},
        )

    def notify(self, notification: dict[str, Any]) -> None:
        attempts = int(os.environ.get("NOTIFY_RETRIES", "3"))
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._http.post("/notify", json=notification)
                if response.status_code < 400:
                    return
                if response.status_code < 500:
                    raise ServiceUnavailable("notifications")
            except httpx.HTTPError as e:
                last_error = e
            time.sleep(0.2 * (attempt + 1))
        raise ServiceUnavailable("notifications") from last_error
