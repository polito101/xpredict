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
        <h1 className="text-2xl font-semibold tracking-tight">
          Create your account
        </h1>
        <p className="text-sm text-zinc-500">
          Get started with XPredict — it&apos;s free.
        </p>
      </header>
      <RegisterForm />
      <p className="text-center text-sm text-zinc-600 dark:text-zinc-400">
        Already have an account?{" "}
        <Link href="/login" className="underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
