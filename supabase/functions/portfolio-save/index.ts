// portfolio-save: add or change a holding in the caller's own portfolio (spec 3a). Active user only.
// deno-lint-ignore-file no-explicit-any
import { createDeps, findCompany, handle, json } from "../_shared/lib.ts";

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

export const handler = handle("active", async ({ body, user, deps }) => {
  const db = deps.db;
  const quantity = num(body.quantity);
  if (quantity === null || quantity <= 0) return json(400, { error: "invalid_quantity" });
  const cost = body.average_cost === undefined || body.average_cost === null ? null : num(body.average_cost);
  if (body.average_cost !== undefined && body.average_cost !== null && (cost === null || cost < 0)) return json(400, { error: "invalid_average_cost" });

  // the portfolio: the caller's own (a given id is checked), or the first one, or a new default
  let portfolioId: number;
  if (body.portfolio_id !== undefined) {
    const { data } = await db.from("portfolios").select("id").eq("id", body.portfolio_id).eq("user_id", user.id).maybeSingle();
    if (!data) return json(404, { error: "not_found" });
    portfolioId = data.id;
  } else {
    const { data } = await db.from("portfolios").select("id").eq("user_id", user.id).order("id").limit(1);
    if (data?.[0]) portfolioId = data[0].id;
    else {
      const ins = await db.from("portfolios").insert({ user_id: user.id, portfolio_name: "התיק שלי" }).select("id").single();
      if (ins.error) throw ins.error;
      portfolioId = ins.data.id;
    }
  }

  const fields: any = {
    quantity, average_cost: cost, cost_currency: typeof body.cost_currency === "string" ? body.cost_currency.slice(0, 3).toUpperCase() : "USD",
    first_buy_date: typeof body.first_buy_date === "string" ? body.first_buy_date : null, notes: typeof body.notes === "string" ? body.notes.slice(0, 1000) : null,
  };

  if (body.holding_id !== undefined) {                              // change: the holding must sit in one of the caller's portfolios
    const { data: h } = await db.from("portfolio_holdings").select("id, portfolio_id").eq("id", body.holding_id).maybeSingle();
    if (!h) return json(404, { error: "not_found" });
    const { data: own } = await db.from("portfolios").select("id").eq("id", h.portfolio_id).eq("user_id", user.id).maybeSingle();
    if (!own) return json(404, { error: "not_found" });             // the same answer for "not yours" and "does not exist"
    const up = await db.from("portfolio_holdings").update(fields).eq("id", h.id).select().single();
    if (up.error) throw up.error;
    return json(200, { holding: up.data });
  }
  const company = await findCompany(deps, body);
  if (!company) return json(404, { error: "company_not_found" });
  const ins = await db.from("portfolio_holdings").insert({ portfolio_id: portfolioId, company_id: company.id, ...fields }).select().single();
  if (ins.error) throw ins.error;
  return json(200, { holding: ins.data });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
