---
name: financial-data-etl
description: Resolve public companies and their exchange listings, discover and extract annual financial statement data, audit existing ValueCompass financial history, backfill missing data, process new annual filings and restatements, normalize heterogeneous financial information, and synchronize validated financial data with the ValueCompass backend.
---

# Financial Data ETL

## Purpose

Maintain accurate, normalized, traceable, and current annual financial data for public companies in ValueCompass.

The skill must support global public companies and must not depend on a single financial-data provider.

For a newly imported company, target up to 10 applicable fiscal years of annual financial history, bounded by the company's public history and the availability of reliable annual financial statements.

The 10-year target is an initial-import and downstream-analysis target, not a database-retention limit.

## Responsibilities and Boundaries

The skill is responsible for:

- resolving a requested company or security to the correct canonical ValueCompass company;
- distinguishing the canonical issuer from its exchange listings;
- checking ValueCompass before external retrieval;
- detecting missing fiscal years, missing required source fields, new annual filings, and justified repairs;
- discovering suitable financial sources;
- extracting source financial facts;
- mapping source terminology to the canonical ValueCompass schema;
- normalizing extracted values;
- evaluating contextual confidence;
- submitting candidate data to approved backend validation and persistence tools;
- re-auditing the resulting database state;
- recording synchronization activity and provenance.

The skill may identify, interpret, extract, map, normalize, compare, and prepare candidate information.

The skill must not:

- execute arbitrary SQL;
- manage database credentials;
- bypass backend validation;
- fabricate, estimate, interpolate, or invent financial values;
- calculate Buffett or Graham scores;
- calculate valuation, fair value, margin of safety, or upside/downside;
- populate deterministic financial-ratio fields from external sources;
- treat every nullable database field as an ETL requirement.

Backend code remains responsible for:

- schema and data types;
- database constraints;
- deterministic sign and normalization enforcement;
- deterministic validation rules;
- approved calculations;
- persistence and upsert behavior;
- transactions and duplicate prevention;
- backend logging;
- authentication and database connectivity.

All database reads and writes must use approved ValueCompass backend tools.

## Canonical Entity Model

`companies` represents the canonical issuer.

`company_listings` represents exchange listings or tradable securities associated with that issuer.

`financial_yearly` represents annual financial history for the canonical issuer and is keyed by `(company_id, fiscal_year)`, not by listing.

A company may therefore have multiple listings while maintaining one canonical annual financial history.

Important currency fields are distinct:

- `companies.reporting_currency` — the company's canonical/current reporting currency when known;
- `financial_yearly.reporting_currency` — the reporting currency of the specific fiscal-year statements;
- `company_listings.trading_currency` — the currency in which a specific listing trades.

Do not assume these currencies are identical.

Company-level public history and listing-level trading history are also distinct:

- `companies.public_since_date` — when the canonical issuer should be treated as public for financial-history coverage;
- `company_listings.listing_start_date` — when a specific listing began.

Do not truncate issuer financial history to the start date of a later ADR, secondary listing, or other later market representation.

## Company and Listing Creation

Always search ValueCompass before creating a company or listing.

If the canonical issuer already exists:

- reuse the existing `company_id`;
- create only a missing listing when required;
- do not create a duplicate company because of a new ticker, exchange, ADR, share class, or security identifier.

If the issuer does not exist:

1. resolve the issuer with sufficient reliability;
2. create the canonical company;
3. obtain `company_id`;
4. create the relevant listing;
5. continue to the financial-data audit.

Do not create a company when identity cannot be resolved reliably.

### Company and Listing Source Fields

When creating or completing canonical company and listing records, retrieve the following source-derived fields when reliably available.

For `companies`:

- `company_name`;
- `country`;
- `reporting_currency`;
- `sector`;
- `industry`;
- `public_since_date`;
- `data_source`.

For `company_listings`:

- `symbol`;
- `exchange`;
- `mic`;
- `trading_currency`;
- `security_type`;
- `share_class`;
- `is_adr`;
- `adr_ratio`;
- `isin`;
- `figi`;
- `share_class_figi`;
- `is_primary`;
- `listing_start_date`;
- `data_source`.

These fields are best-effort source fields unless the backend schema requires them for record creation. Do not fabricate optional identity or classification values merely to populate the database.

Backend/database-managed fields such as IDs, timestamps, and default activity flags are not external retrieval targets unless an approved backend workflow explicitly requires them.

## Financial History Coverage and Retention

For Initial Import, target the most recent 10 fiscal years for which annual statements should reasonably exist.

If the company has fewer than 10 applicable public fiscal years, collect only the available public-company history.

Do not classify as missing:

- fiscal years before the applicable public history;
- annual periods that have not yet produced a published annual report;
- fabricated periods created only to reach 10 years.

Preserve validated historical records after they have been collected.

When a new fiscal year is added, do not delete the oldest stored year merely because more than 10 years are now present.

Example:

```text
Stored before update: FY2016–FY2025
New filing:            FY2026
Stored after update:  FY2016–FY2026
```

Downstream calculation components select the applicable analysis window, such as the most recent 10 fiscal years.

Do not re-fetch older validated history solely because it is outside the current analysis window.

## Core Operating Principles

### Database First

Inspect ValueCompass before external retrieval.

Prefer targeted work on missing, new, corrected, restated, or otherwise justified information over full historical re-import.

### No Fabrication

Never invent, estimate, interpolate, annualize incomplete quarterly data, or substitute a convenient value merely to complete the schema.

### Missing Is Not Zero

Use `0` only when reliable evidence explicitly reports zero.

Use `NULL` when an applicable value cannot be reliably determined.

Keep separate the concepts:

- reported zero;
- unresolved/missing;
- not applicable.

### Candidate Facts

Treat extracted values as candidate facts until mapping, normalization, contextual validation, and backend validation are complete.

Candidate facts may remain in memory; no persistent staging table is required for the MVP.

### Idempotency

Repeated synchronization must not create duplicate companies, listings, or fiscal-year records.

