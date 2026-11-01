// account-delete: deletes the caller's own private data and the account (spec 10). The audit log keeps the action without personal data.
// An admin cannot delete themself here (the admin account is removed from the dashboard), so the system is never left without an admin.
import { createDeps, handle, json } from "../_shared/lib.ts";

export const handler = handle("active", async ({ body, user, profile, deps }) => {
  const db = deps.db;
  if (body.confirm !== true) return json(400, { error: "confirm_required" });
  if (profile?.role === "admin") return json(403, { error: "admin_cannot_self_delete" });
  const ports = await db.from("portfolios").select("id").eq("user_id", user.id);
  const ids = (ports.data ?? []).map((p: { id: number }) => p.id);
  if (ids.length) await db.from("portfolio_holdings").delete().in("portfolio_id", ids);
  await db.from("portfolios").delete().eq("user_id", user.id);
  await db.from("user_watchlist").delete().eq("user_id", user.id);
  await db.from("support_tickets").delete().eq("user_id", user.id);
  await db.from("user_notifications").delete().eq("user_id", user.id);
  await db.from("admin_audit_log").insert({ admin_id: null, action: "user_self_delete", target_type: "user", target_id: null, before: null, after: null });
  const r = await db.auth.admin.deleteUser(user.id);
  if (r.error) throw r.error;
  return json(200, { deleted: true });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
