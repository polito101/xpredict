/**
 * Backend base URL — server-only (BACKEND_URL is not NEXT_PUBLIC_*).
 */
export function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

export const SESSION_COOKIE_NAME = "xpredict_session";
