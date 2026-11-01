// admin-invite: sends an invitation (Supabase Auth). The invited email becomes `active` by the sign-up trigger. Admin only; logged in admin_audit_log.
import { audit, createDeps, handle, json } from "../_shared/lib.ts";

export const handler = handle("admin", async ({ body, user, deps }) => {
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 200) return json(400, { error: "invalid_email" });
  const redirectTo = deps.env("SITE_URL");
  const r = await deps.db.auth.admin.inviteUserByEmail(email, { data: { invited_by: user.id }, ...(redirectTo ? { redirectTo } : {}) });
  if (r.error) return json(400, { error: "invite_failed", message: String(r.error.message ?? "").slice(0, 200) });
  await audit(deps, user.id, "invite", "user", r.data?.user?.id ?? null, null, { email });
  return json(200, { invited: email });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
