"""Carga para Pager: lo que hace una persona de guardia durante su turno.

Casi todo el tiempo mira el panel. Cada tanto abre un incidente, lo reconoce,
deja notas, lo mitiga y lo resuelve; si fue grave, escribe el post-mortem.
Abrir el incidente recorre los tres servicios: incidents valida el servicio en
catalog, busca el turno vigente y le pide a notifications que avise.
"""

import random

from locust import HttpUser, between, task

PEOPLE = ["ana", "bruno", "carla", "diego", "elisa"]

TITLES = [
    "Errores 502 al confirmar el pago",
    "Latencia alta en checkout",
    "Resultados vacíos en la búsqueda",
    "Push duplicados en Android",
    "Cola de correos atrasada",
    "Timeouts contra el proveedor de pagos",
]

NOTES = [
    "Reproducido en producción; reviso el último despliegue.",
    "La tasa de error sube desde las 10:40.",
    "Rollback del último despliegue en curso.",
    "El proveedor confirma degradación de su lado.",
]


class PersonaDeGuardia(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.person = random.choice(PEOPLE)
        response = self.client.get("/catalog/services")
        services = response.json() if response.ok else []
        self.service_ids = [service["id"] for service in services]

    def update(self, incident_id: int, step: str, **fields):
        """Un cambio sobre el incidente; el nombre agrupa la ruta en las estadísticas."""
        return self.client.patch(
            f"/incidents/{incident_id}",
            json={"author": self.person, **fields},
            name=f"/incidents/[id] ({step})",
        )

    @task(6)
    def mirar_el_panel(self):
        self.client.get("/incidents")
        self.client.get("/incidents/summary")

    @task(2)
    def revisar_un_incidente(self):
        incidents = self.client.get("/incidents?status=open", name="/incidents?status=open").json()
        if incidents:
            incident = random.choice(incidents)
            self.client.get(f"/incidents/{incident['id']}", name="/incidents/[id]")

    @task(1)
    def leer_postmortems(self):
        self.client.get("/postmortems")

    @task(3)
    def atender_un_incidente(self):
        if not self.service_ids:
            return
        severity = random.choices([1, 2, 3, 4], weights=[1, 3, 4, 2])[0]
        created = self.client.post(
            "/incidents",
            json={
                "title": random.choice(TITLES),
                "service_id": random.choice(self.service_ids),
                "severity": severity,
                "created_by": self.person,
            },
        )
        if created.status_code != 201:
            return
        incident_id = created.json()["id"]

        self.wait()
        self.update(incident_id, "reconocer", status="investigating", message="Lo tengo, reviso.")
        self.client.get(f"/incidents/{incident_id}", name="/incidents/[id]")

        self.wait()
        self.update(incident_id, "nota", message=random.choice(NOTES))

        self.wait()
        self.update(incident_id, "mitigar", status="mitigated")

        self.wait()
        self.update(incident_id, "resolver", status="resolved", message="Servicio normal.")

        if severity <= 2:
            self.client.post(
                "/postmortems",
                json={
                    "incident_id": incident_id,
                    "summary": "El servicio estuvo degradado para parte de los clientes.",
                    "root_cause": "Un cambio de configuración redujo la capacidad.",
                    "impact": "Errores y demoras durante el incidente.",
                    "action_items": "Alarma sobre la capacidad; prueba de carga antes de desplegar.",
                    "author": self.person,
                },
            )
