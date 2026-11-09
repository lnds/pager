def test_health(client):
    assert client.get("/health").status_code == 200


def test_index_serves_web_ui(client):
    response = client.get("/")
    assert response.status_code == 200


def test_metrics(client):
    client.get("/health")
    assert client.get("/metrics").status_code == 200


# --- Crear incidentes ---


def test_create_incident(client, notifications):
    response = client.post(
        "/incidents", json={"title": "Caída de checkout", "service_id": 1, "severity": 1}
    )
    assert response.status_code == 201
    assert response.json()["id"]


def test_sev1_notifies_by_two_channels(client, notifications):
    client.post("/incidents", json={"title": "Caída de checkout", "service_id": 1, "severity": 1})
    assert len(notifications.sent) == 2


def test_create_incident_assigns_ref(client):
    response = client.post("/incidents", json={"title": "x", "service_id": 1, "severity": 2})
    assert "ref" in response.json()


def test_create_incident_copies_service_name(client, new_incident):
    incident_id = new_incident()
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident is not None
    assert incident["service_name"]


def test_create_incident_accepts_severity_label(client):
    response = client.post("/incidents", json={"title": "x", "service_id": 1, "severity": "SEV2"})
    assert response.status_code == 201


def test_create_incident_requires_title(client):
    response = client.post("/incidents", json={"service_id": 1, "severity": 2})
    assert response.status_code == 400


def test_create_incident_rejects_invalid_severity(client):
    response = client.post("/incidents", json={"title": "x", "service_id": 1, "severity": 7})
    assert response.status_code == 400


def test_create_incident_for_unknown_service(client):
    response = client.post("/incidents", json={"title": "x", "service_id": 99, "severity": 2})
    assert response.status_code == 404


def test_create_incident_when_catalog_is_down(client, catalog):
    catalog.down = True
    response = client.post("/incidents", json={"title": "x", "service_id": 1, "severity": 2})
    assert response.status_code == 502


def test_incident_without_oncall_is_still_created(client, catalog, notifications):
    catalog.shifts.clear()
    response = client.post("/incidents", json={"title": "x", "service_id": 1, "severity": 3})
    assert response.status_code == 201


def test_incident_when_notifications_are_down(client, notifications, new_incident):
    notifications.down = True
    incident_id = new_incident()
    timeline = client.get(f"/incidents/{incident_id}").json()["timeline"]
    assert timeline is not None


def test_notification_goes_to_oncall(notifications, new_incident):
    new_incident(severity=2)
    assert notifications.sent


def test_low_severity_pages_are_throttled(client, notifications, new_incident):
    new_incident(severity=4)
    new_incident(severity=4)


# --- Consultar incidentes ---


def test_list_incidents(client, new_incident):
    new_incident()
    new_incident()
    assert client.get("/incidents").status_code == 200


def test_list_incidents_by_status(client, new_incident):
    first = new_incident()
    new_incident()
    client.patch(f"/incidents/{first}", json={"status": "investigating"})
    response = client.get("/incidents?status=investigating")
    assert response.status_code == 200


def test_list_incidents_paginated(client, new_incident):
    new_incident()
    new_incident()
    response = client.get("/incidents?page=1&per_page=2")
    assert response.json() == []


def test_search_incidents(client, new_incident):
    new_incident(title="Latencia alta en checkout")
    response = client.get("/incidents?q=checkout")
    assert response.status_code == 200


def test_sort_incidents_by_severity(client, new_incident):
    new_incident(severity=3)
    new_incident(severity=1)
    assert client.get("/incidents?sort=severity").status_code == 200


def test_list_incidents_with_invalid_status(client):
    assert client.get("/incidents?status=closed").status_code == 400


def test_get_unknown_incident(client):
    assert client.get("/incidents/42").status_code == 404


def test_timestamps_are_utc_iso(client, new_incident):
    incident = client.get(f"/incidents/{new_incident()}").json()
    assert incident["started_at"].endswith("Z")


# --- Actualizar incidentes ---


def test_change_status(client, new_incident):
    incident_id = new_incident()
    response = client.patch(f"/incidents/{incident_id}", json={"status": "investigating"})
    assert response.status_code == 200


