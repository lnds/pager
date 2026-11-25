"""Punto de entrada de incidents con trazas de OpenTelemetry.

Configura el envío de trazas, instrumenta httpx y psycopg, y después carga la
aplicación del servicio tal como está. El destino y el nombre del servicio
salen de OTEL_EXPORTER_OTLP_ENDPOINT y OTEL_SERVICE_NAME.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

# Antes de cargar el servicio, para que sus clientes y su pool ya salgan instrumentados.
HTTPXClientInstrumentor().instrument()
PsycopgInstrumentor().instrument()

from incidents.main import app  # noqa: E402

# Sin los spans de envío y recepción de cada respuesta, que solo agregan ruido.
FastAPIInstrumentor.instrument_app(app, exclude_spans=["receive", "send"])
