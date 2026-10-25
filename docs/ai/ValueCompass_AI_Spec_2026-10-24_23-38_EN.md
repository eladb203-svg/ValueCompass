---
title: "ValueCompass — AI Layer Specification"
subtitle: "Approved 2026-10-21_16-00 · English (source of truth)"
---

# AI Layer Specification

**Purpose:** define everything the AI does in ValueCompass — which questions, on which text, in which format, and how code checks every answer — so that code stage K5 implements exactly this. **Source:** Rulebook 2026-10-20_23-21 (Part A R1, R13, R16, R18; Part B.1; Part C cards; Part E dictionary). **Model:** Gemini (existing decision: free at this stage). **Status:** approved 2026-10-21 (approvals: section 7; further skills: section 11). Merges the version 2026-10-21_10-37 with later decisions (section 12). Skill prompts: `ValueCompass_AI_Skills_Scoring_2026-10-21_12-17` (A1–A14) and `ValueCompass_AI_Skills_Other_2026-10-21_12-39` (C1, B1–B14, D1, D2). Implementation: K5a done; calibration (skills version 2) and model selection in progress. **Language:** English is the source of truth; the Hebrew version is a translation.

## 1. Principles

| # | Principle | Source |
|---|---|---|
| 1 | The AI only answers predefined questions. It does not compute, convert to points or decide a score — code does | R1, R13 |
| 2 | Every answer carries an **exact quote** from the report. Code checks that the quote appears in the text; a quote not found → the answer is rejected | R16 |
| 3 | No evidence → "insufficient evidence" (counted as missing, not as 0) | R16, M1 |
| 4 | Stability: a fixed, recorded model version, temperature 0, a versioned prompt. The answer is stored and not recomputed until a new annual report or a new question version | R18 |
| 5 | The AI never sees scores, values or prices — only the report text and the question, so the answer is not driven by the conclusion | — |
| 6 | Every call is logged: company, year, question, version, model, date, the text sent (identifier), the raw answer and the check result | E9 |

## 2. Three task types

| Type | What | Output | Stored in |
|---|---|---|---|
| **A. Quality judgment** | A 2 / 1 / 0 question from a Rulebook card | Answer + short reasoning + quotes | `ai_assessments` |
| **B. Data extraction** | A number from the report with no XBRL tag (e.g., CET1, occupancy) | Value + unit + period + basis + quote | `extraction_items` |
| **C. Industry classification** | Tier 3 of Part B.1: one industry from the closed list | Industry + quote | `ai_assessments` (question CLS-1) |

Until code stage K6 the results are stored in files (`scripts/ai_store/*.jsonl`) with the same structure as the tables.

## 3. The text the AI receives

| ID | Section | Source (US) |
|---|---|---|
| TXT-001 | Business | 10-K, Item 1 |
| TXT-002 | Risk factors | 10-K, Item 1A |
| TXT-003 | Competition | "Competition" subsection within Item 1 (when present) |
| TXT-004 | MD&A and governance | 10-K, Item 7 (MD&A) + Item 9A; corporate governance from the proxy (DEF 14A) when available |
| TXT-005 | Segments and customers | Segment note and >10% customer disclosure in the financial statements |
| Notes | For data extraction | The relevant note in the financial statements (debt, regulatory capital, credit, etc.) |

- **File source:** the local filings cache (`scripts/cache/filings`); in K6, retrieval from SEC as needed. The text itself is **not stored in the DB**; only the filing identifier (accession) and the section are stored.
- **Section split:** code finds the Item headings in the HTML and splits into sections; a section not found → the questions that depend on it are "insufficient evidence", flagged `section_not_found`.
- **Length:** each question receives only its sections (table 5). A section longer than the model limit is trimmed in a fixed order (start of section + relevant sub-headings), flagged.
- **Non-US companies:** in the Israel stage — the periodic report from MAYA, the same sections by the Israeli report structure.

## 4. Answer format (JSON) and code checks

### 4.1 Quality judgment (type A)
```
{"question_id": "B3.1-Q1",
 "answer": 2 | 1 | 0 | null,
 "insufficient_evidence": false,
 "reasoning": "up to 3 sentences",
 "quotes": [{"text": "exact quote", "section": "TXT-001"}],
 "extra": {"one_sentence": "..."}}      // only for questions that ask for extra output
```

