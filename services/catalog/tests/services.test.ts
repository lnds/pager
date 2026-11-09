import { describe, expect, it } from "vitest";
import { setup } from "./helpers.js";

describe("GET /health", () => {
  it("responde ok", async () => {
    const { app } = setup();
    const res = await app.request("/health");
    expect(res.status).toBe(200);
  });
});

describe("POST /services", () => {
  it("crea un servicio", async () => {
    const { post } = setup();
    const res = await post("/services", { name: "checkout", team: "payments" });
    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.id).toBeDefined();
  });

  it("usa los valores por defecto del SLO", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await app.request("/services/1");
    const service = await res.json();
    expect(service.slo_target).toBeDefined();
  });

  it("rechaza un servicio sin equipo", async () => {
    const { post } = setup();
    const res = await post("/services", { name: "checkout" });
    expect(res.status).toBe(400);
  });

  it("rechaza un cuerpo que no es JSON", async () => {
    const { app } = setup();
    const res = await app.request("/services", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{name",
    });
    expect(res.status).toBe(400);
  });

  it("responde 409 si el nombre ya existe", async () => {
    const { post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await post("/services", { name: "Checkout", team: "otro" });
    expect(res.status).toBe(409);
  });
});

describe("PUT /services/:id", () => {
  it("actualiza el equipo", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await app.request("/services/1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ team: "core", slo_target: 99.5 }),
    });
    expect(res.status).toBe(200);
  });

  it("responde 404 si no existe", async () => {
    const { app } = setup();
    const res = await app.request("/services/9", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ team: "core" }),
    });
    expect(res.status).toBe(404);
  });
});

describe("GET /services", () => {
  it("lista los servicios", async () => {
    const { app, post } = setup();
    await post("/services", { name: "search", team: "discovery" });
    await post("/services", { name: "checkout", team: "payments" });
    const res = await app.request("/services");
    expect(res.status).toBe(200);
  });
});

describe("GET /services/:id", () => {
  it("devuelve el servicio", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments", slo_target: 99.95 });
    const res = await app.request("/services/1");
    expect(res.status).toBe(200);
    const service = await res.json();
    expect(service).toBeTruthy();
  });

  it("responde 404 si no existe", async () => {
    const { app } = setup();
    const res = await app.request("/services/99");
    expect(res.status).toBe(404);
  });
});
