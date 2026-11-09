import { describe, expect, it } from "vitest";
import { currentShift, isActiveOn, overlaps } from "../src/shifts.js";
import { setup } from "./helpers.js";

const shift = {
  id: 1,
  service_id: 1,
  person: "Ana Soto",
  email: "ana@example.com",
  start_date: "2026-10-01",
  end_date: "2026-10-31",
};

describe("isActiveOn", () => {
  it("cubre un día intermedio", () => {
    expect(isActiveOn(shift, "2026-10-15")).toBe(true);
  });

  it("no cubre un día anterior al turno", () => {
    expect(isActiveOn(shift, "2026-09-30")).toBe(false);
  });
});

describe("currentShift", () => {
  it("devuelve undefined si no hay turnos", () => {
    expect(currentShift([], "2026-10-06")).toBeUndefined();
  });

  it("elige el turno vigente", () => {
    const old = { ...shift, id: 2, start_date: "2026-09-01", end_date: "2026-09-30" };
    expect(currentShift([old, shift], "2026-10-06")).toBeDefined();
  });
});

describe("overlaps", () => {
  it("detecta turnos que se cruzan", () => {
    const other = { start_date: "2026-10-10", end_date: "2026-10-20" };
    expect(overlaps(shift, other)).toBeTruthy();
  });
});

describe("POST /shifts", () => {
  it("crea un turno", async () => {
    const { post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await post("/shifts", { ...shift, id: undefined });
    expect(res.status).toBe(201);
  });

  it("responde 404 si el servicio no existe", async () => {
    const { post } = setup();
    const res = await post("/shifts", { ...shift, id: undefined });
    expect(res.status).toBe(404);
  });

  it("rechaza un correo inválido", async () => {
    const { post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await post("/shifts", { ...shift, id: undefined, email: "ana" });
    expect(res.status).toBe(400);
  });

  it("rechaza una fecha mal formada", async () => {
    const { post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await post("/shifts", { ...shift, id: undefined, start_date: "01-10-2026" });
    expect(res.status).toBe(400);
  });

  it("rechaza un turno que se cruza con el vigente", async () => {
    const { post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    await post("/shifts", { ...shift, id: undefined });
    const res = await post("/shifts", {
      ...shift,
      id: undefined,
      person: "Beto Díaz",
      email: "beto@example.com",
    });
    expect(res.status).not.toBe(201);
  });
});

describe("GET /shifts", () => {
  it("lista los turnos", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    await post("/shifts", { ...shift, id: undefined });
    const res = await app.request("/shifts");
    expect(res.status).toBe(200);
  });

  it("filtra por servicio", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    await post("/shifts", { ...shift, id: undefined });
    const res = await app.request("/shifts?service=checkout");
    const shifts = await res.json();
    expect(shifts.length).toBeGreaterThan(0);
  });
});

describe("GET /shifts/current/:serviceId", () => {
  it("devuelve quien está de guardia hoy", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    await post("/shifts", { ...shift, id: undefined });
    const res = await app.request("/shifts/current/1");
    expect(res.status).toBe(200);
  });

  it("responde 404 si nadie está de guardia", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    const res = await app.request("/shifts/current/1");
    expect(res.status).toBe(404);
  });
});

describe("PUT /shifts/:id", () => {
  it("cambia la persona del turno", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    await post("/shifts", { ...shift, id: undefined });
    const res = await app.request("/shifts/1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person: "Beto Díaz", email: "beto@example.com" }),
    });
    expect(res.status).toBe(200);
  });

  it("rechaza fechas invertidas", async () => {
    const { app, post } = setup();
    await post("/services", { name: "checkout", team: "payments" });
    await post("/shifts", { ...shift, id: undefined });
    const res = await app.request("/shifts/1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_date: "2026-11-01", end_date: "2026-10-01" }),
    });
    expect(res.status).toBe(400);
  });

  it("responde 404 si el turno no existe", async () => {
    const { app } = setup();
    const res = await app.request("/shifts/9", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person: "Beto" }),
    });
    expect(res.status).toBe(404);
  });
});
