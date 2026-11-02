export class SupervisorError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
export const usageError = (m) => new SupervisorError(2, m);
export const failError = (m) => new SupervisorError(1, m);
export const ceilingError = (m) => new SupervisorError(3, m);

export function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

