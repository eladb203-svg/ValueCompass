---
title: "ValueCompass — Stage K6 Specification: Data Loading and Database Connection"
subtitle: "2026-10-25_12-00 · English (source of truth) · approved"
---

# Stage K6 — Data Loading and Database Connection

**Purpose:** connect what was built in K1–K5 into one pipeline that loads a company's data into the database, scores it and keeps it current. K6 covers the code-side components of the system map (RESOLVE, AUDIT, SRC, DQ, REPAIR, PROV), the job runner, the daily AI queue, the automatic addition of a new company, and the database changes they need. Screens are K7.

**Principles:**

- Code collects, computes and decides. The AI only judges, extracts, classifies and writes text (decision of 2026-10-07; Rulebook R1).
- `financial_facts` is the only source of financial data, and the engine reads from it (DB decision of 2026-10-19).
- The first load runs on the free Gemini tier (decision of 2026-10-22). AI calls go through a daily queue that respects the quota.
- Same company + same data + same version = same score (R18). Every write is idempotent: running a job twice changes nothing.
- No write to Supabase without approval. Every migration and every load runs first on the test project (`valuecompass-test`), then on production (`ValueInvestConsult`).

**Sources:**

- Rulebook 2026-10-21_19-26: R5, R15, R17, R18, Part B, Part E with E1–E12.
- DB structure 2026-10-19_12-38.
- AI specification 2026-10-21_16-00.
- AI skills 2026-10-22_13-52 and 2026-10-21_12-39.
- System map 2026-10-21_12-17.

## 1. What exists today

| Area | Exists | Gap for K6 |
|---|---|---|
| Providers | SEC companyfacts, inline XBRL (extension tags), filing index, prices (yfinance), bank / insurance / real-estate facts, provider industry | No ticker → CIK resolution from SEC; no amendment / restatement handling; no FX provider (R15) |
| ETL | `src/etl`: field map, facts in the `financial_facts` shape, extraction store, inputs for the engine and the router | Reads from the local SEC cache, not from the DB |
| Engine | All cards, pricing, coverage, router (Part B) | Writes JSON files, not `score_runs` / `score_details` / `valuations` |
| AI | Scoring A1–A14 (template 3.1), C1, extraction B1–B14 (K5b), file store | Answers in `scripts/ai_store` (files); no queue; no daily budget across companies |
| DB | Migrations 1–7 on production: `financial_facts`, `dictionary_items` (252), `fact_tags`, `filing_periods`, `extraction_items`, `ai_assessments`, `score_runs`, `valuations`, extended `score_details` / `company_score_summary`, views | Legacy `financial_yearly` / `financial_ratios` (empty) still present; repositories still point at them; missing columns (section 6) |

## 2. The pipeline for one company

```
RESOLVE → AUDIT → SELECT SOURCE → COLLECT → DATA-QUALITY CHECKS → WRITE
   → ROUTER (profile) → SCORE without AI → AI QUEUE (C1 → B → A → D1) → SCORE with AI → D2
```

Each company has a **processing state**, which the K7 screen shows:

`resolved` → `data_loaded` → `scored_partial` → `ai_in_progress (n of m)` → `complete`, or `failed` / `unsupported`.

### 2.1 RESOLVE — company and listing

- **Input:** ticker, company name, CIK or ISIN.
- **US:** SEC `company_tickers.json` (ticker → CIK) and the submissions JSON for that CIK. The submissions JSON gives the name, former names, SIC, fiscal-year end, exchanges and the list of filings.
- **One company = one CIK.** Listings go in `company_listings`: share classes, ADRs, a primary listing flag. A ticker change updates the listing, not the company.
- **Listed-entity check (E2):** the ticker must map to the filing entity. After a merger, the price score is "cannot be priced" until the successor files its own annual report.
- **Unsupported in this stage:**
  - Issuers filing 20-F / 40-F (foreign private issuers, IFRS).
  - SPACs and asset-backed issuers (Part B, CL15).
  - Companies without an annual report on SEC.
  - The company is stored with state `unsupported` and a reason; nothing else runs.

### 2.2 AUDIT — what is missing

- **Needed history:** 10 fiscal years of financial facts, t−9 … t.
  - Graham 3.4, 3.5 and 3.6 and normalized EPS use 10 years.
  - Everything else uses 5 years (R5).
- **Comparison:** the annual reports filed (10-K, 10-K/A, 10-KT in the submissions list) against `filing_periods` in the DB.
- **Result:** a plan per year: `present`, `missing`, `superseded` (a newer filing or amendment exists) or `not_available` (before the first XBRL year).
- **Text and AI:**
  - Judgment questions (A1–A14), background (D1) and analysis (D2): **latest annual report only.**
  - Extraction (B1–B14): every year in the window where an item is missing. One call per skill per report, covering all periods shown in that report.

