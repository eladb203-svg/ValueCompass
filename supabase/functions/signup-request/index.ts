// signup-request: the public sign-up form (name + email, no password, no sign-in). Saves a support_tickets row of type 'signup'; NO account is created.
// The admin gets an email (Resend, when a key exists) and sees the request in admin-tickets; approval sends the invitation.
// Limits per 24 hours: 5 requests per IP (stored only as a hash) and 3 per email. Works only while registration_mode = 'open'.
// Deploy with verify_jwt = false (no sign-in exists at this point).
import { createDeps, EMAIL_RX, emailAdmin, handlePublic, json, sha256Hex } from "../_shared/lib.ts";

const PER_IP = 5;
const PER_EMAIL = 3;

export const handler = handlePublic(async ({ body, ip, deps }) => {
  const db = deps.db;
  const name = typeof body.name === "string" ? body.name.trim() : "";
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!name || name.length > 100) return json(400, { error: "invalid_name" });
  if (!EMAIL_RX.test(email) || email.length > 200) return json(400, { error: "invalid_email" });
  const { data: mode } = await db.from("app_settings").select("value").eq("key", "registration_mode").maybeSingle();
  if (mode?.value !== "open") return json(403, { error: "registration_closed" });

  const since = new Date(deps.now().getTime() - 86400000).toISOString();
  const ipHash = await sha256Hex(ip);
  const byIp = await db.from("support_tickets").select("id").eq("type", "signup").eq("ip_hash", ipHash).gte("created_at", since);
  const byEmail = await db.from("support_tickets").select("id").eq("type", "signup").eq("signup_email", email).gte("created_at", since);
  if ((byIp.data?.length ?? 0) >= PER_IP || (byEmail.data?.length ?? 0) >= PER_EMAIL) return json(429, { error: "too_many_requests" });

  const ins = await db.from("support_tickets").insert({ type: "signup", signup_name: name, signup_email: email, ip_hash: ipHash }).select("id").single();
  if (ins.error) throw ins.error;
  await emailAdmin(deps, `ValueCompass: בקשת הרשמה #${ins.data.id}`, `${name} <${email}>\nלאישור או דחייה: דף המנהל.`);
  return json(200, { received: true });
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