### 4.2 Data extraction (type B)
```
{"item_key": "cet1_ratio_standardized", "period": "FY2025",
 "value": 15.7, "unit": "percent" | "USD" | "count" | "ratio",
 "scale": 1 | 1000 | 1000000, "basis": "group" | "company_share" | "...",
 "value_state": "value" | "NA" | "not_disclosed",
 "quote": {"text": "exact quote that contains the number", "section": "note:Regulatory Capital"}}
```

### 4.3 Classification (type C)
```
{"question_id": "CLS-1", "industry": "<one of the list>", "quotes": [...], "reasoning": "..."}
```

### 4.4 What code checks in every answer

| # | Check | Failure → |
|---|---|---|
| 1 | Valid JSON per the structure | One retry, then "insufficient evidence" |
| 2 | Allowed value (2/1/0; industry from the list; unit from the list) | Same |
| 3 | **The quote appears word for word in the text sent** (after normalizing whitespace and quote marks) | Answer rejected → "insufficient evidence", flag `quote_not_found` |
| 4 | Extraction: **the number appears inside the quote** (after scale conversion) | Rejected → missing, flag `value_not_in_quote` |
| 5 | Extraction: the period matches the report year | Rejected → missing |
| 6 | Judgment: at least one quote for every answer other than "insufficient evidence" | Rejected |

Conversion to points is done by code, per the card (e.g., B3.2-Q5: answer × 0.5).

## 5. Question catalogue (type A)

The scale (what 2, 1, 0 mean) is taken **verbatim** from the Rulebook card and inserted into the prompt. If the card changes, the question version is raised and the answers are recomputed.

| ID | Card | Question | Sections | When asked | Extra output |
|---|---|---|---|---|---|
| B3.1-Q1 | Buffett 3.1 #1 | Is it clear what the company sells? | TXT-001 | Always | — |
| B3.1-Q2 | Buffett 3.1 #2 | Is it clear who the customers are? | TXT-001 | Always | — |
| B3.1-Q3 | Buffett 3.1 #3 | Are the revenue sources simple to understand? | TXT-001, TXT-005 | Always | — |
| B3.1-Q4 | Buffett 3.1 #4 | Are the main risks clear? | TXT-002 | Always | The 2–4 risks |
| B3.1-Q5 | Buffett 3.1 #5 | Can the business be explained in one sentence? | TXT-001 | Always | The sentence (≤25 words) |
| B3.2-Q4 | Buffett 3.2 #4 | Is the competitive position stable? | TXT-001, TXT-003 | Always | — |
| B3.2-Q5 | Buffett 3.2 #5 | Is there a clear moat? | TXT-001, TXT-003 | Always | Moat source |
| B3.7-Q3 | Buffett 3.7 #3 | Did M&A create value? | TXT-004, business-combination note | **Only** when code found acquisitions material (≥10%, or Σ FCF ≤ 0 with acquisitions) | — |
| B3.7-Q5 | Buffett 3.7 #5 | Is management transparent, conservative and consistent? | TXT-004 | Always | — |
| B3.8-Q6 | Buffett 3.8 #6 | Does the growth look sustainable? | TXT-001, TXT-004 | Always | — |
| G3.1-Q3 | Graham 3.1 #3 | Is there a critical dependence on one product, customer or market? | TXT-001, TXT-005 | Always | Largest customer / product and its share |
| G3.1-Q4 | Graham 3.1 #4 | Does the company have a proven business position in its industry? | TXT-001, TXT-003 | Always | — |
| G3.8-Q3 | Graham 3.8 #3 | Do reported earnings depend on one-time items? | TXT-004, income statement and notes (5 years) | STANDARD / TECH | — |
| G3.3B-Q4 | Graham 3.3-BANK #4 | Is the loan book diversified? | TXT-001, TXT-004, loan note | **Only** without a loan breakdown (D4) | — |
| CLS-1 | Part B.1 tier 3 | Which ValueCompass industry does the company belong to? | TXT-001 | **Only** when tiers 1–2 did not decide | — |