### 2.3 SELECT SOURCE (SRC)

Fixed hierarchy per item. The first source that has a value wins, and the source is recorded in `source_kind` and `tag_id`.

1. SEC companyfacts (XBRL).
2. Inline XBRL company-extension tags (E6).
3. Sum of four quarters, when an annual value exists only quarterly (E7).
4. FR Y-9C for US bank holding companies (E8).
5. AI extraction with a quote (B1–B14) → `extraction_items`, and into `financial_facts` only when approved.
6. Missing: no row. A collection failure is missing, not 0 (R17).

Israel (MAYA / ESEF) is added to this list in a later stage.

### 2.4 COLLECT

- **Existing providers.** The SEC raw files stay in a local file cache and are not stored in the DB (DB decision).
- **SEC rules:** a User-Agent with contact details, at most 10 requests per second.
- **Prices (yfinance):** one row per stock in `market_snapshot`, updated in place (E1).
- **Government yields (E4) and FX rates (R15):** reference tables `gov_yields` and `fx_rates`.

### 2.5 DATA-QUALITY CHECKS (DQ)

Run before writing. A failed check either rescales and flags, flags only, or holds the value (missing).

| Check | Rule | On failure |
|---|---|---|
| Share-count scale | C14 / E3 | Rescale and flag; larger mismatch → missing |
| Units and currency | Value in the reporting currency; conversion only where R15 requires | Hold + flag |
| Balance identity | Total assets = total liabilities + equity (incl. noncontrolling interests), within 1% | Flag the year |
| Signs | Revenue, total assets ≥ 0; expenses as reported | Flag |
| Restatement | A value differs between the original filing and a later one or an amendment | Take the latest filing; flag `restated`; recompute |
| Year coverage | Fewer than 3 years for a 5-year criterion, or fewer than 5 for a 10-year one | The engine marks the criterion missing (R5) |
| Reconciliations | E11 (FFO, Q6, RE29b), after the engine runs | Flag; extraction approval rules apply |
| Price freshness | E1: price not updated → flagged | No price score until reviewed |

### 2.6 WRITE

- **`financial_facts`:** upsert per company × year × item, with value, status, source kind, tag, flags and basis.
- **`filing_periods`:** accession, form, filing date, fiscal-year end, currency, calculation version.
- **`data_update_log`:** one row per job with counts, missing years and warnings.
- **Idempotent:** the same input writes nothing new.
- **Derived items:** FIN-070 and DRV-001 to DRV-006 are written by the engine with `source_kind = derived`.

### 2.7 SCORE

1. **Router (Part B):** profile, written to `companies.profile` and `company_profile_history` (E10).
2. **Engine:** reads `financial_facts`, approved extractions, AI answers and the price.
3. **Output:** a new `score_runs` row, then `score_details` (criterion and sub-item, with range and coverage), `valuations`, and `company_score_summary` (current state).
4. **First score:** computed right after the data load, **before the AI answers.** AI criteria show as pending (`ai_pending`) and the score as a range. Once the AI answers arrive, a new run.

### 2.8 AI QUEUE

- **Order inside a company:**
  1. C1, only when SIC and the provider industry do not decide.
  2. B extraction, only for missing items.
  3. A1–A14.
  4. D1 background.
  5. Score with AI.
  6. D2 analysis — generated by code, no AI call (Skills 2026-10-25_12-00, 3.3); needs the peer group and the final score.
- **Priority across companies:**
  1. A company a user asked for (new add).
  2. A new annual report.
  3. Bulk backfill.
- **Daily budget:**
  - RPD: the real quota is 500 per Google project; the code cap is 450 per day (shared daily counter, one process). Reset at midnight Pacific time (10:00 Israel).
  - RPM 12. Each attempt counts.
  - When the budget is spent the queue stops and resumes after the reset. Nothing is lost.
- **Calls per company:** about 12 for A1–A14 (measured in K5a-3) + extraction (measured in K5b) + 2 for D1 (English) and T1 (translation), plus retries. D2 costs no call.
- **Storage:** `ai_assessments`, `extraction_items` and a new table for D1/D2 texts (section 6). `scripts/ai_store` files are migrated once.

## 3. Job types (REPAIR) and schedule

| Job | Trigger | What it does |
|---|---|---|
| Initial import | New company | Full pipeline, 10 years |
| Year backfill | AUDIT finds missing years | Collect + write those years; rescore |
| New annual report | Daily check of the submissions list | Collect the new year; router (E10); AI for the new report; rescore |
| Amendment / restatement | 10-K/A, or DQ finds a restated value | Rewrite the affected years; flag; rescore |
| Repair | A failed DQ check fixed, or a code fix | Recompute from the cache; no new download unless needed |
| Price refresh | Daily close + intraday for hot stocks (section 3.1; E1) | `market_snapshot`; price scores and buy prices only (no new run of quality) |
| Yields and FX | Monthly / yearly (E4, R15) | Reference tables; price scores |
| Recompute all | New Rulebook or calculation version | New runs for all companies; AI answers re-asked only when a question or prompt version changes (R18) |

