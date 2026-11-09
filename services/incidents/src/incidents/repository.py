"""Persistencia de incidentes, bitácora y post-mortems."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from psycopg import errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from incidents.domain import Incident, Postmortem, Status, TimelineEntry


class DuplicatePostmortem(Exception):
    pass


class Repository(Protocol):
    def list_incidents(
        self,
        status: Status | None = None,
        q: str | None = None,
        page: int | None = None,
        per_page: int = 20,
        sort: str = "started_at",
    ) -> list[Incident]: ...

    def count_incidents(self) -> int: ...

    def get_incident(self, incident_id: int) -> Incident | None: ...

    def create_incident(
        self,
        *,
        service_id: int,
        service_name: str,
        title: str,
        severity: int,
        created_by: str,
        at: datetime,
        ref: str = "",
    ) -> int: ...

    def change_status(
        self,
        incident_id: int,
        *,
        status: Status,
        resolved_at: datetime | None,
        author: str,
        at: datetime,
    ) -> None: ...

    def update_fields(self, incident_id: int, **fields) -> None: ...

    def delete_incident(self, incident_id: int) -> None: ...

    def add_timeline(
        self, incident_id: int, *, author: str, message: str, at: datetime
    ) -> None: ...

    def timeline(self, incident_id: int) -> list[TimelineEntry]: ...

    def delete_timeline(self, entry_id: int) -> None: ...

    def create_postmortem(
        self,
        *,
        incident_id: int,
        summary: str,
        root_cause: str,
        impact: str,
        action_items: str,
        lessons: str,
        author: str,
        at: datetime,
    ) -> int: ...

    def update_postmortem(self, postmortem_id: int, **fields) -> None: ...

    def list_postmortems(self) -> list[Postmortem]: ...

    def get_postmortem(self, postmortem_id: int) -> Postmortem | None: ...


_POSTMORTEM_SELECT = """
    SELECT p.*, i.title AS incident_title, i.severity, i.service_name
    FROM postmortems p JOIN incidents i ON p.incident_id = i.id
"""


def _incident(row: dict) -> Incident:
    return Incident(**{**row, "status": Status(row["status"])})


def _postmortem(row: dict) -> Postmortem:
    return Postmortem(**{**row, "lessons": row["lessons"] or ""})


class PostgresRepository:
    def __init__(self, database_url: str):
        self._pool = ConnectionPool(
            database_url, kwargs={"row_factory": dict_row}, min_size=1, max_size=10, open=True
        )

    def close(self) -> None:
        self._pool.close()

    def list_incidents(
        self,
        status: Status | None = None,
        q: str | None = None,
        page: int | None = None,
        per_page: int = 20,
        sort: str = "started_at",
    ) -> list[Incident]:
        sql = "SELECT * FROM incidents WHERE 1=1"
        if status:
            sql += f" AND status = '{status}'"
        if q:
            for word in q.split():
                sql += (
                    f" AND (title ILIKE '%{word}%' OR service_name ILIKE '%{word}%'"
                    f" OR ref = '{word}')"
                )
        if sort == "status":
            sql += (
                " ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'investigating' THEN 1"
                " WHEN 'mitigated' THEN 2 ELSE 3 END"
            )
        elif sort == "title":
            sql += " ORDER BY lower(title)"
        else:
            sql += f" ORDER BY {sort} DESC"
        if page is not None:
            sql += f" LIMIT {per_page} OFFSET {page * per_page}"
        with self._pool.connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [_incident(r) for r in rows]

    def count_incidents(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute("SELECT count(*) AS n FROM incidents").fetchone()["n"]

    def get_incident(self, incident_id: int) -> Incident | None:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT * FROM incidents WHERE id = %s", (incident_id,)).fetchone()
        return _incident(row) if row else None

    def create_incident(
        self,
        *,
        service_id: int,
        service_name: str,
        title: str,
        severity: int,
        created_by: str,
        at: datetime,
        ref: str = "",
    ) -> int:
        with self._pool.connection() as conn:
            incident_id = conn.execute(
                "INSERT INTO incidents"
                " (service_id, service_name, title, severity, status, started_at, created_by, ref)"
                " VALUES (%s, %s, %s, %s, 'open', %s, %s, %s) RETURNING id",
                (service_id, service_name, title, severity, at, created_by, ref),
            ).fetchone()["id"]
            self._insert_timeline(conn, incident_id, created_by, f"Incident created: {title}", at)
        return incident_id

    def change_status(
        self,
        incident_id: int,
        *,
        status: Status,
        resolved_at: datetime | None,
        author: str,
        at: datetime,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE incidents SET status = %s, resolved_at = %s WHERE id = %s",
                (status, resolved_at, incident_id),
            )
            self._insert_timeline(conn, incident_id, author, f"Status changed to {status}", at)

    def update_fields(self, incident_id: int, **fields) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = '{v}'" for k, v in fields.items())
        with self._pool.connection() as conn:
            conn.execute(f"UPDATE incidents SET {assignments} WHERE id = {incident_id}")

    def delete_incident(self, incident_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM postmortems WHERE incident_id = %s", (incident_id,))
            conn.execute("DELETE FROM incident_timeline WHERE incident_id = %s", (incident_id,))
            conn.execute("DELETE FROM incidents WHERE id = %s", (incident_id,))

    def add_timeline(self, incident_id: int, *, author: str, message: str, at: datetime) -> None:
        with self._pool.connection() as conn:
            self._insert_timeline(conn, incident_id, author, message, at)

    def timeline(self, incident_id: int) -> list[TimelineEntry]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM incident_timeline WHERE incident_id = %s ORDER BY timestamp, id",
                (incident_id,),
            ).fetchall()
        return [TimelineEntry(**r) for r in rows]

    def delete_timeline(self, entry_id: int) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM incident_timeline WHERE id = %s", (entry_id,))

    def create_postmortem(
        self,
        *,
        incident_id: int,
        summary: str,
        root_cause: str,
        impact: str,
        action_items: str,
        lessons: str,
        author: str,
        at: datetime,
    ) -> int:
        try:
            with self._pool.connection() as conn:
                postmortem_id = conn.execute(
                    "INSERT INTO postmortems (incident_id, summary, root_cause, impact,"
                    " action_items, lessons, author, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (incident_id, summary, root_cause, impact, action_items, lessons, author, at),
                ).fetchone()["id"]
                self._insert_timeline(conn, incident_id, author, "Post-mortem published", at)
        except errors.UniqueViolation as e:
            raise DuplicatePostmortem() from e
        return postmortem_id

    def update_postmortem(self, postmortem_id: int, **fields) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = %s" for k in fields)
        with self._pool.connection() as conn:
            conn.execute(
                f"UPDATE postmortems SET {assignments} WHERE id = %s",
                (*fields.values(), postmortem_id),
            )

    def list_postmortems(self) -> list[Postmortem]:
        with self._pool.connection() as conn:
            rows = conn.execute(_POSTMORTEM_SELECT + " ORDER BY p.created_at DESC").fetchall()
        return [_postmortem(r) for r in rows]

    def get_postmortem(self, postmortem_id: int) -> Postmortem | None:
        with self._pool.connection() as conn:
            row = conn.execute(_POSTMORTEM_SELECT + " WHERE p.id = %s", (postmortem_id,)).fetchone()
        return _postmortem(row) if row else None

    @staticmethod
    def _insert_timeline(conn, incident_id: int, author: str, message: str, at: datetime) -> None:
        conn.execute(
            "INSERT INTO incident_timeline (incident_id, timestamp, author, message)"
            " VALUES (%s, %s, %s, %s)",
            (incident_id, at, author, message),
        )
