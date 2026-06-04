/**
 * Plan 12-05 — Market create/edit form (ADM-02, ADM-03, ADM-07, BET-06).
 *
 * Clone of `branding-form.tsx`: "use client" + react-hook-form + zodResolver +
 * shadcn Form/FormField/FormItem/FormLabel/FormControl/FormMessage + a Loader2
 * submit spinner + sonner toast feedback + the 422 → inline FormMessage mapping.
 *
 * The zod schema MIRRORS the backend `MarketCreate` / `MarketUpdate` contracts
 * (`markets/schemas.py`) for UX only — the FastAPI Field constraints are
 * authoritative (the client mirror never gates security; threat T-12-15).
 *
 * Two modes via a `mode` prop:
 *   - create → fields mirror MarketCreate; the odds field is `initial_odds_yes`.
 *   - edit   → fields mirror MarketUpdate; the odds field is `odds_yes`. When
 *     `betCount > 0` the resolution_criteria field is DISABLED with the locked
 *     helper (ADM-07; the backend returns 423 CRITERIA_LOCKED authoritatively).
 *     Odds + deadline stay editable with bets (documented Phase-4 deviation).
 *
 * BET-06 (A-STAKE-FIELDS): optional Min/Max stake money inputs. Values stay
 * STRINGS end-to-end (SP-1, threat T-12-16) — `Number(...)` is used ONLY for the
 * client min<=max comparison, never for storage. Blank = the platform default.
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { createMarket, updateMarket } from "@/lib/admin-markets-api";
import type {
  MarketCreateBody,
  MarketUpdateBody,
} from "@/lib/admin-markets-types";

// A decimal money/odds string: digits with an optional fractional part.
const DECIMAL_RE = /^\d+(\.\d+)?$/;

// Optional decimal string (blank allowed → platform default). When present it
// must parse as a positive decimal. Money stays a STRING; Number() is only used
// for the comparison below, never for storage (threat T-12-16).
const optionalPositiveDecimal = z
  .string()
  .trim()
  .refine((v) => v === "" || DECIMAL_RE.test(v), {
    message: "Enter a positive amount.",
  })
  .refine((v) => v === "" || Number(v) > 0, {
    message: "Enter a positive amount.",
  });

/**
 * The form's value shape — a superset covering both modes. `odds_yes` is the
 * single odds field name used in BOTH modes at the FORM level; on submit it is
 * mapped to `initial_odds_yes` (create) or `odds_yes` (edit) for the wire body.
 */
export interface MarketFormValues {
  question: string;
  resolution_criteria: string;
  deadline: string;
  odds_yes: string;
  category: string;
  min_stake: string;
  max_stake: string;
}

const MarketSchema = z
  .object({
    question: z
      .string()
      .trim()
      .min(1, "A question is required.")
      .max(500, "Keep the question under 500 characters."),
    resolution_criteria: z
      .string()
      .trim()
      .min(1, "Resolution criteria are required.")
      .max(2000, "Keep the criteria under 2000 characters."),
    deadline: z
      .string()
      .min(1, "The deadline must be in the future.")
      .refine((v) => {
        const d = new Date(v);
        return !Number.isNaN(d.getTime()) && d.getTime() > Date.now();
      }, "The deadline must be in the future."),
    odds_yes: z
      .string()
      .trim()
      .min(1, "Enter odds between 1 and 99%.")
      .refine((v) => {
        if (!DECIMAL_RE.test(v)) return false;
        const n = Number(v);
        return n > 0 && n < 1;
      }, "Enter odds between 1 and 99%."),
    category: z
      .string()
      .trim()
      .max(100, "Keep the category under 100 characters."),
    min_stake: optionalPositiveDecimal,
    max_stake: optionalPositiveDecimal,
  })
  .refine(
    (vals) => {
      if (vals.min_stake === "" || vals.max_stake === "") return true;
      // String values; Number() only for the comparison (never for storage).
      return Number(vals.min_stake) <= Number(vals.max_stake);
    },
    {
      message: "Min stake cannot exceed max stake.",
      path: ["max_stake"],
    },
  );

/** Decoded `{status, fieldErrors}` shape for a thrown market API error. */
interface MarketApiError {
  status: number | null;
  fieldErrors: Record<string, string>;
}

/**
 * Decode a thrown market error back into its `{status, fieldErrors}` shape.
 *
 * The `"use server"` layer throws `Error("API error: <status>")` (legacy
 * string). A richer 422 may carry a JSON message
 * (`{kind:"market_api_error", status, fieldErrors}`) so the form can map each
 * field error inline. Falls back to extracting a 3-digit status from the
 * legacy string, then to a null/empty result so an unexpected error never
 * crashes the handler.
 */