After interrupted or uncertain runs, inspect current database state before continuing.

### Partial Completion

Preserve independently validated work when another source, field, year, or backend operation fails.

A partial failure must not erase previously valid stored data.

## Primary Entry Point

The primary orchestration entry point is:

`sync_company`

The workflow is:

1. resolve the requested company or security;
2. search ValueCompass for the canonical company and relevant listing;
3. create missing company/listing records only when safely resolved;
4. audit existing financial history;
5. build a targeted work plan;
6. perform only the work required by the backend `workflow`;
7. persist validated data through approved backend tools;
8. re-audit the resulting database state;
9. finalize the synchronization log;
10. return a structured synchronization result.

A single run may contain multiple work items.

## Synchronization Outcomes

Use the following final synchronization outcomes:

- `SUCCESS` — all intended applicable work completed reliably;
- `PARTIAL_SUCCESS` — meaningful reliable work completed, but applicable unresolved work remains;
- `NO_CHANGE` — synchronization completed correctly and no persistence change was needed;
- `FAILED` — meaningful reliable synchronization could not be completed.

`AMBIGUOUS` is a company-resolution clarification state, not a financial synchronization outcome.

Do not determine success solely from tool-call responses. The resulting database state is authoritative.

## Synchronization Logging

Use the ValueCompass synchronization log for ETL activity.

When supported, open a log in `running` state and update the same record at completion.

The log should preserve, when applicable:

- `company_id`;
- `request_reference`;
- symbol and exchange;
- `operation_type`;
- `update_scope`;
- primary `data_source`;
- `source_details`;
- `years_requested`;
- `years_imported`;
- `missing_years`;
- `missing_fields`;
- `records_inserted`;
- `records_updated`;
- warnings and errors;
- final status.

`source_details` should hold detailed source usage such as source name, URL/document location, role, fiscal year, and supplementary fields when available.

Never log secrets, passwords, API keys, database credentials, or authentication tokens.

## Required Runtime Capabilities

This skill defines workflow behavior. It does not itself provide database connectivity, web access, credentials, or persistence implementation.

At runtime, the calling agent must be given approved capabilities sufficient to execute the workflow. Exact tool names and schemas may vary, but the available capabilities must cover the following functions.

### ValueCompass Backend Capabilities

The runtime must be able to:

- search and read canonical companies by supported identifiers;
- create a canonical company after reliable resolution;
- update approved company source fields when justified;
- search and read company listings;
- create a listing for an existing or newly created company;
- update approved listing source fields when justified;
- read existing annual financial history for a company;
- read a specific fiscal year and its current fields;
- submit candidate annual financial data for deterministic validation;
- insert or upsert an approved fiscal-year record;
- update only selected financial fields for targeted Backfill or Repair;
- open a synchronization log;
- update/finalize the same synchronization log;
- re-read database state after uncertain writes or before recovery.

All database interaction must occur through these approved backend capabilities. The skill must not require direct SQL or database credentials.

### External Retrieval Capabilities

The runtime must also be able to discover and retrieve public financial evidence, including when applicable:

- web search or equivalent source discovery;
- opening public webpages;
- retrieving official filings and annual reports;
- reading supported public documents such as HTML or PDF financial reports;
- following source links needed to apply the Source Hierarchy.

External retrieval must remain subject to the source-selection, provenance, confidence, validation, and fallback rules defined in this skill.

### Capability Independence

Do not hard-code the skill to a specific database provider, API provider, browser implementation, or financial-data vendor.

The ValueCompass runtime may change the underlying implementation while preserving the capabilities and behavioral contracts required by this skill.

# Workflows

## Resolve Company Workflow

Resolve the requested reference to one canonical ValueCompass company before financial retrieval.

### Accepted Inputs

Resolution may begin from one or more of:

- `company_id`;
- company name;
- symbol/ticker;
- symbol plus exchange or MIC;
- ISIN;
- FIGI.

Use multiple supplied identifiers together.

If supplied identifiers conflict, do not silently choose one. Stop and request clarification or return an appropriate resolution failure.

### Resolution Priority

Use ValueCompass first.

Prefer, when available:

1. valid canonical `company_id`;
2. exact ISIN or FIGI;
3. exact symbol plus exchange or MIC;
4. exact or safely normalized company name;
5. symbol-only lookup.

Do not rely on fuzzy name similarity alone to create or select a canonical company.

### Valid `company_id`

When a valid `company_id` is supplied:

- retrieve the canonical company;
- use its existing identity and listings;
- proceed directly to Audit;
- do not perform unnecessary external identity resolution.

If the `company_id` does not exist, do not invent an association.

### Symbol Plus Exchange or MIC

When symbol and exchange/MIC are supplied:

1. search active `company_listings` for an exact match;
2. if one listing matches, resolve through its `company_id`;
3. if no listing matches, externally resolve that listing and issuer;
4. re-check ValueCompass after external resolution;
5. if the issuer already exists, create only the missing listing;
6. otherwise create the resolved issuer first, then the listing.

### Symbol Only

Retrieve all active matching listings.

If all relevant matches belong to the same canonical `company_id`, resolve that company.

If matches belong to different canonical companies, return `AMBIGUOUS`.

When ambiguous:

- stop financial retrieval;
- do not create or modify canonical records;
- return plausible candidates when available;
- include useful distinctions such as company name, ticker, exchange, and country;
- ask the user to refine the request in the user's interaction language.

If no internal listing matches, continue to external resolution.

### Company Name

Search `companies` using exact or safely normalized company-name matching.

If exactly one canonical company is identified, resolve it.

If multiple plausible companies remain, return `AMBIGUOUS` and request identifying information such as exchange, country, legal name, ticker, ISIN, or another reliable identifier.

If no internal company resolves, continue to external resolution.

### External Resolution

Use external resolution only when ValueCompass cannot resolve identity internally.

External resolution is for issuer/listing identity, not annual financial extraction.

Determine, when reliably available:

