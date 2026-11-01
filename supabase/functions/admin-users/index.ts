// admin-users: list users, approve / disable (status), change role, holding counts. Admin only; every change goes to admin_audit_log.
// The admin screens never show a user's portfolio or watchlist: only counts per company (v_holding_counts, no user ids).
// deno-lint-ignore-file no-explicit-any
import { audit, createDeps, handle, json } from "../_shared/lib.ts";

export const handler = handle("admin", async ({ body, user, deps }) => {
  const db = deps.db;
  if (body.action === "list") {
    const { data: profiles } = await db.from("user_profiles").select("id, full_name, role, status, invited_by, created_at");
    const emails = new Map<string, string>();
    const l = await db.auth.admin.listUsers({ page: 1, perPage: 1000 });
    for (const u of l.data?.users ?? []) emails.set(u.id, u.email);
    return json(200, { users: (profiles ?? []).map((p: any) => ({ ...p, email: emails.get(p.id) ?? null })) });
  }
  if (body.action === "holding_counts") {
    const { data } = await db.from("v_holding_counts").select("*");
    return json(200, { counts: data ?? [] });
  }
  if (body.action === "set_status" || body.action === "set_role") {
    const field = body.action === "set_status" ? "status" : "role";
    const allowed = field === "status" ? ["pending", "active", "disabled"] : ["user", "admin"];
    if (typeof body.user_id !== "string" || !allowed.includes(body.value)) return json(400, { error: "invalid_request" });
    if (body.user_id === user.id) return json(400, { error: "cannot_change_self" });
    const { data: before } = await db.from("user_profiles").select("id, role, status").eq("id", body.user_id).maybeSingle();
    if (!before) return json(404, { error: "not_found" });
    const up = await db.from("user_profiles").update({ [field]: body.value }).eq("id", body.user_id).select("id, role, status").single();
    if (up.error) throw up.error;
    await audit(deps, user.id, body.action, "user", body.user_id, before, up.data);
    return json(200, { user: up.data });
  }
  return json(400, { error: "unknown_action" });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
