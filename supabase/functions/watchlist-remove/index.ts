// watchlist-remove: remove a company from the caller's own watchlist. Active user only.
import { createDeps, findCompany, handle, json } from "../_shared/lib.ts";

export const handler = handle("active", async ({ body, user, deps }) => {
  const company = await findCompany(deps, body);
  if (!company) return json(404, { error: "company_not_found" });
  await deps.db.from("user_watchlist").delete().eq("user_id", user.id).eq("company_id", company.id);
  return json(200, { removed: company.id });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
