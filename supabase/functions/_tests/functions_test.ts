// Deno tests for the Edge Functions: fake database, fake fetch, no network. Run:  deno test supabase/functions/_tests/
// deno-lint-ignore-file no-explicit-any
import { assertEquals } from "jsr:@std/assert@1";
import { type Deps } from "../_shared/lib.ts";
import { handler as portfolioSave } from "../portfolio-save/index.ts";
import { handler as portfolioDelete } from "../portfolio-delete/index.ts";
import { handler as adminUsers } from "../admin-users/index.ts";
import { handler as adminTickets } from "../admin-tickets/index.ts";
import { handler as supportSend } from "../support-send/index.ts";
import { handler as smartSearch } from "../smart-search/index.ts";
import { handler as requestCompany } from "../request-company/index.ts";
import { handler as notificationsRead } from "../notifications-read/index.ts";
import { handler as signupRequest } from "../signup-request/index.ts";
import { handler as brokerImport, mapHeader } from "../broker-import/index.ts";

/** A tiny in-memory stand-in for the supabase-js query builder (eq / in / is / ilike / gte / neq / order / limit / select / insert / update / delete). */
class Q {
  f: Array<(r: any) => boolean> = []; op = "select"; payload: any; lim = 1e9; ret = false;
  constructor(private db: Fake, private t: string) {}
  select(_c?: string) { this.ret = true; return this; }
  insert(p: any) { this.op = "insert"; this.payload = p; return this; }
  update(p: any) { this.op = "update"; this.payload = p; return this; }
  delete() { this.op = "delete"; return this; }
  eq(c: string, v: any) { this.f.push((r) => r[c] === v); return this; }
  neq(c: string, v: any) { this.f.push((r) => r[c] !== v); return this; }
  in(c: string, v: any[]) { this.f.push((r) => v.includes(r[c])); return this; }
  is(c: string, v: any) { this.f.push((r) => (r[c] ?? null) === v); return this; }
  gte(c: string, v: any) { this.f.push((r) => r[c] >= v); return this; }
  ilike(c: string, v: string) { const rx = new RegExp("^" + v.replace(/%/g, ".*") + "$", "i"); this.f.push((r) => rx.test(String(r[c] ?? ""))); return this; }
  order() { return this; }
  limit(n: number) { this.lim = n; return this; }
  single() { return this.run(true); }
  maybeSingle() { return this.run(true); }
  then(res: any, rej: any) { return this.run(false).then(res, rej); }
  async run(one: boolean) {
    const rows = this.db.t(this.t);
    const hit = () => rows.filter((r) => this.f.every((p) => p(r)));
    let out: any[] = [];
    if (this.op === "insert") {
      const items = Array.isArray(this.payload) ? this.payload : [this.payload];
      for (const it of items) { const row = { id: this.db.next++, created_at: "2026-11-01T00:00:00.000Z", ...it }; rows.push(row); out.push(row); }
    } else if (this.op === "update") { out = hit(); out.forEach((r) => Object.assign(r, this.payload)); }
    else if (this.op === "delete") { out = hit(); for (const r of out) rows.splice(rows.indexOf(r), 1); }
    else out = hit().slice(0, this.lim);
    out = out.map((r) => ({ ...r }));                       // like the real client: the caller gets copies, not the stored rows
    return one ? { data: out[0] ?? null, error: null } : { data: out, error: null };
  }
}
class Fake {
  tables: Record<string, any[]> = {}; next = 100; emailed: any[] = [];
  users: Record<string, any> = {};
  t(n: string) { return (this.tables[n] ??= []); }
  from(n: string) { return new Q(this, n); }
  rpc(n: string) { return Promise.resolve({ data: n === "smart_search_take" ? this.cap-- > 0 : null, error: null }); }
  cap = 1;
  auth = {
    getUser: (jwt: string) => Promise.resolve(this.users[jwt] ? { data: { user: this.users[jwt] }, error: null } : { data: null, error: { message: "bad" } }),
    admin: { deleteUser: () => Promise.resolve({ error: null }), listUsers: () => Promise.resolve({ data: { users: [] } }), inviteUserByEmail: (email: string) => Promise.resolve({ data: { user: { id: "inv-" + email } }, error: null }) },
  };
}
function world() {
  const db = new Fake();
  db.users = { tA: { id: "A", email: "a@x" }, tB: { id: "B", email: "b@x" }, tAdmin: { id: "ADM", email: "adm@x" }, tPending: { id: "P", email: "p@x" } };
  db.tables.user_profiles = [{ id: "A", role: "user", status: "active" }, { id: "B", role: "user", status: "active" }, { id: "ADM", role: "admin", status: "active" }, { id: "P", role: "user", status: "pending" }];
  db.tables.companies = [{ id: 1, symbol: "KO", company_name: "Coca-Cola", processing_state: "complete" }];
  const deps: Deps = { db, env: (_k) => undefined, fetch: (() => Promise.reject(new Error("no network in tests"))) as any, now: () => new Date("2026-11-01T00:00:00Z") };
  return { db, deps };
}
const call = (h: any, deps: Deps, token: string | null, body: any = {}, method = "POST") =>
  h(new Request("http://x/", { method, headers: token ? { Authorization: `Bearer ${token}` } : {}, body: method === "POST" ? JSON.stringify(body) : undefined }), deps);

