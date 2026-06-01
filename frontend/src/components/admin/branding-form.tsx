/**
 * Plan 10-03 — Admin branding form (BrandingForm + ColorField + LogoUploadField).
 *
 * Mirrors `recharge-form.tsx`: "use client" + react-hook-form + zodResolver +
 * shadcn Form/FormField/FormItem/FormLabel/FormControl/FormMessage + a Loader2
 * submit spinner (disabled while pending) + sonner toast feedback.
 *
 * The zod schema MIRRORS the Plan 10-01 server contract for UX only — the
 * server is authoritative (D-09). Brand name min 1; each hex must match
 * `^#[0-9a-fA-F]{6}$`. The logo is validated client-side (256 KB cap +
 * PNG/JPEG/WebP/SVG allowlist) purely to surface fast inline feedback; the
 * backend re-validates (size + content-type + magic byte) and is the gate.
 *
 * On submit → `updateTenantConfig` (multipart PUT, Bearer forwarded
 * server-side). Success → the success toast. A 422 thrown error → map server
 * field errors to inline FormMessage (we surface the hex message on the color
 * fields, since hex is the server's only field-level 422). Any other error →
 * the failure toast.
 *
 * Submit button: the DEFAULT (non-destructive) Button variant labeled
 * "Save branding" — saving branding is an idempotent update, NOT a destructive
 * action (UI-SPEC A-SAVE / §Destructive actions: none this phase).
 */
"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { cn } from "@/lib/utils";
import { updateTenantConfig } from "@/lib/branding-admin-api";
import {
  parseBrandingApiError,
  type TenantConfigRead,
} from "@/lib/branding-types";

// Server-mirrored hex allowlist (D-09). UX-only — the server re-validates.
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const HEX_MESSAGE = "Enter a valid hex color, e.g. #4F46E5.";

// Logo client pre-check constants (UI-SPEC A-LOGO — drives the helper + error
// copy). The backend (Plan 10-01) is authoritative: 256 KB cap + allowlist.
const LOGO_MAX_BYTES = 256 * 1024;
const LOGO_ALLOWED_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/svg+xml",
];
const LOGO_TOO_LARGE = "Logo must be 256 KB or smaller.";
const LOGO_WRONG_TYPE = "Logo must be a PNG, JPEG, WebP, or SVG file.";

const BrandingSchema = z.object({
  brand_name: z.string().trim().min(1, "Brand name is required."),
  primary_hex: z.string().regex(HEX_RE, HEX_MESSAGE),
  secondary_hex: z.string().regex(HEX_RE, HEX_MESSAGE),
});

type BrandingValues = z.infer<typeof BrandingSchema>;

/**
 * A FormField wrapping a text Input plus a live swatch <div> whose background
 * reflects the current value. Invalid hex → the swatch falls back to a neutral
 * zinc fill (so a half-typed value never paints a misleading color) and the
 * inline FormMessage surfaces the hex error.
 */
function ColorField({
  control,
  name,
  label,
}: {
  control: ReturnType<typeof useForm<BrandingValues>>["control"];
  name: "primary_hex" | "secondary_hex";
  label: string;
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => {
        const valid = HEX_RE.test(field.value ?? "");
        return (
          <FormItem>
            <FormLabel>{label}</FormLabel>
            <div className="flex items-center gap-2">
              <span
                data-testid={`color-swatch-${name}`}
                aria-hidden="true"
                className="h-9 w-9 shrink-0 rounded-md border border-zinc-200"
                style={{
                  backgroundColor: valid ? field.value : "#f4f4f5",
                }}
              />
              <FormControl>
                <Input
                  type="text"
                  inputMode="text"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  placeholder="#4F46E5"
                  className="font-mono"
                  {...field}
                />
              </FormControl>
            </div>
            <FormMessage />
          </FormItem>
        );
      }}
    />
  );
}

