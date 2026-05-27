/**
 * Plan 02-05 Task 2 — Admin login page (server component shell).
 *
 * `/admin/login` is the SOLE `/admin/*` route the Edge middleware allows
 * through without an `admin_jwt` cookie. The admin section's layout
 * (`app/admin/layout.tsx`) renders the top navigation; this page renders
 * the centered Card + AdminLoginForm.
 *
 * Visual distinction from `/login`:
 *   - "Admin sign in" heading (vs "Sign in" on the player surface).
 *   - Submit button "Sign in as admin" (vs "Sign in" on the player form).
 *   - Lives at `/admin/login` (not `/login`).
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AdminLoginForm } from "./admin-login-form";

export default function AdminLoginPage() {
  return (
    <div className="min-h-[calc(100vh-65px)] flex items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Admin sign in</CardTitle>
        </CardHeader>
        <CardContent>
          <AdminLoginForm />
        </CardContent>
      </Card>
    </div>
  );
}