Deno.test("no token -> 401; unknown token -> 401; GET -> 405", async () => {
  const { deps } = world();
  assertEquals((await call(portfolioSave, deps, null)).status, 401);
  assertEquals((await call(portfolioSave, deps, "nope")).status, 401);
  assertEquals((await call(portfolioSave, deps, "tA", {}, "GET")).status, 405);
});

Deno.test("pending user is refused by every user function (403)", async () => {
  const { deps } = world();
  for (const h of [portfolioSave, portfolioDelete, supportSend, smartSearch, requestCompany, notificationsRead, brokerImport]) assertEquals((await call(h, deps, "tPending", { quantity: 1 })).status, 403);
});

Deno.test("non-admin calls an admin function -> 403, nothing written", async () => {
  const { db, deps } = world();
  assertEquals((await call(adminUsers, deps, "tA", { action: "set_role", user_id: "A", value: "admin" })).status, 403);
  assertEquals((await call(adminTickets, deps, "tA", { action: "list" })).status, 403);
  assertEquals(db.t("user_profiles").find((p) => p.id === "A").role, "user");
  assertEquals(db.t("admin_audit_log").length, 0);
});

Deno.test("admin set_status writes the audit log with before and after; cannot change self", async () => {
  const { db, deps } = world();
  const r = await call(adminUsers, deps, "tAdmin", { action: "set_status", user_id: "P", value: "active" });
  assertEquals(r.status, 200);
  const log = db.t("admin_audit_log");
  assertEquals([log.length, log[0].before.status, log[0].after.status, log[0].admin_id], [1, "pending", "active", "ADM"]);
  assertEquals((await call(adminUsers, deps, "tAdmin", { action: "set_role", user_id: "ADM", value: "user" })).status, 400);
});

Deno.test("user B cannot change or delete A's holding, even by id; the answer is 404", async () => {
  const { db, deps } = world();
  db.tables.portfolios = [{ id: 10, user_id: "A" }];
  db.tables.portfolio_holdings = [{ id: 50, portfolio_id: 10, company_id: 1, quantity: 5 }];
  assertEquals((await call(portfolioSave, deps, "tB", { holding_id: 50, quantity: 999 })).status, 404);
  assertEquals((await call(portfolioDelete, deps, "tB", { holding_id: 50 })).status, 404);
  assertEquals((await call(portfolioDelete, deps, "tB", { portfolio_id: 10 })).status, 404);
  assertEquals(db.t("portfolio_holdings")[0].quantity, 5);
  assertEquals((await call(portfolioSave, deps, "tA", { holding_id: 50, quantity: 7 })).status, 200);
  assertEquals(db.t("portfolio_holdings")[0].quantity, 7);
});