- canonical legal company name;
- country;
- sector and industry;
- ticker/symbol;
- exchange and/or MIC;
- primary-listing status;
- current reporting currency;
- listing trading currency;
- security type and share class;
- ADR status and ADR ratio;
- ISIN;
- FIGI and Share Class FIGI;
- `public_since_date`;
- `listing_start_date`;
- company identity `data_source`;
- listing identity `data_source`.

After external resolution, search ValueCompass again before creating anything to detect an issuer already stored under another listing, ticker, ADR, or identifier.

Do not create a canonical company from a weak or uncertain match.

### Resolution Outcomes

Use:

- `RESOLVED_EXISTING`;
- `RESOLVED_NEW_LISTING`;
- `RESOLVED_NEW_COMPANY`;
- `AMBIGUOUS`;
- `NOT_FOUND`.

`AMBIGUOUS` and `NOT_FOUND` must not create or modify canonical company records.

A successful resolution returns `company_id` and, when applicable, `listing_id`.

## Audit Existing Financial Data Workflow

Audit ValueCompass before external financial retrieval.

The audit determines:

- what annual information already exists;
- what expected history is missing;
- which applicable source fields are unresolved;
- whether a new annual filing should be checked;
- whether `REPAIR` work (NULL required fields) exists;
- the targeted work plan.

### Expected History States

Before classifying data as missing, distinguish:

- `EXPECTED_AND_PRESENT`;
- `EXPECTED_BUT_MISSING`;
- `NOT_YET_EXPECTED`.

Only `EXPECTED_BUT_MISSING` automatically creates historical backfill work.

A newly public company with no annual report yet is valid and should not receive a fabricated fiscal-year record or a failure solely because no annual report exists.

### Audit Inputs

Inspect at least:

- `companies.public_since_date`;
- stored fiscal years;
- fiscal-year end dates;
- filing dates;
- source information;
- relevant `SOURCE` fields and their `NULL` values;
- latest stored fiscal year;
- latest known filing date.

Do not treat every nullable field as required.

### Missing Fiscal Year

A fiscal year is missing only when:

1. it falls within the applicable public financial-history period;
2. an annual report for the period should reasonably exist;
3. no corresponding `financial_yearly` record exists.

### Partial Fiscal Year

A stored year may require field-level backfill when an applicable required `SOURCE` field is unresolved.

Do not create external backfill for:

- `CALCULATED` fields;
- `SYSTEM` fields;
- `SOURCE_IF_REPORTED` fields solely because they are absent;
- fields established as `NOT_APPLICABLE`.

### Work Plan

The audit produces exactly one workflow per run. Active workflows:

- `METADATA_REPAIR`;
- `INITIAL_IMPORT`;
- `BACKFILL`;
- `REPAIR`;
- `NO_ACTION`.

Planned, not currently active (the backend does not trigger them; never start them on your own initiative):

- `CHECK_FOR_NEW_FILING`;
- `INCREMENTAL_UPDATE`.

The audit itself must not overwrite financial data.

### Workflow Names

The ValueCompass backend runs the audit and sends exactly one `workflow` value in the ETL request. The names are defined once in `src/constants.py` (`FinancialWorkflow`) and are authoritative:

| `workflow` | Status | Meaning | What to do |
|---|---|---|---|
| `METADATA_REPAIR` | active | Critical company metadata listed in `metadata_fields` (for example `public_since_date`) is missing, so expected years cannot be computed | Research only the listed metadata fields and submit them through the approved metadata tool. Do not retrieve or submit financial data. |
| `INITIAL_IMPORT` | active | No fiscal year is stored for the company | Import the fiscal years listed in `years` (see Initial Import Workflow) |
| `BACKFILL` | active | Entire expected fiscal years are missing | Retrieve and submit each fiscal year listed in `years` |
| `REPAIR` | active | Fiscal years exist, but required source fields are `NULL` | Fill only the fields listed per year in `missing_fields`. Do not re-examine or overwrite existing non-`NULL` values. |
| `NO_ACTION` | active | Nothing to do | Do nothing |
| `CHECK_FOR_NEW_FILING` | planned, not active | Detect a newly published annual filing | Not triggered by the backend. Do not start it. |
| `INCREMENTAL_UPDATE` | planned, not active | Add newly published annual information to an existing company | Not triggered by the backend. Do not start it. |

The backend accepts financial writes only for fiscal years listed in `years`, and only under `INITIAL_IMPORT`, `BACKFILL`, or `REPAIR`. A rejected write is a signal to stop, not to retry with a different year or workflow.

The same rules apply to every company. Take the company identity only from the ETL request and backend tools, never from assumptions about a specific issuer.

## Initial Import Workflow

Use when annual history should already exist but ValueCompass does not contain sufficient history.

### Scope

Target the most recent 10 expected annual fiscal years, limited by the issuer's applicable public history.

Do not include pre-public or not-yet-published periods.

### Report Inventory

Before broad extraction, identify the available annual evidence and associate it with fiscal periods.

Track, when available:

- fiscal year/period;
- document or filing type;
- fiscal-year end date;
- filing/publication date;
- source type;
- URL or document identifier;
- reporting currency;
- current and comparative periods covered.

One document may cover multiple fiscal years.

### Per-Year Processing

For each target fiscal year:

1. identify suitable evidence;
2. extract required source facts;
3. map to canonical fields;
4. normalize units, signs, currency context, dates, and share scale;
5. construct candidate data;
6. retain provenance;
7. perform contextual validation;
8. submit to backend validation;
9. persist accepted data through approved upsert tools.

If no reliable evidence exists for an entire expected year, leave the year absent rather than creating an all-`NULL` record.

Validated years should be independently persistable so one failed year does not roll back other valid years.

After import, re-audit the company.

## Backfill and Repair Workflow

Backfill and Repair are targeted maintenance operations.

### Backfill

`BACKFILL` means entire expected fiscal years are missing.

For each missing year, retrieve and validate that year only.

If reasonable sources are exhausted, preserve the absent year and keep it eligible for future backfill.

### Repair

