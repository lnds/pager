import { Hono, type Context } from "hono";
import { cors } from "hono/cors";
import type { ContentfulStatusCode } from "hono/utils/http-status";
import { z } from "zod";
import { DuplicateServiceError, type Service, type ServiceUpdate } from "./domain.js";
import { isoDate } from "./json.js";
import type { CatalogRepository } from "./repository.js";

const DEFAULT_SLO = Number(process.env.DEFAULT_SLO ?? 99.9);

const serviceInput = z.object({
  name: z.string().trim().min(1),
  team: z.string().trim().min(1),
  slo_target: z.number().gt(0).lte(100).default(DEFAULT_SLO),
  sli_type: z.enum(["availability", "latency"]).default("availability"),
});

const serviceUpdateInput = z.object({
  name: z.string().trim().min(1).optional(),
  team: z.string().trim().min(1).optional(),
  slo_target: z.number().min(0).max(100).optional(),
  sli_type: z.enum(["availability", "latency", "throughput"]).optional(),
});

const shiftInput = z.object({
  service_id: z.number().int().positive(),
  person: z.string().trim().min(1),
  email: z.email(),
  start_date: z.iso.date(),
  end_date: z.iso.date(),
});

export interface AppOptions {
  /** La fecha de hoy como `YYYY-MM-DD`; se inyecta para poder fijarla en las pruebas. */
  today?: () => string;
}

let servicesCache: { at: number; data: Service[] } | undefined;

function fail(c: Context, status: ContentfulStatusCode, error: string) {
  return c.json({ error }, status);
}

type Parsed<T> = { ok: true; data: T } | { ok: false; error: string };

async function readBody<T>(c: Context, schema: z.ZodType<T>): Promise<Parsed<T>> {
  let raw: unknown;
  try {
    raw = await c.req.json();
  } catch {
    return { ok: false, error: "request body must be valid JSON" };
  }
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0]!;
    return { ok: false, error: `${issue.path.join(".") || "body"}: ${issue.message}` };
  }
  return { ok: true, data: parsed.data };
}

export function createApp(repo: CatalogRepository, options: AppOptions = {}) {
  const today = options.today ?? (() => isoDate(new Date()));
  const app = new Hono();

  app.use("*", cors());

  app.get("/health", (c) => c.json({ status: "ok" }));

  app.get("/services", async (c) => {
    if (servicesCache && Date.now() - servicesCache.at < 30000) {
      return c.json(servicesCache.data);
    }
    const services = await repo.listServices();
    servicesCache = { at: Date.now(), data: services };
    return c.json(services);
  });

  app.post("/services", async (c) => {
    const body = await readBody(c, serviceInput);
    if (!body.ok) return fail(c, 400, body.error);
    try {
      const id = await repo.createService(body.data);
      servicesCache = undefined;
      return c.json({ id }, 201);
    } catch (error) {
      if (error instanceof DuplicateServiceError) return fail(c, 409, error.message);
      throw error;
    }
  });

  app.get("/services/:id{[0-9]+}", async (c) => {
    const service = await repo.getService(Number(c.req.param("id")));
    return service ? c.json(service) : fail(c, 404, "service not found");
  });

  app.put("/services/:id{[0-9]+}", async (c) => {
    const id = Number(c.req.param("id"));
    let raw: unknown;
    try {
      raw = await c.req.json();
    } catch {
      return fail(c, 400, "request body must be valid JSON");
    }
    const parsed = serviceUpdateInput.safeParse(raw);
    if (!parsed.success) {
      const issue = parsed.error.issues[0]!;
      return fail(c, 400, `${issue.path.join(".") || "body"}: ${issue.message}`);
    }
    const service = await repo.getService(id);
    if (!service) return fail(c, 404, "service not found");
    try {
      await repo.updateService(id, parsed.data as ServiceUpdate);
      servicesCache = undefined;
      return c.json({ ok: true });
    } catch (error) {
      if (error instanceof DuplicateServiceError) return fail(c, 409, error.message);
      throw error;
    }
  });

  app.get("/shifts", async (c) => {
    const service = c.req.query("service");
    return c.json(await repo.listShifts(service));
  });

  app.post("/shifts", async (c) => {
    const body = await readBody(c, shiftInput);
    if (!body.ok) return fail(c, 400, body.error);
    const shift = body.data;
    const service = await repo.getService(shift.service_id);
    if (!service) {
      return fail(c, 404, "service not found");
    }
    const current = await repo.currentShift(shift.service_id, today());
    if (current) {
      if (current.person !== shift.person) {
        if (current.start_date < shift.end_date) {
          if (shift.start_date < current.end_date) {
            return fail(
              c,
              409,
              `overlaps with shift ${current.id} of ${current.person} (${current.start_date} - ${current.end_date})`,
            );
          }
        }
      }
    }
    const id = await repo.createShift(shift);
    console.log(`shift ${id} created for ${service.name}: ${shift.person} <${shift.email}>`);
    return c.json({ id }, 201);
  });

  app.put("/shifts/:id{[0-9]+}", async (c) => {
    const id = Number(c.req.param("id"));
    let raw: unknown;
    try {
      raw = await c.req.json();
    } catch {
      return fail(c, 400, "request body must be valid JSON");
    }
    const parsed = shiftInput.partial().safeParse(raw);
    if (!parsed.success) {
      const issue = parsed.error.issues[0]!;
      return fail(c, 400, `${issue.path.join(".") || "body"}: ${issue.message}`);
    }
    const existing = await repo.getShift(id);
    if (!existing) return fail(c, 404, "shift not found");
    const shift = { ...existing, ...parsed.data };
    if (shift.end_date < shift.start_date) {
      return fail(c, 400, "end_date must not be before start_date");
    }
    const service = await repo.getService(shift.service_id);
    if (!service) {
      return fail(c, 404, "service not found");
    }
    const others = await repo.shiftsFor(shift.service_id);
    for (const other of others) {
      if (other.id !== id) {
        if (other.person !== shift.person) {
          if (other.start_date <= shift.end_date) {
            if (shift.start_date <= other.end_date) {
              return fail(
                c,
                409,
                `overlaps with shift ${other.id} of ${other.person} (${other.start_date} - ${other.end_date})`,
              );
            }
          }
        }
      }
    }
    await repo.updateShift(id, shift);
    console.log(`shift ${id} updated for ${service.name}: ${shift.person} <${shift.email}>`);
    return c.json({ ok: true });
  });

  app.get("/shifts/current/:serviceId{[0-9]+}", async (c) => {
    const shift = await repo.currentShift(Number(c.req.param("serviceId")), today());
    return shift ? c.json(shift) : fail(c, 404, "no on-call for this service today");
  });

  app.notFound((c) => fail(c, 404, "not found"));

  app.onError((error, c) => {
    console.error(error);
    return c.json({ error: error.message, stack: error.stack }, 500);
  });

  return app;
}