function parseMarketApiError(err: unknown): MarketApiError {
  const message = err instanceof Error ? err.message : String(err ?? "");
  try {
    const parsed = JSON.parse(message) as Partial<MarketApiError> & {
      kind?: string;
    };
    if (parsed && parsed.kind === "market_api_error") {
      return {
        status: typeof parsed.status === "number" ? parsed.status : null,
        fieldErrors:
          parsed.fieldErrors && typeof parsed.fieldErrors === "object"
            ? parsed.fieldErrors
            : {},
      };
    }
  } catch {
    // Not JSON — fall through to the legacy string form.
  }
  const legacy = /(\d{3})/.exec(message);
  return {
    status: legacy ? Number(legacy[1]) : null,
    fieldErrors: {},
  };
}

const EMPTY_VALUES: MarketFormValues = {
  question: "",
  resolution_criteria: "",
  deadline: "",
  odds_yes: "0.5",
  category: "",
  min_stake: "",
  max_stake: "",
};

export function MarketForm({
  mode,
  marketId,
  initialValues,
  betCount = 0,
}: {
  mode: "create" | "edit";
  marketId?: string;
  initialValues?: MarketFormValues;
  betCount?: number;
}) {
  const router = useRouter();
  const [submitting, setSubmitting] = React.useState(false);
  const criteriaLocked = mode === "edit" && betCount > 0;

  const form = useForm<MarketFormValues>({
    resolver: zodResolver(MarketSchema),
    defaultValues: initialValues ?? EMPTY_VALUES,
    mode: "onSubmit",
  });

  const onSubmit = form.handleSubmit(async (values) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      // Optional fields: blank → omit (the backend treats omission as default).
      const category = values.category.trim() || undefined;
      const minStake = values.min_stake.trim() || undefined;
      const maxStake = values.max_stake.trim() || undefined;

      if (mode === "create") {
        const body: MarketCreateBody = {
          question: values.question.trim(),
          resolution_criteria: values.resolution_criteria.trim(),
          deadline: values.deadline,
          initial_odds_yes: values.odds_yes.trim(),
          ...(category !== undefined ? { category } : {}),
          ...(minStake !== undefined ? { min_stake: minStake } : {}),
          ...(maxStake !== undefined ? { max_stake: maxStake } : {}),
        };
        const created = await createMarket(body);
        toast.success("Market created.");
        const newId = (created as { id?: string } | null)?.id;
        router.push(newId ? `/admin/markets/${newId}` : "/admin/markets");
      } else {
        const body: MarketUpdateBody = {
          // Only send criteria when it is editable (ADM-07 lock).
          ...(criteriaLocked
            ? {}
            : { resolution_criteria: values.resolution_criteria.trim() }),
          deadline: values.deadline,
          odds_yes: values.odds_yes.trim(),
          ...(category !== undefined ? { category } : {}),
          ...(minStake !== undefined ? { min_stake: minStake } : {}),
          ...(maxStake !== undefined ? { max_stake: maxStake } : {}),
        };
        await updateMarket(marketId as string, body);
        toast.success("Market updated.");
        router.push(`/admin/markets/${marketId}`);
      }
    } catch (err) {
      const { status, fieldErrors } = parseMarketApiError(err);
      if (status === 401 || status === 403) {
        toast.error("Your session expired. Please sign in again.");
      } else if (status === 422 && Object.keys(fieldErrors).length > 0) {
        for (const [field, message] of Object.entries(fieldErrors)) {
          // Map the FORM odds field name regardless of the wire name.
          const formField = (
            field === "initial_odds_yes" ? "odds_yes" : field
          ) as keyof MarketFormValues;
          form.setError(formField, { type: "server", message });
        }
      } else {
        toast.error(
          mode === "create"
            ? "Couldn't create the market. Please try again."
            : "Couldn't save changes. Please try again.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Form {...form}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(e);
        }}
        className="flex max-w-lg flex-col gap-4"
        noValidate
      >
        <FormField
          control={form.control}
          name="question"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Question</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  placeholder="Will it rain tomorrow?"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="resolution_criteria"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Resolution criteria</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Describe exactly how this market resolves..."
                  disabled={criteriaLocked}
                  {...field}
                />
              </FormControl>
              {criteriaLocked ? (
                <FormDescription>
                  Resolution criteria are locked once a market has bets.
                </FormDescription>
              ) : null}
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="deadline"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Deadline</FormLabel>
              <FormControl>
                <Input type="datetime-local" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="odds_yes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Initial odds (YES)</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  inputMode="decimal"
                  placeholder="0.5"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                A probability between 0 and 1 (e.g. 0.5 for 50%).
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="category"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Category</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  placeholder="Optional — e.g. Sports"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="min_stake"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Min stake (PLAY_USD)</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  inputMode="decimal"
                  placeholder="Optional"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Leave blank to use the platform default limits.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="max_stake"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Max stake (PLAY_USD)</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  inputMode="decimal"
                  placeholder="Optional"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Leave blank to use the platform default limits.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div>
          <Button type="submit" disabled={submitting}>
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {mode === "create" ? "Create market" : "Save changes"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
