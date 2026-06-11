/**
 * quick-260611-lcr (DEMO-01) — one-click demo access button.
 *
 * Client component rendered (only) by the login page when NEXT_PUBLIC_DEMO_MODE
 * is "true" (the env gate lives in page.tsx, the SERVER component, so the button
 * is fully ABSENT in white-label / production builds — not merely hidden).
 *
 * On click it invokes the `demoLoginAction` Server Action, which POSTs to the
 * DEMO_MODE-gated backend `/auth/demo-login` and re-sets the returned session
 * cookie (the browser cannot reach the backend directly — cookie is HttpOnly +
 * cross-origin, no Next rewrite for /auth/*). On success the client navigates to
 * /markets; on failure an inline error is shown.
 */
"use client";

import { useActionState, startTransition, useEffect } from "react";
import { useRouter } from "next/navigation";

import { demoLoginAction } from "@/lib/auth";
import type { ActionState } from "@/lib/auth-schemas";
import { Button } from "@/components/ui/button";

export function DemoLoginButton() {
  const router = useRouter();
  const [state, formAction, pending] = useActionState<ActionState, void>(
    demoLoginAction,
    undefined,
  );

  // On a successful demo session, navigate into the app. Done in an effect so
  // the navigation reacts to the action's resolved state.
  useEffect(() => {
    if (state && "success" in state && state.success) {
      router.push("/markets");
    }
  }, [state, router]);

  const error = state && "errors" in state ? state.errors._form?.[0] : undefined;

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="secondary"
        className="w-full"
        disabled={pending}
        onClick={() => startTransition(() => formAction())}
      >
        {pending ? "Cargando…" : "Probar la demo"}
      </Button>
      {error && (
        <p
          role="alert"
          className="text-sm font-medium text-red-500"
          data-testid="demo-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}
