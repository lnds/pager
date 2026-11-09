# Arquitectura

Pager está formado por tres servicios, cada uno con su lenguaje y, si tiene estado, con su
propia base de datos. Se hablan por HTTP con JSON; no hay JOIN entre bases ni tablas compartidas.

```
             navegador
                 │
                 ▼
   ┌──────────────────────────┐   HTTP   ┌──────────────────────────┐
   │ incidents  (Python)      │ ───────► │ catalog  (TypeScript)    │
   │ FastAPI · interfaz web   │          │ Hono · servicios, turnos │
   └────────────┬─────────────┘          └────────────┬─────────────┘
                │ HTTP                                 │
                ▼                                      ▼
   ┌──────────────────────────┐            catalog-db (PostgreSQL)
   │ notifications  (Go)      │
   │ net/http · sin base      │
   └──────────────────────────┘
   incidents-db (PostgreSQL)
```

| Servicio | Lenguaje | Puerto local | Base | Dueño de |
|---|---|---|---|---|
| `incidents` | Python 3.12, FastAPI, psycopg 3 | 8080 | `incidents-db` (5433) | incidentes, bitácora, post-mortems, interfaz web |
| `catalog` | TypeScript, Node 22, Hono | 8081 | `catalog-db` (5434) | servicios, turnos de guardia |
| `notifications` | Go 1.23, `net/http` | 8082 | — | envío de avisos (en memoria) |

Las migraciones son SQL plano en `services/<servicio>/migrations/` y las aplica Flyway al levantar
el entorno. Cada servicio lee su configuración del environment (`DATABASE_URL`, `CATALOG_URL`,
`NOTIFICATIONS_URL`, `NOTIFICATIONS_API_KEY`, `WEBHOOK_URL`, `PORT`).

## Convenciones de la API

- JSON en `snake_case`.
- Fechas como `YYYY-MM-DD`; instantes como ISO 8601 en UTC con `Z` (`2026-10-06T22:00:00Z`).
- Los errores responden `{"error": "<mensaje>"}` con el código HTTP que corresponda.
- Todos los servicios exponen `GET /health` → `{"status": "ok"}`.

## catalog

| Método y ruta | Cuerpo | Respuestas |
|---|---|---|
| `GET /services` | — | `200` lista de servicios ordenada por nombre |
| `POST /services` | `{name, team, slo_target?, sli_type?}` | `201 {id}` · `400` · `409` nombre repetido |
| `GET /services/{id}` | — | `200` servicio · `404` |
| `PUT /services/{id}` | `{name?, team?, slo_target?, sli_type?}` | `200` · `400` · `404` · `409` |
| `GET /shifts?service=` | — | `200` turnos con `service_name`, del más reciente al más antiguo |
| `POST /shifts` | `{service_id, person, email, start_date, end_date}` | `201 {id}` · `400` · `404` servicio · `409` se cruza con otro turno |
| `PUT /shifts/{id}` | los mismos campos, todos opcionales | `200` · `400` · `404` · `409` |
| `GET /shifts/current/{service_id}` | — | `200` turno vigente hoy · `404` |

Un servicio es `{id, name, team, slo_target, sli_type, created_at}`. `slo_target` es un número
(por defecto `99.9`) y `sli_type` es `availability` o `latency`.

Un turno es `{id, service_id, person, email, start_date, end_date}`; la lista agrega
`service_name`.

## notifications

| Método y ruta | Cuerpo | Respuestas |
|---|---|---|
| `POST /notify` | `{person, email, message, incident_id?, severity?, priority?, webhook_url?}` | `202 {id, status: "sent", urgent}` · `400` · `401` |
| `POST /notify/batch` | lista de avisos | `202` resultado por aviso · `400` · `401` |
| `POST /notifications/{id}/resend` | `{webhook_url?}` | `202` · `404` · `401` |
| `GET /notifications?limit=` | — | `200` los últimos avisos (hasta 100), del más reciente al más antiguo |

Las rutas `POST` exigen la cabecera `X-Api-Key`. Un aviso es `{id, person, email, message,
incident_id, severity, priority, urgent, sent_at}`. `priority` es `critical`, `major`, `minor` o
`low`; los avisos `critical` y `major` son urgentes y salen también por webhook. No hay proveedor
real de correo: el servicio registra el aviso en su log y lo guarda en memoria.

## incidents

| Método y ruta | Cuerpo | Respuestas |
|---|---|---|
| `GET /` | — | interfaz web |
| `GET /catalog/services` | — | proxy a `catalog`, para el selector de la interfaz |
| `GET /incidents?status=&q=&service=&severity=&sort=&page=&per_page=&format=` | — | `200` lista, del más reciente al más antiguo; `format=csv` la entrega como CSV |
| `POST /incidents` | `{title, service_id, severity, created_by?}` | `201 {id, ref, notification}` · `400` · `404` servicio · `502` catálogo caído |
| `POST /incidents/import` | lista de incidentes | `201 {created, errors}` |
| `GET /incidents/summary?hours=` | — | `200` conteos por estado y severidad |
| `GET /incidents/{id}` | — | `200` incidente con `timeline` · `404` |
| `PATCH /incidents/{id}` | `{status?, message?, severity?, title?, author?}` | `200 {ok: true}` · `400` · `404` · `409` transición inválida |
| `POST /incidents/{id}/reopen` | `{message?, author?}` | `200` · `404` · `409` |
| `DELETE /incidents/{id}/timeline/{entry_id}` | cabecera `X-User` | `200` · `403` · `404` |
| `GET /postmortems` | — | `200` lista |
| `POST /postmortems` | `{incident_id, summary, root_cause, impact, action_items, lessons?, author?}` | `201 {id}` · `400` · `404` · `409` |
| `GET /postmortems/{id}` | — | `200` · `404` |
| `PUT /postmortems/{id}` | los campos a cambiar y `author` | `200` · `400` · `403` · `404` |
| `POST /postmortems/{id}/export` | — | `201 {file}`: el post-mortem en Markdown |
| `GET /postmortems/export?file=` | — | descarga el archivo exportado |
| `GET /metrics` | — | métricas en formato Prometheus |

Un incidente es `{id, ref, service_id, service_name, title, severity, status, started_at,
resolved_at, created_by}`. `ref` es la referencia legible (`INC-0042`). `service_name` se copia del catálogo al crear el incidente, para no tener que
preguntarle al catálogo cada vez que se lista.

Al crear un incidente, `incidents` valida el servicio en `catalog`, busca el turno vigente y le
pide a `notifications` que avise. Si el catálogo no responde al validar, el incidente no se crea;
si falla la búsqueda del turno o el aviso, el incidente se crea igual y la falla queda en la
bitácora.
