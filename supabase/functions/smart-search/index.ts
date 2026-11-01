// smart-search: one search bar (spec 5). Ticker / name matching first; otherwise S1 (Gemini, its own key) behind it, within a global daily cap.
// No GEMINI_SEARCH_KEY or the cap is reached or Gemini fails: the regular search answers, silently. The reply never mentions smart search.
// Nothing found and the query looks like a ticker: request-company runs automatically. Active user only.
// deno-lint-ignore-file no-explicit-any
import { createDeps, handle, isTicker, json, normTicker, type Deps } from "../_shared/lib.ts";
import { requestCompany } from "../_shared/request.ts";

const COLS = "id, symbol, company_name, exchange, country, processing_state";

async function regular(deps: Deps, q: string): Promise<any[]> {
  const like = q.replace(/[%_,()]/g, " ").trim();
  if (!like) return [];
  const a = await deps.db.from("companies").select(COLS).ilike("symbol", like + "%").limit(10);
  const b = await deps.db.from("companies").select(COLS).ilike("company_name", "%" + like + "%").limit(10);
  const seen = new Map<number, any>();
  for (const r of [...(a.data ?? []), ...(b.data ?? [])]) seen.set(r.id, r);
  const exact = like.toUpperCase();
  return [...seen.values()].sort((x, y) => (y.symbol === exact ? 1 : 0) - (x.symbol === exact ? 1 : 0)).slice(0, 10);
}

/** S1: the model proposes tickers; each one is validated and looked up in the database (the model never produces a result by itself). */
async function smart(deps: Deps, q: string): Promise<any[]> {
  const key = deps.env("GEMINI_SEARCH_KEY");
  if (!key) return [];
  const take = await deps.db.rpc("smart_search_take");
  if (take.error || take.data !== true) return [];                  // cap reached (or unreadable): fall back silently
  try {
    const model = deps.env("GEMINI_SEARCH_MODEL") ?? "gemini-2.5-flash-lite";
    const r = await deps.fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": key },
      body: JSON.stringify({
        contents: [{ parts: [{ text: `Return JSON {"tickers":[...]}: up to 5 US stock tickers that best match this search text. Text: ${JSON.stringify(q.slice(0, 100))}` }] }],
        generationConfig: { responseMimeType: "application/json", temperature: 0 },
      }),
    });
    if (!r.ok) return [];
    const j = await r.json();
    const parsed = JSON.parse(j?.candidates?.[0]?.content?.parts?.[0]?.text ?? "{}");
    const tickers = (Array.isArray(parsed.tickers) ? parsed.tickers : []).map(normTicker).filter(isTicker).slice(0, 5);
    if (!tickers.length) return [];
    const { data } = await deps.db.from("companies").select(COLS).in("symbol", tickers);
    return data ?? [];
  } catch { return []; }
}

export const handler = handle("active", async ({ body, user, deps }) => {
  const q = typeof body.query === "string" ? body.query.trim().slice(0, 100) : "";
  if (!q) return json(400, { error: "query_required" });
  let results = await regular(deps, q);
  if (!results.length) results = await smart(deps, q);
  if (results.length) return json(200, { results });
  const out: any = { results: [], not_found: true };
  const t = normTicker(q);
  if (isTicker(t) && !/\s/.test(q)) out.request = await requestCompany(deps, user.id, t);
  return json(200, out);
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
