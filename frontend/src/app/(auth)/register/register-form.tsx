/**
 * Plan 02-04 — Player registration form (client component).
 *
 * zod resolver (via `RegisterSchema`) mirrors the backend
 * `validate_password` rules so users see violations BEFORE the
 * Server Action is invoked. Backend always re-validates.
 */
"use client";

import { useActionState, startTransition } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { registerAction } from "@/lib/auth";
import { RegisterSchema, type ActionState } from "@/lib/auth-schemas";
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

type RegisterValues = z.infer<typeof RegisterSchema>;

export function RegisterForm() {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    registerAction,
    undefined,
  );

  const form = useForm<RegisterValues>({
    resolver: zodResolver(RegisterSchema),
    defaultValues: {
      email: "",
      password: "",
      confirm_password: "",
      display_name: "",
    },
    mode: "onSubmit",
  });

  const formError =
    state && "errors" in state ? state.errors._form?.[0] : undefined;

  const onSubmit = form.handleSubmit((values) => {
    const fd = new FormData();
    fd.append("email", values.email);
    fd.append("password", values.password);
    fd.append("confirm_password", values.confirm_password);
    if (values.display_name) fd.append("display_name", values.display_name);
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
          name="display_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Display name (optional)</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  autoComplete="nickname"
                  {...field}
                  value={field.value ?? ""}
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
          <p
            role="alert"
            className="text-sm font-medium text-red-500"
            data-testid="form-error"
          >
            {formError}
          </p>
        )}
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </Form>
  );
}
