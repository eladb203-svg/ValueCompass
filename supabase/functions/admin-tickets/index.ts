// admin-tickets: list tickets, change a status, reply. Admin only; every change goes to admin_audit_log.
// A support / bug ticket changes status only here. A company_request follows the runner automatically (database trigger); the admin may change it by hand in exceptions.
// A sign-up request (type signup) is decided only by action "signup_decision": approve -> invitation email (same helper as admin-invite), status done; reject -> closed, no email.
// The notification to the ticket owner is created by the database trigger on the status / reply change.
// deno-lint-ignore-file no-explicit-any
import { audit, createDeps, handle, inviteUser, json } from "../_shared/lib.ts";

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
    if (before.type === "signup") return json(400, { error: "use_signup_decision" });
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
  if (body.action === "signup_decision") {
    if (!Number.isInteger(body.ticket_id) || !["approve", "reject"].includes(body.decision)) return json(400, { error: "invalid_request" });
    const { data: t } = await db.from("support_tickets").select("id, type, status, signup_name, signup_email").eq("id", body.ticket_id).maybeSingle();
    if (!t || t.type !== "signup") return json(404, { error: "not_found" });
    if (t.status !== "open") return json(409, { error: "already_decided" });
    if (body.decision === "approve") {
      const r = await inviteUser(deps, user.id, t.signup_email, t.signup_name);
      if (!r.ok) return json(400, { error: "invite_failed", message: r.message });           // the request stays open
      await audit(deps, user.id, "invite", "user", r.userId, null, { email: t.signup_email, from_ticket: t.id });
    }
    const up = await db.from("support_tickets").update({ status: body.decision === "approve" ? "done" : "closed" }).eq("id", t.id).select("id, type, status").single();
    if (up.error) throw up.error;
    await audit(deps, user.id, body.decision === "approve" ? "signup_approve" : "signup_reject", "ticket", String(t.id), { status: t.status }, { status: up.data.status });
    return json(200, { ticket: up.data });
  }
  return json(400, { error: "unknown_action" });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