Deno.test("portfolio-save creates the caller's own default portfolio; a foreign portfolio_id is refused", async () => {
  const { db, deps } = world();
  db.tables.portfolios = [{ id: 10, user_id: "A" }];
  assertEquals((await call(portfolioSave, deps, "tB", { symbol: "KO", quantity: 1, portfolio_id: 10 })).status, 404);
  assertEquals((await call(portfolioSave, deps, "tB", { symbol: "KO", quantity: 1 })).status, 200);
  assertEquals(db.t("portfolios").filter((p) => p.user_id === "B").length, 1);
  assertEquals((await call(portfolioSave, deps, "tB", { symbol: "KO", quantity: -1 })).status, 400);
});

Deno.test("support-send always saves; the email goes only to the admin and only with a key; the attached portfolio is the caller's", async () => {
  const { db, deps } = world();
  db.tables.app_settings = [{ key: "admin_email", value: "admin@x" }];
  db.tables.portfolios = [{ id: 10, user_id: "A" }, { id: 11, user_id: "B" }];
  db.tables.portfolio_holdings = [{ id: 1, portfolio_id: 10, company_id: 1, quantity: 5 }, { id: 2, portfolio_id: 11, company_id: 1, quantity: 9 }];
  let r = await call(supportSend, deps, "tA", { type: "bug", body: "it broke", attach_portfolio: true });
  assertEquals(r.status, 200);
  const t = db.t("support_tickets")[0];
  assertEquals([t.user_id, t.type, t.portfolio_attach.holdings.length, t.portfolio_attach.holdings[0].quantity], ["A", "bug", 1, 5]);
  assertEquals((await r.json()).emailed, false);                              // no RESEND_API_KEY: saved, no email
  const sent: any[] = [];
  const d2: Deps = { ...deps, env: (k) => (k === "RESEND_API_KEY" ? "k" : undefined), fetch: ((u: string, init: any) => { sent.push([u, JSON.parse(init.body)]); return Promise.resolve({ ok: true }); }) as any };
  r = await call(supportSend, d2, "tA", { type: "support", body: "question" });
  assertEquals([(await r.json()).emailed, sent[0][1].to], [true, ["admin@x"]]);
  assertEquals((await call(supportSend, deps, "tA", { type: "other", body: "x" })).status, 400);
});

Deno.test("smart-search: no key -> regular search, no smart wording; cap reached -> regular search", async () => {
  const { deps } = world();
  let r = await call(smartSearch, deps, "tA", { query: "coca" });
  let j = await r.json();
  assertEquals([r.status, j.results.length, JSON.stringify(j).includes("smart")], [200, 1, false]);
  const d2: Deps = { ...deps, env: (k) => (k === "GEMINI_SEARCH_KEY" ? "k" : undefined), fetch: (() => Promise.reject(new Error("must not be called when the cap is reached"))) as any };
  (d2.db as Fake).cap = 0;
  r = await call(smartSearch, d2, "tA", { query: "coca" });
  j = await r.json();
  assertEquals(j.results.length, 1);
});

Deno.test("smart-search with Gemini: tickers are validated and looked up; the model never invents a result", async () => {
  const { db, deps } = world();
  db.tables.companies.push({ id: 2, symbol: "PEP", company_name: "PepsiCo", processing_state: "complete" });
  const d2: Deps = { ...deps, env: (k) => (k === "GEMINI_SEARCH_KEY" ? "k" : undefined),
    fetch: (() => Promise.resolve({ ok: true, json: () => Promise.resolve({ candidates: [{ content: { parts: [{ text: JSON.stringify({ tickers: ["pep", "ZZZ", "not a ticker!!"] }) }] } }] }) })) as any };
  (db as Fake).cap = 5;
  const j = await (await call(smartSearch, d2, "tA", { query: "the other cola company" })).json();
  assertEquals(j.results.map((r: any) => r.symbol), ["PEP"]);
});

Deno.test("a search with no result calls request-company automatically (ticker-like query)", async () => {
  const { db, deps } = world();
  const d2: Deps = { ...deps, fetch: ((u: string) => Promise.resolve({ ok: true, json: () => Promise.resolve(u.includes("company_tickers") ? { "0": { cik_str: 1, ticker: "ABCD", title: "Abcd Inc" } } : { sic: "3570", filings: { recent: { form: ["10-K"] } } }) })) as any };
  const j = await (await call(smartSearch, d2, "tA", { query: "abcd" })).json();
  assertEquals([j.not_found, j.request.status, j.request.message], [true, "in_progress", "בעיבוד — יושלם בהמשך"]);
  const q = db.t("work_queue")[0];
  assertEquals([q.priority, q.job_type, q.state], [1, "initial_import", "queued"]);
  const t = db.t("support_tickets")[0];
  assertEquals([t.type, t.requested_ticker, t.user_id, t.status], ["company_request", "ABCD", "A", "open"]);
  await call(requestCompany, d2, "tA", { ticker: "ABCD" });                    // the same request again: no second ticket, no second task
  assertEquals([db.t("support_tickets").length, db.t("work_queue").length], [1, 1]);
});

