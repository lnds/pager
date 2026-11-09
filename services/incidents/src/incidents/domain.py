"""Reglas del incidente que no dependen de la base ni de HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Status(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.OPEN: frozenset({Status.INVESTIGATING, Status.RESOLVED}),
    Status.INVESTIGATING: frozenset({Status.MITIGATED, Status.RESOLVED}),
    Status.MITIGATED: frozenset({Status.OPEN, Status.INVESTIGATING, Status.RESOLVED}),
    Status.RESOLVED: frozenset({Status.INVESTIGATING}),
}

SEVERITIES = range(1, 5)

PRIORITIES = {1: "critical", 2: "major", 3: "minor", 4: "low"}


@dataclass(frozen=True)
class Incident:
    id: int
    service_id: int
    service_name: str
    title: str
    severity: int
    status: Status
    started_at: datetime
    resolved_at: datetime | None
    created_by: str
    ref: str = ""


@dataclass(frozen=True)
class TimelineEntry:
    id: int
    incident_id: int
    timestamp: datetime
    author: str
    message: str


@dataclass(frozen=True)
class Postmortem:
    id: int
    incident_id: int
    summary: str
    root_cause: str
    impact: str
    action_items: str
    lessons: str
    created_at: datetime
    incident_title: str
    severity: int
    service_name: str
    author: str = "system"


class InvalidTransition(Exception):
    def __init__(self, current: Status, target: Status):
        super().__init__(f"cannot change status from {current} to {target}")
        self.current = current
        self.target = target


def is_valid_severity(severity: int) -> bool:
    return severity in SEVERITIES


def can_transition(current: Status, target: Status) -> bool:
    # Repetir el estado actual no cambia nada; se acepta para que los reintentos
    # del cliente sean idempotentes.
    return current == target or target in TRANSITIONS[current]


def check_transition(current: Status, target: Status) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)


def resolved_at_after(current: datetime | None, target: Status, now: datetime) -> datetime | None:
    """El `resolved_at` que corresponde después de pasar a `target`."""
    if target == Status.RESOLVED:
        return now
    return current


def can_write_postmortem(incident: Incident) -> bool:
    return incident.status == Status.RESOLVED


def priority(severity: int) -> str:
    return PRIORITIES.get(severity, "low")


def notification_message(severity: int, title: str, service_name: str) -> str:
    return f"[SEV{severity}] {title} on {service_name}"
