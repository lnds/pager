from datetime import UTC, datetime
from unittest.mock import MagicMock

from incidents import notifier
from incidents.memory import InMemoryRepository

NOW = datetime(2026, 10, 6, 22, 0, tzinfo=UTC)


def test_notifications_client_is_called():
    notifications = MagicMock()
    notifications.notify.return_value = {"status": "sent"}
    assert notifications.notify({"email": "ana@example.com"}) == {"status": "sent"}
    notifications.notify.assert_called_once()


def test_page_oncall_returns_notification():
    repo = InMemoryRepository()
    catalog = MagicMock()
    notifications = MagicMock()
    result = notifier.page_oncall(
        repo, catalog, notifications, 1, 1, 2, "Latencia alta", "checkout", NOW
    )
    assert result is not None


def test_page_oncall_when_nobody_is_on_call():
    repo = InMemoryRepository()
    catalog = MagicMock()
    catalog.current_shift.return_value = None
    result = notifier.page_oncall(
        repo, catalog, MagicMock(), 1, 1, 2, "Latencia alta", "checkout", NOW
    )
    assert result is None
