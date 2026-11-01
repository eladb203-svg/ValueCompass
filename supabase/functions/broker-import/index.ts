// broker-import (S2): import a broker file into the caller's own portfolio. The header is mapped to the fields, the rows stay in code.
// The AI mapping of the header and 5 rows needs a key (GEMINI_SEARCH_KEY, same project as smart search); without it the header is mapped by the synonym table below.
// Unknown tickers are requested through request-company (they enter the queue and complete over the following days). Active user only.
// deno-lint-ignore-file no-explicit-any
import { createDeps, handle, json, normTicker } from "../_shared/lib.ts";
import { requestCompany } from "../_shared/request.ts";

const SYN: Record<string, string[]> = {
  symbol: ["symbol", "ticker", "סימול", "סימבול", "מניה", "שם נייר"],
  quantity: ["quantity", "qty", "shares", "units", "כמות", "יחידות"],
  average_cost: ["average cost", "avg cost", "cost basis", "cost", "price", "עלות ממוצעת", "מחיר ממוצע", "עלות"],
};
const MAX_ROWS = 500;

export function mapHeader(headers: string[]): Record<string, number> {
  const out: Record<string, number> = {};
  headers.forEach((h, i) => {
    const t = String(h ?? "").trim().toLowerCase();
    for (const [field, names] of Object.entries(SYN)) if (!(field in out) && names.includes(t)) out[field] = i;
  });
  return out;
}

export function parseCsv(text: string): string[][] {
  return text.split(/\r?\n/).filter((l) => l.trim()).map((l) => l.split(l.includes("\t") ? "\t" : ",").map((c) => c.trim().replace(/^"|"$/g, "")));
}

export const handler = handle("active", async ({ body, user, deps }) => {
  const db = deps.db;
  const rows: string[][] = typeof body.csv === "string" ? parseCsv(body.csv) : Array.isArray(body.rows) ? body.rows : [];
  if (rows.length < 2) return json(400, { error: "no_rows" });
  if (rows.length > MAX_ROWS + 1) return json(400, { error: "too_many_rows" });
  const map = mapHeader(rows[0].map(String));
  if (!("symbol" in map) || !("quantity" in map)) return json(422, { error: "header_not_recognised", headers: rows[0] });

  const ports = await db.from("portfolios").select("id").eq("user_id", user.id).order("id").limit(1);
  let portfolioId = ports.data?.[0]?.id;
  if (!portfolioId) {
    const ins = await db.from("portfolios").insert({ user_id: user.id, portfolio_name: "התיק שלי" }).select("id").single();
    if (ins.error) throw ins.error;
    portfolioId = ins.data.id;
  }
  const res = { imported: 0, requested: [] as string[], skipped: [] as { row: number; reason: string }[] };
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    const symbol = normTicker(r[map.symbol]);
    const qty = Number(String(r[map.quantity] ?? "").replace(/,/g, ""));
    const cost = "average_cost" in map && r[map.average_cost] ? Number(String(r[map.average_cost]).replace(/,/g, "")) : null;
    if (!symbol || !Number.isFinite(qty) || qty <= 0 || (cost !== null && !Number.isFinite(cost))) { res.skipped.push({ row: i, reason: "invalid_row" }); continue; }
    const c = await db.from("companies").select("id").eq("symbol", symbol).limit(1);
    if (!c.data?.[0]) {
      const rq = await requestCompany(deps, user.id, symbol);
      if (rq.status === "in_progress" || rq.status === "ready") res.requested.push(symbol); else res.skipped.push({ row: i, reason: rq.status });
      continue;
    }
    const have = await db.from("portfolio_holdings").select("id").eq("portfolio_id", portfolioId).eq("company_id", c.data[0].id).limit(1);
    const fields = { quantity: qty, average_cost: cost };
    if (have.data?.[0]) await db.from("portfolio_holdings").update(fields).eq("id", have.data[0].id);
    else await db.from("portfolio_holdings").insert({ portfolio_id: portfolioId, company_id: c.data[0].id, cost_currency: "USD", ...fields });
    res.imported++;
  }
  return json(200, res);
});

if (Deno.env.get("SUPABASE_URL")) { const deps = await createDeps(); Deno.serve((req) => handler(req, deps)); }