### 3.1 Schedule and scheduler (decided 2026-10-23)

**Scheduler inside the system.** One runner process holds the whole schedule and the queue in code (APScheduler). It records every run in `data_update_log`.

- **Starting it:** Windows Task Scheduler only starts the process when the PC starts.
- **A missed job:** a job missed while the PC was off runs as soon as the runner starts.
- **DB-only checks:** `pg_cron` in Supabase handles checks that live only in the database, e.g., flagging a price that was not refreshed (E1).
- **Moving to the cloud:** the same runner moves to the cloud before launch.

| Job | When (Israel time) | Notes |
|---|---|---|
| **Daily close prices, all stocks** | Once per exchange, after its close; overall window 10:00–23:00 | Updates price scores and the conclusion only. No AI, no new quality run, D2 unchanged |
| **Intraday prices, "hot" stocks** | Every 30–60 min during each exchange's trading hours, within 10:00–23:00 | **"Hot"** = held in a portfolio or on a watchlist and within about 10% above the buy price. Many tickers per request. Basis for future buy-price alerts |
| **New annual reports and amendments** | Daily 06:00 | **One request:** the SEC daily form index. Filter 10-K / 10-K/A for our CIKs, then queue those companies |
| **AI queue** | Daily from 10:00, after the Gemini quota reset | All AI work: new companies (priority), new annual reports, missing extraction. Stops at the daily budget and resumes the next day |
| **Government yields** | Monthly; annual value yearly | E4 |
| **FX rates** | Daily | R15 (used from the Israel stage) |
| **Missing-data audit** | Weekly | Finds years or items not loaded |

### 3.2 How the parts connect

| Connection | How | Stage |
|---|---|---|
| Python runner ↔ DB | Supabase service-role key, kept only on the runner | K6a |
| ETL ↔ sources | The existing providers, writing to the DB, with the job types above | K6b |
| AI queue ↔ Gemini ↔ DB | Answers and texts stored in tables instead of files | K6c |
| Schedule | Section 3.1 | K6d |
| Screen ↔ DB | supabase-js, read-only, RLS (each user sees only what is allowed) | K7 |
| Screen ↔ smart search | A Supabase Edge Function calls Gemini with a **separate key and Google project** (its own daily quota), so searches never use the loading quota | K7 |
| Screen → runner | **Through `work_queue`:** add company, import file or admin approval writes a request; the runner picks it up | K6c (queue) + K7 (buttons) |

## 4. Adding a company that is not in the DB (decided 2026-10-21)

1. **Search:** the user searches a ticker or name that is not in the DB. RESOLVE looks it up on SEC.
2. **Found and supported:**
   - The company is created.
   - An initial import is queued at priority 1.
   - The screen shows "מבצע עיבוד וניתוח של החברה, נא המתן מספר דקות" ("Processing and analysing the company, please wait a few minutes"), with the current state.
3. **How long it takes:**
   - **Code part:** minutes.
   - **AI part:** about 12–20 calls. With quota left this takes minutes; without quota, the next day, with the partial score shown meanwhile.
4. **Not found or unsupported:** a clear message with the reason.

## 5. Running place (open decision)

| Option | For | Against |
|---|---|---|
| **A. Local runner (your PC) — recommended for K6** | Works today; the cache and `.env` are there; no cost | Jobs run only when the PC is on; not suitable for a public app |
| B. Scheduled cloud runner (e.g., GitHub Actions on a schedule) | No server to maintain; free minutes for small jobs | SEC cache must be rebuilt or stored; secrets in the cloud |
| C. Small cloud server / container service | Always on; suits the public app (K7) | Monthly cost and maintenance |

**Decided (2026-10-22): A — local runner for K6.** Supabase holds all data; the PC only runs the code (collection, engine, AI calls) and keeps the code, `.env` secrets and the SEC download cache. When the PC is off, data in Supabase stays readable; only updates pause. B or C is decided before the app is opened to users (K7).

## 6. Database changes (migration 8 onward)