`REPAIR` means a fiscal year exists but applicable required `SOURCE` fields are `NULL`.

- preserve existing validated values;
- search only the unresolved fields listed in `missing_fields`;
- use field-level source fallback;
- update only the affected fields.

If reasonable sources are exhausted, preserve `NULL` and keep the year eligible for future repair.

### Correction of Existing Values (planned, not active)

Re-examining existing non-`NULL` values is not performed by any active workflow. The guidance below describes how it would work once the backend supports it. Do not apply it on your own initiative.

An existing canonical value may have a justified reason to be reconsidered.

Valid triggers may include:

- explicit official restatement;
- official prior-period correction;
- wrong issuer or fiscal-period mapping;
- confirmed unit or currency normalization error;
- confirmed financial-concept mapping error;
- structurally invalid stored data;
- materially stronger authoritative evidence correcting a weaker prior source.

A different number from another website is not enough.

Before correcting, compare:

- source authority;
- issuer identity;
- fiscal period;
- reporting currency;
- unit scale;
- consolidated versus standalone context;
- accounting concept;
- restatement/correction status.

Do not let weaker supplementary evidence overwrite stronger authoritative data without clear justification.

### Restatements (planned, not active)

When an authoritative later filing explicitly revises a prior period:

1. identify affected years and fields;
2. confirm the same canonical concept;
3. normalize the revised values;
4. validate through the backend;
5. update only affected historical facts;
6. update primary source when appropriate;
7. record the reason and source evidence in the log.

Do not delete the historical fiscal year.

### Unresolved Conflict

If the existing value remains sufficiently reliable and the conflict cannot be resolved, preserve it and log the conflict.

If the existing value is determined unreliable and no replacement can be established, the backend may set the affected field to `NULL` according to approved persistence rules.

After `BACKFILL` or `REPAIR`, re-audit.

## Incremental Update and New Filing Workflow (planned, not active)

The backend does not trigger `CHECK_FOR_NEW_FILING` or `INCREMENTAL_UPDATE` today. This section is retained as the design for a future version; do not execute it.

Use when Audit determines that an existing company may have newly published annual information.

Do not re-import the complete historical dataset.

### Determine Current State

Inspect:

- latest stored fiscal year;
- latest fiscal-year end date;
- latest filing date;
- existing annual records.

Do not infer that a new annual report exists merely because the calendar year changed.

### Identify New Annual Filings

Search only for annual filings or annual financial reports newer than the latest applicable stored period.

If no new relevant annual filing exists, return `NO_CHANGE`.

If several fiscal years became available since the last synchronization, process them chronologically when practical.

### Verify and Import

For each new annual fiscal year:

1. verify issuer, annual period, reporting entity, currency, units, and source authenticity;
2. extract the required source facts;
3. normalize and validate;
4. use field-level fallback for unresolved required fields;
5. persist the new year through approved tools.

Do not overwrite older years merely because the new report includes comparative columns.

### Comparative Data and Restatements

Review comparative figures only when they indicate:

- explicit restatement;
- prior-period correction;
- accounting-policy change affecting prior periods;
- material reclassification;
- another justified correction condition.

If comparative values differ without a reliable explanation, preserve existing validated values and log the discrepancy.

When a justified historical revision exists, route only affected fields/years through the planned correction workflow.

### Scheduled Checks

An external scheduler may invoke `sync_company`.

Scheduling policy does not belong in this skill.

A scheduled invocation must still audit first and must not modify data unless new or justified corrected information actually exists.

# Source Hierarchy and Provenance

## Source Authority

Use the hierarchy as a preference order, not as a requirement to search every source.

### Tier 1 — Regulatory and Official Filing Systems

Examples:

- SEC EDGAR;
- MAGNA;
- Companies House;
- FCA/RNS;
- TDnet;
- equivalent national regulatory filing systems.

### Tier 2 — Official Exchange Sources

Examples:

- MAYA;
- Nasdaq;
- NYSE;
- LSE;
- TASE;
- JPX;
- Deutsche Börse;
- Euronext;
- equivalent official exchange services.

### Tier 3 — Company Investor Relations and Official Annual Reports

Use official company annual reports, audited financial statements, consolidated statements, financial results, notes, and related official disclosures.

A verified audited annual report remains authoritative even if another official regulatory copy is not separately retrieved.

### Tier 4 — Historical Annual Report Archives

Example:

- AnnualReports.com.

Verify issuer, fiscal period, and reporting entity. Treat an authenticated official annual report according to the authority of the document itself, even when retrieved from a third-party archive.

### Tier 5 — Public Structured Financial Databases

Examples:

- StockAnalysis;
- Macrotrends;
- Morningstar;
- MarketWatch.

Useful for long history, targeted missing fields, and cross-checks when stronger sources are insufficient.

### Tier 6 — Aggregators and APIs

Examples:

- Yahoo Finance;
- FMP;
- TIKR;
- Koyfin;
- QuickFS;
- CompaniesMarketCap.

Use as fallback, supplementary, or validation sources. No single provider is mandatory.

### Tier 7 — Secondary and Analytical Sources

Example:

- Seeking Alpha.

Use only as supplementary context or cross-check when stronger evidence is unavailable or insufficient.

## Source Selection

Before accepting a value, verify:

- canonical company;
- fiscal period;
- reporting entity;
- reporting currency;
- unit scale;
- accounting concept;
- source authenticity.

If a sufficiently authoritative source already provides a reliable fact, stop searching for that fact.

## Field-Level Fallback

Fallback must operate at the smallest practical scope.

When some fields are already validated:

1. preserve them;
2. identify unresolved fields only;
3. move to the next suitable source;
4. search specifically for those fields;
5. stop per field once reliable evidence is found;
6. continue only for fields that remain unresolved.

Prefer:

`missing field → next source → missing field`

over:

`missing field → retrieve entire fiscal year again`.

A weaker supplementary source must not overwrite stronger validated values merely because it fills another field.

If applicable sources are reasonably exhausted, leave the value `NULL`.

## Source Conflicts

