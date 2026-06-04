/**
 * Plan 12-06 — shared error decode for the settlement dialogs.
 *
 * The `"use server"` settlement wrappers (`admin-markets-api.ts`) throw
 * `Error("API error: <status>")` on a non-2xx response (the status is preserved
 * in the message string). A 401/403 means the admin_jwt expired — each dialog
 * branches that to the verbatim UI-SPEC "Your session expired. Please sign in
 * again." toast (mirrors the ban dialog's catch / branding-form.tsx:213).
 * Anything else falls through to the per-action generic failure toast.
 */

/** True when a thrown wrapper error carries a 401 or 403 status code. */
export function isSessionExpiredError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err ?? "");
  return /\b(401|403)\b/.test(message);
}