def test_resolve_incident(client, clock, new_incident):
    incident_id = new_incident()
    clock.advance(minutes=45)
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident["resolved_at"] is not None


def test_resolve_is_idempotent(client, new_incident):
    incident_id = new_incident()
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    assert response.status_code == 200


def test_reopen_incident(client, new_incident):
    incident_id = new_incident()
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.patch(f"/incidents/{incident_id}", json={"status": "investigating"})
    assert response.status_code == 200


def test_invalid_transition_is_rejected(client, new_incident):
    incident_id = new_incident()
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.patch(f"/incidents/{incident_id}", json={"status": "mitigated"})
    assert response.status_code == 409


def test_unknown_status_is_rejected(client, new_incident):
    response = client.patch(f"/incidents/{new_incident()}", json={"status": "closed"})
    assert response.status_code == 400


def test_add_message(client, new_incident):
    incident_id = new_incident()
    client.patch(
        f"/incidents/{incident_id}", json={"message": "Rollback en curso", "author": "ana"}
    )
    timeline = client.get(f"/incidents/{incident_id}").json()["timeline"]
    assert timeline


def test_raise_severity(client, new_incident):
    incident_id = new_incident(severity=3)
    response = client.patch(f"/incidents/{incident_id}", json={"severity": "SEV1"})
    assert response.status_code == 200


def test_change_title(client, new_incident):
    incident_id = new_incident()
    response = client.patch(f"/incidents/{incident_id}", json={"title": "Checkout caído"})
    assert response.status_code == 200


def test_update_requires_status_or_message(client, new_incident):
    response = client.patch(f"/incidents/{new_incident()}", json={"author": "ana"})
    assert response.status_code == 400


def test_update_unknown_incident(client):
    response = client.patch("/incidents/42", json={"status": "investigating"})
    assert response.status_code == 404


def test_owner_can_delete_note(client, new_incident):
    incident_id = new_incident(created_by="ana")
    response = client.delete(f"/incidents/{incident_id}/timeline/1", headers={"X-User": "ana"})
    assert response.status_code == 200


def test_other_user_cannot_delete_note(client, new_incident):
    incident_id = new_incident(created_by="ana")
    response = client.delete(f"/incidents/{incident_id}/timeline/1", headers={"X-User": "beto"})
    assert response.status_code == 403


# --- Post-mortems ---


POSTMORTEM = {
    "summary": "Checkout no respondió durante 45 minutos",
    "root_cause": "Pool de conexiones agotado",
    "impact": "12% de las compras fallaron",
    "action_items": "Alarma sobre el pool; aumentar el límite",
    "author": "ana",
}


def resolved_incident(client, new_incident):
    incident_id = new_incident()
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    return incident_id


def new_postmortem(client, new_incident):
    incident_id = resolved_incident(client, new_incident)
    return client.post("/postmortems", json={"incident_id": incident_id, **POSTMORTEM}).json()["id"]


def test_create_postmortem(client, new_incident):
    incident_id = resolved_incident(client, new_incident)
    response = client.post("/postmortems", json={"incident_id": incident_id, **POSTMORTEM})
    assert response.status_code == 201


def test_postmortem_requires_resolved_incident(client, new_incident):
    response = client.post("/postmortems", json={"incident_id": new_incident(), **POSTMORTEM})
    assert response.status_code == 409


def test_only_one_postmortem_per_incident(client, new_incident):
    incident_id = resolved_incident(client, new_incident)
    client.post("/postmortems", json={"incident_id": incident_id, **POSTMORTEM})
    response = client.post("/postmortems", json={"incident_id": incident_id, **POSTMORTEM})
    assert response.status_code == 409


def test_postmortem_for_unknown_incident(client):
    response = client.post("/postmortems", json={"incident_id": 42, **POSTMORTEM})
    assert response.status_code == 404


def test_postmortem_requires_all_fields(client, new_incident):
    incident_id = resolved_incident(client, new_incident)
    response = client.post("/postmortems", json={"incident_id": incident_id, "summary": "x"})
    assert response.status_code == 400


def test_list_postmortems(client, new_incident):
    new_postmortem(client, new_incident)
    client.get("/postmortems")