When sources disagree, evaluate:

- source authority;
- issuer identity;
- period;
- currency;
- units;
- consolidated versus standalone context;
- accounting presentation;
- restatement/correction status;
- classification changes.

Do not average, choose the first value, or choose the value that best fits historical trends.

A later authoritative restatement may supersede the earlier canonical value.

If unresolved, preserve a sufficiently reliable existing value or leave the field unresolved, and log the conflict.

## Provenance

For each fiscal year, identify one primary source when practical.

`financial_yearly.source` stores only the primary source name, for example:

- `SEC EDGAR`;
- `Company IR`;
- `MAYA`;
- `AnnualReports`;
- `StockAnalysis`;
- `Macrotrends`;
- `Morningstar`;
- `FMP`.

Do not store URLs or concatenated source histories in `financial_yearly.source`.

Supplementary sources may fill individual fields without changing the primary source.

Detailed provenance belongs in the synchronization log, including when available:

- primary and supplementary source names;
- full URLs/document locations;
- fiscal years;
- supplementary fields;
- unresolved fields;
- source conflicts;
- warnings/extraction issues.

Do not create a separate persistent fact-level provenance table for the MVP.

# Financial Field Scope

Each `financial_yearly` field belongs to one category:

- `SOURCE` — actively retrieve when applicable;
- `SOURCE_IF_REPORTED` — retrieve only when explicitly and reliably reported or allowed by an approved deterministic mapping;
- `CALCULATED` — do not retrieve as the canonical value; ValueCompass calculates it;
- `SYSTEM` — backend/database controlled.

Not every `SOURCE` field is applicable to every business model or reporting framework.

## Fiscal-Year Metadata

| Field | Category |
|---|---|
| `fiscal_year` | `SOURCE` |
| `fiscal_year_end_date` | `SOURCE` |
| `filing_date` | `SOURCE` |
| `reporting_currency` | `SOURCE` |
| `source` | `SOURCE` |

`company_id`, `created_at`, and `updated_at` are `SYSTEM`.

## Income Statement

| Field | Category |
|---|---|
| `revenue` | `SOURCE` |
| `gross_profit` | `SOURCE` |
| `operating_income` | `SOURCE` |
| `ebit` | `SOURCE_IF_REPORTED` |
| `ebitda` | `SOURCE_IF_REPORTED` |
| `income_before_tax` | `SOURCE` |
| `income_tax_expense` | `SOURCE` |
| `net_income` | `SOURCE` |
| `eps_diluted` | `SOURCE` |
| `interest_expense` | `SOURCE` |
| `depreciation_and_amortization` | `SOURCE` |

Do not assume `operating_income = EBIT` unless an approved deterministic rule establishes the equivalence.

Do not map Adjusted, Normalized, Underlying, or company-specific non-GAAP EBITDA directly into `ebitda` without an explicit approved rule.

## Cash Flow

| Field | Category |
|---|---|
| `operating_cash_flow` | `SOURCE` |
| `capex` | `SOURCE` |
| `free_cash_flow` | `CALCULATED` |
| `stock_based_compensation` | `SOURCE` |
| `adjusted_free_cash_flow` | `CALCULATED` |
| `dividends_paid` | `SOURCE` |
| `share_repurchases` | `SOURCE` |
| `dividends_per_share` | `SOURCE` |

The ETL skill must not search external sources for canonical `free_cash_flow` or `adjusted_free_cash_flow`.

External FCF values may be diagnostic only.

## Balance Sheet

| Field | Category |
|---|---|
| `total_assets` | `SOURCE` |
| `total_liabilities` | `SOURCE` |
| `total_equity` | `SOURCE` |
| `total_debt` | `SOURCE` |
| `long_term_debt` | `SOURCE` |
| `cash_and_equivalents` | `SOURCE` |
| `short_term_investments` | `SOURCE` |
| `accounts_receivable` | `SOURCE` |
| `current_assets` | `SOURCE` |
| `current_liabilities` | `SOURCE` |
| `goodwill` | `SOURCE` |
| `intangible_assets` | `SOURCE` |

Do not construct a canonical field from unrelated components unless an approved deterministic backend rule permits it.

## Share Data

| Field | Category |
|---|---|
| `shares_outstanding` | `SOURCE` |
| `weighted_avg_shares_diluted` | `SOURCE` |

Keep point-in-time shares outstanding distinct from weighted-average diluted shares.

## Fields Outside ETL Calculation Scope

Do not populate `financial_ratios` from external source metrics.

All ratio fields are produced by deterministic ValueCompass logic from canonical inputs and approved market inputs where applicable.

This includes margins, ROE, ROA, ROIC, effective tax rate, NOPAT, invested capital, working capital, liquidity ratios, debt ratios, net debt, coverage ratios, book value, tangible book value, NCAV, payout ratios, dilution metrics, growth rates, and CAGR metrics.

Do not calculate or populate Buffett/Graham scores, price scores, valuation scores, fair value, margin of safety, or upside/downside.

## Applicability and Completeness

A `NULL` does not automatically mean defective data.

For completeness, classify source fields conceptually as:

- `AVAILABLE`;
- `UNRESOLVED`;
- `NOT_APPLICABLE`.

Do not repeatedly search for a field established as `NOT_APPLICABLE`.

For the MVP, `NOT_APPLICABLE` may remain a workflow/audit classification rather than a persistent fact-level state.

`SOURCE_IF_REPORTED`, `CALCULATED`, and `SYSTEM` fields must not trigger external backfill solely because they are `NULL`.

# Normalization and Mapping Rules

## General Rule

Normalize representation without changing economic meaning.

Do not force an uncertain source concept into a canonical field.

When reliable mapping cannot be established, leave the field unresolved.

## Monetary Units

Store monetary statement values in full reporting-currency units.

Examples:

```text
Source: USD millions
Revenue: 125.4
Stored revenue: 125400000
```

Apply stated thousands/millions/billions scale before persistence.

Do not guess an unknown scale.

## Currency

