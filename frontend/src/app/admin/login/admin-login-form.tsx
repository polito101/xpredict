/**
 * Plan 02-05 Task 2 — Admin login form (client component).
 *
 * Mirrors the player `LoginForm` (Plan 02-04) but:
 *   - Binds to `adminLoginAction` instead of `loginAction`.
 *   - Uses `AdminLoginSchema` (no password length enforcement; admins are
 *     seeded via `bin/create_admin.py` which bypasses validate_password).
 *   - Submit button labelled "Sign in as admin" to distinguish from the
 *     player UX visually + textually (success criteria #2).
 *
 * On submit, builds a FormData payload and invokes `formAction` inside
 * `startTransition` (silences React 19's "useActionState outside transition"
 * warning) — identical pattern to player LoginForm.
 */
"use client";

import { useActionState, startTransition } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { adminLoginAction } from "@/lib/auth";
import { AdminLoginSchema, type ActionState } from "@/lib/auth-schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";

type AdminLoginValues = z.infer<typeof AdminLoginSchema>;

export function AdminLoginForm() {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    adminLoginAction,
    undefined,
  );

  const form = useForm<AdminLoginValues>({
    resolver: zodResolver(AdminLoginSchema),
    defaultValues: { email: "", password: "" },
    mode: "onSubmit",
  });

  const formError =
    state && "errors" in state ? state.errors._form?.[0] : undefined;

  const onSubmit = form.handleSubmit((values) => {
    const fd = new FormData();
    fd.append("email", values.email);
    fd.append("password", values.password);
    startTransition(() => formAction(fd));
  });

  return (
    <Form {...form}>
      <form
        action={formAction}
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(e);
        }}
        className="space-y-4"
        noValidate
      >
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="current-password"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {formError && (
          <p
            role="alert"
            className="text-sm font-medium text-red-500"
            data-testid="form-error"
          >
            {formError}
          </p>
        )}
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Signing in…" : "Sign in as admin"}
        </Button>
      </form>
    </Form>
  );
}
