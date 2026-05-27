/**
 * Plan 02-04 — Shared zod schemas for the player auth surface.
 *
 * Lives in a SEPARATE module from `auth.ts` because Next.js 15 forbids
 * non-async (synchronous) exports from a file with the `"use server"`
 * directive. Server Actions can only export async functions — schemas,
 * constants, and pure helpers must live elsewhere.
 *
 * The schemas mirror the backend `validate_password` rules so the client
 * form can surface obvious mistakes before the Server Action is invoked.
 * The backend is always the authoritative validator.
 */
import { z } from "zod";

const passwordRule = z
  .string()
  .min(12, "Password must be at least 12 characters")
  .regex(/[A-Z]/, "Password must contain an uppercase letter")
  .regex(/[a-z]/, "Password must contain a lowercase letter")
  .regex(/\d/, "Password must contain a digit");

export const LoginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

export const RegisterSchema = z
  .object({
    email: z.string().email("Enter a valid email address"),
    password: passwordRule,
    confirm_password: z.string(),
    display_name: z.string().optional(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: "Passwords must match",
    path: ["confirm_password"],
  });

export const ForgotSchema = z.object({
  email: z.string().email("Enter a valid email address"),
});

export const ResetSchema = z
  .object({
    token: z.string().min(1, "Reset token is required"),
    password: passwordRule,
    confirm_password: z.string(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: "Passwords must match",
    path: ["confirm_password"],
  });

export const VerifySchema = z.object({
  token: z.string().min(1, "Verification token is required"),
});

/**
 * Plan 02-05 — Admin login schema.
 *
 * Mirror of `LoginSchema` but consumed by `adminLoginAction` which POSTs to
 * `/admin/auth/login` (OAuth2 username/password form, per Plan 02-03). The
 * client-side password length is intentionally NOT enforced here: admins are
 * SEEDED via `bin/create_admin.py`, which BYPASSES `UserManager.validate_password`
 * (operator-trusted bootstrap path). Backend remains authoritative.
 */
export const AdminLoginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

// Shared return-shape contract for Server Actions consumed via `useActionState`.
export type ActionErrors = Record<string, string[] | undefined> & {
  _form?: string[];
};

export type ActionState =
  | { errors: ActionErrors }
  | { success: true; message: string }
  | undefined;

export type VerifyResult = { status: "success" | "error"; detail?: string };
