/**
 * Plan 17-04 — Event create/edit form (EVA-01, EVA-02).
 *
 * Clone of `market-form.tsx` (RHF + zodResolver + shadcn `Form*` + `Loader2` +
 * sonner + 422→inline mapping), with a DYNAMIC outcomes editor via
 * `useFieldArray` (min 2, each `{label, initial_odds∈(0,1)}`, add/remove with a
 * 2-floor). Create posts `CreateEventRequest`; edit posts `UpdateEventRequest`
 * (the outcomes are a whole-list replace).
 *
 * EDIT-LOCK (EVA-02): the backend returns HTTP 423 once any child has a bet,
 * which blocks the whole PATCH. Since the event read carries no bet count, the
 * lock is discovered on submit: a 423 sets `locked`, disables every field, and
 * shows the lock banner (the backend is authoritative).
 *
 * The zod schema mirrors the backend `event_schemas.py` for UX only — FastAPI is
 * authoritative. Money/odds stay strings (`Number()` only for the range check).
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Plus, X } from "lucide-react";
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
import { createEvent, updateEvent } from "@/lib/admin-events-api";
import {
  isEventLockedError,
  type CreateEventRequest,
  type UpdateEventRequest,
  type OutcomeInput,
} from "@/lib/admin-events-types";
import { isSessionExpiredError } from "@/components/admin/settlement-dialog-utils";

const DECIMAL_RE = /^\d*\.?\d+$/;

const outcomeSchema = z.object({
  label: z
    .string()
    .trim()
    .min(1, "A label is required.")
    .max(100, "Keep the label under 100 characters."),
  initial_odds: z
    .string()
    .trim()
    .min(1, "Enter odds between 0 and 1.")
    .refine((v) => {
      if (!DECIMAL_RE.test(v)) return false;
      const n = Number(v);
      return n > 0 && n < 1;
    }, "Enter odds between 0 and 1 (e.g. 0.5)."),
});

const EventSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "A title is required.")
    .max(500, "Keep the title under 500 characters."),
  category: z.string().trim().max(100, "Keep the category under 100 characters."),
  deadline: z
    .string()
    .min(1, "The deadline must be in the future.")
    .refine((v) => {
      const d = new Date(v);
      return !Number.isNaN(d.getTime()) && d.getTime() > Date.now();
    }, "The deadline must be in the future."),
  resolution_criteria: z
    .string()
    .trim()
    .max(2000, "Keep the criteria under 2000 characters."),
  outcomes: z
    .array(outcomeSchema)
    .min(2, "An event needs at least 2 outcomes."),
});

export interface EventFormValues {
  title: string;
  category: string;
  deadline: string;
  resolution_criteria: string;
  outcomes: { label: string; initial_odds: string }[];
}

const EMPTY_VALUES: EventFormValues = {
  title: "",
  category: "",
  deadline: "",
  resolution_criteria: "",
  outcomes: [
    { label: "", initial_odds: "" },
    { label: "", initial_odds: "" },
  ],
};

export function EventForm({
  mode,
  groupId,
  initialValues,
}: {
  mode: "create" | "edit";
  groupId?: string;
  initialValues?: EventFormValues;
}) {
  const router = useRouter();
  const [submitting, setSubmitting] = React.useState(false);
  const [locked, setLocked] = React.useState(false);

  const form = useForm<EventFormValues>({
    resolver: zodResolver(EventSchema),
    defaultValues: initialValues ?? EMPTY_VALUES,
    mode: "onSubmit",
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "outcomes",
  });

  const onSubmit = form.handleSubmit(async (values) => {
    if (submitting || locked) return;
    setSubmitting(true);
    try {
      const category = values.category.trim() || undefined;
      const criteria = values.resolution_criteria.trim() || undefined;
      const outcomes: OutcomeInput[] = values.outcomes.map((o) => ({
        label: o.label.trim(),
        initial_odds: o.initial_odds.trim(),
      }));

      if (mode === "create") {
        const body: CreateEventRequest = {
          title: values.title.trim(),
          deadline: values.deadline,
          outcomes,
          ...(category !== undefined ? { category } : {}),
          ...(criteria !== undefined ? { resolution_criteria: criteria } : {}),
        };
        const created = await createEvent(body);
        toast.success("Event created.");
        router.push(
          created?.slug ? `/admin/events/${created.slug}` : "/admin/events",
        );
      } else {
        const body: UpdateEventRequest = {
          title: values.title.trim(),
          deadline: values.deadline,
          outcomes,
          ...(category !== undefined ? { category } : { category: null }),
        };
        await updateEvent(groupId as string, body);
        toast.success("Event updated.");
        router.refresh();
      }
    } catch (err) {
      if (isEventLockedError(err)) {
        setLocked(true);
        toast.error("Outcomes are locked once the event has a bet.");
      } else if (isSessionExpiredError(err)) {
        toast.error("Your session expired. Please sign in again.");
      } else {
        toast.error(
          mode === "create"
            ? "Couldn't create the event. Please try again."
            : "Couldn't save changes. Please try again.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  });

  const outcomesError =
    form.formState.errors.outcomes?.root?.message ??
    form.formState.errors.outcomes?.message;

  return (
    <Form {...form}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(e);
        }}
        className="flex max-w-2xl flex-col gap-4"
        noValidate
      >
        {locked && (
          <div
            role="alert"
            className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-300"
          >
            This event has bets and can no longer be edited.
          </div>
        )}

        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Title</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  placeholder="Who will win the election?"
                  disabled={locked}
                  {...field}
                />
              </FormControl>
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
                  placeholder="Optional — e.g. Politics"
                  disabled={locked}
                  {...field}
                />
              </FormControl>
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
                <Input type="datetime-local" disabled={locked} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {mode === "create" && (
          <FormField
            control={form.control}
            name="resolution_criteria"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Resolution criteria</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder="Optional — describe how each outcome resolves..."
                    disabled={locked}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <fieldset className="flex flex-col gap-3" disabled={locked}>
          <legend className="text-sm font-medium">Outcomes</legend>
          <p className="text-sm text-zinc-500">
            At least 2 outcomes; each is an independent YES/NO market with an
            initial YES probability between 0 and 1.
          </p>
          {fields.map((arrayField, index) => (
            <div key={arrayField.id} className="flex items-start gap-2">
              <FormField
                control={form.control}
                name={`outcomes.${index}.label`}
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormControl>
                      <Input
                        type="text"
                        aria-label={`Outcome ${index + 1} label`}
                        placeholder="e.g. Candidate A"
                        disabled={locked}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name={`outcomes.${index}.initial_odds`}
                render={({ field }) => (
                  <FormItem className="w-28">
                    <FormControl>
                      <Input
                        type="text"
                        inputMode="decimal"
                        aria-label={`Outcome ${index + 1} odds`}
                        placeholder="0.5"
                        disabled={locked}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => remove(index)}
                disabled={locked || fields.length <= 2}
                aria-label={`Remove outcome ${index + 1}`}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ))}
          {outcomesError && (
            <p role="alert" className="text-sm font-medium text-red-500">
              {outcomesError}
            </p>
          )}
          <div>
            <Button
              type="button"
              variant="outline"
              onClick={() => append({ label: "", initial_odds: "" })}
              disabled={locked}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add outcome
            </Button>
          </div>
          {mode === "edit" && (
            <FormDescription>
              Editing outcomes replaces the full set; this is only allowed before
              the event has any bets.
            </FormDescription>
          )}
        </fieldset>

        <div>
          <Button type="submit" disabled={submitting || locked}>
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {mode === "create" ? "Create event" : "Save changes"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
