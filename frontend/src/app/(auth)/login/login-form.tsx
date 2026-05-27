/**
 * Plan 02-04 — Player login form (client component).
 *
 * Combines react-hook-form's `useForm` (client-side zod validation +
 * focus/blur tracking) with React 19 `useActionState` (server-driven
 * error display + pending state from the `loginAction` Server Action).
 *
 * On submit, the form builds a FormData payload (so we keep
 * Progressive Enhancement — the form would still work without JS,
 * since `loginAction` is a Server Action) and invokes `formAction`,
 * which is the action wrapper provided by `useActionState`.
 */
"use client";

import { useActionState, startTransition } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { loginAction } from "@/lib/auth";
import { LoginSchema, type ActionState } from "@/lib/auth-schemas";
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

type LoginValues = z.infer<typeof LoginSchema>;

export function LoginForm() {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    loginAction,
    undefined,
  );

  const form = useForm<LoginValues>({
    resolver: zodResolver(LoginSchema),
    defaultValues: { email: "", password: "" },
    // The Server Action is the authoritative error source; the client zod
    // schema only stops obvious mistakes (empty fields, invalid format).
    mode: "onSubmit",
  });

  // Form-level error from the Server Action (e.g. "Invalid credentials").
  const formError =
    state && "errors" in state ? state.errors._form?.[0] : undefined;

  // Imperative submit handler: run client-side zod validation, then invoke
  // the action with explicit FormData. This double-binds the form so it
  // works both with JS (this path) and without (the browser-native
  // `action={formAction}` path — set via the attribute below).
  const onSubmit = form.handleSubmit((values) => {
    const fd = new FormData();
    fd.append("email", values.email);
    fd.append("password", values.password);
    // React 19 transition wrapper — keeps `pending` accurate and silences
    // the "useActionState was called outside of a transition" dev warning.
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
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </Form>
  );
}
