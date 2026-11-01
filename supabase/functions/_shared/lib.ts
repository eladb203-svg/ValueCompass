// Shared helpers for the ValueCompass Edge Functions (security stage, spec 3a and 9).
// Every function: JWT -> user -> profile (status / role) -> action on the caller's own rows only. Tables are reached with the service role,
// so the checks here are the only gate: never skip them. Handlers take `deps`, so tests run with a fake database and no network.
// deno-lint-ignore-file no-explicit-any

export interface Deps {
  db: any;                                          // supabase-js client (service role) or the test fake
  env: (key: string) => string | undefined;
  fetch: typeof fetch;
  now: () => Date;
}

export type Need = "signed_in" | "active" | "admin";
export interface Ctx { req: Request; body: any; user: { id: string; email?: string }; profile: { id: string; role: string; status: string } | null; deps: Deps }

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

export async function createDeps(): Promise<Deps> {
  const { createClient } = await import("npm:@supabase/supabase-js@2");
  const url = Deno.env.get("SUPABASE_URL")!;
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  return { db: createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } }), env: (k) => Deno.env.get(k), fetch, now: () => new Date() };
}

/** Wraps a function body: CORS, POST only, JSON body, JWT -> user, status / role check, generic 500. */
export function handle(need: Need, fn: (c: Ctx) => Promise<Response>) {
  return async (req: Request, deps: Deps): Promise<Response> => {
    if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
    if (req.method !== "POST") return json(405, { error: "method_not_allowed" });
    try {
      const jwt = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
      if (!jwt) return json(401, { error: "unauthorized" });
      const { data, error } = await deps.db.auth.getUser(jwt);
      if (error || !data?.user) return json(401, { error: "unauthorized" });
      const user = { id: data.user.id as string, email: data.user.email as string | undefined };
      const { data: profile } = await deps.db.from("user_profiles").select("id, role, status").eq("id", user.id).maybeSingle();
      if (need !== "signed_in") {
        if (!profile || profile.status !== "active") return json(403, { error: "forbidden" });
        if (need === "admin" && profile.role !== "admin") return json(403, { error: "forbidden" });
      }
      let body: any = {};
      try { body = await req.json(); } catch { body = {}; }
      if (body === null || typeof body !== "object" || Array.isArray(body)) body = {};
      return await fn({ req, body, user, profile, deps });
    } catch (_e) {
      return json(500, { error: "server_error" });
    }
  };
}

export async function audit(deps: Deps, adminId: string, action: string, targetType: string, targetId: string | null, before: unknown, after: unknown) {
  const { error } = await deps.db.from("admin_audit_log").insert({ admin_id: adminId, action, target_type: targetType, target_id: targetId, before: before ?? null, after: after ?? null });
  if (error) throw new Error("audit_failed");
}

export const isTicker = (s: unknown): s is string => typeof s === "string" && /^[A-Z][A-Z0-9.\-]{0,9}$/.test(s);
export const normTicker = (s: unknown): string => String(s ?? "").trim().toUpperCase();

/** A company by id or symbol. -> row or null. */
export async function findCompany(deps: Deps, body: any): Promise<any | null> {
  if (Number.isInteger(body.company_id)) {
    const { data } = await deps.db.from("companies").select("id, symbol, company_name, processing_state").eq("id", body.company_id).maybeSingle();
    return data ?? null;
  }
  const sym = normTicker(body.symbol);
  if (!isTicker(sym)) return null;
  const { data } = await deps.db.from("companies").select("id, symbol, company_name, processing_state").eq("symbol", sym).limit(1);
  return data?.[0] ?? null;
}

/** Sends the admin an email through Resend. Never throws: the record is already saved. */
export async function emailAdmin(deps: Deps, subject: string, text: string): Promise<boolean> {
  const key = deps.env("RESEND_API_KEY");
  if (!key) return false;
  try {
    const { data } = await deps.db.from("app_settings").select("value").eq("key", "admin_email").maybeSingle();
    const to = data?.value ?? deps.env("ADMIN_EMAIL");
    if (!to) return false;
    const r = await deps.fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: deps.env("EMAIL_FROM") ?? "ValueCompass <onboarding@resend.dev>", to: [to], subject, text }),
    });
    return r.ok;
  } catch { return false; }
}

export const EMAIL_RX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Like `handle`, for a function with no sign-in (signup-request): CORS, POST only, JSON body, generic 500. `ip` is the caller's address. */
export function handlePublic(fn: (c: { req: Request; body: any; ip: string; deps: Deps }) => Promise<Response>) {
  return async (req: Request, deps: Deps): Promise<Response> => {
    if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
    if (req.method !== "POST") return json(405, { error: "method_not_allowed" });
    try {
      let body: any = {};
      try { body = await req.json(); } catch { body = {}; }
      if (body === null || typeof body !== "object" || Array.isArray(body)) body = {};
      const ip = (req.headers.get("cf-connecting-ip") ?? req.headers.get("x-forwarded-for") ?? "unknown").split(",")[0].trim() || "unknown";
      return await fn({ req, body, ip, deps });
    } catch (_e) {
      return json(500, { error: "server_error" });
    }
  };
}

export async function sha256Hex(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Sends the Supabase invitation (the user sets a password from the link and becomes `active` by the sign-up trigger). -> {ok, userId?, message?} */
export async function inviteUser(deps: Deps, adminId: string, email: string, name?: string): Promise<{ ok: boolean; userId: string | null; message?: string }> {
  const redirectTo = deps.env("SITE_URL");
  const data: any = { invited_by: adminId };
  if (name) data.full_name = name;
  const r = await deps.db.auth.admin.inviteUserByEmail(email, { data, ...(redirectTo ? { redirectTo } : {}) });
  if (r.error) return { ok: false, userId: null, message: String(r.error.message ?? "").slice(0, 200) };
  return { ok: true, userId: (r.data?.user?.id ?? null) as string | null };
}
