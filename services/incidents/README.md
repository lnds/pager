# incidents

Incidentes, bitácora, post-mortems e interfaz web de Pager. Python 3.12 con
[FastAPI](https://fastapi.tiangolo.com), [psycopg 3](https://www.psycopg.org/psycopg3/) y
[httpx](https://www.python-httpx.org). El contrato de la API está en
[`docs/arquitectura.md`](../../docs/arquitectura.md).

## Comandos

```bash
uv sync                       # dependencias
uv run pytest                 # pruebas, sin base de datos
uv run ruff check .           # lint
uv run ruff format .          # formato
```

Para correr el servicio fuera de Docker, levanta el resto del entorno desde la raíz del repo y
apunta las variables a él:

```bash
docker compose up -d incidents-migrations catalog notifications
DATABASE_URL=postgresql://pager:pager@localhost:5433/incidents \
CATALOG_URL=http://localhost:8081 \
NOTIFICATIONS_URL=http://localhost:8082 \
uv run uvicorn incidents.main:app --reload --port 8080
```

## Estructura

| Archivo | Qué hace |
|---|---|
| `src/incidents/domain.py` | Reglas del incidente: estados, transiciones, severidad. Sin I/O. |
| `src/incidents/api.py` | Rutas HTTP. `create_app` recibe repositorio, clientes y reloj. |
| `src/incidents/admin.py` | Rutas de operación bajo `/admin`. |
| `src/incidents/notifier.py` | Avisos a quien está de guardia. |
| `src/incidents/config.py` | Configuración leída del environment. |
| `src/incidents/repository.py` | El contrato del repositorio y su implementación en PostgreSQL. |
| `src/incidents/memory.py` | Implementación en memoria que usan las pruebas. |
| `src/incidents/clients.py` | Clientes HTTP de catalog y notifications. |
| `src/incidents/main.py` | Punto de entrada: lee el environment y arma la aplicación. |
| `src/incidents/static/` | Interfaz web. |
| `migrations/` | Esquema de la base, en SQL plano para Flyway. |
