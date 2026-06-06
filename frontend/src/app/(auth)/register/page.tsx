/**
 * Plan 02-04 — Player registration page.
 *
 * Server Component shell. Form lives in `register-form.tsx` ("use client").
 */
import Link from "next/link";
import { RegisterForm } from "./register-form";

export default function RegisterPage() {
  return (
    <div className="space-y-6">
      <header className="space-y-2 text-center">
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Create your account
        </h1>
        <p className="text-sm text-muted-foreground">
          Get started with XPrediction — it&apos;s free.
        </p>
      </header>
      <RegisterForm />
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
