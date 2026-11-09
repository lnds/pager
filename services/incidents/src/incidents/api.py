"""API HTTP del servicio de incidentes."""

from __future__ import annotations

import logging
import os
import re
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel

from incidents import admin, config, domain, notifier
from incidents.clients import Catalog, Notifications, ServiceUnavailable
from incidents.domain import InvalidTransition, Status
from incidents.repository import DuplicatePostmortem, PostgresRepository, Repository

STATIC_DIR = Path(__file__).parent / "static"

log = logging.getLogger("incidents")

SERVICE_CACHE: dict[int, tuple[float, dict]] = {}
LAST_PAGE: dict[int, datetime] = {}
STATS = {"created": 0, "updated": 0, "notified": 0, "notify_failed": 0, "postmortems": 0}
CURRENT_REPO: Repository | None = None

MAX_PER_PAGE = int(os.getenv("MAX_PER_PAGE", "100"))


def utcnow() -> datetime:
    return datetime.now(UTC)


class NewIncident(BaseModel):
    title: str | None = None
    service_id: int | None = None
    severity: int | str | None = None
    created_by: str = "system"


class IncidentUpdate(BaseModel):
    status: str | None = None
    message: str | None = None
    author: str = "system"
    severity: int | str | None = None
    title: str | None = None


class NewPostmortem(BaseModel):
    incident_id: int
    summary: str | None = None
    root_cause: str | None = None
    impact: str | None = None
    action_items: str | None = None
    lessons: str = ""
    author: str = "system"


