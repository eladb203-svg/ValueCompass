// portfolio-delete: delete a holding (holding_id) or a whole portfolio (portfolio_id) of the caller. Active user only.
import { createDeps, handle, json } from "../_shared/lib.ts";

export const handler = handle("active", async ({ body, user, deps }) => {
  const db = deps.db;
  if (body.holding_id !== undefined) {
    const { data: h } = await db.from("portfolio_holdings").select("id, portfolio_id").eq("id", body.holding_id).maybeSingle();
    if (!h) return json(404, { error: "not_found" });
    const { data: own } = await db.from("portfolios").select("id").eq("id", h.portfolio_id).eq("user_id", user.id).maybeSingle();
    if (!own) return json(404, { error: "not_found" });
    await db.from("portfolio_holdings").delete().eq("id", h.id);
    return json(200, { deleted: "holding", id: h.id });
  }
  if (body.portfolio_id !== undefined) {
    const { data: own } = await db.from("portfolios").select("id").eq("id", body.portfolio_id).eq("user_id", user.id).maybeSingle();
    if (!own) return json(404, { error: "not_found" });
    await db.from("portfolio_holdings").delete().eq("portfolio_id", own.id);
    await db.from("portfolios").delete().eq("id", own.id).eq("user_id", user.id);
    return json(200, { deleted: "portfolio", id: own.id });
  }
  return json(400, { error: "holding_id_or_portfolio_id_required" });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
