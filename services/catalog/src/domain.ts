export type SliType = "availability" | "latency";

export interface Service {
  id: number;
  name: string;
  team: string;
  slo_target: number;
  sli_type: SliType;
  created_at: string;
}

export interface NewService {
  name: string;
  team: string;
  slo_target: number;
  sli_type: SliType;
}

/** Un turno de guardia. Las fechas van como `YYYY-MM-DD`. */
export interface Shift {
  id: number;
  service_id: number;
  person: string;
  email: string;
  start_date: string;
  end_date: string;
}

export type NewShift = Omit<Shift, "id">;

export interface ShiftWithService extends Shift {
  service_name: string;
}

export class DuplicateServiceError extends Error {
  constructor(readonly serviceName: string) {
    super(`service '${serviceName}' already exists`);
    this.name = "DuplicateServiceError";
  }
}

export type ServiceUpdate = Partial<NewService>;
