// Trazas de OpenTelemetry para catalog. Se carga antes que el servicio con
// `node --import`, así que el código del servicio no cambia. El destino y el
// nombre del servicio salen de OTEL_EXPORTER_OTLP_ENDPOINT y OTEL_SERVICE_NAME.
import { createRequire } from "node:module";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { NodeSDK } from "@opentelemetry/sdk-node";

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter(),
  instrumentations: [
    new HttpInstrumentation({
      // El nombre del span es la ruta con los identificadores reemplazados.
      requestHook: (span, request) => {
        if (request.url !== undefined) {
          const path = request.url.split("?")[0].replace(/\/\d+/g, "/{id}");
          span.updateName(`${request.method} ${path}`);
        }
      },
    }),
  ],
});
sdk.start();

// La instrumentación se aplica cuando el módulo se carga con require.
createRequire(import.meta.url)("node:http");

process.on("SIGTERM", () => void sdk.shutdown());
