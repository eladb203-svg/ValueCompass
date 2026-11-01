// watchlist-add: add (or update the targets of) a company on the caller's own watchlist. Active user only.
// deno-lint-ignore-file no-explicit-any
import { createDeps, findCompany, handle, json } from "../_shared/lib.ts";

const TARGETS = ["target_buffett_quality_score", "target_buffett_price_score", "target_graham_quality_score", "target_graham_price_score"];

export const handler = handle("active", async ({ body, user, deps }) => {
  const db = deps.db;
  const company = await findCompany(deps, body);
  if (!company) return json(404, { error: "company_not_found" });
  const fields: any = { notes: typeof body.notes === "string" ? body.notes.slice(0, 1000) : null };
  for (const k of TARGETS) {
    if (body[k] === undefined || body[k] === null) fields[k] = null;
    else if (typeof body[k] === "number" && Number.isFinite(body[k])) fields[k] = body[k];
    else return json(400, { error: "invalid_" + k });
  }
  const { data: have } = await db.from("user_watchlist").select("id").eq("user_id", user.id).eq("company_id", company.id).maybeSingle();
  const r = have
    ? await db.from("user_watchlist").update(fields).eq("id", have.id).eq("user_id", user.id).select().single()
    : await db.from("user_watchlist").insert({ user_id: user.id, company_id: company.id, ...fields }).select().single();
  if (r.error) throw r.error;
  return json(200, { watch: r.data });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
