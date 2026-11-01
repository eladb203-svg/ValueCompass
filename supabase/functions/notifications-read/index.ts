// notifications-read: mark the caller's own notifications as read (all of them, or the given ids). Active user only.
import { createDeps, handle, json } from "../_shared/lib.ts";

export const handler = handle("active", async ({ body, user, deps }) => {
  let q = deps.db.from("user_notifications").update({ read_at: deps.now().toISOString() }).eq("user_id", user.id).is("read_at", null);
  if (Array.isArray(body.ids)) {
    const ids = body.ids.filter((i: unknown) => Number.isInteger(i));
    if (!ids.length) return json(200, { marked: 0 });
    q = q.in("id", ids);
  }
  const { data, error } = await q.select("id");
  if (error) throw error;
  return json(200, { marked: data?.length ?? 0 });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
