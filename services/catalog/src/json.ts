/** Un instante en ISO 8601, UTC y sin milisegundos: `2026-10-06T22:00:00Z`. */
export function isoInstant(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** La fecha UTC de un instante, como `YYYY-MM-DD`. */
export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}