| # | Change | Why |
|---|---|---|
| 8 | Drop `financial_yearly`, `financial_ratios`, `financial_overview_view` (`supabase/pending/drop_legacy.sql`), together with rewriting `financial_repository.py` | Replaced by `financial_facts` and `v_display_metrics` |
| 9 | `companies`: add `cik` (unique), `sic`, `vc_industry`, `classification_tier`, `classification_status`, `processing_state`, `unsupported_reason`; the profile check in `companies`, `company_profile_history` and `score_runs` accepts `UNSUPPORTED` | Part B, CL15; open item from K4b |
| 10 | `extraction_items`: add `skill_id`, `skill_version`, `model`, `prompt_version`, `control` (jsonb: name, result, values) | Provenance (R18) and the approval queue |
| 11 | `ai_assessments`: add `accession`, `skill_version` | R18: source document per answer |
| 12 | New `ai_texts`: company, fiscal year, kind (`background` / `analysis`), language, text, model, prompt version, `run_id` for the analysis; `approval_status` (`pending_review` / `approved` / `failed`), `edited_by` (`ai` / `human`), `human_reviewed` (bool; false → the screen shows "תרגום אוטומטי"), `checks` (jsonb) — a Hebrew background that passes the checks is shown at once (Skills 2026-10-25_12-00) | D1 / D2 must be stored (the "texts not stored" rule is about report text, not generated text) |
| 13 | New `work_queue`: company, job type, fiscal year, skill, priority, state (`queued`, `running`, `done`, `failed`, `deferred_quota`), attempts, next run time, last error, payload | One queue for data jobs and AI tasks |
| 14 | `score_runs`: add `peer_group` (jsonb: company ids, definition, fallback flag) | D2 compares to a fixed group per run |
| 15 | View `v_company_status` for the screen: processing state, last run, AI progress | K7 |

All changes run first on `valuecompass-test` with the same checks as the DB stage (baseline identical to production), then on production after approval. RLS: users read approved rows only, as today.

## 7. Code changes

- **Repositories:**
  - `financial_repository` rewritten for `financial_facts` (read and write).
  - `company_repository` with the new columns.
  - New repositories for the queue, `ai_texts` and score outputs.
- **Engine input from the DB:** a new path builds exactly the same inputs as today's path from the cache. **Identity test:** for all 54 golden companies, inputs from the DB = inputs from the cache, and the scores equal the golden.
- **AI store:** `src/ai/store.py` keeps one interface with two back ends, files (tests) and DB (production).
- **Runner:** a command-line runner with these commands:
  - `load <ticker>`
  - `audit <ticker>`
  - `daily` (new reports, prices)
  - `ai-queue --budget N`
  - `backfill --universe <list>`
  - `status <ticker>`
- **Logging:** each job writes to `data_update_log`; each AI attempt keeps its `attempt_log`.

## 8. First load (data already in hand)

1. The 54 golden companies, from the local cache to `financial_facts` (identity test).
2. The earlier extraction CSV files (banks, insurance, real estate) → `extraction_items`, as **pending** (DB decision of 2026-10-18). AI extraction from K5b replaces or confirms them through the approval queue.
3. AI answers from `scripts/ai_store` (the final K5 run) → `ai_assessments`.
4. **Development set (decided 2026-10-22):** KO (STANDARD), MSFT (TECH), JPM (BANK), CB (INSURANCE), O (net-lease REIT), AMT (tower REIT), INTC (weak company). The 54 golden companies stay for code-only regression tests (no AI). More companies are loaded only after ETL, all scoring components and the display metrics are complete (end of K6).

## 9. Acceptance tests

| Test | Pass |
|---|---|
| Identity | 54 companies: DB inputs = cache inputs; scores = golden |
| Idempotency | Running the same job twice → 0 rows changed |
| Restatement | A simulated 10-K/A changes one value → flag, rewrite, new run |
| New report | A simulated new 10-K → new year, router, AI queued, new run |
| Quota | Budget 10 → the queue stops at 10, resumes on the next run, no duplicate answers |
| New company | An unknown ticker → resolved, loaded, partial score, then complete |
| Unsupported | A 20-F filer → `unsupported` with a reason |
| RLS | A regular user sees only approved extraction and AI rows |

## 10. Sub-stages

| Stage | Content |
|---|---|
| **K6a** | Migrations 8–11 on test, then production; repositories; engine input from the DB; identity test on 54 companies |
| **K6b** | RESOLVE, AUDIT, SRC, DQ, WRITE; job log; restatement and new-report handling; runner commands `load`, `audit`, `status` |
| **K6c** | `work_queue`, `ai_texts`, score outputs to the DB; AI queue with the daily budget; new-company flow; migration of the file store |
| **K6d** | Daily jobs (new reports, prices, yields, FX); first load of the wider universe |

## 11. Decisions (2026-10-22)

1. **Running place:** local runner for K6; cloud (B or C) decided before K7 opens to users.
2. **History depth:** 10 fiscal years — approved.
3. **Universe:** development set of 7 companies (section 8); wider loading only after K6 is complete.
4. **US only for now:** 20-F / 40-F filers, SPACs, asset-backed issuers and companies without SEC annual reports are unsupported. Israel next after K7; ESEF (Europe) and IFRS filers later.
5. **Earlier extraction CSVs:** a value confirmed by K5b is loaded as approved; all others as pending.
