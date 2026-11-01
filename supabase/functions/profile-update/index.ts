// profile-update: the caller changes only the display name and the language. role / status / invited_by are never read from the request.
// deno-lint-ignore-file no-explicit-any
import { createDeps, handle, json } from "../_shared/lib.ts";

export const handler = handle("active", async ({ body, user, deps }) => {
  const patch: any = {};
  if (body.full_name !== undefined) {
    if (typeof body.full_name !== "string" || body.full_name.length > 100) return json(400, { error: "invalid_full_name" });
    patch.full_name = body.full_name.trim();
  }
  if (body.preferred_language !== undefined) {
    if (!["he", "en"].includes(body.preferred_language)) return json(400, { error: "invalid_language" });
    patch.preferred_language = body.preferred_language;
  }
  if (!Object.keys(patch).length) return json(400, { error: "nothing_to_update" });
  const r = await deps.db.from("user_profiles").update(patch).eq("id", user.id).select("full_name, preferred_language").single();
  if (r.error) throw r.error;
  return json(200, { profile: r.data });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
