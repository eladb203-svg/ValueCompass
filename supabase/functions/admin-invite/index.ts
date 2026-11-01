// admin-invite: sends an invitation (Supabase Auth). The invited email becomes `active` by the sign-up trigger. Admin only; logged in admin_audit_log.
// Also used by admin-tickets when a sign-up request is approved (same helper, inviteUser).
import { audit, createDeps, EMAIL_RX, handle, inviteUser, json } from "../_shared/lib.ts";

export const handler = handle("admin", async ({ body, user, deps }) => {
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!EMAIL_RX.test(email) || email.length > 200) return json(400, { error: "invalid_email" });
  const r = await inviteUser(deps, user.id, email);
  if (!r.ok) return json(400, { error: "invite_failed", message: r.message });
  await audit(deps, user.id, "invite", "user", r.userId, null, { email });
  return json(200, { invited: email });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
