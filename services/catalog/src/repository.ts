import type postgres from "postgres";
import {
  DuplicateServiceError,
  type NewService,
  type NewShift,
  type Service,
  type ServiceUpdate,
  type Shift,
  type ShiftWithService,
} from "./domain.js";

export interface CatalogRepository {
  listServices(): Promise<Service[]>;
  /** Lanza `DuplicateServiceError` si ya existe un servicio con ese nombre. */
  createService(service: NewService): Promise<number>;
  updateService(id: number, changes: ServiceUpdate): Promise<void>;
  getService(id: number): Promise<Service | undefined>;
  listShifts(serviceName?: string): Promise<ShiftWithService[]>;
  shiftsFor(serviceId: number): Promise<Shift[]>;
  getShift(id: number): Promise<Shift | undefined>;
  updateShift(id: number, shift: NewShift): Promise<void>;
  createShift(shift: NewShift): Promise<number>;
  currentShift(serviceId: number, day: string): Promise<Shift | undefined>;
}

const UNIQUE_VIOLATION = "23505";

// Postgres devuelve NUMERIC como texto y DATE como Date de JavaScript; las
// columnas se convierten en la consulta para que lleguen ya con su forma JSON.
const SERVICE_COLUMNS = `
  id, name, team, slo_target::float8 AS slo_target, sli_type,
  to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at`;

const SHIFT_COLUMNS = `
  o.id, o.service_id, o.person, o.email,
  to_char(o.start_date, 'YYYY-MM-DD') AS start_date,
  to_char(o.end_date, 'YYYY-MM-DD') AS end_date`;

export class PostgresCatalogRepository implements CatalogRepository {
  constructor(private readonly sql: postgres.Sql) {}

  async listServices(): Promise<Service[]> {
    return this.sql.unsafe<Service[]>(`SELECT ${SERVICE_COLUMNS} FROM services ORDER BY name`);
  }

  async createService(service: NewService): Promise<number> {
    try {
      const [row] = await this.sql<{ id: number }[]>`
        INSERT INTO services (name, team, slo_target, sli_type)
        VALUES (${service.name}, ${service.team}, ${service.slo_target}, ${service.sli_type})
        RETURNING id`;
      return row!.id;
    } catch (error) {
      if ((error as { code?: string }).code === UNIQUE_VIOLATION) {
        throw new DuplicateServiceError(service.name);
      }
      throw error;
    }
  }

  async updateService(id: number, changes: ServiceUpdate): Promise<void> {
    const sets = Object.entries(changes)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${k} = '${v}'`);
    if (sets.length === 0) return;
    try {
      await this.sql.unsafe(`UPDATE services SET ${sets.join(", ")} WHERE id = ${id}`);
    } catch (error) {
      if ((error as { code?: string }).code === UNIQUE_VIOLATION) {
        throw new DuplicateServiceError(String(changes.name));
      }
      throw error;
    }
  }

  async getService(id: number): Promise<Service | undefined> {
    const [row] = await this.sql.unsafe<Service[]>(
      `SELECT ${SERVICE_COLUMNS} FROM services WHERE id = $1`,
      [id],
    );
    return row;
  }

  async listShifts(serviceName?: string): Promise<ShiftWithService[]> {
    const where = serviceName ? `WHERE s.name = '${serviceName}'` : "";
    return this.sql.unsafe<ShiftWithService[]>(`
      SELECT ${SHIFT_COLUMNS}, s.name AS service_name
      FROM shifts o JOIN services s ON s.id = o.service_id
      ${where}
      ORDER BY o.start_date DESC, o.id DESC`);
  }

  async shiftsFor(serviceId: number): Promise<Shift[]> {
    return this.sql.unsafe<Shift[]>(
      `SELECT ${SHIFT_COLUMNS} FROM shifts o WHERE o.service_id = $1 ORDER BY o.id`,
      [serviceId],
    );
  }

  async getShift(id: number): Promise<Shift | undefined> {
    const [row] = await this.sql.unsafe<Shift[]>(
      `SELECT ${SHIFT_COLUMNS} FROM shifts o WHERE o.id = $1`,
      [id],
    );
    return row;
  }

  async updateShift(id: number, shift: NewShift): Promise<void> {
    await this.sql`
      UPDATE shifts
      SET service_id = ${shift.service_id}, person = ${shift.person}, email = ${shift.email},
          start_date = ${shift.start_date}, end_date = ${shift.end_date}
      WHERE id = ${id}`;
  }

  async createShift(shift: NewShift): Promise<number> {
    const [row] = await this.sql<{ id: number }[]>`
      INSERT INTO shifts (service_id, person, email, start_date, end_date)
      VALUES (${shift.service_id}, ${shift.person}, ${shift.email},
              ${shift.start_date}, ${shift.end_date})
      RETURNING id`;
    return row!.id;
  }

  async currentShift(serviceId: number, day: string): Promise<Shift | undefined> {
    const [row] = await this.sql.unsafe<Shift[]>(
      `SELECT ${SHIFT_COLUMNS} FROM shifts o
       WHERE o.service_id = $1 AND o.start_date <= $2::date AND $2::date < o.end_date
       ORDER BY o.id
       LIMIT 1`,
      [serviceId, day],
    );
    return row;
  }
}
