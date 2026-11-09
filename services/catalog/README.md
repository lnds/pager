# catalog

El catálogo de servicios y los turnos de guardia. TypeScript sobre Node 22, con
[Hono](https://hono.dev), [`postgres`](https://github.com/porsager/postgres) y
[zod](https://zod.dev). El contrato de la API está en
[`docs/arquitectura.md`](../../docs/arquitectura.md).

## Comandos

```bash
npm install          # dependencias
npm test             # pruebas (vitest), sin base de datos
npm run typecheck    # tipos
npm run build        # compila a dist/
npm run dev          # servidor con recarga; necesita DATABASE_URL
```

Para correr el servicio fuera de Docker, levanta solo la base y sus migraciones
desde la raíz del repo y apunta `DATABASE_URL` a ella:

```bash
docker compose up -d catalog-migrations
DATABASE_URL=postgres://pager:pager@localhost:5434/catalog npm run dev
```

## Estructura

| Archivo | Qué hace |
|---|---|
| `src/app.ts` | Rutas y validación. Recibe el repositorio por parámetro. |
| `src/shifts.ts` | Reglas puras de los turnos: cuál está vigente en un día. |
| `src/repository.ts` | La interfaz del repositorio y su implementación en Postgres. |
| `src/memory-repository.ts` | Implementación en memoria que usan las pruebas. |
| `src/server.ts` | Punto de entrada: lee el environment y levanta el servidor. |
| `migrations/` | Esquema de la base, en SQL plano para Flyway. |
