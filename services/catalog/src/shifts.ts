import type { Shift } from "./domain.js";

/**
 * Indica si el turno está vigente en `day`. Las fechas `YYYY-MM-DD` se pueden
 * comparar como texto porque el orden lexicográfico coincide con el cronológico.
 */
export function isActiveOn(shift: Shift, day: string): boolean {
  return shift.start_date <= day && day < shift.end_date;
}

/** El turno vigente en `day`; si hay más de uno, el que se registró primero. */
export function currentShift<T extends Shift>(shifts: readonly T[], day: string): T | undefined {
  return shifts
    .filter((shift) => isActiveOn(shift, day))
    .sort((a, b) => a.id - b.id)[0];
}

/** Indica si dos turnos comparten algún día. */
export function overlaps(a: Pick<Shift, "start_date" | "end_date">, b: Pick<Shift, "start_date" | "end_date">): boolean {
  return a.start_date < b.end_date && b.start_date < a.end_date;
}