**Profile adjustments** (same question, extended input — per the cards):
- **Income real estate:** B3.1 — input adds asset types, lease structure and corporate complexity. B3.2-Q4/Q5 — the instruction distinguishes a durable location / asset advantage from a temporarily rising property market. B3.7-Q3 — **corporate** acquisitions only, not property purchases. B3.7-Q5 — input adds equity issuance vs value per share and use of disposal proceeds. B3.8-Q6 — organic vs acquisition-led vs revaluation-led growth.
- **Banks and insurance:** questions unchanged; input is the same sections.

## 6. Extraction catalogue (type B)

The items the dictionary marks "**AI**" when untagged. Every extraction: value, unit, scale, period, basis, quote.

| Dictionary | Item | Profile | Where in the report | Notes |
|---|---|---|---|---|
| FIN-106 | CET1 and required CET1 (per approach) | Banks | Regulatory capital / Item 7 | Both approaches when reported (D10, V9) |
| FIN-107 | LCR | Banks | LCR disclosure | Q4 average; measurement type (V10); exemption (V11) |
| FIN-140 | Loan breakdown | Banks | Loan note | Lines as reported; mapping to the 5 categories in code |
| FIN-141, FIN-144 | Total regulatory capital; RWA | Banks | Regulatory capital | Per approach |
| FIN-170, FIN-171 | Uninsured deposits; SCB, G-SIB | Banks | Item 7 / capital | — |
| FIN-117 | Regulatory capital ratio and regime | Insurance | Solvency / statutory disclosure | Q3: group / subsidiary, stated floor, year t−1 |
| FIN-118 | Prior-period development | Insurance | Reserve roll-forward | Only when untagged |
| FIN-136 | Investment portfolio by category and rating | Insurance | Investment / credit-quality note | Q8b |
| FIN-175 | Catastrophe losses; ALM disclosure | Insurance | Item 7 | — |
| FIN-043, FIN-044 | New-investment yields; same-property NOI growth | Real estate | Item 7 / supplemental | RE21 basis recorded |
| FIN-121, FIN-122 | Maintenance capex; income-preserving TI/LC | Real estate | AFFO reconciliation | — |
| FIN-125, FIN-143 | Economic property value; stabilized vs development | Real estate | Fair-value note | — |
| FIN-137, FIN-138 | Committed facilities; maturities | Real estate | Debt / liquidity note | Only when untagged |
| FIN-142 | Unencumbered NOI / assets | Real estate | Debt note | — |
| FIN-145, FIN-146 | Occupancy; largest tenant | Real estate | Item 1 / Item 7 | Metric by asset type (table A) |
| FIN-152, FIN-182 | Balance-sheet line classification for NAV | Real estate | Balance sheet | The AI assigns a line to an RP2a class; code sums |
| FIN-153, FIN-184 | OP units; single-basis items | Real estate | Equity / EPS note | RE28 |
| FIN-180, FIN-181 | RE30 items; FFO reconciliation lines | Real estate | FFO reconciliation | — |
| FIN-183 | Profile-test inputs | Real estate | Balance sheet / income statement | Every year in the window (K4b: AMT, EQIX, PSA) |
| FIN-191 | Mortgage loans and MBS | Router | Balance sheet / notes | Only when untagged |
| — | Insurance-liability components in an extension tag | Router / insurance | Reserve note | Found in K4b: CI, ALL |

## 7. Approval of answers (decided 2026-10-21)

| Type | When used | Admin approval |
|---|---|---|
| Quality judgment (type A) | **Immediately** once it passes every check (4.4) | None. Sample review; manual correction with a reason, stored as a new version |
| Data extraction (type B), default | Immediately once it passes every check | None |
| Data extraction with a **control** (table 7.1) | Immediately when the control passes | **Only when the control fails** |
| Data extraction **always approved** (table 7.1) | Only after approval (development: used with the flag `extraction_unapproved`) | **Always** |
| Industry classification (type C) | Per Part B.1: automatic when it agrees with the provider industry | **Always on disagreement** |

### 7.1 Extractions with a control or always approved