Deno.test("request-company: not found, 20-F filer, SEC down -> reason and a prefilled report form; nothing queued", async () => {
  const { db, deps } = world();
  const mk = (tickers: any, sub: any, ok = true): Deps => ({ ...deps, fetch: ((u: string) => Promise.resolve({ ok, json: () => Promise.resolve(u.includes("company_tickers") ? tickers : sub) })) as any });
  let j = await (await call(requestCompany, mk({}, {}), "tA", { ticker: "NOPE" })).json();
  assertEquals([j.status, j.reason, !!j.report_form], ["unsupported", "הטיקר לא נמצא ברשימת ה-SEC — ייתכן שהחברה התמזגה או נמחקה מהמסחר", true]);
  const failed = db.t("support_tickets");
  assertEquals([failed.length, failed[0].type, failed[0].status, failed[0].fail_reason, failed[0].requested_ticker, failed[0].user_id], [1, "company_request", "failed", j.reason, "NOPE", "A"]);
  await call(requestCompany, mk({}, {}), "tA", { ticker: "NOPE" });                    // asked again: still one failed request
  j = await (await call(requestCompany, mk({ "0": { cik_str: 2, ticker: "FORN", title: "Foreign" } }, { sic: "3570", filings: { recent: { form: ["20-F"] } } }), "tA", { ticker: "FORN" })).json();
  assertEquals([j.status, j.report_form.type], ["unsupported", "support"]);
  j = await (await call(requestCompany, mk({}, {}, false), "tA", { ticker: "DOWN" })).json();
  assertEquals(j.status, "unavailable");
  j = await (await call(requestCompany, deps, "tA", { ticker: "bad ticker!" })).json();
  assertEquals(j.status, "invalid");
  assertEquals([db.t("work_queue").length, db.t("support_tickets").length], [0, 1]);   // only the failed request of NOPE; nothing queued
});

Deno.test("admin-tickets: status values follow the ticket type; the change is audited", async () => {
  const { db, deps } = world();
  db.tables.support_tickets = [{ id: 1, type: "support", status: "open", user_id: "A" }, { id: 2, type: "company_request", status: "in_progress", user_id: "A", requested_ticker: "X" }];
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "update", ticket_id: 1, status: "done" })).status, 400);
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "update", ticket_id: 1, status: "closed", reply: "fixed" })).status, 200);
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "update", ticket_id: 2, status: "failed", reason: "no 10-K" })).status, 200);
  assertEquals([db.t("support_tickets")[1].fail_reason, db.t("admin_audit_log").length], ["no 10-K", 2]);
});

const signup = (deps: Deps, body: any, ip = "1.1.1.1") =>
  signupRequest(new Request("http://x/", { method: "POST", headers: { "x-forwarded-for": ip }, body: JSON.stringify(body) }), deps);

Deno.test("signup-request: no sign-in -> a request is saved, no account, admin emailed; closed mode refuses; bad input refused", async () => {
  const { db, deps } = world();
  db.tables.app_settings = [{ key: "registration_mode", value: "open" }, { key: "admin_email", value: "adm@x" }];
  deps.env = (k) => (k === "RESEND_API_KEY" ? "k" : undefined);
  const sent: any[] = [];
  deps.fetch = ((_u: string, init: any) => { sent.push(JSON.parse(init.body)); return Promise.resolve({ ok: true }); }) as any;
  assertEquals((await signup(deps, { name: "Dana", email: " Dana@X.com " })).status, 200);
  const t = db.t("support_tickets")[0];
  assertEquals([t.type, t.signup_email, t.signup_name, t.user_id ?? null, t.status ?? "open", t.ip_hash.length], ["signup", "dana@x.com", "Dana", null, "open", 64]);
  assertEquals([db.t("user_profiles").length, sent.length, sent[0].to], [4, 1, ["adm@x"]]);   // no profile added; one email, to the admin
  assertEquals((await signup(deps, { name: "", email: "a@b.co" })).status, 400);
  assertEquals((await signup(deps, { name: "x", email: "nope" })).status, 400);
  db.t("app_settings")[0].value = "invite";
  assertEquals((await signup(deps, { name: "Dana", email: "d2@x.com" })).status, 403);
});

