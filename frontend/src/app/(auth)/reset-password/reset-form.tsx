/**
 * Plan 02-04 — Reset-password form (client component).
 *
 * Receives the token via prop from the server component. The form keeps
 * the token in a hidden input so the FormData payload carries it to the
 * Server Action.
 */
"use client";

import { useActionState, startTransition } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { resetPasswordAction } from "@/lib/auth";
import { ResetSchema, type ActionState } from "@/lib/auth-schemas";
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

type ResetValues = z.infer<typeof ResetSchema>;

export function ResetForm({ token }: { token: string }) {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    resetPasswordAction,
    undefined,
  );

  const form = useForm<ResetValues>({
    resolver: zodResolver(ResetSchema),
    defaultValues: { token, password: "", confirm_password: "" },
    mode: "onSubmit",
  });

  const formError =
    state && "errors" in state ? state.errors._form?.[0] : undefined;

  const onSubmit = form.handleSubmit((values) => {
    const fd = new FormData();
    fd.append("token", values.token);
    fd.append("password", values.password);
    fd.append("confirm_password", values.confirm_password);
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
        <input type="hidden" {...form.register("token")} value={token} />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>New password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="new-password"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="confirm_password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Confirm password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="new-password"
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
          {pending ? "Resetting…" : "Reset password"}
        </Button>
      </form>
    </Form>
  );
}
