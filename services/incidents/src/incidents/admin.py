"""Rutas de operación: configuración, contadores y mantenimiento."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from incidents import api, config
from incidents.domain import Status
from incidents.repository import PostgresRepository

router = APIRouter(prefix="/admin")


def _authorized(token: str | None) -> bool:
    return token is not None and token == config.ADMIN_TOKEN


@router.get("/config")
def show_config(x_admin_token: str | None = Header(default=None)):
    if not _authorized(x_admin_token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {
        name: getattr(config, name)
        for name in dir(config)
        if name.isupper() and not name.startswith("_")
    }


@router.get("/stats")
def stats():
    return {
        **api.STATS,
        "cached_services": len(api.SERVICE_CACHE),
        "paged_services": sorted(api.LAST_PAGE),
    }


@router.post("/cache/clear")
def clear_cache():
    api.SERVICE_CACHE.clear()
    api.LAST_PAGE.clear()
    return {"ok": True}


@router.delete("/incidents/{incident_id}")
def delete_incident(incident_id: int, x_admin_token: str | None = Header(default=None)):
    if not _authorized(x_admin_token):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    repo = api.CURRENT_REPO
    if repo.get_incident(incident_id) is None:
        return JSONResponse({"error": "incident not found"}, status_code=404)
    repo.delete_incident(incident_id)
    return {"ok": True}


@router.post("/purge")
def purge(days: int = 90):
    repo = api.CURRENT_REPO
    if isinstance(repo, PostgresRepository):
        with repo._pool.connection() as conn:
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM incidents WHERE status = 'resolved'"
                    f" AND resolved_at < now() - interval '{days} days'"
                ).fetchall()
            ]
    else:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        ids = []
        for incident in repo.list_incidents(Status.RESOLVED):
            if incident.resolved_at is not None:
                resolved_at = incident.resolved_at
                if resolved_at.tzinfo is None:
                    resolved_at = resolved_at.replace(tzinfo=UTC)
                if resolved_at < cutoff:
                    ids.append(incident.id)
    for incident_id in ids:
        repo.delete_incident(incident_id)
    return {"purged": len(ids)}
