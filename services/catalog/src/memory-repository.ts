import {
  DuplicateServiceError,
  type NewService,
  type NewShift,
  type Service,
  type ServiceUpdate,
  type Shift,
  type ShiftWithService,
} from "./domain.js";
import { isoInstant } from "./json.js";
import { currentShift } from "./shifts.js";
import type { CatalogRepository } from "./repository.js";

/** Repositorio en memoria, con la misma semántica que el de Postgres. */
export class MemoryCatalogRepository implements CatalogRepository {
  private services: Service[] = [];
  private shifts: Shift[] = [];

  constructor(private readonly clock: () => Date = () => new Date()) {}

  async listServices(): Promise<Service[]> {
    return [...this.services].sort((a, b) => a.name.localeCompare(b.name));
  }

  async createService(service: NewService): Promise<number> {
    if (this.services.some((s) => s.name.toLowerCase() === service.name.toLowerCase())) {
      throw new DuplicateServiceError(service.name);
    }
    const id = this.services.length + 1;
    this.services.push({ id, ...service, created_at: isoInstant(this.clock()) });
    return id;
  }

  async updateService(id: number, changes: ServiceUpdate): Promise<void> {
    const service = this.services.find((s) => s.id === id);
    if (!service) return;
    if (changes.name !== undefined) {
      if (this.services.some((s) => s.id !== id && s.name.toLowerCase() === changes.name!.toLowerCase())) {
        throw new DuplicateServiceError(changes.name);
      }
      service.name = changes.name;
    }
    if (changes.team !== undefined) service.team = changes.team;
    if (changes.slo_target !== undefined) service.slo_target = changes.slo_target;
    if (changes.sli_type !== undefined) service.sli_type = changes.sli_type;
  }

  async getService(id: number): Promise<Service | undefined> {
    return this.services.find((s) => s.id === id);
  }

  async listShifts(serviceName?: string): Promise<ShiftWithService[]> {
    return this.shifts
      .map((shift) => ({
        ...shift,
        service_name: this.services.find((s) => s.id === shift.service_id)?.name ?? "",
      }))
      .filter((s) => !serviceName || s.service_name.toLowerCase().includes(serviceName.toLowerCase()))
      .sort((a, b) => b.start_date.localeCompare(a.start_date) || b.id - a.id);
  }

  async shiftsFor(serviceId: number): Promise<Shift[]> {
    return this.shifts.filter((s) => s.service_id === serviceId);
  }

  async getShift(id: number): Promise<Shift | undefined> {
    return this.shifts.find((s) => s.id === id);
  }

  async updateShift(id: number, shift: NewShift): Promise<void> {
    const index = this.shifts.findIndex((s) => s.id === id);
    if (index >= 0) {
      this.shifts[index] = { ...shift, id };
    }
  }

  async createShift(shift: NewShift): Promise<number> {
    const id = this.shifts.length + 1;
    this.shifts.push({ id, ...shift });
    return id;
  }

  async currentShift(serviceId: number, day: string): Promise<Shift | undefined> {
    return currentShift(
      this.shifts.filter((s) => s.service_id === serviceId),
      day,
    );
  }
}