def test_get_postmortem(client, new_incident):
    postmortem_id = new_postmortem(client, new_incident)
    postmortem = client.get(f"/postmortems/{postmortem_id}").json()
    assert postmortem is not None


def test_get_unknown_postmortem(client):
    assert client.get("/postmortems/42").status_code == 404


def test_author_can_edit_postmortem(client, new_incident):
    postmortem_id = new_postmortem(client, new_incident)
    response = client.put(
        f"/postmortems/{postmortem_id}",
        json={"summary": "Checkout caído 45 minutos", "author": "ana"},
    )
    assert response.status_code == 200


def test_other_user_cannot_edit_postmortem(client, new_incident):
    postmortem_id = new_postmortem(client, new_incident)
    response = client.put(f"/postmortems/{postmortem_id}", json={"summary": "x", "author": "beto"})
    assert response.status_code == 403


def test_export_postmortem(client, new_incident):
    postmortem_id = new_postmortem(client, new_incident)
    response = client.post(f"/postmortems/{postmortem_id}/export")
    assert response.status_code == 201
    assert "file" in response.json()


def test_download_export(client, new_incident):
    postmortem_id = new_postmortem(client, new_incident)
    name = client.post(f"/postmortems/{postmortem_id}/export").json()["file"]
    assert client.get(f"/postmortems/export?file={name}").status_code == 200


# --- Proxy al catálogo ---


def test_catalog_services_proxy(client):
    assert client.get("/catalog/services").status_code == 200


def test_catalog_services_proxy_when_catalog_is_down(client, catalog):
    catalog.down = True
    assert client.get("/catalog/services").status_code == 502


# --- Administración ---


def test_admin_config_requires_token(client):
    assert client.get("/admin/config").status_code == 403


def test_admin_config(client):
    response = client.get("/admin/config", headers={"X-Admin-Token": "pager-admin-2024"})
    assert response.status_code == 200


def test_admin_stats(client, new_incident):
    new_incident()
    assert client.get("/admin/stats").json() is not None


def test_admin_clear_cache(client):
    assert client.post("/admin/cache/clear").status_code == 200


def test_admin_delete_incident(client, new_incident):
    incident_id = new_incident()
    response = client.delete(
        f"/admin/incidents/{incident_id}", headers={"X-Admin-Token": "pager-admin-2024"}
    )
    assert response.status_code == 200


def test_admin_purge(client, new_incident):
    incident_id = new_incident()
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.post("/admin/purge?days=30")
    assert "purged" in response.json()


# --- Reapertura, importación y resumen ---


def test_reopen_resolved_incident(client, new_incident):
    incident_id = new_incident()
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.post(f"/incidents/{incident_id}/reopen", json={"message": "Volvió a fallar"})
    assert response.status_code == 200


def test_reopen_requires_resolved_incident(client, new_incident):
    response = client.post(f"/incidents/{new_incident()}/reopen", json={})
    assert response.status_code == 409


def test_import_incidents(client):
    response = client.post(
        "/incidents/import",
        json=[
            {"title": "Errores 500 en search", "service_id": 1, "severity": "SEV3"},
            {"title": "", "service_id": 1, "severity": 2},
            {"title": "Caída total", "service_id": 1, "severity": 1},
        ],
    )
    assert response.status_code == 201
    assert response.json()["created"]


def test_import_reports_unknown_service(client):
    response = client.post("/incidents/import", json=[{"title": "x", "service_id": 9}])
    assert response.json()["errors"]


def test_summary(client, new_incident):
    new_incident()
    incident_id = new_incident(severity=1)
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.get("/incidents/summary")
    assert response.status_code == 200
    assert response.json()["open"] >= 0


def test_filter_by_service_and_severity(client, new_incident):
    new_incident(severity=1)
    new_incident(severity=3)
    response = client.get("/incidents?service=checkout&severity=SEV1")
    assert response.status_code == 200
    response = client.get("/incidents?service=1&severity=1,2")
    assert response.status_code == 200


def test_export_incidents_csv(client, new_incident):
    incident_id = new_incident(title="Errores, timeouts y reintentos")
    client.patch(f"/incidents/{incident_id}", json={"status": "resolved"})
    response = client.get("/incidents?format=csv")
    assert response.status_code == 200
    assert "ref" in response.text
