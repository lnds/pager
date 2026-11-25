# incidents con trazas de OpenTelemetry, sin tocar su código: la imagen es la
# del servicio más los paquetes de OpenTelemetry, y el proceso arranca desde
# otel_main.py, que configura las trazas y después carga la aplicación.
# Contexto: services/incidents; los archivos de esta carpeta llegan como «obs».

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev
COPY --from=obs requirements.txt /tmp/otel.txt
RUN uv pip install --python .venv/bin/python -r /tmp/otel.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
COPY --from=obs otel_main.py ./
USER nobody
EXPOSE 8080
CMD ["uvicorn", "otel_main:app", "--host", "0.0.0.0", "--port", "8080"]
