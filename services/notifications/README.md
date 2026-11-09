# notifications

Servicio de avisos de Pager, en Go con la biblioteca estándar. Recibe el pedido de avisar a quien
está de guardia, lo registra en su log como JSON y guarda los últimos 100 avisos en memoria. No
tiene base de datos ni proveedor real de correo. Los avisos urgentes salen además por webhook
cuando hay uno configurado (`WEBHOOK_URL`) o cuando el pedido trae `webhook_url`.

El contrato de la API está en [`docs/arquitectura.md`](../../docs/arquitectura.md).

## Comandos

```bash
go run .          # levanta el servicio en el puerto 8080 (o en $PORT)
go test ./...     # pruebas
go vet ./...      # análisis estático
```

Para probarlo a mano:

```bash
curl -X POST localhost:8082/notify \
  -H 'Content-Type: application/json' \
  -H 'X-Api-Key: pgr_live_7f3a9c2e81b44d0f9a6e5c1b2d8f4a70' \
  -d '{"person":"Ana Soto","email":"ana@example.com","message":"[SEV2] Latencia alta en checkout"}'
curl localhost:8082/notifications
```
