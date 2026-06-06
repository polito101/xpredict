/**
 * Plan 02-04 — Forgot-password form (client component).
 *
 * Critical UX: success message is INTENTIONALLY the same whether the email
 * exists or not — `forgotPasswordAction` returns the same string regardless
 * of backend status. This mirrors the backend's 202-on-everything contract
 * and is the T-02-38 enumeration-mitigation control.
 */
"use client";

import { useActionState, startTransition } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { forgotPasswordAction } from "@/lib/auth";
import { ForgotSchema, type ActionState } from "@/lib/auth-schemas";
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

type ForgotValues = z.infer<typeof ForgotSchema>;

export function ForgotForm() {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    forgotPasswordAction,
    undefined,
  );

  const form = useForm<ForgotValues>({
    resolver: zodResolver(ForgotSchema),
    defaultValues: { email: "" },
    mode: "onSubmit",
  });

  const successMessage =
    state && "success" in state && state.success ? state.message : undefined;
  const formError =
    state && "errors" in state ? state.errors._form?.[0] : undefined;

  const onSubmit = form.handleSubmit((values) => {
    const fd = new FormData();
    fd.append("email", values.email);
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
        {successMessage ? (
          <p
            role="status"
            className="rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400"
          >
            {successMessage}
          </p>
        ) : (
          <>
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
            {formError && (
              <p role="alert" className="text-sm font-medium text-red-500">
                {formError}
              </p>
            )}
            <Button type="submit" disabled={pending} className="w-full">
              {pending ? "Sending…" : "Send reset link"}
            </Button>
          </>
        )}
      </form>
    </Form>
  );
}