| Skill | Why not fully automatic | Control | Approval |
|---|---|---|---|
| FIN-121, FIN-122 maintenance capex; TI/LC | Company definitions differ; income-preserving vs growth split is a judgment; an error moves OE, the base of the Buffett value in real estate | Q6: OE vs the company's AFFO − SBC; gap ≤15% | When Q6 is flagged |
| FIN-125, FIN-143 property value; stabilized vs development | The number is usually explicit, but the basis (consolidated / company share, JV) is not (RP2c); a wrong basis distorts LTV and NAV | Basis stated in the quote; value within a plausible range vs carrying value | When the basis is not explicit or the value is out of range |
| FIN-137, FIN-138 committed facilities; maturities | One number decides whether pricing is blocked (RP1a); total vs undrawn facility confusion flips the result | Distance from the threshold | When 12-month coverage is between 0.8x and 1.25x |
| FIN-152, FIN-182 balance-sheet classification for NAV | Interpretation, not extraction: dozens of lines assigned to RP2a classes, with no reported number to compare | None adequate | **Always** |
| FIN-153, FIN-184 OP units; single-basis items | Sets the share count and so every per-share value; complex structures | None adequate (rare: partnership REITs only) | **Always** |
| FIN-180, FIN-181 RE30 items; FFO reconciliation lines | Signs and double counting (the O FX case moved a price score 4.52 → 2.68) | E11 (computed vs reported FFO ≤10%) and RE29b (5 pp) | When a control is flagged |
| FIN-183 profile-test inputs | Sets the profile | Two-year stability; distance from the threshold | Only in the S3a band (±5 pp) |
| FIN-191 mortgage loans and MBS | Sets UNSUPPORTED | As FIN-183 | Only in the S3a band |
| Insurance-liability components in an extension tag | Sets the profile (CI, ALL) | As FIN-183 | Only in the S3a band |
| CLS-1 on disagreement | Two sources disagree; no automatic way to know which is right | — | **Always** (Part B.1) |

### 7.2 How approval works

1. **Review list:** every item awaiting approval appears in one list (admin screen, K7; until then a review file generated by a script). Each item shows: company, skill, the extracted value or answer, the **quote with its section and filing**, **why it is in the list** (always-approve skill / which control failed / borderline), and **the effect** (e.g., "if approved: 12-month coverage 0.95x → pricing blocked").
2. **Admin actions:** approve; correct (new value + reason); reject (→ missing). Bulk approval for a company or a skill. Every action is logged (who, when, reason) in `extraction_items` (`approval_status`, `approved_by`, `approved_at`).
3. **Until approved:** the value is **not used** in the published score. The sub-item is missing, or, for the profile, the previous profile stays (new company: STANDARD with the flag "classification pending"); for pricing: "pending review". In development the value is used with the flag `extraction_unapproved`.
4. **After approval:** the score is recomputed for that company only.
5. **Corrections later:** a corrected value is a new version; the old one stays in the log.

## 8. Cost, rate and storage

- **Volume per company per year:** about 13 quality questions + 0–15 extractions by profile + 0–1 classification → about 15–30 calls.
- **One call per question** (not one huge question), so each answer is checked and stored separately and a failure does not drop the rest. Gemini free-tier rate limits are checked at the start of K5; the queue handles waiting and retries.
- **Recompute** only for a new annual report or a raised question version; otherwise the stored answer is used.

## 9. Testing (part of K5)

1. **Reference set:** manual answers for about 10 sample companies (several per profile), all quality questions. Measure: agreement rate, and how often the AI is more than one point off.
2. **Stability:** the same question twice → the same answer (temperature 0).
3. **Quotes:** share of quotes found in the text. Target: 100% for answers used (the rest are rejected anyway).
4. **Extraction:** compare with the values already extracted by hand in the CSV files (about 1,250 rows) — the existing reference set.
5. **Score effect:** a new golden with AI answers instead of `ai_pending`; every score change explained by a specific answer.

## 10. Open decisions

