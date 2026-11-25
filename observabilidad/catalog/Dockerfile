# catalog con trazas de OpenTelemetry, sin tocar su código: la imagen es la del
# servicio más los paquetes de OpenTelemetry, y Node carga tracing.mjs antes
# que el servicio.
# Contexto: services/catalog; los archivos de esta carpeta llegan como «obs».

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.build.json ./
COPY src/ ./src/
RUN npm run build && npm prune --omit=dev
RUN npm install --no-save --omit=dev --no-audit --no-fund \
    @opentelemetry/api@1.10.0 \
    @opentelemetry/sdk-node@0.301.2 \
    @opentelemetry/exporter-trace-otlp-proto@0.301.2 \
    @opentelemetry/instrumentation-http@0.301.2

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=obs tracing.mjs ./
USER node
EXPOSE 8080
CMD ["node", "--import", "./tracing.mjs", "dist/server.js"]
