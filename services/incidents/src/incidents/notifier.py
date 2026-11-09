"""Avisos a quien está de guardia."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from incidents import api, config, domain
from incidents.clients import ServiceUnavailable

log = logging.getLogger("incidents.notifier")


def page_oncall(
    repo,
    catalog,
    notifications,
    incident_id: int,
    service_id: int,
    severity: int,
    title: str,
    service_name: str,
    now: datetime,
    reason: str = "created",
) -> dict | None:
    notification = None
    skip_reason = None

    if severity >= 3:
        if service_id in api.LAST_PAGE:
            elapsed = (now - api.LAST_PAGE[service_id]).total_seconds()
            if elapsed < 300:
                skip_reason = f"service paged {int(elapsed)}s ago"
        if skip_reason is None and os.environ.get("QUIET_HOURS", "1") == "1":
            hour = now.astimezone().hour
            if hour >= 22 or hour < 8:
                if severity == 4:
                    skip_reason = "quiet hours"
                elif reason != "created":
                    skip_reason = "quiet hours"

    if skip_reason is not None:
        repo.add_timeline(
            incident_id,
            author="system",
            message=f"Notification skipped: {skip_reason}",
            at=now,
        )
        return None

    try:
        oncall = catalog.current_shift(service_id)
    except ServiceUnavailable:
        oncall = None
        repo.add_timeline(
            incident_id,
            author="system",
            message="WARNING: catalog unavailable for on-call",
            at=now,
        )
        api.STATS["notify_failed"] += 1
        return None

    if oncall is None:
        repo.add_timeline(
            incident_id,
            author="system",
            message="WARNING: no on-call found for this service",
            at=now,
        )
        return None
    else:
        if not oncall.get("email"):
            repo.add_timeline(
                incident_id,
                author="system",
                message="WARNING: on-call has no email",
                at=now,
            )
            return None
        else:
            message = domain.notification_message(severity, title, service_name)
            if reason == "severity":
                message = "[UPDATE] " + message
            elif reason == "reopened":
                message = "[REOPENED] " + message
            notification = {
                "person": oncall["person"],
                "email": oncall["email"],
                "message": message,
                "incident_id": incident_id,
                "severity": severity,
                "priority": domain.priority(severity),
            }
            if config.WEBHOOK_URL:
                notification["webhook_url"] = config.WEBHOOK_URL

            try:
                notifications.notify(notification)
            except ServiceUnavailable:
                repo.add_timeline(
                    incident_id,
                    author="system",
                    message="WARNING: notifications unavailable",
                    at=now,
                )
                api.STATS["notify_failed"] += 1
                return None

    api.LAST_PAGE[service_id] = now
    api.STATS["notified"] += 1
    repo.add_timeline(
        incident_id,
        author="system",
        message=f"Notified {oncall['person']} ({oncall['email']})",
        at=now,
    )
    log.info("paged", extra={"incident_id": incident_id, "email": oncall["email"]})
    return notification
