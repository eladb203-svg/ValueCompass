---
title: "ValueCompass — System Component Map"
subtitle: "2026-10-21_12-17 · English (source of truth)"
---

# System Component Map

**Purpose:** for every component — what it is, its type, and the stage in which it is built. **Principle (decision of 2026-10-07; Rulebook R1):** code collects, computes and decides; the AI only judges defined questions, extracts from text, classifies when no structured source decides, and writes text. **Language:** English is the source of truth; the Hebrew version is a translation.

**Types:** **Code** = backend logic · **Job** = scheduled or background job · **DB** = database structure · **AI** = skill (details in the AI specification) · **UI** = screen.

## 1. Flow

```
Resolve company → audit what is missing → select source → collect (source providers / AI extraction) → data-quality checks
   → backfill / repair / update → DB (financial_facts, extraction_items)
   → profile router → calculation engine (AI judgment answers as inputs) → 4 scores, value, buy price
   → analysis, background, search, portfolio and watchlist → screens
```

## 2. Components

| Layer | Component | Type | What it does | Stage | Status |
|---|---|---|---|---|---|
| **Identity** | Company and listing resolution (RESOLVE) | Code | Ticker / ISIN / TASE number / name → company + listing (ADR, dual listing) | K6 | Partial: `company_listings` |
| | Add a new company | Job + UI | Company not found → added automatically, "processing and analysing" | K6–K7 | — |
| **Collection** | Audit what is missing (AUDIT) | Code | Filed reports vs what exists in the DB → what is needed | K6 | — |
| | Source selection (SRC) | Code | Fixed hierarchy: SEC → ESEF → Magna → AI reading of the report | K6 | SEC provider exists |
| | Source providers | Code | SEC companyfacts and inline XBRL; prices; yields; FX | K6 | SEC and prices exist |
| | Input layer in the financial_facts shape | Code | Item → dictionary key, state per item | K2 | ✅ |
| | Extraction from text | AI (#16–#29) | Untagged items, with a quote | K5 | — |
| **Quality** | Data-quality checks (DQ) | Code | Units, currency, balance identity, scale (C14), reconciliations (E11), restatement | K6 | Partly in the engine |
| | Backfill / repair / update (REPAIR) | Code + Job | Job type from the audit result: initial import, year backfill, repair, new report | K6 | — |
| | Provenance (PROV) | DB | Tag per fact, document per extraction, filing per year | ✅ structure | ✅ |
| | Approval queue | UI + DB | Items for admin approval, with quote, control and impact | K7 | Tables exist |
| **Calculation** | Profile router (METH) | Code | Profile per Part B | K4b | ✅ |
| | Industry classification, tier 3 | AI (#15) | When SIC and provider industry do not decide | K5 | Interface exists |
| | Scoring and valuation engine | Code | All cards, pricing, coverage | K1–K3 | ✅ |
| | Judgment questions | AI (#1–#14) | 2 / 1 / 0 with a quote; input to the engine | K5 | Written (A1–A14) |
| | Peer group (PEER) | Code | Fixed group: same profile and same industry, with a fallback group when few companies | K5 (before the analysis) | — |
| **Content** | Company background | AI (#30) | Product, segments, markets, business environment, competitors, advantage (from the moat answer) | K5 | — |
| | Results analysis | AI (#31) | Two paragraphs: what drove quality and price, peer comparison; once per scoring run | End of K5 | — |
| | Score-change explanation (CHANGE) | Code (+ a sentence in #31) | Difference between two runs and its cause | K7 | — |
| **Search** | Plain search | Code | Name / ticker, incl. typos | K7 | — |
| | Smart search | AI (#32) + Code | Free text → structured filter; code searches | K7 | — |
| **Storage** | DB structure | DB | financial_facts, extraction, AI answers, runs, valuations, views | ✅ | ✅ (migration 8 in K6) |
| | Engine and ETL connected to the DB | Code | Write and read | K6 | — |
| **App** | Company page, lists, portfolio, watchlist, admin screen | UI | Per the display specification | K7 | Part 1 in the spec |
| | Portfolio analysis (PORT), watchlist alerts (WATCH), summary report (REPORT) | Code + UI (+ optional AI text) | — | After K7 | — |
| **Jobs** | Price refresh, new annual report, recomputation | Job | E1, D9, E10 | K6 | — |

## 3. Roadmap

| Stage | Content | Status |
|---|---|---|
| K1–K4b | Baseline, input layer, rulebook fixes, router | ✅ |
| **K5** | AI layer: judgment questions, classification, extraction (incl. general), background, analysis; peer group; file storage | Next |
| **K6** | ETL and DB: resolution, audit, providers, data-quality checks, backfill and repair, DB write and read, scheduled jobs, migration 8, structure additions (UNSUPPORTED, SIC, industry) | — |
| **K7** | Screens: company page, lists, plain and smart search, add company, portfolio and watchlist, approval queue | — |
| After | Israel and further markets; portfolio analysis, alerts, reports | — |