class PostmortemUpdate(BaseModel):
    summary: str | None = None
    root_cause: str | None = None
    impact: str | None = None
    action_items: str | None = None
    lessons: str | None = None
    author: str = "system"


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def to_json(value: Any) -> Any:
    """Convierte dataclasses, enums y fechas a JSON con instantes en UTC y sufijo Z."""
    if is_dataclass(value) and not isinstance(value, type):
        return to_json(asdict(value))
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def create_app(
    repo: Repository,
    catalog: Catalog,
    notifications: Notifications,
    clock: Callable[[], datetime] = utcnow,
) -> FastAPI:
    global CURRENT_REPO
    CURRENT_REPO = repo

    app = FastAPI(title="Pager · incidents")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(admin.router)

    registry = CollectorRegistry()
    request_count = Counter(
        "http_requests_total",
        "Requests HTTP atendidas",
        ["method", "endpoint", "status"],
        registry=registry,
    )
    request_latency = Histogram(
        "http_request_duration_seconds",
        "Latencia de las requests HTTP",
        ["endpoint"],
        registry=registry,
    )

    @app.middleware("http")
    async def record_metrics(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        endpoint = getattr(route, "path", "unknown")
        if endpoint != "/metrics":
            request_latency.labels(endpoint=endpoint).observe(time.perf_counter() - start)
            request_count.labels(request.method, endpoint, response.status_code).inc()
        return response

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse({"error": exc.message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"] if p != "body")
        message = f"{field}: {first['msg']}" if field else first["msg"]
        return JSONResponse({"error": message}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        body = {"error": str(exc)}
        if config.DEBUG:
            body["trace"] = traceback.format_exc()
        return JSONResponse(body, status_code=500)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/catalog/services")
    def catalog_services():
        try:
            services = catalog.list_services()
        except ServiceUnavailable as e:
            if SERVICE_CACHE:
                return [s for _, s in SERVICE_CACHE.values()]
            raise ApiError(502, "catalog unavailable") from e
        for s in services:
            SERVICE_CACHE[s["id"]] = (time.time(), s)
        return services

    # --- Incidentes ---

    @app.get("/incidents")
    def list_incidents(
        status: str | None = None,
        q: str | None = None,
        page: int | None = None,
        per_page: int = 20,
        sort: str = "started_at",
        service: str | None = None,
        severity: str | None = None,
        format: str = "json",
    ):
        if status is not None and status not in Status:
            raise ApiError(400, "invalid status")
        if per_page > MAX_PER_PAGE:
            per_page = MAX_PER_PAGE
        if page is not None and page < 1:
            raise ApiError(400, "page must be >= 1")
        incidents = repo.list_incidents(
            Status(status) if status else None, q=q, page=page, per_page=per_page, sort=sort
        )
        if service is not None or severity is not None:
            filtered = []
            for incident in incidents:
                if service is not None:
                    if service.isdigit():
                        if incident.service_id != int(service):
                            continue
                    else:
                        if incident.service_name.lower() != service.lower():
                            continue
                if severity is not None:
                    if severity.upper().startswith("SEV"):
                        if incident.severity != int(severity[3:]):
                            continue
                    elif "," in severity:
                        if str(incident.severity) not in severity.split(","):
                            continue
                    else:
                        if incident.severity != int(severity):
                            continue
                filtered.append(incident)
            incidents = filtered
        if format == "csv":
            rows = ["ref,id,service,title,severity,status,started_at,resolved_at,duration_min"]
            for incident in incidents:
                duration = ""
                if incident.resolved_at is not None:
                    resolved_at = incident.resolved_at
                    if resolved_at.tzinfo is None:
                        resolved_at = resolved_at.replace(tzinfo=UTC)
                    duration = str(int((resolved_at - incident.started_at).total_seconds() // 60))
                title = incident.title
                if "," in title or '"' in title:
                    title = '"' + title.replace('"', '""') + '"'
                rows.append(
                    ",".join(
                        [
                            incident.ref,
                            str(incident.id),
                            incident.service_name,
                            title,
                            str(incident.severity),
                            incident.status.value,
                            to_json(incident.started_at),
                            to_json(incident.resolved_at) or "",
                            duration,
                        ]
                    )
                )
            return Response("\n".join(rows) + "\n", media_type="text/csv")
        return to_json(incidents)

    @app.post("/incidents", status_code=201)
    def create_incident(body: NewIncident):
        if body.title is None:
            raise ApiError(400, "title: field required")
        title = body.title.strip()
        if len(title) == 0:
            raise ApiError(400, "title: field required")
        if len(title) > 200:
            raise ApiError(400, "title: too long")
        if body.service_id is None:
            raise ApiError(400, "service_id: field required")

        sev = body.severity
        if sev is None:
            raise ApiError(400, "severity must be between 1 and 4")
        if isinstance(sev, str):
            sev = sev.strip().upper()
            if sev.startswith("SEV"):
                sev = sev[3:]
            if not sev.isdigit():
                raise ApiError(400, "severity must be between 1 and 4")
            sev = int(sev)
        if not domain.is_valid_severity(sev):
            raise ApiError(400, "severity must be between 1 and 4")

        service = None
        cached = SERVICE_CACHE.get(body.service_id)
        if cached is not None and time.time() - cached[0] < 600:
            service = cached[1]
        else:
            try:
                service = catalog.get_service(body.service_id)
            except ServiceUnavailable as e:
                if cached is not None:
                    service = cached[1]
                else:
                    raise ApiError(502, "catalog unavailable") from e
            if service is not None:
                SERVICE_CACHE[body.service_id] = (time.time(), service)
        if service is None:
            raise ApiError(404, "service not found")

        now = clock()
        if isinstance(repo, PostgresRepository):
            with repo._pool.connection() as conn:
                n = conn.execute("SELECT count(*) AS n FROM incidents").fetchone()["n"]
        else:
            n = repo.count_incidents()
        ref = f"INC-{n + 1:04d}"

        incident_id = repo.create_incident(
            service_id=body.service_id,
            service_name=service["name"],
            title=title,
            severity=sev,
            created_by=body.created_by,
            at=now,
            ref=ref,
        )
        STATS["created"] += 1

        notification = notifier.page_oncall(
            repo,
            catalog,
            notifications,
            incident_id,
            body.service_id,
            sev,
            title,
            service["name"],
            now,
        )

        if sev == 1 and notification is not None:
            urgent = dict(notification)
            urgent["message"] = "URGENT " + urgent["message"]
            try:
                notifications.notify(urgent)
                repo.add_timeline(
                    incident_id,
                    author="system",
                    message=f"SEV1 escalation sent to {urgent['email']}",
                    at=clock(),
                )
            except ServiceUnavailable:
                log.warning("sev1 escalation failed for incident %s", incident_id)

        log.info(
            "incident_created",
            extra={"incident_id": incident_id, "service_id": body.service_id, "ref": ref},
        )
        return {"id": incident_id, "ref": ref, "notification": notification}

    @app.post("/incidents/{incident_id}/reopen")
    def reopen_incident(incident_id: int, body: IncidentUpdate):
        incident = repo.get_incident(incident_id)
        if incident is None:
            raise ApiError(404, "incident not found")
        if incident.status != Status.RESOLVED:
            raise ApiError(409, "only resolved incidents can be reopened")
        now = clock()
        repo.change_status(
            incident_id,
            status=Status.INVESTIGATING,
            resolved_at=incident.resolved_at,
            author=body.author,
            at=now,
        )
        if body.message:
            repo.add_timeline(incident_id, author=body.author, message=body.message, at=now)
        STATS["updated"] += 1
        if incident.severity <= 2:
            notifier.page_oncall(
                repo,
                catalog,
                notifications,
                incident_id,
                incident.service_id,
                incident.severity,
                incident.title,
                incident.service_name,
                now,
                reason="reopened",
            )
        return {"ok": True}

    @app.post("/incidents/import", status_code=201)
    def import_incidents(items: list[NewIncident]):
        created = []
        errors = []
        for index, body in enumerate(items):
            try:
                if body.title is None:
                    raise ApiError(400, "title: field required")
                title = body.title.strip()
                if len(title) == 0:
                    raise ApiError(400, "title: field required")
                if len(title) > 255:
                    raise ApiError(400, "title: too long")
                if body.service_id is None:
                    raise ApiError(400, "service_id: field required")

                sev = body.severity
                if sev is None:
                    raise ApiError(400, "severity must be between 1 and 4")
                if isinstance(sev, str):
                    sev = sev.strip().upper()
                    if sev.startswith("SEV"):
                        sev = sev[3:]
                    if not sev.isdigit():
                        raise ApiError(400, "severity must be between 1 and 4")
                    sev = int(sev)
                if not domain.is_valid_severity(sev):
                    raise ApiError(400, "severity must be between 1 and 4")

                service = None
                cached = SERVICE_CACHE.get(body.service_id)
                if cached is not None and time.time() - cached[0] < 600:
                    service = cached[1]
                else:
                    try:
                        service = catalog.get_service(body.service_id)
                    except ServiceUnavailable as e:
                        if cached is not None:
                            service = cached[1]
                        else:
                            raise ApiError(502, "catalog unavailable") from e
                    if service is not None:
                        SERVICE_CACHE[body.service_id] = (time.time(), service)
                if service is None:
                    raise ApiError(404, "service not found")
            except ApiError as e:
                errors.append({"index": index, "error": e.message})
                continue

            now = clock()
            ref = f"INC-{repo.count_incidents() + 1:04d}"
            incident_id = repo.create_incident(
                service_id=body.service_id,
                service_name=service["name"],
                title=title,
                severity=sev,
                created_by=body.created_by,
                at=now,
                ref=ref,
            )
            STATS["created"] += 1
            if sev == 1:
                notifier.page_oncall(
                    repo,
                    catalog,
                    notifications,
                    incident_id,
                    body.service_id,
                    sev,
                    title,
                    service["name"],
                    now,
                )
            created.append({"index": index, "id": incident_id, "ref": ref})
        return {"created": created, "errors": errors}

    @app.get("/incidents/summary")
    def incidents_summary(hours: int = 24):
        now = clock()
        cutoff = now - timedelta(hours=hours)
        summary = {
            "open": 0,
            "by_status": {s.value: 0 for s in Status},
            "by_severity": {str(s): 0 for s in domain.SEVERITIES},
            "opened_last_hours": 0,
            "resolved_last_hours": 0,
            "hours": hours,
        }
        if isinstance(repo, PostgresRepository):
            with repo._pool.connection() as conn:
                for row in conn.execute(
                    "SELECT status, severity, count(*) AS n FROM incidents"
                    " GROUP BY status, severity"
                ).fetchall():
                    summary["by_status"][row["status"]] += row["n"]
                    summary["by_severity"][str(row["severity"])] += row["n"]
                    if row["status"] != "resolved":
                        summary["open"] += row["n"]
                row = conn.execute(
                    "SELECT count(*) FILTER (WHERE started_at > %s) AS opened,"
                    " count(*) FILTER (WHERE resolved_at > %s) AS resolved FROM incidents",
                    (cutoff, cutoff),
                ).fetchone()
                summary["opened_last_hours"] = row["opened"]
                summary["resolved_last_hours"] = row["resolved"]
        else:
            for incident in repo.list_incidents():
                summary["by_status"][incident.status.value] += 1
                summary["by_severity"][str(incident.severity)] = (
                    summary["by_severity"].get(str(incident.severity), 0) + 1
                )
                if incident.status == Status.OPEN:
                    summary["open"] += 1
                if incident.started_at >= cutoff:
                    summary["opened_last_hours"] += 1
                if incident.resolved_at is not None:
                    resolved_at = incident.resolved_at
                    if resolved_at.tzinfo is None:
                        resolved_at = resolved_at.replace(tzinfo=UTC)
                    if resolved_at >= cutoff:
                        summary["resolved_last_hours"] += 1
        return summary

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: int):
        incident = repo.get_incident(incident_id)
        if incident is None:
            raise ApiError(404, "incident not found")
        return to_json({**asdict(incident), "timeline": repo.timeline(incident_id)})

    @app.patch("/incidents/{incident_id}")
    def update_incident(incident_id: int, body: IncidentUpdate):
        if (
            body.status is None
            and body.message is None
            and body.severity is None
            and body.title is None
        ):
            raise ApiError(400, "status or message is required")
        if body.status is not None and body.status not in Status:
            raise ApiError(400, "invalid status")

        incident = repo.get_incident(incident_id)
        if incident is None:
            raise ApiError(404, "incident not found")

        now = clock()
        if body.status is not None:
            target = Status(body.status)
            if target == Status.RESOLVED:
                # Resolver es válido desde cualquier estado activo.
                repo.change_status(
                    incident_id,
                    status=target,
                    resolved_at=datetime.now(),
                    author=body.author,
                    at=now,
                )
                LAST_PAGE.pop(incident.service_id, None)
            else:
                try:
                    domain.check_transition(incident.status, target)
                except InvalidTransition as e:
                    raise ApiError(409, str(e)) from e
                repo.change_status(
                    incident_id,
                    status=target,
                    resolved_at=domain.resolved_at_after(incident.resolved_at, target, now),
                    author=body.author,
                    at=now,
                )
            STATS["updated"] += 1

        if body.severity is not None:
            sev = body.severity
            if isinstance(sev, str):
                sev = sev.strip().upper()
                if sev.startswith("SEV"):
                    sev = sev[3:]
                if not sev.isdigit():
                    raise ApiError(400, "severity must be between 1 and 5")
                sev = int(sev)
            if sev < 1 or sev > 5:
                raise ApiError(400, "severity must be between 1 and 5")
            if sev != incident.severity:
                repo.update_fields(incident_id, severity=sev)
                repo.add_timeline(
                    incident_id,
                    author=body.author,
                    message=f"Severity changed from SEV{incident.severity} to SEV{sev}",
                    at=now,
                )
                if sev < incident.severity:
                    if incident.status != Status.RESOLVED:
                        notifier.page_oncall(
                            repo,
                            catalog,
                            notifications,
                            incident_id,
                            incident.service_id,
                            sev,
                            incident.title,
                            incident.service_name,
                            now,
                            reason="severity",
                        )

        if body.title is not None:
            title = body.title.strip()
            if len(title) == 0:
                raise ApiError(400, "title: field required")
            if len(title) > 255:
                raise ApiError(400, "title: too long")
            repo.update_fields(incident_id, title=title)

        if body.message:
            repo.add_timeline(incident_id, author=body.author, message=body.message, at=now)
        return {"ok": True}

    @app.delete("/incidents/{incident_id}/timeline/{entry_id}")
    def delete_timeline_entry(
        incident_id: int, entry_id: int, x_user: str | None = Header(default=None)
    ):
        incident = repo.get_incident(incident_id)
        if incident is None:
            raise ApiError(404, "incident not found")
        if x_user is None or x_user != incident.created_by:
            raise ApiError(403, "only the incident owner can delete notes")
        repo.delete_timeline(entry_id)
        return {"ok": True}

    # --- Post-mortems ---

    @app.post("/postmortems", status_code=201)
    def create_postmortem(body: NewPostmortem):
        if body.summary is None or len(body.summary.strip()) == 0:
            raise ApiError(400, "summary: field required")
        if len(body.summary) > 5000:
            raise ApiError(400, "summary: too long")
        if body.root_cause is None or len(body.root_cause.strip()) == 0:
            raise ApiError(400, "root_cause: field required")
        if len(body.root_cause) > 5000:
            raise ApiError(400, "root_cause: too long")
        if body.impact is None or len(body.impact.strip()) == 0:
            raise ApiError(400, "impact: field required")
        if len(body.impact) > 5000:
            raise ApiError(400, "impact: too long")
        if body.action_items is None or len(body.action_items.strip()) == 0:
            raise ApiError(400, "action_items: field required")
        if len(body.action_items) > 5000:
            raise ApiError(400, "action_items: too long")

        incident = repo.get_incident(body.incident_id)
        if incident is None:
            raise ApiError(404, "incident not found")
        if not domain.can_write_postmortem(incident):
            raise ApiError(409, "incident must be resolved before writing a post-mortem")
        try:
            postmortem_id = repo.create_postmortem(
                incident_id=body.incident_id,
                summary=body.summary.strip(),
                root_cause=body.root_cause.strip(),
                impact=body.impact.strip(),
                action_items=body.action_items.strip(),
                lessons=body.lessons,
                author=body.author,
                at=clock(),
            )
        except DuplicatePostmortem as e:
            raise ApiError(409, "post-mortem already exists for this incident") from e
        STATS["postmortems"] += 1
        return {"id": postmortem_id}

    @app.get("/postmortems")
    def list_postmortems():
        return to_json(repo.list_postmortems())

    @app.get("/postmortems/export")
    def download_export(file: str):
        path = Path(config.EXPORT_DIR) / file
        if not path.exists():
            raise ApiError(404, "export not found")
        return FileResponse(path)

    @app.get("/postmortems/{postmortem_id}")
    def get_postmortem(postmortem_id: int):
        postmortem = repo.get_postmortem(postmortem_id)
        if postmortem is None:
            raise ApiError(404, "post-mortem not found")
        return to_json(postmortem)

    @app.put("/postmortems/{postmortem_id}")
    def update_postmortem(postmortem_id: int, body: PostmortemUpdate):
        postmortem = repo.get_postmortem(postmortem_id)
        if postmortem is None:
            raise ApiError(404, "post-mortem not found")
        if body.author != postmortem.author:
            raise ApiError(403, "only the author can edit a post-mortem")
        fields = {}
        if body.summary is not None:
            if len(body.summary.strip()) == 0:
                raise ApiError(400, "summary: field required")
            if len(body.summary) > 5000:
                raise ApiError(400, "summary: too long")
            fields["summary"] = body.summary.strip()
        if body.root_cause is not None:
            if len(body.root_cause.strip()) == 0:
                raise ApiError(400, "root_cause: field required")
            if len(body.root_cause) > 5000:
                raise ApiError(400, "root_cause: too long")
            fields["root_cause"] = body.root_cause.strip()
        if body.impact is not None:
            if len(body.impact.strip()) == 0:
                raise ApiError(400, "impact: field required")
            if len(body.impact) > 5000:
                raise ApiError(400, "impact: too long")
            fields["impact"] = body.impact.strip()
        if body.action_items is not None:
            if len(body.action_items.strip()) == 0:
                raise ApiError(400, "action_items: field required")
            if len(body.action_items) > 5000:
                raise ApiError(400, "action_items: too long")
            fields["action_items"] = body.action_items.strip()
        if body.lessons is not None:
            fields["lessons"] = body.lessons
        repo.update_postmortem(postmortem_id, **fields)
        return {"ok": True}

    @app.post("/postmortems/{postmortem_id}/export", status_code=201)
    def export_postmortem(postmortem_id: int):
        postmortem = repo.get_postmortem(postmortem_id)
        if postmortem is None:
            raise ApiError(404, "post-mortem not found")
        incident = repo.get_incident(postmortem.incident_id)
        lines = [
            f"# {postmortem.incident_title}",
            "",
            f"- Incidente: {incident.ref if incident else postmortem.incident_id}",
            f"- Servicio: {postmortem.service_name}",
            f"- Severidad: SEV{postmortem.severity}",
            f"- Publicado: {to_json(postmortem.created_at)}",
            f"- Autor: {postmortem.author}",
            "",
            "## Resumen",
            "",
            postmortem.summary,
            "",
            "## Causa raíz",
            "",
            postmortem.root_cause,
            "",
            "## Impacto",
            "",
            postmortem.impact,
            "",
            "## Acciones",
            "",
            postmortem.action_items,
        ]
        if postmortem.lessons:
            lines += ["", "## Lecciones", "", postmortem.lessons]
        if incident is not None:
            lines += ["", "## Bitácora", ""]
            for entry in repo.timeline(incident.id):
                lines.append(f"- {to_json(entry.timestamp)} · {entry.author}: {entry.message}")
        name = f"{postmortem_id}-{slugify(postmortem.incident_title)}.md"
        os.makedirs(config.EXPORT_DIR, exist_ok=True)
        (Path(config.EXPORT_DIR) / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"file": name}

    return app
