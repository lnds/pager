// Punto de entrada de notifications con trazas de OpenTelemetry. Reemplaza al
// main.go del servicio: el resto del código es el mismo.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

// traceContext lee la cabecera traceparent aunque traiga indicadores que esta
// versión de la biblioteca no conoce. Los SDK recientes marcan además del bit
// «sampled» el de identificador aleatorio (indicadores 03), y la biblioteca
// descarta la cabecera completa: aquí se conserva solo el bit «sampled».
type traceContext struct{ propagation.TraceContext }

func (p traceContext) Extract(ctx context.Context, carrier propagation.TextMapCarrier) context.Context {
	header := carrier.Get("traceparent")
	if len(header) == 55 && strings.HasPrefix(header, "00-") {
		if flags, err := strconv.ParseUint(header[53:], 16, 8); err == nil && flags > 1 {
			carrier = propagation.MapCarrier{
				"traceparent": fmt.Sprintf("%s%02x", header[:53], flags&1),
				"tracestate":  carrier.Get("tracestate"),
			}
		}
	}
	return p.TraceContext.Extract(ctx, carrier)
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// El destino y el nombre del servicio salen de OTEL_EXPORTER_OTLP_ENDPOINT
	// y OTEL_SERVICE_NAME.
	ctx := context.Background()
	exporter, err := otlptracehttp.New(ctx)
	if err != nil {
		logger.Error("otel_exporter_failed", "error", err)
		os.Exit(1)
	}
	provider := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exporter))
	defer func() { _ = provider.Shutdown(ctx) }()
	otel.SetTracerProvider(provider)
	otel.SetTextMapPropagator(traceContext{})

	srv := otelhttp.NewHandler(NewServer(NewStore(), logger), "notifications",
		otelhttp.WithSpanNameFormatter(func(_ string, r *http.Request) string {
			return r.Method + " " + r.URL.Path
		}))
	logger.Info("notifications_listening", "port", port, "api_key", apiKey())
	if err := http.ListenAndServe(":"+port, srv); err != nil {
		logger.Error("server_stopped", "error", err)
		os.Exit(1)
	}
}
