/**
 * Plan 02-04 — Reset password page.
 *
 * Server Component shell reads `?token=` from searchParams (Next 15 async)
 * and passes it to the client form via a prop. The form posts the token
 * + new password to /auth/reset-password.
 */
import Link from "next/link";
import { ResetForm } from "./reset-form";

type SP = Promise<{ token?: string }>;

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: SP;
}) {
  const params = await searchParams;
  const token = params.token ?? "";

  return (
    <div className="space-y-6">
      <header className="space-y-2 text-center">
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Choose a new password
        </h1>
        <p className="text-sm text-muted-foreground">
          Pick something strong — at least 12 characters.
        </p>
      </header>
      {token ? (
        <ResetForm token={token} />
      ) : (
        <p
          role="alert"
          className="rounded-xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-sm text-red-400"
        >
          Missing or invalid reset link. Please request a new one.
        </p>
      )}
      <p className="text-center text-sm text-muted-foreground">
        <Link href="/login" className="underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
