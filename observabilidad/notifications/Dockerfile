# notifications con trazas de OpenTelemetry: el código del servicio con el
# main.go de esta carpeta, que envuelve el servidor HTTP. Go no tiene
# instrumentación automática, así que aquí sí hay código.
# Contexto: services/notifications; los archivos de esta carpeta llegan como «obs».

FROM golang:1.23-alpine AS builder
WORKDIR /src
COPY --from=obs go.mod go.sum ./
RUN go mod download
COPY server.go store.go ./
COPY --from=obs main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/notifications .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/notifications /notifications
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/notifications"]
