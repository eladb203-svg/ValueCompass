// admin-tickets: list tickets, change a status, reply. Admin only; every change goes to admin_audit_log.
// A support / bug ticket changes status only here. A company_request follows the runner automatically (database trigger); the admin may change it by hand in exceptions.
// The notification to the ticket owner is created by the database trigger on the status / reply change.
// deno-lint-ignore-file no-explicit-any
import { audit, createDeps, handle, json } from "../_shared/lib.ts";

const STATUS: Record<string, string[]> = { company_request: ["open", "in_progress", "done", "failed"], support: ["open", "in_progress", "closed"], bug: ["open", "in_progress", "closed"] };

export const handler = handle("admin", async ({ body, user, deps }) => {
  const db = deps.db;
  if (body.action === "list") {
    let q = db.from("support_tickets").select("*").order("created_at", { ascending: false }).limit(200);
    if (typeof body.status === "string") q = q.eq("status", body.status);
    const { data } = await q;
    return json(200, { tickets: data ?? [] });
  }
  if (body.action === "update") {
    if (!Number.isInteger(body.ticket_id)) return json(400, { error: "invalid_request" });
    const { data: before } = await db.from("support_tickets").select("id, type, status, admin_reply, fail_reason").eq("id", body.ticket_id).maybeSingle();
    if (!before) return json(404, { error: "not_found" });
    const patch: any = {};
    if (body.status !== undefined) {
      if (!STATUS[before.type].includes(body.status)) return json(400, { error: "invalid_status" });
      patch.status = body.status;
      if (body.status === "failed") patch.fail_reason = typeof body.reason === "string" ? body.reason.slice(0, 300) : (before.fail_reason ?? "נקבע על ידי המנהל");
    }
    if (body.reply !== undefined) {
      if (typeof body.reply !== "string" || !body.reply.trim() || body.reply.length > 5000) return json(400, { error: "invalid_reply" });
      patch.admin_reply = body.reply.trim();
      patch.replied_at = deps.now().toISOString();
    }
    if (!Object.keys(patch).length) return json(400, { error: "nothing_to_update" });
    const up = await db.from("support_tickets").update(patch).eq("id", before.id).select("id, type, status, admin_reply, fail_reason").single();
    if (up.error) throw up.error;
    await audit(deps, user.id, "ticket_update", "ticket", String(before.id), before, up.data);
    return json(200, { ticket: up.data });
  }
  return json(400, { error: "unknown_action" });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
