import { createApp } from "../src/app.js";
import { MemoryCatalogRepository } from "../src/memory-repository.js";

export const TODAY = "2026-10-06";

export function setup() {
  const repo = new MemoryCatalogRepository(() => new Date("2026-10-06T12:00:00.000Z"));
  const app = createApp(repo, { today: () => TODAY });

  async function post(path: string, body: unknown) {
    return app.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  return { app, repo, post };
}