For each fiscal year, store monetary values in that fiscal year's reporting currency and persist:

`financial_yearly.reporting_currency`.

Do not automatically convert annual statement values to USD, EUR, listing currency, or another comparison currency.

Do not confuse:

- current/canonical company reporting currency;
- historical fiscal-year reporting currency;
- listing trading currency.

FX conversion belongs to a downstream component.

## Sign Conventions

Preserve economic sign for performance values such as:

- `gross_profit`;
- `operating_income`;
- `ebit`;
- `ebitda`;
- `income_before_tax`;
- `net_income`;
- `eps_diluted`;
- `operating_cash_flow`.

Use positive magnitudes for expense/outflow fields when they represent expenses or cash outflows:

- `income_tax_expense`;
- `interest_expense`;
- `depreciation_and_amortization`;
- `capex`;
- `stock_based_compensation`;
- `dividends_paid`;
- `share_repurchases`.

Example:

```text
Cash-flow statement capex: (500)
Stored capex: 500
```

This supports deterministic formulas such as:

`Free Cash Flow = Operating Cash Flow - CapEx`

The backend enforces the final approved convention.

Balance-sheet liabilities and debt are normally stored as positive balances, not negated merely because they are obligations.

Legitimately negative equity or other balances may remain negative.

## Per-Share and Share Counts

Keep per-share values as per-share values:

- `eps_diluted`;
- `dividends_per_share`.

Do not multiply them by share counts.

Normalize share counts to full shares.

Example:

```text
Weighted-average diluted shares: 325.4 million
Stored: 325400000
```

Do not substitute `shares_outstanding` for `weighted_avg_shares_diluted` or vice versa.

## Fiscal Period and Dates

Map data to the issuer's fiscal year, not the publication calendar year.

Use the stated fiscal-year label, period-end date, and filing metadata.

Store the actual `fiscal_year_end_date` when reliable; do not fabricate December 31.

`filing_date` is the official filing/publication date, not the fiscal-year end or ValueCompass retrieval date.

## Canonical Concept Mapping

Map by accounting meaning, not exact wording.

Possible revenue candidates include:

- Revenue;
- Revenues;
- Total Revenue;
- Net Revenue;
- Net Sales;
- Sales.

Map them to `revenue` only when they represent the canonical top line.

Possible operating-income candidates include:

- Operating Profit;
- Operating Income;
- Income from Operations.

Again, confirm accounting equivalence.

Semantic similarity alone is insufficient.

## Net Income and Equity

Financial reports may expose several net-income and equity concepts.

Do not silently switch among materially different definitions across years.

Examples requiring care include:

- consolidated net income;
- net income attributable to parent/common shareholders;
- non-controlling interests;
- total equity;
- shareholders' equity;
- equity attributable to owners of the parent.

Use the approved ValueCompass canonical definition. If the correct mapping is unclear, do not guess.

## Debt

Do not equate total liabilities with debt.

`total_debt` represents interest-bearing debt according to the approved ValueCompass definition.

Potential components may include:

- short-term borrowings;
- current portion of long-term debt;
- long-term borrowings;
- bonds;
- other interest-bearing debt.

If construction from components is required, it must follow an approved deterministic backend rule.

## Cash, Investments, Goodwill, and Intangibles

Keep separate:

- `cash_and_equivalents`;
- `short_term_investments`;
- `goodwill`;
- `intangible_assets`.

Do not split a combined source amount arbitrarily.

Use notes or another authoritative source when reliable separation is available.

## CapEx

Map only expenditures representing the approved ValueCompass CapEx concept, such as qualifying purchases/additions of property, plant, equipment, fixed assets, or equivalent capital assets.

Do not automatically include business acquisitions, financial investments, financing transactions, or unrelated investing cash flows.

## Stock-Based Compensation

Map `stock_based_compensation` only to employee/management share-based or equity-based compensation expense.

If not clear in the main statements, inspect applicable notes or cash-flow reconciliation disclosures before moving to weaker sources.

## Dividends and Repurchases

Keep `dividends_paid` distinct from `dividends_per_share`.

Do not derive one from the other inside the ETL skill.

Map `share_repurchases` only to qualifying cash spent repurchasing the issuer's own equity.

Do not confuse repurchases with share issuance, acquisition-related transactions, or employee withholding transactions without confirming context.

## Accounting Framework and Reporting Entity

The skill may encounter US GAAP, IFRS, or local standards.

Map based on accounting/economic equivalence rather than identical wording.

Prefer consolidated statements when consolidated reporting is appropriate.

Do not mix consolidated and standalone values within one fiscal-year record without a justified, documented reason.

## Annual Versus Quarterly

`financial_yearly` contains annual data.

Do not populate it directly from an individual quarterly report.

Quarterly reconstruction is allowed only if an approved deterministic workflow explicitly supports it. The AI must not independently sum or annualize quarters.

## Reported Versus Adjusted/Non-GAAP

Prefer canonical reported statement values.

Do not automatically map:

- adjusted earnings;
- adjusted operating profit;
- adjusted EPS;
- adjusted EBITDA;
- normalized earnings;
- management-defined non-GAAP measures

into standard canonical fields unless an explicit approved rule permits it.

## Restated Values

When a later authoritative filing explicitly restates a prior period, store the restated value in the original fiscal year once a correction workflow becomes active (planned).

Do not assign the historical restatement to the year in which it was published.

## Mapping Confidence

Accept a mapping only when concept, period, reporting entity, scale, and currency are sufficiently clear.

If not:

1. inspect stronger or supplementary evidence;
2. inspect notes when appropriate;
3. preserve stronger already validated data;
4. leave the field unresolved if ambiguity remains.

# Validation Rules

Every candidate fact or fiscal-year dataset must pass contextual validation and approved deterministic backend validation before persistence.

Use:

- `VALID`;
- `WARNING`;
- `REJECTED`.

`VALID` may persist.

`WARNING` may persist when evidence is still sufficiently reliable, but the issue must be logged.

`REJECTED` must not persist.

## Context Validation

Verify, when applicable:

- canonical company;
- annual fiscal period;
- reporting entity;
- consolidated/standalone context;
- reporting currency;
- unit scale;
- source authority and authenticity;
- statement/note context.

A reasonable-looking number from the wrong company, year, entity, currency, or statement is invalid.

## Hard Validation

Reject when applicable:

- wrong canonical company;
- wrong fiscal period;
- quarterly data incorrectly used as annual;
- unsupported canonical field;
- fabricated/estimated value;
- unresolved accounting-concept mapping;
- unknown scale when normalization is required;
- unknown reporting currency when the monetary value cannot safely be interpreted;
- invalid data type;
- negative share count;
- hard sign-convention violation after normalization;
- confirmed extraction from the wrong statement or reporting entity.

Do not bypass rejection to complete the record.

## Unit and Scale Checks

Normalize to full units before persistence.

Large unexplained changes of roughly 1,000x or 1,000,000x should trigger scale re-checks.

An anomaly triggers investigation; it is not automatic proof of error.

## Sign Checks

Expense/outflow-magnitude fields should not remain negative after approved normalization.

Fields with legitimate negative economic meaning may remain negative, including losses, negative cash flow, and negative equity when supported by the source.

## Share Checks

Share counts cannot be negative.

Large changes should trigger checks for:

- scale;
- stock splits/reverse splits;
- issuance;
- repurchases;
- share-class changes.

Do not reject legitimate corporate-action changes.

## Accounting Consistency Checks

When sufficient compatible fields exist, use diagnostic checks such as:

`Assets ≈ Liabilities + Equity`

and review cases such as:

`total_debt < long_term_debt`

or:

`gross_profit > revenue`.

These are investigation aids, not automatic correction formulas.

Differences may reflect rounding, non-controlling interests, classification differences, lease treatment, or legitimate reporting context.

Never alter data merely to force an accounting relationship.

## EPS Diagnostic Check

When available, compare:

`net_income / weighted_avg_shares_diluted`

with `eps_diluted` as a diagnostic only.

Do not calculate or overwrite EPS from this relationship.

Differences may arise from preferred dividends, attribution, non-controlling interests, dilution, discontinued operations, stock splits, rounding, or presentation.

## Cross-Year Checks

Compare with neighboring stored years to detect possible:

- scale error;
- currency change/error;
- wrong period;
- extraction error;
- source change.

Large changes are warnings/investigation triggers, not automatic rejection.

Legitimate causes include acquisitions, divestitures, restructuring, major operating changes, accounting-policy changes, reporting-currency changes, or exceptional gains/losses.

## Source Conflict Validation

When sources conflict, verify issuer, period, currency, units, concept, authority, and restatement/correction context.

Do not average values or choose the value closest to historical trends.

Apply the Source Hierarchy and the correction rules.

## Applicability

Use conceptual states:

- `AVAILABLE`;
- `UNRESOLVED`;
- `NOT_APPLICABLE`.

Do not force industrial-company concepts onto banks, insurers, or other financial institutions when the standard field is not economically comparable or not reported in that form.

Potentially sector-sensitive concepts include:

- gross profit;
- current assets/current liabilities;
- conventional EBITDA;
- conventional debt.

Where no approved sector-specific rule exists, prefer `NULL` or `NOT_APPLICABLE` over fabricated equivalence.

## SOURCE_IF_REPORTED and CALCULATED Fields

Missing `ebit` or `ebitda` does not automatically make a year incomplete.

Do not externally backfill `CALCULATED` fields such as `free_cash_flow`, `adjusted_free_cash_flow`, or downstream `financial_ratios`.

## Warning Conditions

Potential warnings include:

- unusually large year-over-year change;
- material balance-sheet reconciliation difference;
- material EPS diagnostic difference;
- `total_debt < long_term_debt` under unclear definitions;
- unusual negative balance;
- material source disagreement;
- changed comparative figures;
- unusual reporting presentation;
- limited supporting-source availability.

Record material warnings in the synchronization log.

## Partial Validation

One rejected field does not automatically invalidate all other fields or years.

When safe:

- preserve validated fields;
- leave rejected/unresolved fields `NULL`;
- continue independent fields/years;
- record unresolved fields in `missing_fields`.

Required processing order:

`extract → map → normalize → contextual validation → backend validation → persist`

# Error Handling, Retries, and Confidence

## Temporary Technical Failures

A temporary technical failure is a condition that may succeed later without changing the requested data or source.

Examples:

- network timeout;
- temporary website unavailability;
- HTTP 429;
- HTTP 5xx;
- interrupted document download;
- temporary API failure;
- temporary backend/database connection failure.

Use bounded retries.

The backend/orchestration layer should control retry count, delay, and backoff.

Do not retry indefinitely.

If retries are exhausted:

1. log the failure;
2. use another applicable source when possible;
3. preserve validated work;
4. leave unresolved fields/years eligible for future synchronization.

## Data Problems Are Not Retry Problems

Do not treat these as temporary technical failures:

- unclear concept mapping;
- conflicting values;
- unknown currency;
- unknown scale;
- wrong company;
- wrong fiscal year;
- missing disclosure;
- field not reported;
- quarterly document when annual data is required.

These require additional evidence, another source, clarification, or an unresolved result.

## Source and Document Failure

One failed source must not automatically fail the entire synchronization.

If a report is inaccessible or unreadable:

1. retry only when the failure appears temporary;
2. look for another official copy;
3. use an authenticated historical archive when appropriate;
4. continue through applicable fallback sources.

Do not extract from corrupted, incomplete, or uncertain content.

## Field and Fiscal-Year Isolation

A failed field does not invalidate other validated fields.

A failed fiscal year does not invalidate other validated fiscal years.

Use field-level fallback and independently persistable fiscal-year units when safe.

This may result in `PARTIAL_SUCCESS`.

## Backend Operation Failure

Never bypass a failed approved backend tool.

If a write result is uncertain:

1. read current database state through an approved tool;
2. determine whether the write actually persisted;
3. retry only if it did not persist and retry is safe.

