/**
 * Plan 02-04 — Player login page.
 *
 * Server Component shell that reads searchParams (Next 15: must be `await`ed)
 * to show post-register / post-reset notices, then mounts the client form.
 */
import Link from "next/link";
import { LoginForm } from "./login-form";
import { DemoLoginButton } from "./demo-login-button";

type SP = Promise<{ registered?: string; reset?: string }>;

export default async function LoginPage({
  searchParams,
}: {
  searchParams: SP;
}) {
  const params = await searchParams;
  return (
    <div className="space-y-6">
      <header className="space-y-2 text-center">
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Sign in
        </h1>
        <p className="text-sm text-muted-foreground">
          Welcome back to XPrediction
        </p>
      </header>
      {params.registered === "1" && (
        <p
          role="status"
          className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400"
        >
          Check your email to verify your account.
        </p>
      )}
      {params.reset === "1" && (
        <p
          role="status"
          className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400"
        >
          Password reset. Please sign in with your new password.
        </p>
      )}
      <LoginForm />
      {process.env.NEXT_PUBLIC_DEMO_MODE === "true" && (
        <>
          <div className="flex items-center gap-3 text-xs uppercase tracking-wide text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            <span>o</span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <DemoLoginButton />
        </>
      )}
      <p className="text-center text-sm text-muted-foreground">
        <Link href="/forgot-password" className="underline">
          Forgot your password?
        </Link>
      </p>
      <p className="text-center text-sm text-muted-foreground">
        Need an account?{" "}
        <Link href="/register" className="underline">
          Create one
        </Link>
      </p>
    </div>
  );
}
