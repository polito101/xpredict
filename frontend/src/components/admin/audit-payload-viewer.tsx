/**
 * Plan 08-03 — Collapsible audit JSONB payload viewer (D-12).
 *
 * Collapsed by default: one-line `JSON.stringify` preview truncated to 80 chars
 * in muted text, with a chevron toggle. Expanded: a `<pre>` block of
 * `JSON.stringify(payload, null, 2)`. `aria-expanded` tracks state; the
 * expanded region is `role="region"` aria-labelled "Audit event payload"
 * (UI-SPEC §Accessibility). No prettifying per event type in v1 — raw JSON.
 */
"use client";

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { truncate } from "@/lib/admin-format";

export function AuditPayloadViewer({
  payload,
}: {
  payload: Record<string, unknown>;
}) {
  const [expanded, setExpanded] = React.useState(false);
  const regionId = React.useId();

  const oneLine = React.useMemo(() => {
    try {
      return truncate(JSON.stringify(payload), 80);
    } catch {
      return "{…}";
    }
  }, [payload]);

  const pretty = React.useMemo(() => {
    try {
      return JSON.stringify(payload, null, 2);
    } catch {
      return String(payload);
    }
  }, [payload]);

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={regionId}
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1 text-left text-xs text-muted-foreground hover:text-foreground"
      >
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        )}
        <span className={cn("font-mono", !expanded && "truncate")}>
          {expanded ? "Hide payload" : oneLine}
        </span>
      </button>
      {expanded && (
        <pre
          id={regionId}
          role="region"
          aria-label="Audit event payload"
          className="overflow-x-auto rounded-md bg-surface p-4 text-xs font-mono text-foreground"
        >
          {pretty}
        </pre>
      )}
    </div>
  );
}
