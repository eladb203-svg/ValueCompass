// Request a company that is not in the database (spec 3a). Used by request-company, smart-search and broker-import.
// RESOLVE-lite against SEC: ticker -> CIK (company_tickers.json) -> submissions (annual-report form family). Supported 10-K filers are
// inserted as `resolved` and queued at priority 1 (the runner continues exactly as for any new company). Every request is a support_tickets row
// of type company_request, so the user gets notifications as the runner moves the company (database trigger).
// deno-lint-ignore-file no-explicit-any
import { type Deps, isTicker, normTicker } from "./lib.ts";

export type RequestResult =
  | { status: "ready"; company_id: number; symbol: string }
  | { status: "in_progress"; company_id: number | null; symbol: string; message: string }
  | { status: "unsupported" | "invalid" | "unavailable"; symbol: string; reason: string; report_form: any };

export const REASON_NOT_IN_SEC = "הטיקר לא נמצא ברשימת ה-SEC — ייתכן שהחברה התמזגה או נמחקה מהמסחר";
const MSG_PROCESSING = "בעיבוד — יושלם בהמשך";
const ANNUAL = ["10-K", "10-K/A", "10-KT", "10-KT/A", "10-K405", "10-K405/A"];
const FOREIGN = ["20-F", "20-F/A", "40-F", "40-F/A"];

function reportForm(symbol: string, reason: string) {
  return { type: "support", subject: "בקשה להוספת חברה", body: `ביקשתי להוסיף את ${symbol}. הסיבה שהוצגה: ${reason}`, tech: { requested_ticker: symbol, stage: "request-company", reason } };
}

async function secJson(deps: Deps, url: string): Promise<any | null> {
  const ua = deps.env("SEC_USER_AGENT") ?? "ValueCompass admin@example.invalid";
  const r = await deps.fetch(url, { headers: { "User-Agent": ua, Accept: "application/json" } });
  if (!r.ok) throw new Error("sec_unavailable");                          // not the same as "not found": the user is asked to try again
  return await r.json();
}

export async function requestCompany(deps: Deps, userId: string, rawTicker: unknown): Promise<RequestResult> {
  const symbol = normTicker(rawTicker);
  if (!isTicker(symbol)) return { status: "invalid", symbol, reason: "סימול לא תקין", report_form: reportForm(symbol, "סימול לא תקין") };
  const db = deps.db;

  let { data: rows } = await db.from("companies").select("id, symbol, processing_state, unsupported_reason").eq("symbol", symbol).limit(1);
  let company = rows?.[0] ?? null;
  if (company?.processing_state === "complete") return { status: "ready", company_id: company.id, symbol };
  if (company?.processing_state === "unsupported") {
    const reason = company.unsupported_reason ?? "חברה שאינה נתמכת";
    return { status: "unsupported", symbol, reason, report_form: reportForm(symbol, reason) };
  }

  if (!company) {
    let tickers: any; let hitSub: any = null; let hit: any = null; let cik = "";
    try {
    tickers = await secJson(deps, "https://www.sec.gov/files/company_tickers.json");
    hit = Object.values(tickers as Record<string, any>).find((t: any) => String(t.ticker).toUpperCase() === symbol) as any;
    if (hit) { cik = String(hit.cik_str).padStart(10, "0"); hitSub = await secJson(deps, `https://data.sec.gov/submissions/CIK${cik}.json`); }
    } catch { return { status: "unavailable", symbol, reason: "בדיקת ה-SEC אינה זמינה כרגע, נסו שוב בעוד כמה דקות", report_form: reportForm(symbol, "SEC לא זמין") }; }
    if (!hit) {                                                              // not in the SEC list: unsupported, and the request is recorded as failed with the reason
      const again = await db.from("support_tickets").select("id").eq("user_id", userId).eq("type", "company_request").eq("requested_ticker", symbol).eq("status", "failed").eq("fail_reason", REASON_NOT_IN_SEC).limit(1);
      if (!again.data?.[0]) await db.from("support_tickets").insert({ user_id: userId, type: "company_request", requested_ticker: symbol, status: "failed", fail_reason: REASON_NOT_IN_SEC, body: null });
      return { status: "unsupported", symbol, reason: REASON_NOT_IN_SEC, report_form: reportForm(symbol, REASON_NOT_IN_SEC) };
    }
    const sub = hitSub;
    const forms: string[] = sub?.filings?.recent?.form ?? [];
    let reason: string | null = null;
    if (sub?.sic === "6770") reason = "חברת שיק פתוח (SPAC)";
    else if (sub?.sic === "6189") reason = "מנפיק ניירות ערד מגובי נכסים";
    else if (!forms.some((f) => ANNUAL.includes(f))) reason = forms.some((f) => FOREIGN.includes(f)) ? "מגישה דוח 20-F / 40-F (עדיין לא נתמך)" : "אין דוח שנתי 10-K";
    if (reason) return { status: "unsupported", symbol, reason, report_form: reportForm(symbol, reason) };
    const ins = await db.from("companies").insert({
      symbol, company_name: hit.title ?? symbol, exchange: "US", country: "US", reporting_currency: "USD", cik, sic: sub?.sic ?? null, processing_state: "resolved", is_active: true,
    }).select("id, symbol, processing_state").single();
    if (ins.error) {                                                         // a concurrent request created it: use that row
      const again = await db.from("companies").select("id, symbol, processing_state").eq("symbol", symbol).limit(1);
      company = again.data?.[0] ?? null;
      if (!company) throw new Error("company_insert_failed");
    } else company = ins.data;
  }

  // the work queue: priority 1, unless a task of this kind is already open (then it is lifted to priority 1)
  const open = await db.from("work_queue").select("id, priority").eq("company_id", company.id).eq("job_type", "initial_import").in("state", ["queued", "running", "deferred_quota"]).limit(1);
  if (open.data?.[0]) {
    if (open.data[0].priority > 1) await db.from("work_queue").update({ priority: 1 }).eq("id", open.data[0].id);
  } else {
    await db.from("work_queue").insert({ company_id: company.id, job_type: "initial_import", priority: 1, state: "queued", attempts: 0, next_run_at: deps.now().toISOString(), payload: { requested: true } });
  }

  // who asked: one open request per user and ticker (unique index); a repeat request is the same request
  const t = await db.from("support_tickets").select("id").eq("user_id", userId).eq("type", "company_request").eq("requested_ticker", symbol).in("status", ["open", "in_progress"]).limit(1);
  if (!t.data?.[0]) {
    const status = ["data_loaded", "scored_partial", "ai_in_progress"].includes(company.processing_state) ? "in_progress" : "open";
    await db.from("support_tickets").insert({ user_id: userId, type: "company_request", requested_ticker: symbol, company_id: company.id, status, body: null });
  }
  return { status: "in_progress", company_id: company.id, symbol, message: MSG_PROCESSING };
}
