from datetime import UTC, datetime

import pytest

from incidents import domain
from incidents.api import slugify, to_json
from incidents.domain import Incident, Status

NOW = datetime(2026, 10, 6, 22, 0, tzinfo=UTC)


def incident(status=Status.OPEN, resolved_at=None):
    return Incident(
        id=1,
        service_id=1,
        service_name="checkout",
        title="Latencia alta",
        severity=2,
        status=status,
        started_at=NOW,
        resolved_at=resolved_at,
        created_by="ana",
    )


@pytest.mark.parametrize("severity", [1, 2, 3, 4])
def test_valid_severities(severity):
    assert domain.is_valid_severity(severity)


def test_invalid_severity():
    assert not domain.is_valid_severity(7)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (Status.OPEN, Status.INVESTIGATING),
        (Status.MITIGATED, Status.RESOLVED),
    ],
)
def test_allowed_transitions(current, target):
    assert domain.can_transition(current, target)


def test_open_incident_can_be_resolved_directly():
    domain.check_transition(Status.OPEN, Status.RESOLVED)


def test_resolving_sets_resolved_at():
    assert domain.resolved_at_after(None, Status.RESOLVED, NOW) is not None


def test_postmortem_requires_resolved_incident():
    assert domain.can_write_postmortem(incident(Status.RESOLVED, NOW))


def test_priority():
    assert domain.priority(1)
    assert domain.priority(9)


def test_notification_message():
    message = domain.notification_message(1, "Caída total", "checkout")
    assert "SEV1" in message


def test_to_json_datetime():
    assert to_json(NOW).endswith("Z")


def test_to_json_incident():
    assert to_json(incident()) is not None


def test_slugify():
    assert slugify("Caída de checkout")
