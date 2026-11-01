// support-send: a support request or error report. Always saved in support_tickets; the admin gets an email through Resend when RESEND_API_KEY exists.
// Users get no email, only in-app notifications. Active user only. (The signed-out "can't sign in" form is not served here: a ticket needs an owner.)
// deno-lint-ignore-file no-explicit-any
import { createDeps, emailAdmin, handle, json } from "../_shared/lib.ts";

const DAILY_LIMIT = 20;                                             // per user: a runaway screen cannot flood the table

export const handler = handle("active", async ({ body, user, deps }) => {
  const db = deps.db;
  if (!["support", "bug"].includes(body.type)) return json(400, { error: "invalid_type" });
  if (typeof body.body !== "string" || !body.body.trim() || body.body.length > 5000) return json(400, { error: "invalid_body" });
  const since = new Date(deps.now().getTime() - 86400000).toISOString();
  const recent = await db.from("support_tickets").select("id").eq("user_id", user.id).neq("type", "company_request").gte("created_at", since);
  if ((recent.data?.length ?? 0) >= DAILY_LIMIT) return json(429, { error: "too_many_requests" });

  const tech = body.tech && typeof body.tech === "object" && !Array.isArray(body.tech) ? body.tech : {};
  let attach: any = null;
  if (body.attach_portfolio === true) {                             // the admin sees the portfolio only when the user attaches it
    const ports = await db.from("portfolios").select("id, portfolio_name").eq("user_id", user.id);
    const ids = (ports.data ?? []).map((p: any) => p.id);
    const hold = ids.length ? await db.from("portfolio_holdings").select("portfolio_id, company_id, quantity, average_cost, cost_currency").in("portfolio_id", ids) : { data: [] };
    attach = { portfolios: ports.data ?? [], holdings: hold.data ?? [] };
  }
  const ins = await db.from("support_tickets").insert({ user_id: user.id, type: body.type, body: body.body.trim(), tech, portfolio_attach: attach }).select("id, status").single();
  if (ins.error) throw ins.error;
  const emailed = await emailAdmin(deps, `ValueCompass: ${body.type === "bug" ? "תקלה" : "פנייה"} #${ins.data.id}`, `${body.body.trim()}\n\n${JSON.stringify(tech)}\nuser: ${user.id}`);
  return json(200, { ticket_id: ins.data.id, status: ins.data.status, emailed });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
