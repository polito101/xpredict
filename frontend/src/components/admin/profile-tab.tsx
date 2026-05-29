/**
 * Plan 08-03 — Profile tab (user detail).
 *
 * Two-column key-value layout per UI-SPEC: label column 160px
 * (`text-sm font-medium text-zinc-500`), value `text-sm text-zinc-900`. Fields:
 * Email, Display Name, Verified, Status, Signup Date, Last Activity.
 *
 * "Verified" is driven off the `is_verified` boolean (NOT `email_verified_at`,
 * which is always null on the detail endpoint — see <backend_contracts>): green
 * Check + "Verified" when true, red X + "Not verified" when false. `Status` uses
 * UserStatusBadge, with the ban date appended when the user is banned.
 *
 * `last_activity` is always null on the detail endpoint (list-only), so it
 * renders as "—" via `formatRelativeTime`.
 */
import { Check, X } from "lucide-react";

import { UserStatusBadge } from "@/components/admin/user-status-badge";
import type { UserDetail } from "@/lib/admin-types";
import { formatDate, formatRelativeTime } from "@/lib/admin-format";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-4">
      <dt className="w-40 shrink-0 text-sm font-medium text-zinc-500">
        {label}
      </dt>
      <dd className="text-sm text-zinc-900 dark:text-zinc-50">{children}</dd>
    </div>
  );
}

export function ProfileTab({ user }: { user: UserDetail }) {
  return (
    <dl className="flex flex-col gap-4">
      <Row label="Email">{user.email}</Row>
      <Row label="Display Name">
        {user.display_name ?? <span className="text-zinc-400">—</span>}
      </Row>
      <Row label="Verified">
        {user.is_verified ? (
          <span className="inline-flex items-center gap-1.5 text-emerald-700 dark:text-emerald-400">
            <Check className="h-4 w-4" aria-hidden="true" />
            Verified
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-red-700 dark:text-red-400">
            <X className="h-4 w-4" aria-hidden="true" />
            Not verified
          </span>
        )}
      </Row>
      <Row label="Status">
        <span className="inline-flex items-center gap-2">
          <UserStatusBadge status={user.status} />
          {user.status === "banned" && user.banned_at && (
            <span className="text-sm text-zinc-500">
              since {formatDate(user.banned_at)}
            </span>
          )}
        </span>
      </Row>
      <Row label="Signup Date">{formatDate(user.created_at)}</Row>
      <Row label="Last Activity">
        {formatRelativeTime(user.last_activity)}
      </Row>
    </dl>
  );
}