| # | Question | Recommendation |
|---|---|---|
| 1 | Admin approval for quality judgments | **Decided 2026-10-21:** none (section 7) |
| 2 | Language of prompt and answer | English (reports and JSON in English); user display translated |
| 3 | Corporate governance from the proxy (DEF 14A) for B3.7-Q5 | Yes, when in the cache |
| 4 | Retroactive extraction for every window year (FIN-183, insurance components) | Yes, only for items the router or the scoring need per year |

## 11. Further skills (approved 2026-10-21; implemented in their own stage)

Defined now because three of them shape the database (stage K6). Same principles as section 1: fixed model and versioned prompt, temperature 0, stored output, code checks.

| Skill | What it does | Input | Rules | Stored / refreshed | Approval | Stage |
|---|---|---|---|---|---|---|
| **D. Company background** | 4–6 lines: what the company does and its products; segments; where it operates and its business environment; main competitors; competitive advantage | TXT-001, TXT-003, TXT-005; our data (industry, profile, revenue) | Facts only from the report; numbers only from our data. The competitive advantage **reuses the stored B3.2-Q5 answer** (moat), so the background never contradicts the score | Once per annual report | None | K5 |
| **E. General fallback extraction** | When code finds no XBRL tag for any dictionary item (not only the catalogue in section 6), extracts it from the financial statements | Item definition from Rulebook Part E; statements and notes | Checks 4.4 + **outlier control**: a value more than 3× or less than ⅓ of the adjacent years is flagged | With the facts | As 7.1: automatic; approval when the item sets value or profile, or the outlier control fails | K5 |
| **F. Results analysis** | Two paragraphs, each ≤60 words (enforced by code; longer → regenerated, not cut) — quality, then value: what drove the quality scores, what drove the value and price scores, the main strength, the main weakness, what limits the buy price, and the position vs peers | **Only our results** (scores, sub-item values, flags) + peer position **computed by code** (e.g., quartile within the profile) | No fact or number that is not in the results; every claim maps to a sub-item; no reference to today's price (the numbers beside it show the price) | **Once per scoring run** that changes scores (new report or Rulebook version); the stored text is shown, never regenerated on view | None | End of K5 |
| **G. Smart search** | Turns a free-text request into a structured query: company names / tickers it recognized and filters from a closed list of fields and operators | The request; the list of fields, operators and profiles | The AI never runs SQL; **code** resolves names and tickers in the DB and runs the filters; the interpretation is shown above the results; free name/ticker search works without AI (fuzzy match) | Not stored (cached per request text) | None | K6–K7 |

**Company not in the database (for the ETL stage):** when the search finds no company, the app either offers "add this company?" or adds it automatically with the message "processing and analysing the company, please wait a few minutes". Decided 2026-10-21: **automatic** (no user confirmation). Open for K6: supported exchanges; limits per user; whether an UNSUPPORTED company is added (shown as "not supported").

## 12. Later decisions merged into this version (2026-10-21)

| # | Decision |
|---|---|
| 1 | Results analysis: two paragraphs (quality; value), each ≤60 words — replaces "one paragraph ≤100 words" |
| 2 | **Revised 2026-10-24:** the company background (D1) is written by the AI in **English** (all checks run on the English text against the report) and then translated to Hebrew in a second short call (T1) with the glossary; both versions are stored. The results analysis (D2) is **generated by code** from fixed sentence frames, directly in Hebrew — no AI. Judgment and extraction answers stay in English (internal). Reason: the fixed model produced mixed-script errors (Arabic or Latin letters inside Hebrew words) when composing Hebrew from long English text |
| 3 | A company not in the database is added automatically (K6) |
| 4 | Peer group: computed by code, fixed — same profile and same ValueCompass industry; fewer than 5 companies → same profile only; n and definition always shown |
| 5 | The model is selected by quality, not latency: agreement with a reference set, stability ≥95%, availability on the free tier; once selected it is pinned (no automatic fallback to another model); a model change is a new version and answers are recomputed (R18) |
| 6 | **Pinned model (2026-10-22):** `gemini-3.5-flash-lite`, temperature 0, seed 20261021; free tier, 500 requests/day per Google project (code cap 450). Smart search and file-column mapping use a separate Google project and key |
| 7 | Every call cap is enforced in code (the shared daily counter stops the run), never by manual checking |