export function BrandingForm({ initial }: { initial: TenantConfigRead }) {
  const [submitting, setSubmitting] = React.useState(false);
  const [logoFile, setLogoFile] = React.useState<File | null>(null);
  const [logoError, setLogoError] = React.useState<string | null>(null);
  const [logoPreview, setLogoPreview] = React.useState<string | null>(
    initial.logo_url,
  );
  // Track an object URL so we can revoke it (avoid leaking blob URLs).
  const objectUrlRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
      }
    };
  }, []);

  const form = useForm<BrandingValues>({
    resolver: zodResolver(BrandingSchema),
    defaultValues: {
      brand_name: initial.brand_name,
      primary_hex: initial.primary_hex,
      secondary_hex: initial.secondary_hex,
    },
    mode: "onSubmit",
  });

  function onLogoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setLogoError(null);

    if (!file) {
      setLogoFile(null);
      return;
    }

    // Client pre-check (UX only — the server is authoritative).
    if (!LOGO_ALLOWED_TYPES.includes(file.type)) {
      setLogoError(LOGO_WRONG_TYPE);
      setLogoFile(null);
      return;
    }
    if (file.size > LOGO_MAX_BYTES) {
      setLogoError(LOGO_TOO_LARGE);
      setLogoFile(null);
      return;
    }

    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
    }
    const url = URL.createObjectURL(file);
    objectUrlRef.current = url;
    setLogoPreview(url);
    setLogoFile(file);
  }

  const onSubmit = form.handleSubmit(async (values) => {
    if (submitting) return;
    // Block submit when the client logo pre-check is unresolved.
    if (logoError) return;
    setSubmitting(true);
    try {
      await updateTenantConfig({
        brand_name: values.brand_name.trim(),
        primary_hex: values.primary_hex,
        secondary_hex: values.secondary_hex,
        ...(logoFile ? { logo: logoFile } : {}),
      });
      toast.success(
        "Branding updated. Players see it on their next page load.",
      );
    } catch (err) {
      // The server is authoritative (D-09). Decode the real backend status +
      // structured field errors (WR-04) instead of degrading every failure to
      // "invalid fields".
      const { status, fieldErrors } = parseBrandingApiError(err);

      if (status === 401 || status === 403) {
        // Session expired / not an admin — this is NOT a field problem.
        toast.error("Your session expired. Please sign in again.");
      } else if (status === 422) {
        // Field-level validation rejection — map each server error to the
        // field that actually failed (brand_name vs a hex), not blanket onto
        // the colors. The server message for a hex mismatch is generic, so we
        // surface the friendlier HEX_MESSAGE on the color fields.
        const entries = Object.entries(fieldErrors);
        if (entries.length > 0) {
          for (const [field, message] of entries) {
            if (field === "primary_hex" || field === "secondary_hex") {
              form.setError(field, { type: "server", message: HEX_MESSAGE });
            } else if (field === "brand_name") {
              form.setError("brand_name", { type: "server", message });
            }
          }
        } else {
          // 422 with no recognizable field loc — surface a generic message
          // rather than blaming a specific (possibly valid) field.
          toast.error("Couldn't save branding. Check the fields and try again.");
        }
      } else {
        // 5xx / network / unknown — a server-side problem, not the user's input.
        toast.error("Couldn't save branding. Please try again in a moment.");
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
          name="brand_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Brand name</FormLabel>
              <FormControl>
                <Input type="text" placeholder="XPredict" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <ColorField
          control={form.control}
          name="primary_hex"
          label="Primary color"
        />
        <ColorField
          control={form.control}
          name="secondary_hex"
          label="Secondary color"
        />

        {/* LogoUploadField — file input + <img> object-URL preview. */}
        <FormItem>
          <FormLabel htmlFor="branding-logo">Logo</FormLabel>
          <FormControl>
            <Input
              id="branding-logo"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
              onChange={onLogoChange}
            />
          </FormControl>
          <FormDescription>PNG, JPEG, WebP or SVG. Max 256 KB.</FormDescription>
          <div data-testid="logo-preview" className="pt-1">
            {logoPreview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={logoPreview}
                alt="Logo preview"
                className="h-16 w-auto rounded-md border border-zinc-200 object-contain"
              />
            ) : (
              <p className="text-sm text-zinc-500">
                No logo uploaded — your brand name shows instead.
              </p>
            )}
          </div>
          {logoError ? (
            <p className={cn("text-sm font-medium text-red-500")} role="alert">
              {logoError}
            </p>
          ) : null}
        </FormItem>

        <div>
          <Button type="submit" disabled={submitting}>
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Save branding
          </Button>
        </div>
      </form>
    </Form>
  );
}
