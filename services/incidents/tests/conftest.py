from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from incidents import api, config
from incidents.api import create_app
from incidents.clients import ServiceUnavailable
from incidents.memory import InMemoryRepository


class FakeCatalog:
    def __init__(self):
        self.services = {1: {"id": 1, "name": "checkout", "team": "payments"}}
        self.shifts = {1: {"person": "Ana Soto", "email": "ana@example.com"}}
        self.down = False

    def list_services(self):
        self._check()
        return list(self.services.values())

    def get_service(self, service_id):
        self._check()
        return self.services.get(service_id)

    def current_shift(self, service_id):
        self._check()
        return self.shifts.get(service_id)

    def _check(self):
        if self.down:
            raise ServiceUnavailable("catalog")


class FakeNotifications:
    def __init__(self):
        self.sent = []
        self.down = False

    def notify(self, notification):
        if self.down:
            raise ServiceUnavailable("notifications")
        self.sent.append(notification)


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 6, 22, 0, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def reset_state(tmp_path, monkeypatch):
    api.SERVICE_CACHE.clear()
    api.LAST_PAGE.clear()
    monkeypatch.setattr(config, "EXPORT_DIR", str(tmp_path))
    yield


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def catalog():
    return FakeCatalog()


@pytest.fixture
def notifications():
    return FakeNotifications()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def client(repo, catalog, notifications, clock):
    return TestClient(create_app(repo, catalog, notifications, clock=clock))


@pytest.fixture
def new_incident(client):
    def create(**overrides):
        body = {"title": "Latencia alta en checkout", "service_id": 1, "severity": 2, **overrides}
        response = client.post("/incidents", json=body)
        assert response.status_code == 201
        return response.json()["id"]

    return create
