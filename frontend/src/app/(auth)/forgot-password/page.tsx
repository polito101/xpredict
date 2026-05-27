/**
 * Plan 02-04 — Forgot password page.
 *
 * Server Component shell. ForgotForm posts to /auth/forgot-password and
 * unconditionally returns the same generic success message
 * (T-02-38: email-enumeration mitigation).
 */
import Link from "next/link";
import { ForgotForm } from "./forgot-form";

export default function ForgotPasswordPage() {
  return (
    <div className="space-y-6">
      <header className="space-y-2 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">
          Reset your password
        </h1>
        <p className="text-sm text-zinc-500">
          We&apos;ll email you a link to set a new password.
        </p>
      </header>
      <ForgotForm />
      <p className="text-center text-sm text-zinc-600 dark:text-zinc-400">
        <Link href="/login" className="underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
