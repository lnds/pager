"""Carga datos de ejemplo en un entorno recién levantado.

Crea tres servicios con su turno de guardia y abre varios incidentes, que
recorren la cadena completa: incidents → catalog (turno vigente) → notifications.
Algunos incidentes avanzan de estado y uno termina con su post-mortem.

Uso: python scripts/seed.py
Solo usa la biblioteca estándar, así que corre igual en macOS, Linux y Windows.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

INCIDENTS = os.environ.get("INCIDENTS_URL", "http://localhost:8080")
CATALOG = os.environ.get("CATALOG_URL", "http://localhost:8081")

SERVICES = [
    ("checkout", "payments", 99.95, "Ana Soto", "ana@example.com"),
    ("search", "discovery", 99.9, "Bruno Díaz", "bruno@example.com"),
    ("notificaciones-push", "engagement", 99.5, "Carla Rojas", "carla@example.com"),
]

INCIDENTS_DATA = [
    # (servicio, título, severidad, creado por, estados por los que pasa, notas)
    ("checkout", "Latencia alta en checkout", 2, "ana", [], []),
    (
        "search",
        "Resultados vacíos para búsquedas con tildes",
        3,
        "bruno",
        ["investigating"],
        ["Reproducido con «canción»; el analizador no normaliza."],
    ),
    (
        "checkout",
        "Errores 502 al confirmar el pago",
        1,
        "ana",
        ["investigating", "mitigated", "resolved"],
        ["Rollback del despliegue 4.12.0", "Tasa de error normal desde las 22:40"],
    ),
    (
        "notificaciones-push",
        "Push duplicados en Android",
        4,
        "carla",
        ["investigating", "mitigated"],
        [],
    ),
]

POSTMORTEM = {
    "summary": "El pago falló para parte de los clientes durante 40 minutos.",
    "root_cause": "El despliegue 4.12.0 redujo el pool de conexiones al proveedor de pagos.",
    "impact": "Cerca del 8% de las compras terminó en error 502.",
    "action_items": "Alarma sobre el pool; prueba de carga antes de cada despliegue.",
    "lessons": "Los cambios de configuración también pasan por revisión.",
    "author": "ana",
}


def request(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        return {"status": e.code, **json.load(e)}


def post(url: str, body: dict) -> dict:
    return request("POST", url, body)


def patch(url: str, body: dict) -> dict:
    return request("PATCH", url, body)


def main() -> int:
    start = date.today() - timedelta(days=7)
    end = date.today() + timedelta(days=30)
    service_ids = {}

    try:
        for name, team, slo, person, email in SERVICES:
            service = post(f"{CATALOG}/services", {"name": name, "team": team, "slo_target": slo})
            print(f"servicio {name}: {service}")
            if "id" not in service:
                continue
            service_ids[name] = service["id"]
            shift = post(
                f"{CATALOG}/shifts",
                {
                    "service_id": service["id"],
                    "person": person,
                    "email": email,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
            )
            print(f"  turno de {person}: {shift}")

        for service, title, severity, author, statuses, notes in INCIDENTS_DATA:
            if service not in service_ids:
                print(f"incidente «{title}»: el servicio {service} no existe, se omite")
                continue
            incident = post(
                f"{INCIDENTS}/incidents",
                {
                    "service_id": service_ids[service],
                    "title": title,
                    "severity": severity,
                    "created_by": author,
                },
            )
            print(f"incidente: {incident}")
            if "id" not in incident:
                continue
            for status in statuses:
                patch(
                    f"{INCIDENTS}/incidents/{incident['id']}",
                    {"status": status, "author": author},
                )
            for note in notes:
                patch(
                    f"{INCIDENTS}/incidents/{incident['id']}",
                    {"message": note, "author": author},
                )
            if statuses and statuses[-1] == "resolved":
                postmortem = post(
                    f"{INCIDENTS}/postmortems", {"incident_id": incident["id"], **POSTMORTEM}
                )
                print(f"  post-mortem: {postmortem}")
    except urllib.error.URLError as e:
        print(f"No pude conectarme ({e.reason}). ¿Está levantado el entorno?", file=sys.stderr)
        return 1

    print(f"\nListo. Abre {INCIDENTS} en el navegador.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
