import { serve } from "@hono/node-server";
import postgres from "postgres";
import { createApp } from "./app.js";
import { PostgresCatalogRepository } from "./repository.js";

const databaseUrl = process.env.DATABASE_URL ?? "postgres://pager:pager@localhost:5434/catalog";

const port = Number(process.env.PORT ?? 8080);
const sql = postgres(databaseUrl);
const app = createApp(new PostgresCatalogRepository(sql));

const server = serve({ fetch: app.fetch, port }, (info) => {
  console.log(`catalog listening on :${info.port}`);
});

function shutdown() {
  server.close();
  void sql.end({ timeout: 5 }).then(() => process.exit(0));
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
