/**
 * Minimal typed client for the XPrediction backend (FastAPI).
 *
 * Base URL comes from NEXT_PUBLIC_API_URL so the same build works in dev,
 * docker-compose, and staging.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(`Request to ${path} failed`, response.status);
  }

  return (await response.json()) as T;
}

export interface HealthStatus {
  status: string;
  service: string;
  environment: string;
  version: string;
}

/** Liveness probe against the backend — proves the wiring end to end. */
export function getHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}