Deno.test("signup-request: 3 per email and 5 per IP in 24 hours", async () => {
  const { db, deps } = world();
  db.tables.app_settings = [{ key: "registration_mode", value: "open" }];
  for (let i = 0; i < 3; i++) assertEquals((await signup(deps, { name: "E", email: "e@x.com" }, "9.9.9." + i)).status, 200);
  assertEquals((await signup(deps, { name: "E", email: "e@x.com" }, "9.9.9.9")).status, 429);
  for (let i = 0; i < 2; i++) assertEquals((await signup(deps, { name: "F", email: `f${i}@x.com` }, "7.7.7.7")).status, 200);
  assertEquals((await signup(deps, { name: "F", email: "f9@x.com" }, "7.7.7.7")).status, 200);
  assertEquals((await signup(deps, { name: "F", email: "f8@x.com" }, "7.7.7.7")).status, 200);
  assertEquals((await signup(deps, { name: "F", email: "f7@x.com" }, "7.7.7.7")).status, 200);
  assertEquals((await signup(deps, { name: "F", email: "f6@x.com" }, "7.7.7.7")).status, 429);
});

Deno.test("admin-tickets: approving a sign-up request invites the email; rejecting closes it without an email; non-admin refused; decided twice -> 409", async () => {
  const { db, deps } = world();
  const invited: string[] = [];
  db.auth.admin.inviteUserByEmail = ((e: string) => { invited.push(e); return Promise.resolve({ data: { user: { id: "u1" } }, error: null }); }) as any;
  db.tables.support_tickets = [{ id: 1, type: "signup", status: "open", signup_name: "Dana", signup_email: "d@x.com" }, { id: 2, type: "signup", status: "open", signup_name: "Rot", signup_email: "r@x.com" }];
  assertEquals((await call(adminTickets, deps, "tA", { action: "signup_decision", ticket_id: 1, decision: "approve" })).status, 403);
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "update", ticket_id: 1, status: "closed" })).status, 400);
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "signup_decision", ticket_id: 1, decision: "approve" })).status, 200);
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "signup_decision", ticket_id: 2, decision: "reject" })).status, 200);
  assertEquals((await call(adminTickets, deps, "tAdmin", { action: "signup_decision", ticket_id: 1, decision: "reject" })).status, 409);
  assertEquals([invited, db.t("support_tickets").map((t) => t.status)], [["d@x.com"], ["done", "closed"]]);
  assertEquals(db.t("admin_audit_log").map((a) => a.action), ["invite", "signup_approve", "signup_reject"]);
});

Deno.test("notifications-read marks only the caller's", async () => {
  const { db, deps } = world();
  db.tables.user_notifications = [{ id: 1, user_id: "A", read_at: null }, { id: 2, user_id: "B", read_at: null }];
  const j = await (await call(notificationsRead, deps, "tA", {})).json();
  assertEquals([j.marked, db.t("user_notifications")[1].read_at], [1, null]);
});

Deno.test("broker-import: header mapping, known tickers imported, unknown ones requested, bad rows skipped", async () => {
  assertEquals(mapHeader(["Ticker", "Shares", "Avg Cost"]), { symbol: 0, quantity: 1, average_cost: 2 });
  const { db, deps } = world();
  const d2: Deps = { ...deps, fetch: (() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })) as any };
  const j = await (await call(brokerImport, d2, "tA", { csv: "Ticker,Shares,Avg Cost\nKO,10,50\nZZZ,5,1\nKO,abc,2" })).json();
  assertEquals([j.imported, j.skipped.length, db.t("portfolio_holdings").length], [1, 2, 1]);
});