Do not assume a timeout means the write definitely failed.

## Recovery and Idempotency

Before resuming an interrupted run:

1. inspect current database state;
2. determine what already persisted;
3. identify unresolved work only;
4. continue from the current state.

Repeated `sync_company` execution must not create duplicates.

## Confidence Levels

Use qualitative workflow confidence:

- `HIGH`;
- `MEDIUM`;
- `LOW`.

Do not invent numerical confidence percentages.

### HIGH

Use when issuer, document, period, concept, currency, scale, and source context are sufficiently clear.

A HIGH candidate may proceed to backend validation.

### MEDIUM

Use when plausible but additional evidence is required, for example:

- unclear terminology;
- lower-priority source for a missing field;
- uncertainty between similar concepts;
- unexplained conflict with authoritative stored data;
- uncertainty about a restatement.

Seek stronger or supplementary evidence.

Do not persist solely because a MEDIUM candidate is the only value found.

### LOW

Use when reliability is insufficient, for example:

- possible wrong issuer;
- unclear fiscal period;
- unknown unit scale;
- unknown currency;
- uncertain source authenticity;
- semantic similarity without accounting confirmation;
- estimated/inferred value.

Do not persist LOW-confidence facts.

## Confidence Is Contextual

Source tier alone does not determine confidence.

Evaluate together:

- source authority;
- issuer identity;
- fiscal period;
- reporting entity;
- document authenticity;
- accounting concept;
- reporting currency;
- scale;
- supporting evidence.

## Stop Searching

Do not search indefinitely.

For each unresolved item:

1. follow the applicable source hierarchy;
2. use targeted fallback;
3. stop when reliable evidence is found;
4. stop when applicable and reasonably available sources are exhausted.

If still unresolved, preserve `NULL` or the absent year, log it, and keep it eligible for future Backfill.

## Failure and Recovery Outcomes

Use `PARTIAL_SUCCESS` when useful reliable work persisted but expected applicable work remains unresolved.

Use `NO_CHANGE` when checks completed correctly but no database modification was needed.

Use `FAILED` when meaningful reliable progress cannot be completed, such as:

- canonical company cannot be resolved;
- required backend persistence remains unavailable;
- no requested financial information can be retrieved reliably;
- a critical validation issue prevents safe persistence;
- database state cannot be safely determined after an unrecoverable backend error.

Previously stored valid data must remain unchanged when a new synchronization fails.

Future runs should rediscover unresolved work through Audit rather than automatically re-importing all history.

# `sync_company` Input and Output Contract

## Input

Conceptual input:

```json
{
  "company_id": null,
  "company_name": null,
  "symbol": null,
  "exchange": null,
  "mic": null,
  "isin": null,
  "figi": null
}
```

At least one usable company identifier must be supplied.

All individual fields are optional.

Do not require information that the skill can safely discover.

When `company_id` is valid, prefer direct internal synchronization without unnecessary external resolution.

When multiple identifiers conflict, resolve the conflict before financial retrieval.

The caller identifies the company; the skill decides the required financial work.

Do not require callers to specify:

- Initial Import;
- Backfill;
- Repair;
- Incremental Update (planned);
- New Filing Check.

## Resolution Before Financial Work

Except for a valid canonical `company_id`, complete company resolution before financial synchronization.

If `AMBIGUOUS`:

- stop financial work;
- do not create or modify canonical records;
- return candidate identities;
- request clarification naturally in the user's interaction language.

If `NOT_FOUND`, do not create placeholders or financial records.

## Output

A completed synchronization should return a structured summary conceptually equivalent to:

```json
{
  "resolution_outcome": "RESOLVED_EXISTING",
  "status": "SUCCESS",
  "company": {
    "company_id": 1,
    "company_name": "Example Corporation",
    "public_since_date": "2000-01-01"
  },
  "listing": {
    "listing_id": 10,
    "symbol": "EXAMPLE",
    "exchange": "NASDAQ",
    "mic": "XNAS"
  },
  "work_plan": [
    "BACKFILL"
  ],
  "work_performed": [
    {
      "type": "BACKFILL",
      "fiscal_year": 2019
    }
  ],
  "years_requested": 1,
  "years_imported": 1,
  "missing_years": [],
  "missing_fields": [],
  "records_inserted": 2,
  "records_updated": 0,
  "warnings": [],
  "errors": []
}
```

The exact backend schema may differ while preserving the same meaning.

The output must communicate:

- resolution outcome;
- final synchronization status;
- canonical company;
- relevant listing when applicable;
- work identified;
- work performed;
- years requested/imported;
- unresolved years;
- unresolved fields;
- records inserted/updated;
- material warnings/errors.

Do not return the complete financial history by default. Detailed financial data belongs to separate approved read operations.

## Clarification Output

Conceptually:

```json
{
  "resolution_outcome": "AMBIGUOUS",
  "status": null,
  "clarification_required": true,
  "candidates": [
    {
      "company_name": "Example Company A",
      "symbol": "ABC",
      "exchange": "NYSE",
      "country": "US"
    },
    {
      "company_name": "Example Company B",
      "symbol": "ABC",
      "exchange": "LSE",
      "country": "GB"
    }
  ]
}
```

Do not expose unnecessary internal database details in user-facing clarification.

## NOT_FOUND

A reasonable unresolved company-identification attempt may return:

```text
resolution_outcome = NOT_FOUND
status = FAILED
```

with an explanation.

Do not create placeholder company records.

## NO_CHANGE

Example:

```json
{
  "resolution_outcome": "RESOLVED_EXISTING",
  "status": "NO_CHANGE",
  "work_plan": ["NO_ACTION"],
  "work_performed": [],
  "missing_years": [],
  "missing_fields": []
}
```

`NO_CHANGE` is successful synchronization, not an error.

## Database State Is Authoritative

After persistence, re-audit and construct the final result from the confirmed ValueCompass state.

Do not report a fiscal year or field as successfully imported merely because extraction or a write call was attempted.
