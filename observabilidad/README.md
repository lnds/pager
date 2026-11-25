# Observabilidad

Pager con trazas, métricas, tablero y carga, sin cambiar el código de los servicios ni el
`compose.yaml` normal. Todo lo de esta carpeta se usa con
[`compose.observabilidad.yaml`](../compose.observabilidad.yaml), encima del `compose.yaml` y con
otro nombre de proyecto (`pager-obs`), así que tiene sus propios contenedores y datos.

```bash
./observabilidad/obs construir   # construye y descarga las imágenes (lo único que necesita red)
./observabilidad/obs iniciar     # levanta todo y carga los datos de ejemplo
./observabilidad/obs abrir       # Locust, Grafana y Jaeger en el navegador
./observabilidad/obs estado      # contenedores, direcciones y si llegan trazas
./observabilidad/obs carga 60    # la misma carga, sin la interfaz de Locust
./observabilidad/obs limpiar     # baja todo y borra los datos
```

Usa los mismos puertos que el entorno normal (`8080` a `8082`, `5433` y `5434`): los dos no pueden
estar arriba a la vez.

| Qué | Dónde |
|---|---|
| Pager | <http://localhost:8080> |
| Locust | <http://localhost:8089> |
| Grafana, con el tablero «Pager: señales de oro» | <http://localhost:3000> |
| Jaeger | <http://localhost:16686> |
| Prometheus | <http://localhost:9090> |

## Cómo está armado

```
 Locust ──► incidents ──► catalog          los tres mandan sus trazas por OTLP
                │                                        │
                └───────► notifications                  ▼
                                              OpenTelemetry Collector
                                                │                 │
                                             trazas     métricas calculadas con las
                                                │      trazas + CPU y memoria de los
                                                ▼            contenedores
                                             Jaeger               │
                                                                  ▼
                                               Grafana ◄──── Prometheus
```

Las señales de oro salen de las trazas: el Collector cuenta los spans de cada servicio y mide
su duración (conector `spanmetrics`), así que tráfico, errores y latencia se calculan igual para
los tres servicios, sin que cada uno publique sus propias métricas. La saturación es el uso de
CPU y memoria de cada contenedor, que el Collector lee de Docker. Prometheus lee además el
`/metrics` que `incidents` ya publicaba.

## Qué se le agrega a cada servicio

| Servicio | Cómo se instrumenta | Dónde |
|---|---|---|
| `incidents` (Python) | Sin tocar el servicio: la imagen suma los paquetes de OpenTelemetry y el proceso arranca desde `otel_main.py`, que instrumenta FastAPI, httpx y psycopg y después carga la aplicación | [`incidents/`](incidents) |
| `catalog` (TypeScript) | Sin tocar el servicio: Node carga `tracing.mjs` antes que el servidor (`node --import`) | [`catalog/`](catalog) |
| `notifications` (Go) | Con código: un `main.go` que envuelve el servidor HTTP con `otelhttp`. Go no tiene instrumentación automática | [`notifications/`](notifications) |

El contexto de la traza viaja entre servicios en la cabecera `traceparent` (W3C Trace Context).
Las llamadas de `catalog` a su base no aparecen en las trazas: su cliente de PostgreSQL no tiene
instrumentación de OpenTelemetry.

## La carga

[`locust/locustfile.py`](locust/locustfile.py) simula a una persona de guardia: mira el panel,
revisa incidentes y, cada tanto, atiende uno de punta a punta (lo abre, lo reconoce, deja notas,
lo mitiga, lo resuelve y, si fue grave, escribe el post-mortem). Abrir un incidente recorre los
tres servicios.
