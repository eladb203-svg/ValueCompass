// request-company: request a stock that is not in the database (spec 3a). The screen calls it automatically when a search finds nothing.
// Found and supported: queued at priority 1 ("בעיבוד — יושלם בהמשך"). Not found / unsupported: the reason plus a prefilled report form. Active user only.
import { createDeps, handle, json } from "../_shared/lib.ts";
import { requestCompany } from "../_shared/request.ts";

export const handler = handle("active", async ({ body, user, deps }) => json(200, await requestCompany(deps, user.id, body.ticker)));

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
