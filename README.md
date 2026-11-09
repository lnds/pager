# Pager

> [!WARNING]
> **Código deliberadamente inseguro y de mala calidad, con fines didácticos.** Este repositorio
> simula un sistema heredado que creció rápido y sin revisión: tiene defectos de diseño, errores y
> vulnerabilidades puestos a propósito para trabajarlos en clases. **No lo despliegues** ni lo
> expongas a internet, y no reutilices su código ni sus credenciales en otros proyectos.

> **Repositorio plantilla para los cursos de [Eduardo Díaz](https://ediaz.dev).** Es el proyecto
> sobre el que se trabaja en clases: crea tu copia con **Use this template** y trabaja en ella.

Plataforma de gestión de incidentes: registra los servicios en producción y sus turnos de
guardia, abre incidentes, avisa a quien está de guardia, sigue cada incidente hasta resolverlo y
guarda el post-mortem.

Son tres servicios en tres lenguajes, cada uno con sus pruebas:

| Servicio | Lenguaje | Qué hace |
|---|---|---|
| [`services/incidents`](services/incidents) | Python · FastAPI | Incidentes, bitácora, post-mortems e interfaz web |
| [`services/catalog`](services/catalog) | TypeScript · Hono | Catálogo de servicios y turnos de guardia |
| [`services/notifications`](services/notifications) | Go · `net/http` | Envío de avisos |

El detalle de la API está en [`docs/arquitectura.md`](docs/arquitectura.md) y las reglas del
negocio en [`docs/dominio.md`](docs/dominio.md). Lo pendiente está en [`BACKLOG.md`](BACKLOG.md).

## Cómo usar esta plantilla

1. En GitHub, **Use this template → Create a new repository**, en tu cuenta.
2. Clónalo y levántalo como se explica abajo.
3. Trabaja en ramas. Las specs que escribas van en `docs/specs/`.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) con Compose (Docker Desktop en macOS y Windows).
- Para correr las pruebas fuera de Docker: [uv](https://docs.astral.sh/uv/) (Python 3.12),
  Node 22 y Go 1.23.

## Levantar el entorno

```bash
docker compose up --build -d
python3 scripts/seed.py        # en Windows: python scripts\seed.py
```

Abre <http://localhost:8080>. El seed crea tres servicios con su turno de guardia y abre varios
incidentes, que recorren los tres servicios: incidents valida el servicio en catalog, busca quién
está de guardia y le pide a notifications que avise. Uno de ellos termina resuelto y con su
post-mortem.

| Qué | Dónde |
|---|---|
| Interfaz web y API de incidents | <http://localhost:8080> · documentación en `/docs` |
| API de catalog | <http://localhost:8081> |
| API de notifications | <http://localhost:8082/notifications> |
| PostgreSQL de incidents | `localhost:5433`, base `incidents`, usuario y clave `pager` |
| PostgreSQL de catalog | `localhost:5434`, base `catalog`, usuario y clave `pager` |

Para detenerlo: `docker compose down`. Para borrar también los datos: `docker compose down -v`.

## Pruebas

Cada servicio se prueba por separado y sin base de datos: las pruebas usan repositorios en
memoria y dobles de los otros servicios.

```bash
cd services/incidents && uv run pytest
cd services/catalog && npm install && npm test
cd services/notifications && go test ./...
```

Con `make` (macOS, Linux o WSL) hay atajos:

| Comando | Qué hace |
|---|---|
| `make up` / `make down` / `make reset` | Levanta, detiene o borra el entorno |
| `make seed` | Carga los datos de ejemplo |
| `make test` | Corre las pruebas de los tres servicios |
| `make lint` | ruff, tsc y go vet |
| `make check` | lint y pruebas: lo mismo que corre la CI |

La CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) corre lint y pruebas de cada
servicio y después levanta el entorno completo con Compose.

## Estructura

```
docs/                    arquitectura, dominio y specs
scripts/seed.py          datos de ejemplo
services/
  incidents/             Python
    src/incidents/       api.py · admin.py · notifier.py · domain.py · repository.py · memory.py
                         clients.py · config.py · static/
    migrations/          SQL de Flyway
    tests/
  catalog/               TypeScript
    src/                 app.ts · shifts.ts · domain.ts · repository.ts · memory-repository.ts
    migrations/
    tests/
  notifications/         Go
compose.yaml
```

Las migraciones se aplican solas al levantar el entorno. Para cambiar el esquema, agrega un
archivo `V<n>__<descripcion>.sql` nuevo; los que ya existen no se editan.
