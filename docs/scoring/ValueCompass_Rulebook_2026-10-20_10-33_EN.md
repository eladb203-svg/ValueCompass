---
title: "ValueCompass — Rulebook"
subtitle: "Closed 2026-10-20_10-33 · English (source of truth)"
---

# ValueCompass — Rulebook

**Version:** closed 2026-10-20_10-33 (amends 2026-10-17_21-51: C5 extended, CL12; FIN-186 added, CL13). **Status:** **closed — the source of truth** for the scoring rules, for the database (stage 2) and for the code (stage 3). It supersedes the governing files: general model v1.3 (2026-10-14_22-35), BANK 2026-10-13_10-20, INSURANCE 2026-10-13_17-25, INCOME_REAL_ESTATE 2026-10-15_11-45 and the consolidated sector rules 2026-10-15_12-00 (S-06: those files still carry the pre-X1 rule and are not to be used). Closure rests on the verification of the book against the source files and the code (2026-10-15, Part V) and on the decision list approved on 2026-10-17 (Part G). Where the code differs from this book, the book governs and the code is aligned in stage 3 (Part H).
**Language:** English is the source of truth; the Hebrew version is a translation.

| Part | Content | Status |
|---|---|---|
| A | Principles and shared rules | ✅ |
| B | Profile assignment | ✅ |
| C | Quality criterion cards (16) | ✅ |
| D | Pricing cards per profile | ✅ |
| E | Data dictionary | ✅ (ETL mapping from the engine; 26 items added) |
| F | ETL requirements | ✅ |
| G | Decision log | ✅ (incl. closure decisions 2026-10-17) |
| H | Known limitations and items to implement | ✅ |
| V | Verification result | ✅ closed |

---

## Part A — Principles and shared rules

**Precedence rule (P0):** the general model applies to every profile. A sector file overrides the general model **only** in the sub-items listed in its "replaced criteria" and "kept criteria — adjustments" tables (sections 4 and 5 of each sector file, mapped in sections 4–5 below). Anything a sector file does not list is governed by the general model. A sector file never changes a shared rule (section 2) unless that rule says so.

**Shared rules across profiles**

| Rule | Content | Source |
|---|---|---|
| R1–R18 | Principles (determinism, code computes, AI only answers defined questions with evidence, no manual exceptions, smoothed growth R14, etc.) | General model |
| C1–C17 | Clarifications. Cross-profile: C1 periods (t−4 … t), C7 dilution by period-end shares, C14 share-scale guard (ETL), C15 value ≤ 0 → "cannot be valued", C16 price and financials of the same listed entity | General model, C17 partial-window scaling |
| M1–M9, D14 | Missing-data policy: missing ≠ 0, criterion valid at ≥70% of points, coverage ≥80% for a full score, no buy price below 80%, no imputation in values; D14 score and range on the same valid set | General model |
| K1 | Every threshold needs an economic or regulatory anchor; the sample only tests discrimination | BANK (adopted by all) |
| Required return | 10% for every Buffett value model (DCF or excess returns); terminal growth 2.5% | General model; sector files |
| Price scales | Buffett: ≥40% discount = 10; classic Graham: ≥50% discount = 10; proportional between anchors (R4) | General model |
| Margin of safety | Buy price = value × (1 − margin by the model's quality score); quality below 55 → "not suitable for purchase" | General model |
| Quality ≠ price | Quality score and value are separate measures in every profile | All |

**Roles in every card:** *Extracts* = who brings the input (code from structured data / AI extraction from text with a quote, approved by the admin); *Computes* = who applies the formula (always code); *Judges* = who assigns the sub-item value (code by thresholds; AI only for a defined qualitative question on the 2 / 1 / 0 scale, then code converts it to points, R1, R13).

**Effect labels for exceptions:** *Missing* (reduces coverage, M1–M5); *N/A* (excluded, no coverage penalty, R9); *Fixed value* (a stated score is assigned); *Rule change* (the formula changes for that case); *Flag* (display only, no score effect).

### A.1 Principles (R1–R18)

| # | Principle | Status |
|---|---|---|
| R1 | A qualitative sub-item is scored by AI from fixed questions on a 2 = clearly yes, 1 = partly, 0 = no scale. Stored in score_details with the reasoning, without history | ✅ 2026-10-10 |
| R2 | Every qualitative question has a verbal definition for each level (2/1/0), which the AI Skill receives. No quantitative anchors | ✅ 2026-10-10 |
| R3 | A criterion's score is the sum of its sub-items. The verbal band tables in the scorecards are display labels only | ✅ 2026-10-10 |
| R4 | Quantitative metric: proportional score (linear interpolation) between thresholds. Below the lower threshold = 0, above the upper threshold = maximum. More than two anchors are allowed (piecewise linear) | ✅ 2026-10-11 |
| R5 | Default measurement period: last 5 years, minimum 3 years, otherwise "missing data". Exception: a criterion that the scorecards explicitly define over 10 years | ✅ 2026-10-11 |
| R6 | A sub-item with no data in the sources (e.g., market share) becomes an AI question based on the annual-report text | ✅ 2026-10-11 |
| R7 | A metric already scored in another criterion is measured twice only for a different aspect (e.g., ROIC: level in 3.4, persistence in 3.2) | ✅ 2026-10-11 |
| R8 | No company- or industry-specific scoring exceptions in the general model. Sector adjustments only through methodology_profile and the sector spec | ✅ 2026-10-11 |
| R9 | A company that does not report a metric gets "not applicable" on that sub-item, not 0. Re-weighting is defined in the missing-data policy | ✅ 2026-10-11 |
| R10 | No penalty for fast growth. The risks of growth companies are measured in 3.5, 3.6, 3.7 and 3.8 | ✅ 2026-10-11 |
| R11 | Ratios between cumulative figures (FCF to net income, capex to net income) are computed on 5-year sums | ✅ 2026-10-11 |
| R12 | Balance-sheet metrics are measured in two aspects: current state (latest year) and consistency over 5 years | ✅ 2026-10-11 |
| R13 | The sub-item structure of the scorecards is kept. Each sub-item is decided by code or by AI, not both. Allowed exception: code decides whether an AI question is needed at all | ✅ 2026-10-11 |
| R14 | Growth of a volatile metric (EPS, FCF) is measured as "smoothed growth": average of the last 2 years vs. average of the first 2 years of the period, annualized over 3 years | ✅ 2026-10-11 |
| R15 | Conversion to USD when comparing with an absolute threshold: flow items (revenue, earnings, cash flows) at the average rate of the reporting year; balance-sheet items at the balance-sheet-date rate; market value and price at the rate on the measurement date | ✅ 2026-10-11 |
| R16 | Every AI answer returns a 0/1/2 score, reasoning, source (report and section) and supporting figure where available. When evidence is insufficient: "insufficient evidence", treated as missing data, never as 0 or an intermediate score | ✅ 2026-10-11 |
| R17 | Data missing because of a collection failure (the company exists but we could not retrieve the data) is "missing data", not 0. A score of 0 only when the data shows weakness | ✅ 2026-10-11 |
| R18 | For every AI assessment, store the scoring-model version, prompt version, source-document ID, extracted evidence and resulting score. An approved qualitative score is not recomputed unless the source data or the methodology version changes. Same company + same data + same version = same score | ✅ 2026-10-11 |

### A.2 Implementation clarifications (C1–C17)

| # | Clarification |
|---|---|
| C1 | "5 years ago" / "first year of the period" = t−4 (5 fiscal years, 4 intervals) everywhere |
| C2 | Invested capital = equity + financial debt − cash − short-term investments (same cash definition as net debt) |
| C3 | Cash and short-term investments exclude funds held for customers. For liquidity ratios, customer-funds assets and the matching liabilities are removed from both current assets and current liabilities |
| C4 | Gross profit: if not reported, derive revenue − cost of revenue; derive cost of revenue from its components only when both goods and services lines exist; otherwise "not applicable" |
| C5 | A line item absent from a statement that was retrieved for that year (buybacks, acquisitions, dividends, impairments, goodwill, intangibles, short-term investments, preferred stock, preferred dividends) = 0 with an "assumed_zero" flag; if the statement itself is missing → missing data |
| C6 | Acquisitions: when the acquisitions line is absent, goodwill acquired in the year is used as a lower-bound proxy (flagged) |
| C7 | Dilution tests (Buffett 3.7 #2, Graham 3.8 #2, Graham Tech gate) use period-end shares outstanding; per-share values (EPS, fair value) use weighted diluted shares. When the period-end count is missing: weighted diluted shares, flagged (STANDARD and TECH_ASSET_LIGHT; BANK / INSURANCE: missing) (2026-10-17) |
| C8 | Dividend per share: if not reported, dividends paid / weighted basic shares (flagged) |
| C9 | D&A: prefer the cash-flow total D&A tag; otherwise depreciation + amortization components, plus finance-lease right-of-use amortization (never added on top of a total tag). When several total tags are filed, the largest; a total below 50% of the component sum is replaced by the components (2026-10-17) |
| C10 | AI items not yet answered ("ai_pending") are a temporary state: excluded from M2 validity and coverage, shown only in the min–max range. In production, AI "insufficient evidence" is missing data (R16) |
| C11 | TECH_ASSET_LIGHT liquidity: current deferred revenue (contract liabilities) is counted in current liabilities only at its cost to deliver: deferred revenue × (1 − latest gross margin); 30% if gross margin is not available. This adjusted working capital is used in Graham 3.2, Graham 3.3 #2 and Buffett 3.6 #3. STANDARD is unchanged |
| C12 | Liquidity (display only): an alternative current ratio that adds non-current marketable debt securities to current assets is shown next to Graham 3.2 / Buffett 3.6 #3. It is **not scored** (rejected 2026-10-13: the explicit tag rarely exists and the derived estimate cannot test credit quality) |
| C13 | Gross margin: when a claims / benefits expense is reported (`PolicyholderBenefitsAndClaimsIncurredNet` or equivalent; not a total-costs tag such as `BenefitsLossesAndExpenses`), it is part of cost of revenue, also when no cost-of-revenue tag exists (e.g., managed care) |
| C14 | Share-count guard (ETL, all profiles): a share-count value about 1,000× off its neighbours (units tagged in thousands) is rescaled and flagged; a larger mismatch = missing; a count below 100,000 (units tagged in millions) is multiplied by 1,000,000 and flagged (2026-10-17) |
| C15 | Fair value ≤ 0 (Buffett DCF or any value model): shown as "cannot be valued (debt exceeds modeled value)", price score 0, no buy price; a negative value is never displayed (2026-10-14, consistent with BANK V6) |
| C16 | Price and financials of the same listed entity (all profiles): when the listed security changed (merger, spin-off, reorganization) and the price belongs to a successor while the financials belong to the predecessor (or the reverse), price score and buy price = "cannot be priced (price and financials of different entities)"; quality is still shown. No exchange-ratio conversion: the successor's value is not the predecessor's value. Pricing resumes once the successor's own financials are reported (2026-10-14, EQR → VMRK) |
| C17 | Partial window (all profiles): a "years of 5" or "transitions of 4" count computed on 3 or 4 valid years (R5 minimum: 3) is scaled to the full window — count × full window / valid window — and flagged `partial_window`. Without it, 3 good years of 3 would be penalized as 3 of 5 (2026-10-17) |

### A.3 Missing-data policy (M1–M9, D14)

#### Sub-item states

| State | When | Example | Effect |
|---|---|---|---|
| Score | Data exists and is computed | | Counted |
| Not applicable (R9) | The metric does not apply to the company by its nature | No buybacks (Buffett 3.7 sub-item 1), no reported gross profit | Excluded from the calculation, no coverage penalty |
| Missing data (R5, R17) | The data should exist but could not be retrieved, or fewer than 3 years | The ETL did not extract working capital | Excluded from the calculation and reduces coverage |
| Insufficient evidence (R16) | The AI found no basis for an answer, or failed | | Same as missing data |
| True 0 | The data exists and shows weakness | No dividend in Graham 3.5, negative equity | Counted as 0 |

#### Rules

| # | Rule |
|---|---|
| M1 | **Criterion score:** sum of the computed sub-items, divided by the sum of their maximums, times the criterion's full weight. A missing sub-item is neither counted as 0 nor granted points |
| M2 | **A criterion is valid** only if at least 70% of its points were computed. Otherwise the whole criterion is "missing data" |
| M3 | **Model quality score:** sum of the valid criteria, scaled to 100 the same way |
| M4 | **Coverage** = share of points (out of 100) actually computed. "Not applicable" counts as covered; "missing data" and "insufficient evidence" do not |
| M5 | Coverage ≥80%: full score. 60%–79%: score flagged "partial", no buy price. Below 60%: no score, "missing data" |
| M6 | **Fair value:** no imputation or assumptions. If any input of the formula is missing → "cannot be valued" and price score "not applicable" |
| M7 | **Buy price** is computed only when there is a fair value and a quality score with coverage ≥80% |
| M8 | **Display:** each score shows the coverage percentage and the list of missing sub-items, with the reason |
| M9 | **Storage:** for every criterion and model, store the normalized score, the points actually observed, the coverage, and a range: minimum (all missing = 0) and maximum (all missing = full). When coverage is below 100%, the range is displayed next to the score. **Range rule (D14):** score, minimum and maximum use the same set of valid criteria; invalid criteria (below M2) enter none of them; not-applicable items create no uncertainty; mandatory check minimum ≤ score ≤ maximum, otherwise the range is not published and an error is logged |

#### Example

A 10-point criterion with 4 sub-items (3+3+2+2). One 2-point sub-item is missing; the others scored 2.5 + 3 + 1.5 = 7 of 8 → 7/8 × 10 = **8.75**, range 7–9. 80% of the points were computed → the criterion is valid (70% threshold).

### A.4 Threshold calibration (K1)

Every threshold needs an economic or regulatory anchor. The sample distribution is used only to test discrimination, not to set thresholds (avoids overfitting a small sample in a benign period). Thresholds marked "check" are reviewed on a broader sample.

### A.5 Graham quality gate (X1, decided 2026-10-15)

One rule for all profiles: the Graham price score is shown, labelled, and the buy price is "not suitable for purchase" when Graham quality is below 55. (Replaces the BANK / INSURANCE rule that hid the score. The code still hides it for BANK and INSURANCE: H-01.)

### A.6 Graham quality labels (display)

| Graham quality score | Label |
|---|---|
| 85–100 | Very conservative and strong |
| 70–84 | Good and stable |
| 55–69 | Borderline |
| Below 55 | Not suitable for the defensive approach |

Display only; scores, margins of safety and buy-price rules are unchanged (general model, "Graham quality summary"; S-05).

---

## Part B — Profile assignment (S3, S3a)

Two layers: **classification** (sector, industry — display and peer comparison, no effect on scores) and **methodology_profile** (selects the model). Code assigns; rows are tested in order and the first match wins.

| Order | Profile | Candidate industries | Confirming test (latest year, code) | Fails → |
|---|---|---|---|---|
| 1a | BANK | Banks | Deposits / total liabilities ≥50% and loans / total assets ≥30% | 1b |
| 1b | BANK | Banks; investment banks and brokers; consumer and commercial credit | Reports regulatory CET1 and LCR as a supervised bank holding company | Investment banks / brokers → STANDARD; credit → UNSUPPORTED |
| 2 | INSURANCE | Insurance; managed health insurance | Insurance liabilities / total liabilities ≥50% | STANDARD (US managed-care organizations fail: Health Care sector, STANDARD) |
| 3 | INCOME_REAL_ESTATE | Income real estate / property REIT | Investment property / total assets ≥50% and rental revenue / total revenue ≥50% (extracted data when tags are missing, RE11; real estate incl. acquired lease intangibles, RE15) | STANDARD (e.g., WELL) |
| 4 | UNSUPPORTED | Mortgage REITs; BDCs and credit funds; non-bank lenders not passing 1b | — | |
| 5a | TECH_ASSET_LIGHT | Software; IT services; internet and advertising | None (industry suffices) | |
| 5b | TECH_ASSET_LIGHT | Hardware; semiconductors; semiconductor equipment; communications equipment; components | R&D / revenue ≥10% and gross margin ≥50% (5-year medians) | STANDARD |
| 6 | STANDARD | All others, incl. asset managers, insurance brokers, exchanges, payments, developers and homebuilders | — | |

- **S3a — borderline:** a test result within 5 pp of its threshold → "borderline assignment" flag and an admin review list; code still decides. When a tag is missing, the test runs on extracted data (the AI extracts numbers; code tests).
- **Stability:** recomputed with every annual report; the profile changes only after two consecutive years with a different result. Industry changes are logged.
- **Manual override (P1):** the admin may correct industry or profile, with a stored and displayed reason.
- **Classification source:** US — SEC SIC mapped to the ValueCompass taxonomy (own names, not GICS); Israel — TASE industry; others — data-provider classification. No classification → AI question choosing from a closed list (R16, R18).

---

## Part C — Quality criterion cards

## C.B3.1 Buffett 3.1 — Simple, understandable business (10)

**What it measures:** whether an investor can understand what the company sells, to whom, how it earns and what can go wrong — Buffett's circle of competence.

### C.B3.1-STD — all profiles

| # | AI question | 2 = clearly yes | 1 = partly | 0 = no |
|---|---|---|---|---|
| 1 | Is it clear what the company sells? | The main products or services can be named in simple words | Generally clear, but many products or very technical ones | Unclear what is actually sold (holdings, complex financial products) |
| 2 | Is it clear who the customers are? | The main customer types can be identified (consumers, businesses, governments) | Several different customer types, or sales through intermediaries that hide the customer | Unclear who pays |
| 3 | Are the revenue sources simple to understand? | Few main sources, with a clear model (sale, subscription, fee) | Several sources, or a model that needs explanation (licensing, advertising, financing) | Many unrelated sources, or a non-transparent model |
| 4 | Are the main risks clear? | 2–4 concrete business risks can be named | Very generic risks, or so many that they cannot be ranked | The business depends on a factor that cannot be assessed (single clinical trial, commodity price, open regulation) |
| 5 | Can the business be explained in one sentence? | A sentence of up to 25 words: what, for whom, and how it makes money | Needs two sentences, or the sentence omits a central part | Not possible |

- **Score:** sum of the 5 answers (0–10), 2 points each. Display label: 0–3 "complex", 4–7 "partly understandable", 8–10 "simple and clear" (R3).
- **Inputs:** TXT-001 Business section, TXT-002 Risk Factors, FIN-060 revenue breakdown.
- **Roles:** Extracts: code (document retrieval). Computes: code (sum). Judges: **AI** per question (2 / 1 / 0, with reasoning, source and "the one sentence"), converted to points by code (R1, R2, R16).
- **Sector variants:** BANK, INSURANCE — unchanged. INCOME_REAL_ESTATE — unchanged questions; the AI input adds asset types, lease structure and corporate complexity.

| Exception | Effect | Rule |
|---|---|---|
| No business description | Criterion **Missing** | General model |
| AI finds insufficient evidence for a question | That question **Missing** (never 0 or a middle score) | R16 |
| No new annual report | Not recomputed; the approved score stays | R18 |

---

## C.B3.2 Buffett 3.2 — Moat (10)

**What it measures:** durable competitive advantage — stable margins, persistent returns and an identifiable moat source. Margin stability weighs more than margin level (R8).

### C.B3.2-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds | Judges |
|---|---|---:|---|---|---|---|
| 1a | Gross margin level | 1.0 | Gross profit / revenue; median | 5 years | ≤20% = 0, ≥40% = 1.0 | Code |
| 1b | Gross margin stability | 1.5 | Range (max − min) of the gross margin | 5 years | ≤3 pp = 1.5, ≥10 pp = 0 | Code |
| 2a | Operating margin stability | 1.5 | Range of EBIT / revenue | 5 years | ≤4 pp = 1.5, ≥12 pp = 0 | Code |
| 2b | No operating margin erosion | 1.0 | Latest operating margin vs the 5-year median | 5 years | ≥ median − 1 pp = 1.0, ≤ median − 5 pp = 0 | Code |
| 3 | Persistent ROIC | 2.0 | Years of 5 with ROIC ≥12% (ROIC as in C.B3.4-STD) | 5 years | 5 = 2, 4 = 1.5, 3 = 1, 2 = 0.5, ≤1 = 0 | Code |
| 4 | Stable competitive position | 2.0 | AI question (Business and Competition sections) | Latest report | 2 / 1 / 0 | AI |
| 5 | Clear moat | 1.0 | AI question; answer × 0.5 | Latest report | 2 / 1 / 0 | AI |

| # | AI question | 2 | 1 | 0 |
|---|---|---|---|---|
| 4 | Is the competitive position stable? | Market leader or among the largest, with a stable or improving position | Stable but not leading, or mixed signals | Losing market share, or the position is eroding (new entrants, price war) |
| 5 | Is there a clear moat? | A concrete moat source can be named (brand, switching costs, scale, network effect, regulation, data, infrastructure), with evidence from the report | A plausible but generic or unproven moat | No identifiable moat, commodity product |

- **Inputs:** FIN-060 revenue, FIN-061 cost of revenue / gross profit, FIN-001 EBIT, ROIC inputs (C.B3.4), TXT-001 Business, TXT-003 Competition.
- **Roles:** Extracts: code (XBRL; report text for the AI). Computes: code. Judges: code (1a–3), **AI** (4–5).
- The 20% / 40% gross-margin thresholds are reference points from the common Buffett-style rule of thumb; they do not decide alone whether a moat exists.

| Exception | Effect | Rule |
|---|---|---|
| No reported gross profit | 1a and 1b **N/A**; derive revenue − cost of revenue when possible; cost of revenue from components only when both goods and services lines exist | R9, C4 |
| Claims / benefits expense reported | Counted in cost of revenue (also without a cost-of-revenue tag) | C13 |
| Invested capital ≤ 0 in a year (sub-item 3) | As C.B3.4-STD | General model |
| AI insufficient evidence | Question **Missing** | R16 |

### C.B3.2-BANK

| # | Change vs STD | Formula | Thresholds |
|---|---|---|---|
| 1a, 1b | **N/A** | — | — |
| 2a, 2b | Pretax margin instead of operating margin | Pretax income / bank revenue; bank revenue = net interest income + noninterest income | Same as STD (D8) |
| 3 | Persistent return on ROTCE | Years of 5 with ROTCE ≥12% (ROTCE as C.B3.4-BANK) | 5 = 2, 4 = 1.5, 3 = 1, 2 = 0.5, ≤1 = 0 |
| 4, 5 | Unchanged (AI) | | |

- **Inputs:** FIN-003 pretax income, FIN-063 net interest income, FIN-064 noninterest income, ROTCE inputs. **Effect of N/A:** the criterion is scored on the remaining 7.5 points and scaled to 10 (M1); coverage unaffected (R9).

### C.B3.2-INS

| # | Change vs STD | Formula | Thresholds |
|---|---|---|---|
| 1a, 1b | **N/A** | — | — |
| 2a, 2b | Total operating margin | Pretax normalized operating profit / operating revenue (C.B3.4-INS); operating revenue = total revenue − investment gains in profit or loss | Same as STD |
| 3 | Persistent return on operating ROE | Years of 5 with operating ROE ≥10% | 5 = 2, 4 = 1.5, 3 = 1, 2 = 0.5, ≤1 = 0 |
| 4, 5 | Unchanged (AI) | | |

- **Effect of N/A:** scored on 7.5 points, scaled to 10 (M1). Years with operating ROE ≥10% are counted here only; Buffett 3.4.2 measures the downside (R7).

### C.B3.2-RE

| # | Change vs STD | Formula | Thresholds |
|---|---|---|---|
| 1a, 1b | **N/A** | — | — |
| 2a, 2b | Normalized FFO margin | Normalized FFO / revenue (normalized FFO: Part E, FIN-070, RE30) | Same as STD |
| 3 | **N/A** — return on capital measured in Buffett 3.4 (R7) | — | — |
| 4, 5 | AI; the AI distinguishes a durable location / asset advantage from a temporarily rising property market | | |

- **Effect of N/A:** scored on 5.5 points (2a, 2b, 4, 5), scaled to 10 (M1).

---

## C.B3.3 Buffett 3.3 — Consistent profitability (15)

**What it measures:** whether the business earns money year after year, without sharp drops — Buffett's preference for predictable earnings.

### C.B3.3-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Positive net income in most years | 6 | Years of 5 with net income > 0 | 5 years | 5 = 6, 4 = 4, 3 = 2, ≤2 = 0 |
| 2 | Stable EPS | 4 | Transitions (of 4) in which diluted EPS fell by more than 10% | 5 years | 0 = 4, 1 = 3, 2 = 1.5, ≥3 = 0 |
| 3 | Revenue growth | 3 | Revenue CAGR t−4 → t | 5 years | ≤0% = 0, ≥5% = 3 (no penalty for high growth, R10) |
| 4 | No exceptionally weak year | 2 | Net income in the weakest year / 5-year median net income | 5 years | ≤0 = 0, ≥50% of the median = 2 |

- **Inputs:** FIN-020 net income, FIN-062 diluted EPS, FIN-060 revenue.
- **Roles:** Extracts: code (XBRL). Computes: code. Judges: code.
- Sub-item 2 counts sharp drops instead of a coefficient of variation, which penalizes fast growth (R10).

| Exception | Effect | Rule |
|---|---|---|
| Negative median net income | Sub-item 4 = **fixed value 0** | General model |
| Fewer than 3 years | **Missing** | R5 |

### Sector variants

| Profile | Change vs STD |
|---|---|
| BANK | Revenue = bank revenue (net interest income + noninterest income); otherwise unchanged |
| INSURANCE | Revenue = operating revenue (total revenue − investment gains in profit or loss); otherwise unchanged |
| INCOME_REAL_ESTATE | By normalized FFO and normalized FFO per share (confirmed against the code, V-01): 1 = years of 5 with normalized FFO > 0; 2 = transitions of 4 with normalized FFO per share down >10%; 3 = CAGR of **total revenue** t−4 → t; 4 = weakest-year normalized FFO / 5-year median (median ≤ 0 → 0). STANDARD thresholds |


---

## C.B3.4 Buffett 3.4 — Return on capital (15)

**What it measures:** how much the business earns on the capital it uses — Buffett's test of a durable, high-return business. Level only; persistence is measured in Buffett 3.2 (R7).

### C.B3.4-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds (R4, linear between anchors) |
|---|---|---:|---|---|---|
| 1 | ROIC | 15 | ROIC_y = NOPAT_y / average invested capital_y; score on the median of the 5 yearly values | t−4 … t (C1) | ≤0% = 0, 6% = 4.5, 10% = 8.5, 15% = 12.5, ≥20% = 15 |

- **NOPAT** = EBIT × (1 − tax rate); tax rate = income tax / pretax income, clipped to 0%–40%; pretax loss or implausible rate → 25%.
- **Invested capital** = equity + financial debt − cash − short-term investments (C2), average of beginning and end of year.
- **Inputs:** FIN-001 EBIT, FIN-002 income tax, FIN-003 pretax income, FIN-010 equity, FIN-011 financial debt, FIN-012 cash, FIN-013 short-term investments.
- **Roles:** Extracts: code (XBRL). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Invested capital ≤ 0 in a year | **Rule change** for that year: use operating invested capital (total assets − cash and short-term investments − non-debt current liabilities); if that is also ≤ 0: positive NOPAT → ROIC_y = 20%, NOPAT ≤ 0 → 0%; then the median as usual | General model |
| Fewer than 3 years available | **Missing** | R5 |
| Funds held for customers | Excluded from cash (and from liquidity tests) | C3 |
| ROE | **Flag** (display only, not scored) | General model |

### C.B3.4-BANK — BANK

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | ROTCE | 10 | (net income − preferred dividends) / average TCE; TCE = equity − preferred stock − goodwill − intangibles | 5-year median | ≤6% = 0, 12% = 6, ≥18% = 10 |
| 2 | ROA | 5 | Net income / average total assets | 5-year median | ≤0.5% = 0, ≥1.25% = 5 |

- **Inputs:** FIN-020 net income, FIN-021 preferred dividends, FIN-010 equity, FIN-022 preferred stock, FIN-023 goodwill, FIN-024 intangibles, FIN-025 total assets.
- **Roles:** Extracts: code (XBRL). Computes: code. Judges: code.
- **Anchors (K1):** ROTCE 6 / 12 / 18% and ROA 0.5 / 1.25% kept after the parallel run — they discriminate and have economic anchors.

| Exception | Effect | Rule |
|---|---|---|
| Path 1b (bank holding company without deposit funding) | None for this criterion (both sub-items apply) | S3 |
| Fewer than 3 years | **Missing** | R5 |

### C.B3.4-INS — INSURANCE

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Operating ROE | 10 | Normalized operating profit after tax / average adjusted equity | 5-year median | ≤5% = 0, 10% = 4, 15% = 7, ≥20% = 10 |
| 2 | Worst year | 5 | Lowest operating ROE of the 5 years | 5 years | ≤0% = 0, ≥8% = 5 |

- **Normalized operating profit (pretax)** = pretax income − non-recurring investment gains + identified one-off losses (goodwill impairment **added back**, as BANK V5: removing a one-off loss raises the profit; 2026-10-17); after tax at the effective rate clipped to 0%–40%, otherwise 25%.
- **Adjusted equity** = equity − preferred stock − rate-driven AOCI (AFS debt securities, discount-rate remeasurement of insurance liabilities, own credit on market-risk benefits); FX and pension AOCI kept.
- **Inputs:** FIN-003 pretax income, FIN-002 income tax, FIN-030 realized and unrealized investment gains, FIN-031 market-risk-benefit remeasurement, FIN-032 goodwill impairment, FIN-010 equity, FIN-022 preferred stock, FIN-033 AOCI by component.
- **Roles:** Extracts: code (XBRL; IFRS filers without XBRL: AI extraction). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Average adjusted equity ≤ 0 in a year | That year's ROE **undefined** (excluded from the median, flagged); sub-item 2 = **fixed value 0** when any year in the window has it | Q8e |
| AOCI component not separable | Equity as reported, **flag** | I13 |
| Change of reporting standard | Series within one standard only; fewer than 3 years under one standard → **Missing** | I18, R5 |
| Persistence | Not here — years with ROE ≥10% are counted in Buffett 3.2.3 (no double counting) | R7 |

### C.B3.4-RE — INCOME_REAL_ESTATE

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Estimated long-run return on new investment over WACC | 4 | (Initial yield on new investment + 2.5% model assumption) − WACC proxy. Direct: weighted stabilized yield on acquisitions and developments completed, as disclosed. Proxy (`NOI_PROXY`): (NOI_t − NOI_t−4 − organic NOI growth) / net growth capital invested t−4 … t−1 | 5 years | 0 pp = 0, 1 = 1, 2 = 2, 3 = 3, ≥4 pp = 4 (check, K1) |
| 2 | Same-property NOI growth | 6 | Like-for-like NOI growth as disclosed | 5-year median | ≤0% = 0, 2% = 3, ≥4% = 6 |
| 3 | NOI margin stability | 5 | Range (max − min) of NOI / property revenue | 5 years | ≤3 pp = 5, ≥10 pp = 0 |

- **WACC proxy** = D / (D + M) × average cost of debt + M / (D + M) × 10%; D = net debt, M = market capitalization at the latest year-end; REITs T = 0.
- **NOI** = rental + other property revenue − property operating expenses (incl. real-estate taxes); always computed by us.
- **Inputs:** FIN-040 rental revenue, FIN-041 other property revenue, FIN-042 property operating expenses, FIN-043 acquisition / development yields, FIN-044 same-property NOI growth, FIN-045 growth capital invested, FIN-046 dispositions, FIN-047 gross real estate at cost, FIN-011 debt, FIN-012 cash, FIN-050 interest expense, FIN-051 market capitalization.
- **Roles:** Extracts: code (income statement, debt, market cap); **AI extraction** with quote for yields (FIN-043), same-property NOI growth (FIN-044) and growth capital split (FIN-045). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No disclosed yields | Sub-item 1 on the proxy, **flag** `NOI_PROXY` | RE18 |
| Proxy: net growth capital < 5% of property value (economic value, else gross cost), or ≤ 0, or gross dispositions > 10% of real estate at t−4 | Sub-item 1 **Missing** | RE22, review 2026-10-15 |
| Same-property NOI history missing | Sub-items 1 (proxy) and 2 **Missing**; with 1 missing alone the criterion keeps 11/15 = 73% (valid, M2) | RE23, M2 |
| 2.5% term | Uniform model assumption, not measured per company; initial yield is before maintenance capex (upward bias) — stated limitation | RE31 |
---

## C.B3.5 Buffett 3.5 — FCF / owner earnings (15)

**What it measures:** whether profits turn into cash the owner could take out without hurting the business — Buffett's owner earnings.

### C.B3.5-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Positive FCF in most years | 5 | Years of 5 with FCF > 0; FCF = CFO − capex | 5 years | 5 = 5, 4 = 3.5, 3 = 2, ≤2 = 0 |
| 2a | FCF margin level | 2 | Median of FCF / revenue | 5 years | ≤0% = 0, ≥15% = 2 |
| 2b | FCF margin stability | 2 | Transitions (of 4) in which the FCF margin fell by more than 5 pp | 5 years | 0 = 2, 1 = 1.5, 2 = 0.75, ≥3 = 0 |
| 3 | FCF vs net income | 3 | Σ FCF / Σ net income (R11) | 5 years | ≤40% = 0, ≥70% = 3 |
| 4 | Maintenance capex not excessive | 3 | Σ maintenance capex / Σ net income (R11); maintenance capex = D&A − amortization of acquired intangibles (when reported separately; otherwise total D&A, flagged), incl. finance-lease amortization (C9) | 5 years | ≤25% = 3, ≥75% = 0 |

- **Inputs:** FIN-080 CFO, FIN-081 capex, FIN-060 revenue, FIN-020 net income, FIN-082 D&A, FIN-083 amortization of acquired intangibles.
- **Roles:** Extracts: code (XBRL). Computes: code. Judges: code.
- Sub-item 4 applies Buffett's rule of thumb to maintenance capex only: growth investment above D&A is not penalized (R10).

| Exception | Effect | Rule |
|---|---|---|
| Σ net income ≤ 0 | Sub-items 3 and 4 = **fixed value 0** | General model |
| Amortization of acquired intangibles not reported separately | Total D&A used, **flag** | General model |
| D&A components only | Depreciation + amortization + finance-lease amortization; never on top of a total tag | C9 |

### C.B3.5-BANK — replaced: earning power and value creation

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Earning power | 4 | PPNR / average total assets; PPNR = pretax income + provision for credit losses | 5-year median | ≤1.0% = 0, ≥2.0% = 4 |
| 2 | Stress coverage | 4 | Median PPNR / (3% × loans, latest year) — scenario: 10% of the loan book in trouble with a 30% loss (Wells Fargo 1990) | 5 years | ≤0.5 = 0, ≥1.0 = 4 |
| 3 | Tangible value creation | 7 | Each year (ΔTBVPS + DPS) / prior TBVPS; median of the 4 annual values; TBVPS = TCE / period-end shares | 4 transitions | ≤0% = 0, ≥12% = 7 |

- **Inputs:** FIN-003 pretax income, FIN-100 provision for credit losses, FIN-025 total assets, FIN-101 loans, TCE inputs (C.B3.4-BANK), FIN-091 period-end shares, FIN-108 DPS.
- **Roles:** Extracts: code. Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Material one-off items in PPNR | **Flag** | Bank file |
| A year with a >10% change in share count | Stays in, **flag** | D2 |
| PPNR is pretax | Stated limitation (less conservative than an after-tax test) | D1 |

### C.B3.5-INS — replaced: earning power and cost of float

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Cost of float | 6 | Cost of float = −underwriting result / average float; scored against the government yield of the same year; median of yearly values | 5 years | Cost ≤0% = 6; 50% of the yield = 3; ≥ yield = 0 (linear) |
| 2 | Cost-of-float consistency | 3 | Years of 5 with cost of float below the government yield | 5 years | 5 = 3, 4 = 2.25, 3 = 1.5, 2 = 0.75, ≤1 = 0 |
| 3 | Total operating margin | 4 | Pretax normalized operating profit / operating revenue | 5-year median | ≤0% = 0, 5% = 2, ≥10% = 4 |
| 4 | Growing cheap float | 2 | Float CAGR over valid years — only if Σ over valid years of (cost − yield) < 0 and ≥3 valid years with cost below the yield; otherwise 0 | 5 years | ≤0% = 0, ≥5% = 2 |

- **Underwriting result** = insurance revenue − claims and benefits − non-claims underwriting expenses (acquisition and other insurance expenses, FIN-112), before investment income and insurance finance expense (US GAAP: interest credited and accretion on future policy benefits are finance expenses, Q1).
- **Float** = insurance liabilities net of reinsurance assets, excluding the discount-rate remeasurement in OCI (I16).
- **Inputs:** FIN-110 insurance revenue, FIN-111 claims and benefits, FIN-112 non-claims underwriting expenses, FIN-114 interest credited / accretion, FIN-116 float components, FIN-119 government yield (annual), normalized-operating-profit inputs (C.B3.4-INS).
- **Roles:** Extracts: code (XBRL; AI for IFRS 17 tables when untagged). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Year with a missing float or underwriting component | Year **Missing** (excluded from the series); a component absent but immaterial (<5% in an adjacent year on the same basis) = 0, flagged | Q8a, Q10 |
| Change in group structure >10% of float | Year excluded from float growth and from cost of float | Q4, Q7 |
| Discontinued operation still in the float (≥10%, presented as discontinued every year) | Basis-mismatch year excluded, **flag** | Q9, Q11a |
| Fewer than 3 valid years | **Missing** | R5 |
| Float partly in other currencies | Measured against the reporting-currency yield, **flag** | Limitation |
| Years after a structural-change year (Q4) | Compared only with each other; no comparison across the change | Q10 |
| Restated comparative years | Counted inside one reporting standard (the standard of the restatement) | I18 |
| Catastrophe losses > 5% of premiums earned in a year | **Flag** (display); catastrophe years stay in the series, not excluded | Q5, I19 |

### C.B3.5-RE — replaced: owner earnings

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | OE per share growth | 8 | CAGR of OE per share t−4 → t | 5 years | ≤0% = 0, 2% = 2, 4% = 4, 6% = 6, ≥8% = 8 |
| 2 | OE per share stability | 7 | Transitions (of 4) without an OE-per-share decline >5% | 5 years | 4 = 7, 3 = 5.25, 2 = 3.5, 1 = 1.75, 0 = 0 |

- **OE** = normalized FFO attributable to common − straight-line rent adjustment (GAAP − cash; a negative adjustment increases OE, RE24) − maintenance capex − income-preserving TI/LC; FFO, deductions and share count on one basis (RE28); SBC not deducted again.
- **Inputs:** FIN-070 normalized FFO, FIN-120 straight-line rent, FIN-121 maintenance capex, FIN-122 TI/LC, FIN-092 weighted diluted shares (+ OP units, RE28).
- **Roles:** Extracts: code (FFO components, straight-line); **AI** with quote (maintenance capex, TI/LC, AFFO reconciliation lines). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Maintenance capex or TI/LC missing | **Rule change:** normalized FFO per share used, `FFO_PROXY` **flag** (growth and stability only) | FFO proxy |
| Towers | TI/LC = 0; maintenance capex = AFFO capital-improvement + corporate capex | RE20a |
| Data centers without a lessor straight-line line | Straight-line = 0, **flag** | RE20a |
| Residential and self-storage | TI/LC = 0; recurring maintenance capex still extracted | RE20 |
| FFO and deductions on different bases | Brought to one basis (company share or whole partnership) | RE28 |

---

## C.B3.6 Buffett 3.6 — Strong balance sheet, reasonable debt (10)

**What it measures:** whether debt is small relative to earnings and comfortably serviced — Buffett's avoidance of leverage risk.

### C.B3.6-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Net debt / EBITDA | 3 | Net debt = financial debt − cash − short-term investments; EBITDA = EBIT + D&A | Latest year | ≤1.0 = 3, 2.0 = 2.25, ≥4.0 = 0; net cash = 3 |
| 2 | Interest coverage | 3 | EBIT / interest expense | Latest year | ≥10 = 3, 5 = 2.25, ≤1.5 = 0 |
| 3 | Liquidity | 1.5 | Current ratio (TECH_ASSET_LIGHT: deferred revenue at cost to deliver, C11) | Latest year | ≥1.5 = 1.5, 1.0 = 0.75, ≤0.7 = 0 |
| 4 | Balance-sheet consistency | 2.5 | Years of 5 with net debt / EBITDA ≤2 and interest coverage ≥5 | 5 years | 5 = 2.5, 4 = 1.75, 3 = 1, ≤2 = 0 |

- **Inputs:** FIN-011 financial debt (excl. leases), FIN-012 cash, FIN-013 short-term investments, FIN-001 EBIT, FIN-082 D&A, FIN-050 interest expense, FIN-085 current assets, FIN-086 current liabilities, FIN-093 deferred revenue (TECH).
- **Roles:** Extracts: code. Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No debt | Sub-item 2 = **fixed value 3** | General model |
| Debt with zero interest expense | Sub-item 2 = **fixed value 3** | General model |
| EBIT ≤ 0 with debt | Sub-item 2 = **fixed value 0** | General model |
| EBITDA ≤ 0 with positive net debt | Sub-item 1 = 0; the year does not count in sub-item 4 | General model |
| Customer funds | Removed from both current assets and current liabilities | C3 |
| Alternative current ratio (with non-current marketable debt securities) | **Flag** (display only) | C12 |

### C.B3.6-BANK — replaced: capital, credit and liquidity

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Capital buffer | 4 | min over approaches of (CET1 − required CET1), pp | Latest year | ≤0 pp = 0, ≥2.5 pp = 4 |
| 2 | Typical charge-offs | 2 | NCO / average loans | 5-year median | ≤0.3% = 2, ≥1.5% = 0 |
| 3 | Nonaccrual loans | 1 | Nonaccrual / gross loans | Latest year | ≤0.5% = 1, ≥3% = 0 |
| 4 | Reserve coverage | 1 | ACL / nonaccrual | Latest year | ≤75% = 0, ≥150% = 1; no nonaccrual = 1 |
| 5 | Liquidity | 2 | LCR | Latest year | ≤100% = 0, ≥110% = 2 |

- **Inputs:** FIN-106 CET1 and required CET1 per approach (AI), FIN-103 NCO, FIN-101 loans, FIN-105 nonaccrual, FIN-104 ACL, FIN-107 LCR (AI).
- **Roles:** Extracts: code (credit items when tagged; FR Y-9C history) and **AI** (CET1, requirements, LCR). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Requirement reported per approach | Taken as reported; not derived from a formula | D10 |
| Only the stress capital buffer reported (non-G-SIB) | Requirement = 4.5% + SCB + surcharge + CCyB; checked against any stated figure | V9 |
| Bank not subject to LCR (by regulatory category) | Sub-item 5 **N/A** | D9, V11 |
| Subject to LCR, no numeric value found | Sub-item 5 **Missing** ("above 100%" is not a value) | D12 |
| LCR quarter-end instead of Q4 average | Accepted, **flag** | V10 |
| No nonaccrual loans | Sub-item 4 = **fixed value 1** | Bank file |
| Coverage thresholds | Weak metric, documented; kept after the parallel run | K1 |

### C.B3.6-INS — replaced: capital, reserves and leverage

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Regulatory capital | 4 | Reported ratio / first intervention level (Solvency: / 100% SCR without transitional measures; US RBC: % of ACL / 200%; Japan SMR / 200%) | Latest year | ≤1.0x = 0, 1.5x = 2, ≥2.0x = 4 |
| 2 | Reserve development | 4 | Adverse prior-period liability experience / relevant liabilities at the start of the year | 5-year median | ≤0% = 4, ≥4% = 0 |
| 3 | Financial leverage | 2 | Financial debt (incl. hybrid) / (financial debt + adjusted equity) | Latest year | ≤20% = 2, ≥40% = 0 |

- **Inputs:** FIN-117 regulatory capital ratio and regime (AI), FIN-118 prior-period development (code / AI), FIN-116 relevant liabilities, FIN-011 financial debt, adjusted equity (C.B3.4-INS).
- **Roles:** Extracts: **AI** (capital ratio; reserve-movement tables when untagged) and code. Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No group ratio | Lead insurance subsidiary, **flag** | Q3 |
| A stated floor ("in excess of X%") | Used as the value, **flag** | Q3 |
| Latest statutory year is t−1 | Accepted, **flag** | Q3 |
| "Exceeds requirements" without a number | Sub-item 1 **Missing** | Q3 |
| Regulatory basis CAL (ratio already stated as % of Company Action Level) | Ratio / 100 (equivalent to % of ACL / 200) | 2026-10-17 |
| Losses on new contracts; rate changes in OCI | Excluded from reserve development | Definition |
| Hybrid / subordinated debt | Fully counted as debt | I17 |

### C.B3.6-RE — replaced: balance sheet and debt

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Net debt / EBITDAre | 4 | Net debt incl. proportionate JV debt when available / EBITDAre | Latest year | ≤5x = 4, ≥9x = 0 |
| 2 | Fixed-charge coverage | 4 | EBITDAre / (interest incl. capitalized + preferred dividends) | Latest year | ≤1.5x = 0, 2x = 1, 2.5x = 2, 3x = 2.67, 4x = 3.33, ≥5x = 4 |
| 3 | Economic LTV | 2 | Net debt / economic property value (IFRS fair value or disclosed fair value) | Latest year | ≤30% = 2, ≥60% = 0 |

- **EBITDAre** = net income + interest + tax + D&A − gains (+ losses) on property sales + impairments of depreciable real estate (IFRS: − fair-value gains / + losses) ± JV adjustments.
- **Inputs:** FIN-011, FIN-012, FIN-013, FIN-123 EBITDAre components, FIN-050 interest incl. capitalized, FIN-021 preferred dividends, FIN-125 economic property value.
- **Roles:** Extracts: code; AI for disclosed fair value and JV share. Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No economic property value (US GAAP without disclosed fair value) | Sub-item 3 **Missing** (no proxy); criterion keeps 8 / 10 (valid, M2) | Comparability principle |
| Debt / gross cost | **Flag** (display only, never called LTV) | Definition |
| JV debt not available | Consolidated net debt, **flag** | Definition |
| Maturity concentration, floating-rate share | **Flag** | RE file |

---

## C.B3.7 Buffett 3.7 — Management and capital allocation (10)

**What it measures:** whether management allocates capital rationally — buys back cheaply, avoids dilution, acquires well, distributes what the cash flow supports, and reports honestly.

### C.B3.7-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds | Judges |
|---|---|---:|---|---|---|---|
| 1 | Relative buyback valuation | 2 | Average P/E in buyback years (weighted by amount) / 5-year median P/E; years with EPS ≤ 0 excluded; P/E at the annual average price | 5 years | ≤0.9 = 2, 1.0 = 1.5, ≥1.2 = 0 | Code |
| 2 | No meaningful dilution | 2 | Period-end shares t / t−4 − 1 (C7) | 5 years | ≤0% = 2, ≥+10% = 0 | Code |
| 3 | M&A created value | 2 | Σ acquisitions / Σ FCF; <10% = 2; otherwise AI question | 5 years | 2 / 1 / 0 | Code → AI (R13) |
| 4 | Distributions supported by cash flow | 2 | Σ (dividends + buybacks) / Σ FCF (R11) | 5 years | ≤100% = 2, ≥150% = 0; no distributions = 2 | Code |
| 5 | Transparent, conservative, consistent management | 2 | AI question | Latest report | 2 / 1 / 0 | AI |

| # | AI question | 2 | 1 | 0 |
|---|---|---|---|---|
| 3 | Did M&A create value? (only when acquisitions are material) | Acquisitions were integrated and generated growth, with no material goodwill impairments | Mixed picture, or too early to judge a large recent acquisition | Material goodwill impairments, overpayment, or acquisitions outside the core business |
| 5 | Is management transparent, conservative and consistent? | Clear reporting, consistent strategy, no restatements or governance disputes | Mixed signals: heavy use of "adjusted" metrics, frequent strategy changes | Restatements, governance problems, aggressive accounting |

- **Inputs:** FIN-088 buybacks, FIN-090 average share price, FIN-062 diluted EPS, FIN-091 period-end shares, FIN-089 acquisitions, FIN-032 goodwill impairment, FIN-087 dividends, FCF inputs (C.B3.5), TXT-004 MD&A / governance.
- **Roles:** Extracts: code; report text for the AI. Computes: code. Judges: code (1, 2, 4, gate of 3), **AI** (3 when material, 5).
- Sub-item 1 tests relative timing (cheap relative to itself), not a comparison with fair value.

| Exception | Effect | Rule |
|---|---|---|
| No buybacks, or no valid year | Sub-item 1 **N/A** | R9 |
| Acquisitions line absent | Goodwill acquired in the year as a lower-bound proxy, **flag** | C6 |
| Period-end share count missing (sub-item 2) | Weighted diluted shares, **flag**; BANK / INSURANCE: **Missing** | C7 |
| Σ FCF ≤ 0 with acquisitions (sub-item 3) | Ratio not computed; the AI question decides | 2026-10-17 |
| Σ FCF ≤ 0 with distributions (sub-item 4) | **Fixed value 0**, **flag** | 2026-10-17 |
| Line absent in a retrieved statement | = 0 with an `assumed_zero` **flag**; statement missing → **Missing** | C5 |

### Sector variants

| Profile | Sub-item | Change vs STD |
|---|---|---|
| BANK, INSURANCE | 3 M&A gate | Σ acquisitions / Σ **net income** <10% = 2; otherwise AI question |
| BANK, INSURANCE | 4 Distributions | Σ (dividends + buybacks) / Σ **net income**: ≤100% = 2, ≥150% = 0 |
| BANK, INSURANCE | 1, 2, 5 | Unchanged (P/E) |
| INCOME_REAL_ESTATE | 1 Buyback valuation | P / normalized FFO instead of P/E |
| INCOME_REAL_ESTATE | 3 M&A gate | **Corporate** acquisitions only (not property purchases) / Σ normalized FFO <10% = 2; otherwise AI question. The denominator is always normalized FFO, also when OE exists (2026-10-17) |
| INCOME_REAL_ESTATE | 4 Distributions | Σ dividends / Σ OE: ≤100% = 2, ≥150% = 0 (FFO proxy **flag**) |
| INCOME_REAL_ESTATE | 5 Management | AI input adds equity issuance vs value per share and use of disposal proceeds |

---

## C.B3.8 Buffett 3.8 — Quality, sustainable growth (15)

**What it measures:** whether growth is consistent, cash-backed, not debt-funded, with margins kept — and whether its drivers are durable.

### C.B3.8-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds | Judges |
|---|---|---:|---|---|---|---|
| 1 | Consistency of revenue growth | 3 | Transitions (of 4) with revenue up | 5 years | 4 = 3, 3 = 2, 2 = 1, ≤1 = 0 | Code |
| 2 | EPS growth | 3 | Smoothed growth of diluted EPS (R14) | 5 years | ≤0% = 0, ≥10% = 3 | Code |
| 3 | FCF growth | 3 | Smoothed growth of FCF (R14) | 5 years | ≤0% = 0, ≥10% = 3 | Code |
| 4 | Growth without excessive debt | 2 | Change in net debt / EBITDA, t vs t−4 | 5 years | Increase ≤0.5 = 2, ≥2.0 = 0; net cash at both points = 2 | Code |
| 5 | Margins maintained | 2 | Net margin: average of the last 2 years vs the first 2 | 5 years | Decline ≤1 pp = 2, ≥5 pp = 0 | Code |
| 6 | Growth is sustainable | 2 | AI question | Latest report | 2 / 1 / 0 | AI |

| # | AI question | 2 | 1 | 0 |
|---|---|---|---|---|
| 6 | Does the growth look sustainable? | Clear, durable growth drivers: expanding market, new products, pricing power; not reliant on one-off events | Growth partly depends on acquisitions, cyclicality or a single product | Growth from one-off events, a shrinking market, or only from acquisitions and debt |

- **Inputs:** FIN-060 revenue, FIN-062 diluted EPS, FCF inputs (C.B3.5), net debt / EBITDA inputs (C.B3.6), FIN-020 net income, TXT-001, TXT-004.
- **Roles:** Extracts: code; report text for the AI. Computes: code. Judges: code (1–5), **AI** (6).
- Sub-item 1 = consistency (rate in 3.3); 4 = trend (level in 3.6); 5 = net margin (operating margin in 3.2).

| Exception | Effect | Rule |
|---|---|---|
| R14 start average ≤ 0 and end > 0 (loss to profit) | **Fixed value** half the points (1.5 of 3), "turnaround" **flag** | R14 |
| R14 end average ≤ 0 (incl. profit to loss) | **Fixed value 0** | R14 |
| Sub-item 4: EBITDA ≤ 0 with net debt | At both points → **fixed value 0**; latest point only → **fixed value 0**; t−4 only → **fixed value 2**, **flag** | 2026-10-17 |

### Sector variants

| Profile | Sub-item | Change vs STD |
|---|---|---|
| BANK | 3 | TBVPS consistency instead of FCF growth: declines in 4 transitions 0 = 3, 1 = 2, 2 = 1, ≥3 = 0 |
| BANK | 4 | Loan growth (risk indicator) instead of debt change: CAGR over valid years = (Π(1 + growth in years without a bank acquisition))^(1/n) − 1; acquisition year = goodwill acquired >1% of equity; ≤10% = 2, ≥20% = 0; fewer than 2 valid years = **Missing** (D7) |
| BANK | 1, 2, 5, 6 | Unchanged (revenue = bank revenue); 5 = net income / bank revenue (V-05) |
| INSURANCE | 3 | Adjusted book value per share growth, smoothed (R14), instead of FCF growth: ≤0% = 0, ≥10% = 3 (V-04) |
| INSURANCE | 4 | **N/A** (leverage measured in Buffett 3.6) |
| INSURANCE | 1, 2, 5, 6 | Unchanged (revenue = operating revenue); 5 = net income / operating revenue |
| INCOME_REAL_ESTATE | 2 | Normalized FFO per share growth (R14) |
| INCOME_REAL_ESTATE | 3 | OE per share growth, smoothed (R14) |
| INCOME_REAL_ESTATE | 4 | Change in net debt / EBITDAre, t vs t−4; STANDARD thresholds (V-05) |
| INCOME_REAL_ESTATE | 5 | Normalized FFO margin (normalized FFO / total revenue), first 2 vs last 2 years; STANDARD thresholds (V-05) |
| INCOME_REAL_ESTATE | 6 | AI: organic vs acquisition-led vs revaluation-led growth |

---

## C.G3.1 Graham 3.1 — Company size and business stability (10)

**What it measures:** whether the company is large, established and not exposed to a single factor — Graham's defensive-investor requirement of size and a proven record.

### C.G3.1-STD — all profiles

| # | Sub-item | Pts | Formula | Period | Thresholds | Judges |
|---|---|---:|---|---|---|---|
| 1 | Company size | 3 | Revenue in USD at the year's average rate (R15) | Latest year | ≤$100M = 0, $300M = 1.5, ≥$750M = 3 | Code |
| 2 | Proven operating history | 3 | Years since the company's first annual report (exchange / regulator metadata: SEC, MAYA, ESEF), not years stored in our database; predecessor years count after a spin-off or merger when the filings present them | — | ≤3 = 0, 5 = 1.5, ≥10 = 3 | Code |
| 3 | No dependence on one product, customer or market | 2 | AI question with defined evidence | Latest report | 2 / 1 / 0 | AI |
| 4 | Proven business position in its industry | 2 | AI question with defined evidence | Latest report | 2 / 1 / 0 | AI |

| # | AI question | Evidence checked | 2 | 1 | 0 |
|---|---|---|---|---|---|
| 3 | Is there a critical dependence on one product, customer or market? | Largest customer share (>10% disclosure), largest product or segment, dependence on a license, patent or single market | No customer above 10% of revenue, and no product or license whose loss would threaten the business; a single reported segment does not by itself reduce the score | A customer at 10%–25%, or a central product, but with a significant additional revenue base | A customer above 25%, a single product, or dependence on one license or market |
| 4 | Does the company have a proven business position in its industry? | Years in the industry, market share or ranking where reported, scale vs competitors, long-standing material customers | One of the central players in its industry or niche, with evidence | A mid-sized player with a stable but not prominent position | Young company, development stage, or an eroding position |

- **Size anchor:** Graham (1973) required $100M sales; by CPI-U (1973: 44.4; 2025: 321.9; ratio 7.25) about $725M in 2025 → $750M. Fixed nominal number per model version (base year 2025), updated with the next version.
- **Inputs:** FIN-060 revenue, FIN-130 FX rates (annual average, year-end), FIN-131 date of the first annual report, TXT-001 Business, TXT-005 segment and customer disclosures.
- **Roles:** Extracts: code (revenue, FX, filing metadata); report text for the AI. Computes: code. Judges: code (1–2), **AI** (3–4).
- **Sector variants:** BANK — size by bank revenue; INSURANCE — size by operating revenue; INCOME_REAL_ESTATE — size by revenue. Otherwise unchanged.

| Exception | Effect | Rule |
|---|---|---|
| Date of the first annual report unknown | Sub-item 2 **Missing** (not 0) | R17 |
| AI insufficient evidence | Question **Missing** | R16 |

---

## C.G3.2 Graham 3.2 — Financial condition and liquidity (15)

**What it measures:** whether the company can meet its near-term obligations comfortably — Graham's current-ratio test of 2.0 for the defensive investor.

### C.G3.2-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Current ratio | 7 | Current assets / current liabilities | Latest year | ≤0.8 = 0, 1.0 = 2, 1.5 = 4.5, ≥2.0 = 7 |
| 2 | Quick ratio | 3 | (Cash + short-term investments + receivables) / current liabilities (inventory excluded) | Latest year | ≤0.5 = 0, ≥1.0 = 3 |
| 3 | Liquidity consistency | 5 | Years of 5 with current ratio ≥1.5 and positive working capital (R12) | 5 years | 5 = 5, 4 = 3.5, 3 = 2, ≤2 = 0 |

- **Inputs:** FIN-085 current assets, FIN-086 current liabilities, FIN-012 cash, FIN-013 short-term investments, FIN-132 receivables, FIN-093 deferred revenue (TECH).
- **Roles:** Extracts: code. Computes: code. Judges: code.
- No separate working-capital sub-item: negative working capital already means a current ratio below 1; working capital vs long-term debt is in Graham 3.3 (R7).

| Exception | Effect | Rule |
|---|---|---|
| TECH_ASSET_LIGHT deferred revenue | Counted in current liabilities at cost to deliver: × (1 − latest gross margin), 30% if no gross margin | C11 |
| Customer funds | Removed from current assets and current liabilities | C3 |
| Alternative current ratio | **Flag** (display only) | C12 |

### C.G3.2-BANK — replaced: capital, liquidity and funding

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Capital buffer | 8 | As C.3.6-BANK #1 | Latest year | ≤0 = 0, ≥3 pp = 8 |
| 2 | Liquidity | 4 | LCR | Latest year | ≤100% = 0, ≥120% = 4 |
| 3 | Deposit funding | 2 | Deposits / (deposits + short-term borrowings + long-term debt + central bank / FHLB advances + repo), each counted once (D15) | Latest year | ≤50% = 0, ≥80% = 2 |
| 4 | Deposit stability | 1 | Worst annual deposit growth over 4 transitions | 5 years | ≤−10% = 0, ≥0% = 1 |

- **Inputs:** FIN-106, FIN-107, FIN-102 deposits, FIN-133 short-term borrowings, FIN-011 long-term debt, FIN-134 central bank / FHLB advances, FIN-135 repo and securities lending.
- **Roles:** Extracts: code; **AI** (CET1, LCR). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Path 1b | Sub-items 3–4 **N/A**; criterion on 12 points (80%, valid, M2) | S3, bank file |
| Exempt from LCR | Sub-item 2 **N/A** | D9, V11 |
| Subject to LCR, not found | Sub-item 2 **Missing** | D12 |
| Repo | Included once in wholesale funding (collateralized: measures reliance on non-deposit funding, not proven instability) | D15 |

### C.G3.2-INS — replaced: capital and liquidity

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Regulatory capital | 10 | Regulatory capital multiple (as C.B3.6-INS #1) | Latest year | ≤1.0x = 0, 1.5x = 5, ≥2.0x = 10 |
| 2 | Portfolio liquidity | 5 | Liquid assets / (total investments + cash); liquid = cash + short-term investments + fixed maturities + equity securities | Latest year | ≤40% = 0, 60% = 3, ≥80% = 5 |

- **Inputs:** FIN-117, FIN-136 investment portfolio by balance-sheet category.
- **Roles:** Extracts: **AI** (capital ratio) and code (portfolio categories; AI when untagged). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Capital-ratio rules (group / subsidiary / floor / t−1 / "exceeds requirements") | As C.B3.6-INS | Q3 |
| ALM (duration matching) | **Flag** where disclosed | I6 |
| Pledged / restricted assets | **Flag** only | Q2 |

### C.G3.2-RE — replaced: financial condition and liquidity

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Fixed-charge coverage | 7 | EBITDAre / (interest incl. capitalized + preferred dividends) | Latest year | ≤1.5x = 0, 2x = 1.75, 2.5x = 3.5, 3x = 4.8, 4x = 6.1, ≥5x = 7 |
| 2 | Near-term debt coverage (24 months) | 8 | (Cash + short-term investments + committed undrawn facilities) / debt maturing within 24 months | Latest year | <0.5 = 0, 0.75 = 2, 1.0 = 4, 1.25 = 5.5, 1.5 = 7, ≥2.0 = 8 |

- **Inputs:** FIN-123, FIN-050, FIN-021, FIN-012, FIN-013, FIN-137 committed undrawn facilities (AI), FIN-138 debt maturities by year.
- **Roles:** Extracts: code (maturities where tagged); **AI** (committed facilities, maturities when untagged). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No maturities within 24 months | Sub-item 2 = **fixed value 8** | RE file |
| Facilities not committed or not available | Not counted | RE file |
| Three-year maturity concentration | **Flag** | RE file |

---

## C.G3.3 Graham 3.3 — Low debt and balance-sheet conservatism (15)

**What it measures:** whether debt is low relative to equity, working capital and earnings — Graham looks at gross debt, not net.

### C.G3.3-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Debt to equity | 5 | Financial debt (gross, excl. leases) / equity | Latest year | ≤0.3 = 5, 0.5 = 4, 1.0 = 2, ≥2.0 = 0 |
| 2 | Long-term debt to working capital | 4 | Long-term debt / working capital | Latest year | ≤0.5 = 4, 1.0 = 2.5, ≥2.0 = 0 |
| 3 | Interest coverage | 3 | EBIT / interest expense | Latest year | ≥10 = 3, 5 = 2, ≤2 = 0 |
| 4 | Consistency | 3 | Years of 5 with debt to equity ≤1.0 and interest coverage ≥5 (R12) | 5 years | 5 = 3, 4 = 2, 3 = 1, ≤2 = 0 |

- **Inputs:** FIN-011 financial debt, FIN-139 long-term debt, FIN-010 equity, FIN-085, FIN-086, FIN-001 EBIT, FIN-050 interest expense.
- **Roles:** Extracts: code. Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No debt | Sub-items 1 and 3 = **fixed value** (5, 3) | General model |
| Equity ≤ 0 with debt | Sub-item 1 = **fixed value 0** | General model |
| No long-term debt | Sub-item 2 = **fixed value 4** | General model |
| Working capital ≤ 0 with long-term debt | Sub-item 2 = **fixed value 0** | General model |
| TECH_ASSET_LIGHT working capital | Adjusted per C11 | C11 |

### C.G3.3-BANK — replaced: credit quality and conservatism

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Worst observed credit-loss year | 5 | Highest NCO rate | Up to 10 years | ≤0.5% = 5, ≥3% = 0 |
| 2 | Nonaccrual loans | 3 | Nonaccrual / gross loans | Latest year | ≤0.5% = 3, ≥3% = 0 |
| 3 | Loss absorption | 4 | ACL / nonaccrual | Latest year | ≤75% = 0, ≥200% = 4; no nonaccrual = 4 |
| 4 | Concentration | 3 | HHI over 5 loan categories (residential mortgage; CRE and construction; C&I; consumer; other), on 100% of loans when ≥80% are mapped by the bank's own classification; CRE > 300% of total regulatory capital → 0 | Latest year | HHI ≤0.25 = 3, ≥0.50 = 0 |

| AI question (only without a loan breakdown) | 2 | 1 | 0 |
|---|---|---|---|
| Is the loan book diversified? | Spread across loan types, industries and regions; no dominant exposure | A prominent but not dominant exposure to one type, industry or region | A dominant exposure (CRE, one industry, region or borrower) |

- **Anchor (K1):** worst year 3% = industry peak charge-off rate in 2010 (FRED CORALACBS, 3.02%); 0.5% = a normal-period level.
- **Inputs:** FIN-103, FIN-101, FIN-105, FIN-104, FIN-140 loan breakdown (AI), FIN-141 total regulatory capital (AI).
- **Roles:** Extracts: code (credit items; FR Y-9C history) and **AI** (loan breakdown, regulatory capital). Computes: code. Judges: code; **AI** only for sub-item 4 without a breakdown (2 = 3 pts, 1 = 1.5, 0 = 0).

| Exception | Effect | Rule |
|---|---|---|
| 6–9 years of NCO history | Sub-item 1 capped at 3 | Bank file |
| Fewer than 6 years | Sub-item 1 **Missing** | Bank file |
| Window without a credit crisis | **Flag** "window contains no credit crisis" | K1 |
| No loan breakdown | **Rule change:** AI question (D4); no evidence → **Missing** | D3, D4, R16 |
| No nonaccrual loans | Sub-item 3 = **fixed value 4** | Bank file |
| CRE classification | Only as classified by the bank or secured by CRE; no guessing | Bank file |
| Total regulatory capital missing | CRE > 300% test skipped, **flag**; the HHI is still scored | 2026-10-17 |

### C.G3.3-INS — replaced: reserves and leverage

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Reserve development | 9 | Reserve deviation (as C.B3.6-INS #2), 5-year median; consistency penalty for years with deviation >1%: 2 years −0.5, 3 years −1, ≥4 years −2; floor 0 | 5 years | 0% = 9, 1% = 6.75, 2% = 4.5, 3% = 2.25, ≥4% = 0 |
| 2 | Financial leverage | 6 | As C.B3.6-INS #3 | Latest year | ≤20% = 6, 30% = 4.5, 40% = 3, 50% = 1.5, ≥60% = 0 |

- **Roles:** Extracts: code / **AI** (reserve tables). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No relevant liability is material | Sub-item 1 **N/A**; criterion on 6 points only if valid under M2, otherwise **Missing** | Insurance file |

### C.G3.3-RE — replaced: debt and balance-sheet conservatism

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Net debt / EBITDAre | 7 | As C.3.6-RE #1 | Latest year | ≤3x = 7, 4x = 6.3, 5x = 5.6, 6x = 4.9, 8x = 3.5, 10x = 2.1, 12x = 1.05, ≥15x = 0 |
| 2 | Financial flexibility | 4 | NOI from unencumbered properties / total NOI (fallback: unencumbered assets / total property, flagged) | Latest year | ≤20% = 0, ≥60% = 4 (check) |
| 3 | Stressed economic LTV | 4 | Stabilized portfolio with economic value: stressed value = value × cap / (cap + 1 pp); stressed LTV = total net debt / (stressed stabilized value + carrying value of development, land and other property) | Latest year | ≤35% = 4, 45% = 2, ≥60% = 0 |

- **Inputs:** FIN-123, FIN-011, FIN-012, FIN-013, FIN-142 unencumbered NOI / assets (AI), FIN-125, FIN-143 stabilized vs development split (AI).
- **Roles:** Extracts: code; **AI** (unencumbered NOI, fair-value split). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| No economic value | Sub-item 3 **Missing**; criterion on 11 points (73%, valid, M2) | Comparability principle |
| Carrying value of other property missing | Sub-item 3 **Missing** | RE26 |
| Unencumbered NOI not disclosed | Unencumbered assets used, **flag** | RE file |
| Threshold must not penalize conservative property-level secured financing | Marked "check" | K1 |

---

## C.G3.4 Graham 3.4 — Earnings stability (15)

**What it measures:** whether earnings held up over a full business cycle — Graham's ten-year record.

### C.G3.4-STD — STANDARD, TECH_ASSET_LIGHT, BANK, INSURANCE

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Profitable years | 9 | Share of years with net income > 0 | 10 years | 100% = 9, 90% = 7, 80% = 5, 70% = 3, ≤60% = 0 |
| 2 | Frequency of declines | 4 | Transitions in which diluted EPS fell by more than 20% | 10 years | 0 = 4, 1 of 9 = 3, 2 of 9 = 1.5, ≥3 of 9 = 0 (as shares with partial history) |
| 3 | Depth of the largest decline | 2 | Max drawdown from the running peak: (peak − EPS_t) / peak, only when the peak is positive; EPS_t ≤ 0 = 100% | 10 years | ≤10% = 2, ≥50% = 0 |

- **Period:** 10 years — an exception to R5 because the scorecards define it; minimum 5 years.
- **Inputs:** FIN-020 net income, FIN-062 diluted EPS (split-adjusted).
- **Roles:** Extracts: code. Computes: code. Judges: code.
- 20% (not 10% as in Buffett 3.3): Graham tests resilience over a full cycle (R7). Decline from peak instead of "weakest year vs average", which would penalize growth (R10).

| Exception | Effect | Rule |
|---|---|---|
| 5–9 years available | Metrics as shares of the available years, **flag** "partial history" | General model |
| Fewer than 5 years | **Missing** | General model |
| One-off charges | Counted as reported | General model |

### C.G3.4-RE

By normalized FFO per share instead of EPS and net income (confirmed against the code, V-06): 1 = share of years (last ≤ 10, minimum 5) with normalized FFO > 0; 2 = share of transitions with normalized FFO per share down >20%; 3 = largest drawdown from the running peak of normalized FFO per share (peak must be positive; a value ≤ 0 = 100%). STANDARD thresholds.

---

## C.G3.5 Graham 3.5 — Dividend history (10)

**What it measures:** an uninterrupted, well-covered dividend — Graham's record of continuous payments.

### C.G3.5-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Continuity | 4 | Most recent consecutive years with a dividend (up to 10) | 10 years | ≤2 = 0, 5 = 1.5, ≥10 = 4 |
| 2 | No cuts | 2 | Years (of 10) in which dividend per share fell by more than 10% | 10 years | 0 = 2, 1 = 1, ≥2 = 0 |
| 3 | Earnings coverage | 2 | Σ dividends / Σ net income (R11) | 5 years | ≤60% = 2, 80% = 1, ≥100% = 0 |
| 4 | Cash-flow coverage | 2 | Σ dividends / Σ FCF (R11) | 5 years | ≤60% = 2, 80% = 1, ≥100% = 0 |

- **Inputs:** FIN-108 DPS, FIN-087 dividends paid, FIN-020 net income, FCF inputs (C.B3.5).
- **Roles:** Extracts: code. Computes: code. Judges: code.
- A cut is measured on dividend per share, so buybacks are not mistaken for a cut. A suspension is captured by sub-items 1 and 2 (no AI question).

| Exception | Effect | Rule |
|---|---|---|
| No dividend in the latest year | Whole criterion = **fixed value 0**, **flag** "does not meet Graham's dividend requirement" (not N/A: the absence of a dividend is data) | General model |
| DPS not reported | Dividends paid / weighted basic shares, **flag** | C8 |

### Sector variants

| Profile | Sub-item | Change vs STD |
|---|---|---|
| BANK, INSURANCE | 4 | **N/A** (cash flow not representative); scored on 8 points, scaled to 10 (M1) |
| BANK, INSURANCE | 1–3 | Unchanged |
| INCOME_REAL_ESTATE | 1, 2 | Unchanged |
| INCOME_REAL_ESTATE | 3 | Coverage by normalized FFO: Σ dividends / Σ normalized FFO; STANDARD thresholds (≤60% = 2, 80% = 1, ≥100% = 0) — checked on the sample, no REIT scores 0 (V-07) |
| INCOME_REAL_ESTATE | 4 | Σ dividends / Σ OE: ≤80% = 2, 100% = 1, ≥120% = 0 (REITs must distribute most taxable income); **Missing** when OE is a proxy |

---

## C.G3.6 Graham 3.6 — Moderate earnings growth (15)

**What it measures:** steady, non-speculative growth over ten years — Graham's test of EPS up by at least a third, using three-year averages.

### C.G3.6-STD — STANDARD, TECH_ASSET_LIGHT, BANK, INSURANCE

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Long-term growth (Graham's test) | 9 | Annualized rate between the average EPS of the first 3 and the last 3 years (over n − 3 years; with 10 years: 7) | 10 years | ≤0% = 0, 4% = 5, ≥10% = 9 |
| 2 | Consistency of growth | 3 | Share of transitions in which diluted EPS rose | 10 years | ≥80% = 3, 60% = 1.5, ≤40% = 0 |
| 3 | Growth continues | 3 | Smoothed EPS growth (R14) | Last 5 years | ≤0% = 0, ≥5% = 3 |

- **Anchor:** a one-third rise over 7 years ≈ 4% a year → 5 of 9 (Graham's pass); 10% ≈ doubling in 7 years → full.
- **Inputs:** FIN-062 diluted EPS (split-adjusted).
- **Roles:** Extracts: code. Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Starting 3-year average ≤ 0 | Sub-item 1 = **fixed value 0** (a failed Graham test, not N/A — unlike Buffett 3.8) | General model |
| Sub-item 3: R14 start average ≤ 0 and end > 0 (loss to profit) | **Fixed value 0** (no turnaround credit in Graham) | 2026-10-17 |
| 6–9 years | Growth annualized, same thresholds | General model |
| Fewer than 6 years | **Missing** | General model |
| High growth | No penalty (R10) | R10 |

### C.G3.6-RE

By normalized FFO per share instead of diluted EPS (V-06, confirmed).

---

## C.G3.7 Graham 3.7 — Quality of equity and assets (10)

**What it measures:** a positive, tangible and stable equity base — the book value the Graham Number relies on.

### C.G3.7-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Tangible equity | 4 | (Equity − goodwill − intangibles) / equity | Latest year | ≥80% = 4, 50% = 2, ≤0% = 0 |
| 2 | Equity stability | 3 | Years of 5 with positive equity (R12) | 5 years | 5 = 3, 4 = 1.5, ≤3 = 0 |
| 3 | Trend of tangible equity per share | 3 | Tangible BVPS t vs t−4 | 5 years | ≥0% = 3, ≤−20% = 0 |

- **Inputs:** FIN-010, FIN-023, FIN-024, FIN-092 diluted shares.
- **Roles:** Extracts: code. Computes: code. Judges: code. Per share, so buybacks are not penalized.

| Exception | Effect | Rule |
|---|---|---|
| Equity ≤ 0 (latest) | Sub-item 1 = **fixed value 0** | General model |
| Tangible BVPS negative at the start and positive at the end | Sub-item 3 = **fixed value 3** | General model |
| Tangible BVPS negative in the latest year | Sub-item 3 = **fixed value 0** | General model |

### C.G3.7-BANK — replaced

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Tangible equity to assets | 5 | TCE / (total assets − goodwill − intangibles) | Latest year | ≤4% = 0, ≥7% = 5 |
| 2 | TBVPS preservation | 3 | CAGR = (TBVPS_t / TBVPS_t−4)^(1/4) − 1 | 5 years | ≤−5% = 0, 0% = 1.5, ≥5% = 3 |
| 3 | Risk intensity | 2 | RWA / total assets | Latest year | ≤50% = 2, ≥100% = 0 |

- **Inputs:** TCE inputs, FIN-025, FIN-091, FIN-144 RWA (AI).
- **Roles:** Extracts: code; **AI** (RWA). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| TBVPS negative at the start and positive at the end | Sub-item 2 = **fixed value 1.5** | D5 |
| TBVPS negative at the end | Sub-item 2 = **fixed value 0** | D5 |

### C.G3.7-INS — replaced

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Adjusted TBVPS preservation | 4 | CAGR of adjusted tangible book value per share (adjusted equity − goodwill − intangibles) | 5 years | ≤−5% = 0, 0% = 2, ≥5% = 4 |
| 2 | Fixed-income credit quality | 3 | Investment-grade fixed income / total fixed income (BBB− / Baa3 or better, NAIC 1–2; unrated = not investment grade) | Latest year | ≤75% = 0, ≥95% = 3 |
| 3 | Complex / volatile assets | 3 | (Equities + real estate + other invested assets + below-investment-grade fixed income) / (total investments + cash) | Latest year | ≤5% = 3, ≥25% = 0 |

- **Inputs:** adjusted equity (C.B3.4-INS), FIN-023, FIN-024, FIN-091, FIN-136.
- **Roles:** Extracts: code / **AI** (credit-quality table). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Negative start, positive end / negative end | Sub-item 1 = **fixed value** 2 / 0 | As D5 |
| Credit-quality table missing | Sub-item 2 **Missing**; sub-item 3 also **Missing** (no partial numerator) | Q8b |
| HHI concentration | Removed (a government-bond portfolio is conservative) | I8 |

### C.G3.7-RE — replaced

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Utilization (table A) | 4 | Occupancy / mapped metric by asset type | 5-year median | ≥95% = 4, 92% = 3, 89% = 2, 85% = 1, ≤80% = 0 |
| 2 | Property income resilience | 4 | Transitions (of 4) without a same-property NOI decline >3% (towers: organic revenue) | 5 years | 4 = 4, 3 = 3, 2 = 2, 1 = 1, 0 = 0 |
| 3 | Tenant concentration | 2 | Largest independent tenant share of rent / NOI | Latest year | ≤5% = 2, 10% = 1.5, 15% = 1, 20% = 0.5, ≥25% = 0 |

| Asset type (table A) | Utilization metric |
|---|---|
| Office, retail, industrial / logistics, residential, healthcare (leased), self-storage, net lease | Occupancy (leased occupancy where both are reported) |
| Data centers | Leased / available capacity (MW or sq ft) |
| Communication towers | Not applicable |
| Diversified | NOI-weighted occupancy |

- **Inputs:** FIN-145 occupancy / utilization (AI), FIN-044 same-property NOI growth (AI), FIN-146 largest tenant share (AI).
- **Roles:** Extracts: **AI** (all three, with quotes). Computes: code. Judges: code.

| Exception | Effect | Rule |
|---|---|---|
| Latest year below the 5-year median by >3 pp | Sub-item 1 capped at 2 | RE file |
| Towers | Sub-item 1 **N/A**, normalized under M1 (not 0, not missing) | Table A |
| Data centers without capacity data | Sub-item 1 **Missing** | Table A |
| Residential and self-storage | Sub-item 3 (tenant concentration) **N/A**, normalized under M1 | RE20 |
| Material cumulative write-downs; country concentration | **Flag** | RE file |

---

## C.G3.8 Graham 3.8 — Earnings quality and dilution (10)

**What it measures:** whether reported earnings are real — backed by cash, not inflated, not dependent on one-offs, not diluted.

### C.G3.8-STD — STANDARD and TECH_ASSET_LIGHT

| # | Sub-item | Pts | Formula | Period | Thresholds | Judges |
|---|---|---:|---|---|---|---|
| 1 | FCF supports net income | 3 | Σ FCF / Σ net income (R11) | 5 years | ≤50% = 0, ≥90% = 3 | Code |
| 2 | No dilution | 2 | Period-end shares t / t−4 − 1 (C7) | 5 years | ≤0% = 2, ≥+10% = 0 | Code |
| 3 | No dependence on one-time items | 2 | AI question | 5 years | 2 / 1 / 0 | AI |
| 4 | EPS not inflated | 2 | Smoothed EPS growth − smoothed operating income growth (R14) | 5 years | Gap ≤3 pp = 2, ≥10 pp = 0 | Code |
| 5 | Net income vs cash-flow gap | 1 | Average of yearly (net income − CFO) / average total assets | 5 years | ≤0% = 1, ≥10% = 0 | Code |

| # | AI question | Evidence | 2 | 1 | 0 |
|---|---|---|---|---|---|
| 3 | Do reported earnings depend on one-time items? | Impairments, restructuring, asset-sale gains, legal settlements, one-off tax items, last 5 years | Immaterial (below ~10% of net income every year) | One material item, or recurring "one-time" items | Material items in most years, or earnings rely on them |

- **Inputs:** FCF inputs, FIN-020, FIN-091, FIN-062, FIN-001, FIN-080, FIN-025, TXT-004.
- **Roles:** Extracts: code; report text for the AI. Computes: code. Judges: code (1, 2, 4, 5), **AI** (3).

| Exception | Effect | Rule |
|---|---|---|
| Σ net income ≤ 0 | Sub-item 1 = **fixed value 0** | General model |
| Starting operating income ≤ 0 | Sub-item 4 = **fixed value 0** | General model |
| Period-end share count missing (sub-item 2) | Weighted diluted shares, **flag** | C7 |
| Sub-item 4: EPS start average ≤ 0 and end > 0 | **Fixed value 0** | 2026-10-17 |
| Sub-item 4: EPS end average ≤ 0 | EPS growth taken as −100% in the gap | 2026-10-17 |

### C.G3.8-BANK — replaced

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | EPS stability | 5 | Transitions (of 4) with a diluted-EPS decline >10% | 5 years | 0 = 5, 1 = 3.5, 2 = 2, ≥3 = 0; a loss year = 0 |
| 2 | Allowance erosion relative to earnings | 3 | Worst year of max(0, NCO − provision) / pretax income | 5 years | ≤5% = 3, ≥20% = 0 |
| 3 | Dilution | 2 | Period-end shares t / t−4 − 1 (C7) | 5 years | ≤0% = 2, ≥+10% = 0 |

| Exception | Effect | Rule |
|---|---|---|
| Year with pretax income ≤ 0 | Counts as ≥20% if NCO > provision, otherwise 0% | D6 |
| Negative provision | **Flag** | Bank file |

### C.G3.8-INS — replaced

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | Reliance on non-recurring investment gains | 5 | Σ max(0, after-tax non-recurring gains) / Σ net income | 5 years | ≤10% = 5, ≥40% = 0 |
| 2 | Operating margin stability | 3 | Transitions (of 4) in which the total operating margin did not fall by more than 2 pp | 5 years | 4 = 3, 3 = 2.25, 2 = 1.5, 1 = 0.75, 0 = 0 |
| 3 | Dilution | 2 | Period-end shares t / t−4 − 1 (C7) | 5 years | ≤0% = 2, ≥+10% = 0 |

| Exception | Effect | Rule |
|---|---|---|
| Σ net income ≤ 0 | Sub-item 1 = **fixed value 0** (not a ratio of 0) | Q8c |

### C.G3.8-RE — replaced

| # | Sub-item | Pts | Formula | Period | Thresholds |
|---|---|---:|---|---|---|
| 1 | OE stability | 5 | Transitions (of 4) without an OE-per-share decline >5% | 5 years | 4 = 5, 3 = 3.75, 2 = 2.5, 1 = 1.25, 0 = 0 |
| 2 | Reported vs economic earnings | 3 | Median annual growth gap: normalized FFO per share − OE per share (penalized only when FFO grows faster); diagnostic OE / FFO | 5 years | ≤1 pp = 3, 2 pp = 2.5, 3 pp = 2, 4 pp = 1, ≥5 pp = 0 |
| 3 | Per-share capital discipline | 2 | Share CAGR ≤1% → 2; otherwise by OE-per-share CAGR | 5 years | ≥4% = 2, 2–4% = 1.5, 0–2% = 1, −2–0% = 0.5, ≤−2% = 0 |

| Exception | Effect | Rule |
|---|---|---|
| OE on the FFO proxy | Sub-item 1 allowed, **flag**; sub-item 2 **Missing** | FFO proxy, RE27 |
| Sub-item 2: OE not positive in all years | **Missing** | RE27 |
| Transition with a base ≤ 0 in either series | Excluded; fewer than 2 valid → **Missing** | Review 2026-10-15 |


---

## Part D — Pricing cards

### D.0 Shared pricing rules (all profiles)

- **Price input:** latest close, refreshed at least daily; a stale price (no update) is flagged and no price score is computed until reviewed (E1). Price and financials of the same listed entity (C16, E2).
- **Discount** = (value − price) / value. **Price score** by the Buffett scale (≥40% = 10) or the Graham scale (classic ≥50% = 10; Tech ≥40% = 10), proportional between anchors (R4) — tables in D.1 and D.2.
- **Buy price** = value × (1 − required margin by the model's quality score); quality below 55 → "not suitable for purchase". **X1:** the Graham price score is always shown, labelled (one rule for all profiles).
- **Value ≤ 0** → "cannot be valued", price score 0, no buy price; a negative value is never shown (C15).
- **No imputation** in a value: any missing input → "cannot be valued" (M6); buy price only with a value and quality coverage ≥80% (M7).
- **Required return** 10%, **terminal growth** 2.5% in every Buffett model. Sensitivities and implied returns are display only.
- **Roles:** Extracts: code (prices, financial inputs; AI-extracted inputs as in the quality cards). Computes: code. Judges: code.

### D.1 STANDARD and TECH_ASSET_LIGHT — Buffett value


#### A. Fair value (DCF)

| Component | Definition |
|---|---|
| Owner earnings per year | Cash flow from operations − stock-based compensation (SBC) − maintenance capex. **Maintenance capex = D&A minus amortization of acquired intangibles** (when reported separately; otherwise total D&A, flagged), including finance-lease amortization (C9). **SBC has three ETL states:** found = the amount; reported none = 0; not found = missing data → "cannot be valued" (R17, M6) |
| Unlevered owner earnings (G3-C) | Owner earnings + interest expense × (1 − tax rate); tax rate = effective rate clipped to 0%–40%, otherwise 25% (as NOPAT). Owner earnings are CFO-based and therefore already after interest; adding back after-tax interest gives the cash flow of the whole business before financing, so debt is subtracted once in the value bridge. The base and stage-1 growth use this unlevered series (the gate tests revenue and EPS only) Interest expense missing in a year of the last 5 → counted as 0, flagged (2026-10-17) |
| Growth eligibility gate | Stage-1 growth is allowed only if (a) revenue rose in ≥3 of the last 4 year-over-year transitions, (b) diluted EPS fell by more than 10% in at most 1 of the last 4 transitions, and (c) diluted EPS was positive in all of the last 5 years. Otherwise stage-1 growth = 0% (flag "growth_gate_failed") |
| Stage-1 growth (years 1–5) | Median owner earnings of the last 5 years vs. median of the previous 5 years, annualized over 5 years, clipped to 0%–12%. With fewer than 10 years: R14 smoothed growth (flagged). 0% if the gate fails Previous-5 median ≤ 0 → 0%, flagged (2026-10-17) |
| Base | **Median owner earnings of the last 5 years, rolled forward × (1 + stage-1 growth)² only when the latest year's owner earnings ≥ the 5-year median** (the median sits at t−2; roll-forward assumes growth since then). When the latest year is below the median, base = the 5-year median without roll-forward (G1) |
| Stage 2 (years 6–10) | Growth declines linearly to terminal growth |
| Terminal growth | 2.5% |
| Discount rate | 10%, uniform for all companies and markets. Applied to unlevered flows (G3-C) it acts as a conservative cost of capital (a WACC is normally below the cost of equity), consistent with Buffett's required return. Re-examined only if a broad sample shows almost no company with a price score above 0 (next alternative: 10-year government bond + premium) |
| Terminal value | Gordon: year-10 cash flow × (1 + 2.5%) / (10% − 2.5%) |
| Excess cash less debt | Cash + short-term investments (C3) − financial debt (definition from 3.6) |
| Fair value per share | (PV of unlevered cash flows + discounted terminal value + excess cash − financial debt) / diluted shares (latest year); debt is subtracted once (G3-C). Value ≤ 0 → C15 |
| Cannot be valued | Owner-earnings base ≤ 0 → "cannot be valued", price score "not applicable" |
| Display only (no score) | **Implied growth:** the stage-1 growth at which fair value equals the current price. **Implied long-term annual return at current price (model value assumptions):** the discount rate at which fair value equals the current price, using the gated stage-1 growth. Both solved on the same unlevered basis (enterprise value − debt + excess cash = price) |

**Rationale:**

- **Median base:** a single abnormal year (e.g., a one-off tax deposit) does not move a 5-year median; rolling it forward two years keeps the base current for growing companies.
- **Growth gate:** Buffett values only predictable businesses with a DCF. Cyclical or declining companies get no stage-1 growth, so a cyclical peak is not mistaken for growth (tested on Nucor and Kraft Heinz).
- **Cash-flow-based owner earnings:** operating cash flow includes working-capital changes and removes non-cash accounting entries.
- **SBC deducted:** operating cash flow adds stock compensation back, and Buffett treats it as a real expense.
- **Maintenance capex = D&A excluding acquisition amortization:** amortization of acquired intangibles records the purchase price, not spending to maintain the business, and deducting it would penalize acquirers twice. Depreciation approximates asset wear. Capex above D&A is growth investment, which is already valued in the forecast. When capex is below D&A, D&A is still deducted, so underinvestment in assets is not rewarded.
- **Uniform 10%:** the minimum return Buffett requires. Allows comparison across companies and markets.
- **12% cap:** few companies sustain high growth for long, and high growth assumptions inflate a DCF sharply.

#### B. Price score (0–10)

Discount = (fair value − current price) / fair value. Proportional score between anchors (R4):

| Discount | ≤−25% | −20% | 0% | 10% | 20% | 30% | ≥40% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Score | 0 | 0.5 | 2.5 | 4.5 | 6.5 | 8.5 | 10 |

#### C. Required margin of safety and buy price

| Buffett quality score | 100 | 85 | 70 | 55 | Below 55 |
|---|---:|---:|---:|---:|---|
| Required margin of safety | 15% | 20% | 30% | 40% | Do not buy |

Proportional between anchors. Buy price = fair value × (1 − margin). Below 55: "not suitable for purchase" is shown instead of a price.

### D.2 STANDARD and TECH_ASSET_LIGHT — Graham value


#### A. Method selection

| methodology_profile | Primary method | Note |
|---|---|---|
| STANDARD | Classic Graham Number | |
| TECH_ASSET_LIGHT | Graham Tech (adjusted FCF) | Graham Number displayed as a conservatism check, not scored |
| BANK / INSURANCE / INCOME_REAL_ESTATE | Part D.3–D.5 | |

The method is decided only by the profile (R8), not by case-by-case judgment.

#### B. Graham Number (classic)

| Component | Definition |
|---|---|
| Normalized EPS | **Average diluted EPS of the last 10 years** (Graham, *Security Analysis*: average earnings over 7–10 years); 7–9 years: average of available years, flagged; fewer than 7: cannot be valued. Loss years are included in the average (G2; consistent with BANK and INSURANCE) |
| BVPS | Equity / diluted shares, latest year |
| Value | √(22.5 × normalized EPS × BVPS) |
| Cannot be valued | Normalized EPS ≤ 0 or BVPS ≤ 0 |
| Display only | Conservatism check Min(Graham Number, EPS × 15, BVPS × 1.5). **Decided:** it does not affect value or score, per the scorecards (the earlier GPT prompt that used Min as the primary value does not govern). Net-Net test: price < ⅔ × NCAV per share (NCAV = current assets − total liabilities) |

#### C. Graham Tech (adjusted FCF)

| Component | Definition |
|---|---|
| Adjusted FCF per year | Cash flow from operations − capex − SBC (full SBC deduction, as in Buffett's owner earnings). SBC uses the three Buffett states: found / reported none = 0 / not found = "cannot be valued" |
| Base | Average adjusted FCF of the last 3 years |
| Multiple by growth | Smoothed growth of adjusted FCF over 5 years (R14): ≤0% = 12, 5% = 15, 10% = 18, 15% = 22, ≥20% = 25; growth not measurable (R14 not computable) → 12, flagged (2026-10-17) |
| Multiple cap by Graham quality | Continuous (R4): quality ≤70 → 15, 85 → 18, ≥95 → 22, linear in between. (The top cap of 22 keeps Graham at least as conservative as Buffett's DCF) |
| Final multiple | The lower of the growth multiple and the quality cap |
| Value per share | (Base × multiple + cash and short-term investments (C3) − financial debt) / diluted shares |
| Cannot be valued | Base ≤ 0, or dilution ≥10% over 5 years (Graham 3.8 sub-item 2 = 0) |

- **The multiple:** how many years of free cash flow are paid for the company. A multiple of 15 means a cash yield of about 6.7% (1/15); 25 means 4%. A high multiple is justified only by growth.
- The scorecards' multiple table (12–15, 15–18, 18–22, 22–25) is translated into two numeric measures, growth (from the table) and quality (cap), so the multiple is set by code without judgment.
- The scorecards' option to use "actual dilution cost" instead of full SBC is not included: full SBC is simple and consistent with Buffett.

#### D. Price score (0–10)

Discount = (value − price) / value. Proportional score between anchors (R4), derived from the scorecards' band tables:

| Discount | ≤−25% | −20% | 0% | 15% | 25% | 40% | ≥50% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Classic | 0 | 0.5 | 2.5 | 4.5 | 6.5 | 8.5 | 10 |

| Discount | ≤−25% | −20% | 0% | 10% | 20% | 30% | ≥40% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tech | 0 | 0.5 | 2.5 | 4.5 | 6.5 | 8.5 | 10 |

#### E. Required margin of safety and buy price

| Graham quality score | 100 | 85 | 70 | 55 | Below 55 |
|---|---:|---:|---:|---:|---|
| Classic | 25% | 30% | 35% | 50% | Do not buy |
| Tech | 20% | 25% | 30% | 40% | Do not buy |

Proportional between anchors. Buy price = value × (1 − margin).

- Display flag: positive EPS but weak FCF (Graham 3.8 sub-item 1 = 0) → "earnings not backed by cash flow, caution".

### D.3 BANK


Quality score and fair value are separate measures. The stress test is part of the quality score; fair value rests on normalized profitability and the cost of equity and does not fully price risk. Stress coverage and the sensitivity range are displayed next to the value.

#### 6.1 Buffett — two-stage excess-returns model (on total tangible equity)

| # | Component | Definition |
|---|---|---|
| V1 | Base | TCE₀ = tangible common equity at the latest year-end (total, not per share). Value per share = total value / period-end shares |
| V1 | ROTCE | ROTCE_norm = 5-year median, capped at 20%, constant over the forecast (base case) |
| V1 | Payout | (Dividends + buybacks) / net income, 5-year sums (R11), clipped to 0%–100%. Buybacks are treated as distributions like dividends; share issuance is not modeled Σ net income ≤ 0 → payout 100% (2026-10-17) |
| V1 | TCE growth | Stage 1 (years 1–5): g₁ = ROTCE_norm × (1 − payout), clipped to 0%–12%; if the growth eligibility gate fails: 2.5%. Stage 2 (years 6–10): linear fade to 2.5% |
| V1 | Equity roll-forward | TCE_t = TCE_t−1 × (1 + g_t); residual income RI_t = (ROTCE_norm − 10%) × TCE_t−1 |
| V2 | Terminal value | RI₁₁ = (ROTCE_norm − 10%) × TCE₁₀; TV₁₀ = RI₁₁ / (10% − 2.5%) |
| V2 | Value | TCE₀ + Σ(t=1..10) RI_t / 1.1^t + TV₁₀ / 1.1^10 |
| — | Cannot be valued | TCE₀ ≤ 0, ROTCE_norm not available, or ROTCE_norm ≤ 2.5% (V6). A negative value is never displayed Price score 0, no buy price (C15; 2026-10-17) |
| V3 | Sensitivity (display only) | (a) ROTCE erosion: only when ROTCE_norm > 10%, ROTCE fades linearly to 10% over years 1–10, terminal RI = 0, growth path as in the base case; when ROTCE_norm ≤ 10%, erosion = base case (V7); (b) ROTCE ± 1 pp, growth recomputed under the same rules. A value range is shown; the price score uses the base case |
| — | Sanity check (display only) | Single-stage justified P/TBV = (ROTCE_norm − 2.5%) / (10% − 2.5%) |
| — | Display only | Implied return at current price; implied ROTCE at current price. Solved numerically (V8): implied return searched from just above 2.5% (the terminal growth rate) to +40%; implied ROTCE from −20% to +40%; tolerance $0.01 per share. Implied return below the lower bound = "below 2.5%"; no root otherwise = "no solution" |

#### 6.2 Graham — Graham Number on tangible book with 10-year EPS

| # | Component | Definition |
|---|---|---|
| V4 | Normalized EPS | Average diluted EPS over 10 years (split-adjusted). 7–9 years: average of available years, flagged; fewer than 7: cannot be valued |
| V4 | Loss years | Included in the average (part of the cycle). Average ≤ 0 → cannot be valued. Loss-year classification: V5 |
| V4 | Tangible book | Latest TBVPS ≤ 0 → cannot be valued |
| V4 | Value | √(22.5 × normalized EPS × TBVPS) |

#### 6.3 Price score and buy price

| | Buffett | Graham |
|---|---|---|
| Price score | Buffett scale (≥40% discount = 10) | Classic Graham scale (≥50% discount = 10) |
| Margin of safety / buy price | Buffett table by Buffett quality | Classic Graham table by Graham quality |
| Quality gate | — | Graham price score shown with a label; buy price "not suitable" below Graham quality 55 (X1, 2026-10-15; replaces the earlier rule that hid the score) |

Rationale for the 20% ROTCE cap: a bank earning above 20% on tangible equity for long almost always relies on leverage or risk; without a cap the model would reward what Buffett warned against.

**Decisions in force (V5–V8):**

| # | Topic | Rule |
|---|---|---|
| V5 | Graham — loss years (ValueCompass rule inspired by Graham's 10-year earnings record) | Window = the same 10 years as the EPS average. **Adjusted PPNR** = PPNR + goodwill impairment + net realized loss on securities (only when a loss), both from standard XBRL tags. Securities-loss tag hierarchy: realized gain/loss on AFS / debt securities first; fallback `DebtAndEquitySecuritiesGainLoss` only when no realized tag is filed for that year, flagged "proxy tag" (may include fair-value changes on equity securities). Only the loss part is added back. Each loss year (diluted EPS < 0) is classified: **operating** = provision for credit losses > adjusted PPNR → cannot be valued; otherwise **one-off** → valued and flagged. Cause, derived deterministically: goodwill impairment / securities losses (whichever adjustment closes the gap); "tax" when pretax income > 0; otherwise "unidentified". Graham price score display per X1 (2026-10-15). Limitation: the 2016–2025 window excludes 2008–2009 |
| V6 | Buffett — negative value | ROTCE_norm ≤ 2.5% → cannot be valued. Means "no valid value under the current model", not an economic value of zero |
| V7 | Buffett — sensitivity paths | Erosion never becomes improvement: applied only when ROTCE_norm > 10%; otherwise erosion = base case. ±1 pp scenarios recompute growth under the same rules; the erosion scenario keeps the base growth path |
| V8 | Implied return / implied ROTCE | Numerical solution, tolerance $0.01 per share. Implied return: lower bound just above 2.5% (below it the terminal value is undefined), shown as "below 2.5%"; implied ROTCE: −20% to +40%; otherwise "no solution" |

### D.4 INSURANCE

Quality score and fair value are separate measures (as BANK).

| # | Component | Definition |
|---|---|---|
| P1 | Buffett — two-stage excess returns | Base E₀ = adjusted equity at the latest year-end (total; rate-driven AOCI removed). ROE_norm = operating ROE, 5-year median, capped at 20%. Payout = (dividends + buybacks) / net income, 5-year sums, clipped 0%–100%. Stage 1 (years 1–5): g₁ = ROE_norm × (1 − payout), clipped 0%–12%; growth eligibility gate fails → 2.5%. Stage 2 (years 6–10): linear fade to 2.5%. E_t = E_t−1 × (1 + g_t); RI_t = (ROE_norm − 10%) × E_t−1. TV₁₀ = RI₁₁ / (10% − 2.5%). Value = E₀ + Σ RI_t / 1.1^t + TV₁₀ / 1.1^10; per share = value / period-end shares (as BANK V1–V2) Σ net income ≤ 0 → payout 100% (as V1) |
| P2 | Buffett — edge cases | Cannot be valued: E₀ ≤ 0, ROE_norm unavailable, or ROE_norm ≤ 2.5% (as V6); no negative value is shown. Sensitivity (display): erosion only when ROE_norm > 10%, fading to 10% over years 1–10 with terminal RI = 0 and the base growth path; ROE ± 1 pp with growth recomputed (as V7). Implied return and implied ROE solved numerically (as V8): implied return from just above 2.5% to +40% ("below 2.5%" when lower); implied ROE −20% to +40%; tolerance $0.01 per share; otherwise "no solution" Value ≤ 0 or cannot be valued → price score 0, no buy price (C15; 2026-10-17) |
| P3 | Graham — Graham Number | √(22.5 × normalized EPS × adjusted tangible book value per share). Normalized EPS = average operating EPS over 10 years (normalized operating profit after tax / diluted shares; non-recurring investment gains excluded; split-adjusted). 7–9 years: average of available years, flagged; fewer than 7: cannot be valued. **Loss years are included in the average** (a catastrophe year is part of the insurance cycle; no BANK-V5-style exclusion). Average ≤ 0 or adjusted TBVPS ≤ 0 → cannot be valued. Graham price score per X1 (shown, labelled; buy price "not suitable" below quality 55) |
| P4 | Price score and buy price | General-model scales: Buffett (≥40% discount = 10) and classic Graham (≥50% discount = 10); margin-of-safety / buy-price tables by the respective quality score |
| P5 | Growth eligibility gate for insurers | The gate (revenue up in 3 of 4 transitions; EPS decline >10% at most once; EPS positive in all 5 years) uses **insurance revenue** (premiums earned + policy fees) and **operating EPS** instead of total revenue and reported EPS, which move with markets. Thresholds unchanged |

**Data guard (ETL, all profiles):** share-count series are checked for values about 1,000× off their neighbours (units tagged in thousands); such a year is rescaled and flagged, a larger mismatch is missing (found: WRB FY2017–22).

**Pricing round (2026-10-13, prices of 2026-10-12):** all values between 0.54× (AIG) and 2.81× (PGR) adjusted book; implied returns 5.5% (MET) to 15.3% (RNR); erosion sensitivity cuts value by 27–52% for the nine companies with ROE_norm >10% — read the range, not the point. **Documented limitation:** operating ROE and operating EPS exclude gains on equity portfolios, so equity-heavy insurers (e.g., CINF) are valued conservatively; consistent with Graham's representative earnings; to revisit if Berkshire-type insurers are added.

The operating total does not depend on Q1 (Q1 moves amounts between underwriting and investment lines only), so 10-year operating EPS can be computed from XBRL.

### D.5 INCOME_REAL_ESTATE

Quality score and value are separate measures (as BANK and INSURANCE). Pricing is equity-based: debt is part of the operating model of an income-property company.

| # | Component | Definition |
|---|---|---|
| RP1 | Buffett — DCF of OE per share | Flows = OE per share attributable to common (after interest, preferred dividends and non-OP-unit NCI; OP units counted as shares). Discount rate 10% (model parameter, a conservative required return, not a measured cost of equity). Base, stage-1 growth, growth gate (on normalized FFO per share and revenue), stage-2 fade, 2.5% terminal growth and G1 roll-forward rule: as in the general model v1.3. Price and financials of the same listed entity (C16). **No debt subtraction** (flows are already after interest); excess cash is not added. Value ≤ 0 → C15 Previous-5 median ≤ 0 → stage-1 growth 0% (as the general model; 2026-10-17) |
| RP1a | Leverage and liquidity guard | No Buffett price score or buy price when: net debt / EBITDAre > 8x; EBITDAre ≤ 0; debt data missing (incl. a 12-month coverage that cannot be computed because maturities or committed facilities are missing); **12-month liquidity coverage < 1.0x** = (cash + short-term investments + undrawn committed facilities) / debt maturing in the next 12 months (the company depends on new market funding within a year). Two windows on purpose: 12 months = immediate liquidity test before a buy price; 24 months (Graham 3.2.2) = quality score of near-term financial conservatism. 7.5x–8.5x leverage is flagged borderline (display, as S3a; the block is unchanged). The DCF value may be shown for analysis, labelled "not a buy price" Quality coverage below 80% does not block the price score: as in every profile it removes only the buy price (M7) (2026-10-17) |
| RP1b | Recent-trend growth condition | Added to the growth gate: if same-property NOI fell in the latest year, or occupancy fell by more than 2 pp in the latest year, stage-1 growth = 0 (flag `growth_gate_recent_trend`). Same-property NOI missing → latest-year revenue decline tested instead; occupancy not applicable (table A) → that part not tested. Buffett prices growth only where the business is predictable |
| RP2 | Graham — conservative NAV | NAV (equity) = stabilized NOI / conservative cap rate + carrying value of the assets valued at carrying value under RP2a − net debt − other claims. **Other claims** = preferred equity + noncontrolling interests under RP2b + finance-lease liabilities not already in debt (no liability counted twice; working-capital items excluded). NAV per share = NAV attributable to common / shares under RP2b. **Conservative cap rate** = max(latest monthly average of the 10-year government yield in the currency of the NOI + 3 pp, 6%) (US: FRED GS10; matches the daily price refresh; ETL requirement) — a test parameter, not a final threshold; multi-currency companies: reporting currency, flagged. **One cap rate for all asset types** (confirmed after round 1): no asset-type spread and no floor at the market-implied rate (circular — the price would set the value); the growth of low-yield asset types is priced by the Buffett DCF. The market-implied cap rate is shown for display No monthly yield for the month → the latest annual average, flagged; no yield at all → "cannot be valued" (M6) (2026-10-17) |
| RP2a | Asset classification for NAV | (1) **Already in the capitalized NOI → 0:** real estate in place, acquired lease intangibles, straight-line rent receivable, deferred leasing costs, right-of-use assets of ground leases (ground rent is already in property expenses; the matching operating-lease liability is not a claim). (2) **Carrying value:** development and construction in progress, land, equity-method JV interests, notes and loans receivable, financial investments at carrying value (fair value or amortized cost). (3) **Working capital → excluded** (mixed lines that cannot be split stay here — conservative) (symmetrical with payables): receivables, prepaid and other current assets. (4) **Excluded:** cash (already in net debt), goodwill. (5) **Unidentified** = total assets − (1) to (4); above 10% of total assets → no Graham price score (indicative NAV shown) |
| RP2b | Noncontrolling interests and shares | When diluted shares include OP units: deduct only non-OP-unit NCI (e.g., partners in consolidated JVs). When the NCI cannot be split: shares excluding OP units and the whole NCI deducted, flagged. OP units are never both counted in shares and deducted as NCI |
| RP2c | One basis for NOI, debt and JV interests | Two mutually exclusive bases: (a) **consolidated** — consolidated NOI, consolidated debt, NCI deducted (RP2b), unconsolidated JV interests at carrying value (RP2a); or (b) **proportionate** — the company's share of NOI incl. JVs and the proportionate debt, JV interests not added separately. Never JV NOI capitalized and the JV interest added. Default (a); every NOI line used in the NAV is tied to assets in the value basis and to the shareholders measured |
| RP3 | Price score and buy price | General-model scales: Buffett (≥40% discount = 10), classic Graham (≥50% discount = 10); margin of safety by the respective quality score. Double conservatism (conservative cap rate + 50% discount) checked in the run, not pre-adjusted |
| RP5 | Market-distress flag (display) | Shown when the market-implied cap rate exceeds the conservative cap rate by more than 3 pp: "the market prices distress not visible in the annual data — check the latest results before buying". Shown with it: NAV without development and land. Market-implied cap rate = NOI / (market capitalization + net debt + other claims − non-NOI assets). The flag itself changes no score; its pricing consequence is RP5a |
| RP5a | Binding pricing rule triggered by RP5 — **dedicated conservatism rule** | When RP5 is shown, the Graham price score and buy price use the NAV without development and land. **Rationale (a conservatism decision, not a proven economic finding):** the conservative cap rate already carries 3 pp over the government yield; the trigger means the market demands at least twice that premium, which may reflect distress but also asset quality, risk, business mix or market expectations. Graham would not credit non-income-producing assets at cost then. Requires a sensitivity check (follow-up item). The full NAV stays on display. Buffett is unchanged (the flag is shown) |
| — | Display only | Price / average normalized FFO ≤ 15 (indicative only — FFO is before recurring capex); IFRS reported fair value next to the conservative NAV; the Graham NAV is labelled "conservative value under a uniform model assumption, not a market-value estimate"; sensitivities: Graham cap rate ±1 pp and NAV without development and land; Buffett discount rate ±1 pp and stage-1 growth ±1 pp |

The classic Graham Number is not applied to real estate.

#### D.5a Real-estate definitions (computed by code)

| Item | Definition |
|---|---|
| FFO (uniform) | US GAAP (NAREIT): net income + real-estate-related D&A incl. share of unconsolidated JVs (source priority, RE17: 1. the company's FFO reconciliation; 2. real-estate D&A tag; 3. total D&A, flagged) − gains on sale of depreciable property and of interests in real-estate entities (RE12) + impairments of depreciable real estate ± JV adjustments + OP-unit / noncontrolling adjustments as in the company's reconciliation − preferred dividends. IFRS: net income − fair-value gains (+ losses) on investment property, net of deferred tax − gains on property sales − preferred dividends. The reported FFO (incl. Israeli ISA FFO) is reconciled to this formula, not used directly; a difference >10% after RE17 is flagged for review (E11) |
| Normalized FFO (recurring property earnings) | **Normalized FFO = FFO − Σ non-recurring P&L items** (RE30), each item signed as in net income: gain = positive, loss = negative (removing a loss adds it back). Items, in this order, each counted once: (1) gains / losses on sales of real estate incl. development properties and land (RE29); (2) impairments of non-real-estate assets and investments, unless already inside item (3); (3) realized and unrealized results of non-real-estate investments (RE29a); (4) unrealized FX remeasurement, **net of the related hedging derivatives** (RE29b; without a net line, the amount the company itself adds back in its FFO / AFFO reconciliation); (5) loss on debt extinguishment, transaction / merger costs. An amount already removed in the FFO source (company reconciliation) is not removed again. **Control (RE29b):** if the Q1 or Q6 reconciliation gap widens by more than 5 pp after the removal, the company is flagged for review |
| Owner earnings (OE) | Normalized FFO attributable to common shareholders (after preferred dividends and non-OP-unit noncontrolling interests) − straight-line rent adjustment (= GAAP rent − cash rent received; a negative adjustment increases OE, RE24) − maintenance capex − income-preserving TI/LC. FFO, every deduction and the share count on one basis (RE28). **No double counting:** SBC is already an expense in net income and is not deducted again; an item already deducted in the base is not deducted again; growth TI / capex are not deducted |
| FFO proxy | When maintenance capex or TI/LC is missing: normalized FFO per share, `metric_basis = FFO_PROXY`, allowed **only** for growth and stability sub-items; level-based sub-items (dividend coverage) are missing |
| Same-property NOI and occupancy basis | Taken on the company's primary reported basis, and the basis is recorded (RE21) |

---

## Part E — Data dictionary

The ETL source column is the engine's actual mapping (verification of 2026-10-15, V-02): the first tag or source in the priority chain, per profile (G = general, BK = bank, IN = insurance, RE = real estate). Alternatives in priority order and ETL notes: E.2. Items marked **required, not yet implemented** stay in the dictionary as requirements (Part H). Rows FIN-160 to FIN-185 were added on 2026-10-17 (items the engine uses that the draft lacked, N-01 to N-26).

### E.1 Dictionary

| ID | Item | Definition | Statement | ETL source (primary) | Extracts | Used in (sample) |
|---|---|---|---|---|---|---|
| FIN-001 | EBIT | Operating income; when not reported: pretax income + interest expense (2026-10-17) | Income statement | G.ebit: `OperatingIncomeLoss` | Code | B3.4-STD |
| FIN-002 | Income tax | Income tax expense | Income statement | G.tax: `IncomeTaxExpenseBenefit`; IN.tax: `IncomeTaxExpenseBenefit`; RE.income_tax: `IncomeTaxExpenseBenefit` | Code | B3.4-STD, INS |
| FIN-003 | Pretax income | Income before income taxes | Income statement | G.pretax: `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`; BK.pretax: `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`; IN.pretax: `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` | Code | B3.4-STD, INS |
| FIN-010 | Equity | Total shareholders' equity (parent) | Balance sheet | G.equity: `StockholdersEquity`; BK.equity: `StockholdersEquity`; IN.equity: `StockholdersEquity` | Code | B3.4 all |
| FIN-011 | Financial debt | Short- and long-term borrowings, incl. current portion; excludes operating leases | Balance sheet / debt note | G: current = `DebtCurrent`, else `LongTermDebtCurrent` + short-term borrowings / `CommercialPaper` / `NotesPayableCurrent`; non-current = `LongTermDebtNoncurrent`, else `LongTermDebt` - current, else `LongTermNotesPayable` / `NotesPayableNoncurrent`; absent with a balance sheet = 0 (flagged); BK.st_borrow: `ShortTermBorrowings`; BK.lt_debt: `LongTermDebt`; IN.debt_total: `DebtLongtermAndShorttermCombinedAmount`; IN.debt_lt: `LongTermDebt`; IN.debt_st: `ShortTermBorrowings`; IN.debt_junior_sub: `JuniorSubordinatedNotes`; RE.debt_total: `LongTermDebt`; RE: sum of standard tags per company (DEBT_PARTS: O, BXP, AMT) + extraction `debt_total_bs` | Code | B3.4-STD, RE |
| FIN-012 | Cash | Cash and equivalents, excluding customer funds (C3) | Balance sheet | G.cash: `CashAndCashEquivalentsAtCarryingValue`; IN.cash: `CashAndCashEquivalentsAtCarryingValue`; RE.cash: `CashAndCashEquivalentsAtCarryingValue` | Code | B3.4-STD, RE |
| FIN-013 | Short-term investments | Marketable securities, current | Balance sheet | G.sti: `ShortTermInvestments`; RE.sti: `ShortTermInvestments` | Code | B3.4-STD |
| FIN-020 | Net income | Net income attributable to the parent | Income statement | G.net_income: `NetIncomeLoss`; BK.net_income: `NetIncomeLoss`; BK.ni_common: `NetIncomeLossAvailableToCommonStockholdersBasic`; IN.net_income: `NetIncomeLoss`; RE.net_income: `NetIncomeLoss` | Code | B3.4-BANK |
| FIN-021 | Preferred dividends | Dividends on preferred stock | Income statement / equity | BK.pref_div: `PreferredStockDividendsIncomeStatementImpact`; RE.pref_div: `PreferredStockDividendsIncomeStatementImpact` | Code | B3.4-BANK |
| FIN-022 | Preferred stock | Carrying value of preferred equity | Balance sheet | BK.preferred: `PreferredStockValue`; IN.preferred: `PreferredStockValue`; RE.pref_equity: `PreferredStockValue` | Code | B3.4-BANK, INS |
| FIN-023 | Goodwill | Goodwill | Balance sheet | G.goodwill: `Goodwill`; BK.goodwill: `Goodwill`; IN.goodwill: `Goodwill`; RE.goodwill: `Goodwill` | Code (C5: absent = 0, flagged) | B3.4-BANK |
| FIN-024 | Intangibles | Intangible assets excluding goodwill | Balance sheet | G.intangibles: `IntangibleAssetsNetExcludingGoodwill`; BK.intangibles: `IntangibleAssetsNetExcludingGoodwill`; IN.intangibles: `IntangibleAssetsNetExcludingGoodwill`; RE.intangibles_net: `IntangibleAssetsNetExcludingGoodwill` | Code | B3.4-BANK |
| FIN-025 | Total assets | Total assets | Balance sheet | G.assets: `Assets`; BK.assets: `Assets`; IN.assets: `Assets`; RE.assets: `Assets` | Code | B3.4-BANK |
| FIN-030 | Investment gains | Realized and unrealized investment gains / losses in profit or loss | Income statement | IN.gains_realized: `RealizedInvestmentGainsLosses`; BK.securities_gain_loss: `DebtSecuritiesRealizedGainLoss` | Code | B3.4-INS |
| FIN-031 | MRB remeasurement | Remeasurement of market-risk benefits / embedded derivatives | Income statement / notes | IN.mrb_change: `MarketRiskBenefitChangeInFairValueGainLoss`; IN.mrb_liability: `MarketRiskBenefitLiabilityAmount` | Code / AI | B3.4-INS |
| FIN-032 | Goodwill impairment | Goodwill impairment loss | Income statement | BK.goodwill_impairment: `GoodwillImpairmentLoss`; IN.goodwill_impairment: `GoodwillImpairmentLoss`; G.impairments: `GoodwillImpairmentLoss` | Code | B3.4-INS |
| FIN-033 | AOCI by component | AFS unrealized, discount-rate remeasurement, own credit, FX, pension | Equity note | IN.aoci_total: `AccumulatedOtherComprehensiveIncomeLossNetOfTax`; IN.aoci_afs_tag: `AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax` | Code; AI when untagged | B3.4-INS |
| FIN-040 | Rental revenue | Lease / rental income | Income statement | RE.rental_revenue: `OperatingLeaseLeaseIncome` | Code | B3.4-RE |
| FIN-041 | Other property revenue | Tenant reimbursements, other property income | Income statement | RE.other_property_revenue: (no standard tag; extension / extraction) | Code | B3.4-RE |
| FIN-042 | Property operating expenses | Property opex incl. real-estate taxes | Income statement | RE.prop_opex: `DirectCostsOfLeasedAndRentedPropertyOrEquipment`; RE.re_tax: `RealEstateTaxExpense`; RE.repairs: `CostOfPropertyRepairsAndMaintenance`; RE.cost_of_revenue: `CostOfRevenue` | Code | B3.4-RE |
| FIN-043 | New-investment yields | Stabilized yield on acquisitions and developments completed | MD&A / supplemental | Extraction store only: `acquisition_yield`, `development_yield`, `acquisition_invested`, `development_invested` | **AI** (quote) | B3.4-RE |
| FIN-044 | Same-property NOI growth | Like-for-like NOI growth — on the company's primary reported basis; the basis is recorded (RE21) | MD&A | Extraction store only: `same_property_noi_growth` | **AI** (quote) | B3.4-RE |
| FIN-045 | Growth capital | Acquisitions and development spend (net of dispositions for the proxy) | Cash-flow statement / notes | RE.acq_real_estate: `PaymentsToAcquireRealEstate`; RE.acq_business: `PaymentsToAcquireBusinessesNetOfCashAcquired`; RE.development: `PaymentsToDevelopRealEstateAssets`; RE.capital_improvements: `PaymentsForCapitalImprovements` | Code; split by AI | B3.4-RE |
| FIN-046 | Dispositions | Gross proceeds / carrying value of real estate sold | Cash-flow statement / notes | RE.sale_proceeds: `ProceedsFromSaleOfRealEstateHeldforinvestment` | Code | B3.4-RE |
| FIN-047 | Gross real estate at cost | Real estate before accumulated depreciation | Balance sheet / Schedule III | RE.re_gross: `RealEstateGrossAtCarryingValue`; RE.re_net: `RealEstateInvestmentPropertyNet` | Code (display; materiality test only) | B3.4-RE |
| FIN-050 | Interest expense | Interest expense incl. capitalized interest | Income statement / notes | G.interest_expense: `InterestExpense`; IN.interest_expense: `InterestExpense`; RE.interest_expense: `InterestExpense`; RE.interest_capitalized: `InterestCostsCapitalized` | Code | B3.4-RE |
| FIN-051 | Market capitalization | Price × shares outstanding at year-end | Price provider | Computed: current price x latest `shares_out` (not a stored fact) | Code | B3.4-RE |
| FIN-060 | Revenue | Total revenue (BANK: net interest income + noninterest income; INSURANCE: operating revenue) | Income statement | G.revenue: `Revenues`; RE.total_revenue: `Revenues`; IN.revenue_total: `Revenues`; IN.premiums: `PremiumsEarnedNet`; IN.policy_fees: `InsuranceCommissionsAndFees`; BK.nii: `InterestIncomeExpenseNet`; BK.nonint: `NoninterestIncome` | Code | B3.1, B3.2, B3.3 |
| FIN-061 | Cost of revenue / gross profit | Cost of revenue, or gross profit as reported (C4, C13) | Income statement | G.gross_profit: `GrossProfit`; G.cost_of_revenue: `CostOfRevenue`; G.claims_expense: `PolicyholderBenefitsAndClaimsIncurredNet` | Code | B3.2 |
| FIN-062 | Diluted EPS | Earnings per diluted share | Income statement | G.eps: `EarningsPerShareDiluted`; BK.eps: `EarningsPerShareDiluted`; IN.eps: `EarningsPerShareDiluted`; RE.eps: `EarningsPerShareDiluted` | Code | B3.3 |
| FIN-063 | Net interest income | Interest income − interest expense (banks) | Income statement | BK.nii: `InterestIncomeExpenseNet` | Code | B3.2-BANK, B3.3-BANK |
| FIN-064 | Noninterest income | Fees and other noninterest income (banks) | Income statement | BK.nonint: `NoninterestIncome` | Code | B3.2-BANK, B3.3-BANK |
| FIN-070 | Normalized FFO | FFO − Σ non-recurring P&L items, signed (RE30); full definition in D.5a | Computed | Computed (RE30): FFO = net income + real-estate D&A (company reconciliation `recon_re_da` > `re_depr` > `da_total`) + gains / impairments adjustment (`gains_sale` + `gains_re_entities` + `impairment`, or `recon_gi_net`) - preferred dividends + OP-unit / JV reconciliation lines; items removed: `re29_re_sale_gains*` / `dev_gains_reported`, `re29_nonre_impairments*`, `re29a_nonre_inv*`, `fx_unrealized` or `re29b_fx_net`, `debt_extinguishment`, `transaction_costs` | Code (from FIN inputs) | B3.2-RE, B3.3-RE |
| TXT-001 | Business section | Description of the business | Annual report | Not implemented (AI questions are `ai_pending` placeholders) | Code (retrieval) → AI — **required, not yet implemented** | B3.1, B3.2 |
| TXT-002 | Risk Factors | Risk factors | Annual report | Not implemented | Code (retrieval) → AI — **required, not yet implemented** | B3.1 |
| FIN-080 | CFO | Cash flow from operations | Cash-flow statement | G.cfo: `NetCashProvidedByUsedInOperatingActivities` | Code | B3.5 |
| FIN-081 | Capex | Purchases of property and equipment | Cash-flow statement | G.capex: `PaymentsToAcquirePropertyPlantAndEquipment` | Code | B3.5 |
| FIN-082 | D&A | Total depreciation and amortization (C9) | Cash-flow statement | G.da: `DepreciationDepletionAndAmortization`; RE.da_total: `DepreciationAndAmortization`; RE.re_depr: `SECScheduleIIIRealEstateAccumulatedDepreciationDepreciationExpense` | Code | B3.5, B3.6 |
| FIN-083 | Amortization of acquired intangibles | Amortization of intangibles from acquisitions | Notes | G.acq_amort: `AmortizationOfIntangibleAssets` | Code | B3.5 |
| FIN-084 | SBC | Stock-based compensation (three states: found / reported none = 0 / not found = missing) | Cash-flow statement | G.sbc: `ShareBasedCompensation`; RE.sbc: `ShareBasedCompensation` | Code | Pricing |
| FIN-085 | Current assets | Total current assets (C3) | Balance sheet | G.cur_assets: `AssetsCurrent` | Code | B3.6 |
| FIN-086 | Current liabilities | Total current liabilities (C3) | Balance sheet | G.cur_liab: `LiabilitiesCurrent` | Code | B3.6 |
| FIN-087 | Dividends paid | Cash dividends to common | Cash-flow statement | G.dividends: `PaymentsOfDividendsCommonStock`; BK.dividends: `PaymentsOfDividendsCommonStock`; IN.dividends: `PaymentsOfDividendsCommonStock`; RE.dividends: `PaymentsOfDividendsCommonStock` | Code (C5) | B3.7 |
| FIN-088 | Buybacks | Repurchases of common stock | Cash-flow statement | G.buybacks: `PaymentsForRepurchaseOfCommonStock`; BK.buybacks: `PaymentsForRepurchaseOfCommonStock`; IN.buybacks: `PaymentsForRepurchaseOfCommonStock`; RE.buybacks: `PaymentsForRepurchaseOfCommonStock` | Code (C5) | B3.7 |
| FIN-089 | Acquisitions | Cash paid for acquisitions, net (C6 fallback: goodwill acquired) | Cash-flow statement | G.acquisitions: `PaymentsToAcquireBusinessesNetOfCashAcquired`; G.goodwill_acquired: `GoodwillAcquiredDuringPeriod`; BK.acquisitions: `PaymentsToAcquireBusinessesNetOfCashAcquired`; IN.acquisitions: `PaymentsToAcquireBusinessesNetOfCashAcquired` | Code | B3.7 |
| FIN-090 | Average share price | Annual average price per fiscal year | Price provider | Price provider `load_prices` (yfinance Close, split-adjusted; average of the fiscal year, >= 100 trading days) | Code | B3.7 |
| FIN-091 | Period-end shares | Shares outstanding at year-end (C7, C14) | Balance sheet / cover | G.shares_out: `CommonStockSharesOutstanding`; BK.shares_out: `CommonStockSharesOutstanding`; IN.shares_out: `CommonStockSharesOutstanding`; RE.shares_out: `CommonStockSharesOutstanding` | Code | B3.5-BANK, B3.7 |
| FIN-092 | Weighted diluted shares | Weighted-average diluted shares | Income statement | G.shares: `WeightedAverageNumberOfDilutedSharesOutstanding`; BK.shares_dil: `WeightedAverageNumberOfDilutedSharesOutstanding`; IN.shares_dil: `WeightedAverageNumberOfDilutedSharesOutstanding`; RE.shares_dil: `WeightedAverageNumberOfDilutedSharesOutstanding` | Code | B3.5-RE, per-share values |
| FIN-093 | Deferred revenue, current | Contract liabilities, current (TECH, C11) | Balance sheet | G.deferred_rev_current: `ContractWithCustomerLiabilityCurrent` | Code | B3.6-TECH |
| FIN-100 | Provision for credit losses | Provision charged to income | Income statement | BK.provision: `ProvisionForLoanLeaseAndOtherLosses` | Code | B3.5-BANK |
| FIN-101 | Loans | Loans and leases, gross / net | Balance sheet | BK.loans: `FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss` | Code | B3.5-BANK, B3.6-BANK, B3.8-BANK |
| FIN-103 | NCO | Net charge-offs | Credit-quality note | BK._nco_net: `FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoffAfterRecovery`; BK._wo_gross: `FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoff`; BK._recoveries: `FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossRecovery` | Code; FR Y-9C history (D13); AI when untagged | B3.6-BANK |
| FIN-104 | ACL | Allowance for credit losses | Balance sheet / note | BK.acl: `FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest` | Code; AI when untagged | B3.6-BANK |
| FIN-105 | Nonaccrual loans | Loans on nonaccrual status (D11) | Credit-quality note | BK.nonaccrual: `FinancingReceivableExcludingAccruedInterestNonaccrual`; BK.past_due_90: `FinancingReceivableExcludingAccruedInterest90DaysOrMorePastDueStillAccruing` | Code; AI when untagged | B3.6-BANK |
| FIN-106 | CET1 and required CET1 | Per approach, as reported (D10, V9) | Annual / risk report | Extraction store: `cet1_ratio_standardized`, `cet1_ratio_advanced`, `cet1_required_standardized`, `cet1_required_advanced`, `scb`, `gsib_surcharge`, `rwa_*`, `total_capital_*` | **AI** (quote) | B3.6-BANK |
| FIN-107 | LCR | Q4 average (V10); exemption by regulatory category (V11) | Annual report / LCR disclosure | Extraction store: `lcr_q4_average` (value, `NA` = exempt, `MISSING`) | **AI** (quote) | B3.6-BANK |
| FIN-108 | DPS | Dividend per share (C8 fallback) | Notes | G.dps: `CommonStockDividendsPerShareDeclared`; BK.dps: `CommonStockDividendsPerShareDeclared`; IN.dps: `CommonStockDividendsPerShareDeclared`; RE.dps: `CommonStockDividendsPerShareDeclared` | Code | B3.5-BANK |
| FIN-110 | Insurance revenue | Premiums earned + policy fees (IFRS 17: insurance revenue) | Income statement | IN.premiums: `PremiumsEarnedNet`; IN.policy_fees: `InsuranceCommissionsAndFees` | Code; AI for IFRS without XBRL | B3.5-INS |
| FIN-111 | Claims and benefits | Claims and benefits incurred (C13) | Income statement | IN.benefits: `PolicyholderBenefitsAndClaimsIncurredNet`; G.claims_expense: `PolicyholderBenefitsAndClaimsIncurredNet` | Code | B3.5-INS |
| FIN-112 | Non-claims underwriting expenses | Acquisition costs and other insurance expenses as one item (not split); derived inside the underwriting-result identity (merged with FIN-113, 2026-10-17) | Income statement | Not mapped separately | Code | B3.5-INS |
| FIN-114 | Interest credited / accretion | Interest credited to policyholder accounts; accretion on future policy benefits (Q1) | Income statement / LDTI roll-forward | IN.interest_credited: `InterestCreditedToPolicyholdersAccountBalances` | Code; AI for roll-forward | B3.5-INS |
| FIN-116 | Float components | Insurance liabilities, reinsurance assets, OCI discount-rate remeasurement (I16) | Balance sheet / notes | IN.claims_gross: `LiabilityForClaimsAndClaimsAdjustmentExpense`; IN.claims_net: `LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet`; IN.reins_unpaid: `ReinsuranceRecoverablesOnPaidAndUnpaidLosses`; IN.fpb: `LiabilityForFuturePolicyBenefits`; IN.pab: `PolicyholderContractDeposits`; IN.unearned: `UnearnedPremiums`; IN.reins_prepaid: `PrepaidReinsurancePremiums`; IN.aoci_total: `AccumulatedOtherComprehensiveIncomeLossNetOfTax` | Code; AI when untagged | B3.5-INS, B3.6-INS |
| FIN-117 | Regulatory capital ratio | Ratio and regime (Q3) | Solvency / statutory disclosure | Extraction store: `reg_capital_ratio` (note: basis ACL / CAL / SCR / SMR / OTHER) | **AI** (quote) | B3.6-INS |
| FIN-118 | Prior-period development | Adverse prior-period liability experience (I3, I20) | Claims roll-forward / LDTI / IFRS 17 tables | IN.prior_year_dev: `LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseIncurredClaimsPriorYears`; IN.ldti_remeasurement: `LiabilityForFuturePolicyBenefitRemeasurementGainLoss`; IN.fpb_adverse_development: `LiabilityForFuturePolicyBenefitAdverseDevelopmentExpense` | Code / **AI** | B3.6-INS |
| FIN-119 | Government yield (annual) | Annual average 10-year yield per currency (E4a) | Constants table | File `scripts/gov_yields.csv` (USD `DGS10`, JPY `JGB 10Y`; annual averages 2016-2025) | Code | B3.5-INS |
| FIN-120 | Straight-line rent | GAAP rent − cash rent (RE24) | Cash-flow statement / AFFO reconciliation | RE.straight_line: `StraightLineRent` | Code; AI from AFFO when untagged | B3.5-RE |
| FIN-121 | Maintenance capex (RE) | Recurring capex as stated by the company | Supplemental / AFFO reconciliation | RE.maint_capex: (no standard tag; extension / extraction) | **AI** (quote) | B3.5-RE |
| FIN-122 | TI/LC | Income-preserving tenant improvements and leasing commissions | Supplemental / AFFO reconciliation | RE.ti_lc_total: `PaymentsForTenantImprovements` | **AI** (quote) | B3.5-RE |
| FIN-123 | EBITDAre components | Gains / losses on property sales, impairments of depreciable real estate, JV adjustments | Income statement / notes | RE.gains_sale: `GainLossOnSaleOfProperties`; RE.gains_re_entities: `EquityMethodInvestmentRealizedGainLossOnDisposal`; RE.impairment: `ImpairmentOfRealEstate`; RE.da_total: `DepreciationAndAmortization`; RE.interest_expense: `InterestExpense`; RE.income_tax: `IncomeTaxExpenseBenefit` | Code | B3.6-RE |
| FIN-125 | Economic property value | IFRS investment property at fair value, or disclosed fair value (US GAAP) | Balance sheet / notes | Extraction store: `fair_value_real_estate` | Code / **AI** | B3.6-RE |
| TXT-004 | MD&A / governance | Management discussion, governance, restatements | Annual report | Not implemented | Code (retrieval) → AI — **required, not yet implemented** | B3.7, B3.8 |
| FIN-102 | Deposits | Total deposits | Balance sheet | BK.deposits: `Deposits` | Code | G3.2-BANK |
| FIN-130 | FX rates | Annual average and year-end rate per currency (R15) | FX provider | Not implemented | Code — **required, not yet implemented** | G3.1 |
| FIN-131 | First annual report date | Date of the company's first annual report (SEC, MAYA, ESEF metadata) | Regulator / exchange metadata | `first_annual_report` = earliest 10-K / 10-K405 / 10-KT filing date in the SEC submissions JSON | Code | G3.1 |
| FIN-132 | Receivables | Accounts receivable, current | Balance sheet | G.receivables: `AccountsReceivableNetCurrent` | Code | G3.2 |
| FIN-133 | Short-term borrowings | Short-term borrowings (banks) | Balance sheet | BK.st_borrow: `ShortTermBorrowings` | Code | G3.2-BANK |
| FIN-134 | Central bank / FHLB advances | Advances from central bank / FHLB | Balance sheet | BK.fhlb: `AdvancesFromFederalHomeLoanBanks` | Code | G3.2-BANK |
| FIN-135 | Repo and securities lending | Repurchase agreements and securities-lending liabilities (D15) | Balance sheet | Extraction store: `funding:repo:*` lines | Code | G3.2-BANK |
| FIN-136 | Investment portfolio by category | Cash, short-term, fixed maturities, equities, mortgage loans, policy loans, real estate, other invested assets; credit quality (Q2) | Investment notes | IN.investments: `Investments` | Code; AI when untagged | G3.2-INS, G3.7-INS |
| FIN-137 | Committed undrawn facilities | Committed and available credit facilities | Debt note / liquidity section | Extraction store: `committed_undrawn_facilities` | Code; **AI** when untagged | G3.2-RE, RP1a |
| FIN-138 | Debt maturities | Principal maturing by year (12 / 24 months) | Debt note | RE.mat_year1: `LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths`; RE.mat_year2: `LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo` | Code; **AI** when untagged | G3.2-RE, RP1a |
| FIN-139 | Long-term debt | Long-term debt, non-current | Balance sheet | G: `LongTermDebtNoncurrent`, else `LongTermDebt` - current, else notes (field `debt_lt`) | Code | G3.3 |
| FIN-140 | Loan breakdown | Loans by category, mapped to 5 categories | Notes | Extraction store: `loan:<line>` rows mapped to 5 categories by `LOAN_MAP` (per bank) | **AI**, mapping in code | G3.3-BANK |
| FIN-141 | Total regulatory capital | Total regulatory capital (banks) | Risk report | Extraction store: `total_capital_<approach>` (derived from the ratio and RWA when missing, flagged) | **AI** | G3.3-BANK |
| FIN-142 | Unencumbered NOI / assets | NOI or assets free of secured debt | Debt note / supplemental | Extraction store: `unencumbered_noi_share`, `unencumbered_assets_share` | **AI** | G3.3-RE |
| FIN-143 | Stabilized vs development split | Fair value of stabilized income property vs development / land | Notes | Extraction store: `stabilized_noi`, `stabilized_value`, `other_property_value` | **AI** | G3.3-RE |
| TXT-005 | Segment and customer disclosures | Major customers (>10%), segments, licenses | Annual report / notes | Not implemented | Code (retrieval) → AI — **required, not yet implemented** | G3.1 |
| FIN-144 | RWA | Risk-weighted assets, binding approach | Risk report | Extraction store: `rwa_<approach>` | **AI** | G3.7-BANK |
| FIN-145 | Occupancy / utilization | Occupancy or the mapped metric by asset type (table A) — on the company's primary reported basis; the basis is recorded (RE21) | MD&A / property tables | Extraction store: `occupancy` | **AI** (quote) | G3.7-RE, RP1b |
| FIN-146 | Largest tenant share | Largest independent tenant share of rent / NOI | Business / MD&A | Extraction store: `largest_tenant_share` | **AI** (quote) | G3.7-RE |
| PRC-001 | Share price | Latest close, refreshed at least daily (E1) | Price provider | Price provider `load_prices`: yfinance history cached in `scripts/cache/prices` | Code | D.0 |
| FIN-150 | Government yield (monthly) | Latest monthly average 10-year yield per currency (E4b; US FRED GS10) | Constants table | File `scripts/gov_yields.csv` row `USD, 2026-09, GS10` (single monthly row) | Code | D.5 RP2 |
| FIN-151 | 10-year EPS history | Diluted EPS, split-adjusted, 7–10 years | Income statement | G.eps: `EarningsPerShareDiluted` | Code | D.2, D.3, D.4 |
| FIN-152 | NAV inputs (RP2a) | Balance-sheet classification: in NOI / carrying value / working capital / excluded / unidentified | Balance sheet / notes | Extraction store: `bsa_<class>__<slug>` lines, classes noi / carry / carryfin / inre / wc / excl / other (FY2025 only) | Code; **AI** classification with quotes | D.5 |
| FIN-153 | NCI and OP units | Noncontrolling interests split (OP-unit vs other), OP-unit count (RP2b) | Equity note | RE.nci_total: `MinorityInterest`; RE.nci_op: `MinorityInterestInOperatingPartnerships`; RE.nci_lp: `MinorityInterestInLimitedPartnerships`; RE.nci_redeemable: `RedeemableNoncontrollingInterestEquityCarryingAmount` | Code; **AI** split | D.5 |
| TXT-003 | Competition | Competition discussion | Annual report | Not implemented | Code (retrieval) → AI — **required, not yet implemented** | B3.2 |
| FIN-160 | Goodwill acquired in the year (N-01) | Goodwill recognized in business combinations in the year (S-09) | Goodwill note | `GoodwillAcquiredDuringPeriod` (G, BK, IN) | Code | C6; B3.8-BANK #4 (D7); INS Q4 |
| FIN-161 | Total liabilities (N-02) | Total liabilities | Balance sheet | `Liabilities` (G, IN) | Code | D.2 Net-Net; INS float share |
| FIN-162 | Funds held for clients; restricted cash (N-03) | Customer funds and restricted cash removed from cash (C3) | Balance sheet | `FundsHeldForClients`; `RestrictedCashAndCashEquivalents`; `RestrictedCashCurrent` | Code | C3 |
| FIN-163 | Cover-page share count (N-04) | Shares outstanding on the annual-report cover | Cover page | `dei:EntityCommonStockSharesOutstanding` | Code | FIN-091 fallback |
| FIN-164 | Weighted basic shares (N-05) | Weighted average basic shares | Income statement | `WeightedAverageNumberOfSharesOutstandingBasic` | Code | C8 |
| FIN-165 | Pretax income, domestic and foreign (N-06) | Components of pretax income | Tax note | `…BeforeIncomeTaxesDomestic`; `…Foreign` | Code | FIN-003 fallback; INS FX flag |
| FIN-166 | Depreciation; finance-lease ROU amortization (N-07) | D&A components (C9) | Cash-flow statement / notes | `Depreciation`; `FinanceLeaseRightOfUseAssetAmortization` | Code | C9, FIN-082 |
| FIN-167 | Non-current marketable debt securities (N-08) | For the alternative current ratio (display) | Balance sheet | `AvailableForSaleSecuritiesDebtSecuritiesNoncurrent`; `MarketableSecuritiesNoncurrent` (+ derived) | Code | C12 |
| FIN-168 | Claims / benefits expense (STANDARD) (N-09) | Claims expense counted in cost of revenue (managed care) | Income statement | `PolicyholderBenefitsAndClaimsIncurredNet` | Code | C13 |
| FIN-169 | Net income to common; profit or loss; NCI (N-10) | Bank income lines | Income statement | `NetIncomeLossAvailableToCommonStockholdersBasic`; `ProfitLoss`; `NetIncomeLossAttributableToNoncontrollingInterest` | Code | BANK inputs |
| FIN-170 | 90+ days past due accruing; uninsured deposits (N-11) | Display items (D11; S-09) | Credit note; deposit disclosure | BK `past_due_90`; extraction `uninsured_deposits` | Code; **AI** (deposits) | Display |
| FIN-171 | Stress capital buffer; G-SIB surcharge; LCR measurement type (N-12) | Inputs to the CET1 requirement and to LCR | Regulatory disclosures | Extraction (`scb`, `gsib_surcharge`, LCR note) | **AI** (quote) | V9, V10 |
| FIN-172 | Discontinued operations (N-13) | Income from discontinued operations, net of tax | Income statement | `IncomeLossFromDiscontinuedOperationsNetOfTax…` (IN) | Code | Q9 |
| FIN-173 | Structural-change indicators (N-14) | Divestiture proceeds, deconsolidation cash, goodwill written off on sale; structural events | Cash-flow statement / notes | Tags of `divestiture_proceeds`, `deconsolidation_cash`, `goodwill_written_off_sale`; extraction `structural_event` | Code; **AI** (events) | Q4, Q7 |
| FIN-174 | Separate accounts; MRB liability; total investments (N-15) | Insurance balance-sheet items | Balance sheet | IN `separate_accounts`, `mrb_liability`, `investments` | Code | INS float share, display |
| FIN-175 | Catastrophe losses; ALM disclosure (N-16) | Catastrophe losses of the latest year; whether ALM is disclosed | MD&A | Extraction `cat_loss_latest`, `alm_disclosed` | **AI** (quote) | Q5 flag, I6 flag |
| FIN-176 | Real-estate taxes; repairs and maintenance (N-17) | NOI components | Income statement | `RealEstateTaxExpense`; `CostOfPropertyRepairsAndMaintenance` | Code | FIN-042 |
| FIN-177 | Gains on sale of interests in real-estate entities (N-18) | Excluded from FFO (RE12) | Income statement | `EquityMethodInvestmentRealizedGainLossOnDisposal` | Code | D.5a FFO |
| FIN-178 | Unrealized FX result; FX net of hedges (N-19) | RE30 item 4 (RE29a, RE29b) | Income statement / FFO reconciliation | `ForeignCurrencyTransactionGainLossUnrealized…`; extraction `re29b_fx_net` | Code; **AI** (net line) | D.5a |
| FIN-179 | Debt extinguishment; transaction costs (N-20) | RE30 item 5 | Income statement | `GainsLossesOnExtinguishmentOfDebt`; `BusinessCombinationAcquisitionRelatedCosts` | Code | D.5a |
| FIN-180 | RE sale gains; non-RE impairments; non-RE investment results; development gains (N-21) | RE30 items 1–3 | Income statement / notes | Extraction `re29_re_sale_gains*`, `re29_nonre_impairments*`, `re29a_nonre_inv*`, `dev_gains_reported` | **AI** (quote) | D.5a |
| FIN-181 | Company FFO reconciliation lines and reported figures (N-22) | Net income, real-estate D&A, NCI and JV adjustments, gains / impairments; reported FFO, core FFO, AFFO, EBITDAre | FFO reconciliation (supplement / annual report) | Extraction store | **AI** (quote) | RE17, Q1, Q2, Q6 (E11) |
| FIN-182 | NAV inputs and claims (details of FIN-152, FIN-153) (N-23) | Equity-method investments, construction in progress, development land, preferred equity, finance-lease liabilities, NCI, balance-sheet classification | Balance sheet / notes | RE `equity_method_inv`, `cip`, `re_dev_land`, `pref_equity`, `finance_lease_liab`, `nci_*`; extraction `bsa_*` | Code; **AI** classification | RP2a, RP2b |
| FIN-183 | Profile-test inputs (N-24) | Total assets, property value, rental revenue and total revenue for the profile test | Balance sheet / income statement | Extraction `profile_total_assets`, `profile_property_value`, `profile_rental_revenue`, `profile_total_revenue` | Code; **AI** (quote) | Part B (RE11) |
| FIN-184 | Single-basis items (N-25) | Share-basis override, share of the operating partnership's income, weighted partnership units, whether diluted shares include OP units | Equity note / EPS note | Extraction `shares_basis_override`, `inc_share_of_bplp`, `partnership_units_weighted`, `diluted_includes_op` | **AI** (quote) | RE28 |
| FIN-185 | Secured debt (N-26) | Secured part of debt | Debt note | `SecuredDebt` (RE) | Code | Debt composition (display) |
| FIN-186 | Net investment income | Net investment income of an insurer (before realized and unrealized gains) | Income statement | IN engine field `net_investment_income` | Code | INSURANCE inputs (engine) |

### E.2 Alternatives and ETL notes

Alternatives are tried in order, year by year, after the primary source. Tags and code fields are quoted as in the engine.

| ID | Item | Alternatives (priority order) | ETL note |
|---|---|---|---|
| FIN-001 | EBIT | — | Derived as pretax income + interest expense when `OperatingIncomeLoss` is absent (2026-10-17) |
| FIN-003 | Pretax income | G.pretax: `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments`; BK.pretax: `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments`; IN.pretax: `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` | Fallback: domestic + foreign components (both required) |
| FIN-010 | Equity | G.equity: `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`; BK.equity: `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`; IN.equity: `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` | — |
| FIN-011 | Financial debt | BK.st_borrow: `OtherShortTermBorrowings`; BK.lt_debt: `LongTermDebtNoncurrent` , `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities` , `LongTermDebtAndCapitalLeaseObligations`; IN.debt_lt: `LongTermDebtNoncurrent` , `LongTermDebtAndCapitalLeaseObligations` , `NotesPayable`; IN.debt_st: `DebtCurrent`; IN.debt_junior_sub: `SubordinatedDebt`; RE.debt_total: `DebtInstrumentCarryingAmount` | Chains with `LongTermDebtAndCapitalLease*` tags include finance-lease liabilities (flagged); operating leases stay excluded |
| FIN-012 | Cash | G.cash: `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`; IN.cash: `Cash` , `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` | The restricted-cash tag is reduced by funds held for clients and restricted cash (C3) |
| FIN-013 | Short-term investments | G.sti: `MarketableSecuritiesCurrent` , `AvailableForSaleSecuritiesDebtSecuritiesCurrent` , `OtherShortTermInvestments` | Absent = 0 when total assets exist (C5) |
| FIN-020 | Net income | G.net_income: `NetIncomeLossAvailableToCommonStockholdersBasic` , `ProfitLoss`; IN.net_income: `NetIncomeLossAvailableToCommonStockholdersBasic`; RE.net_income: `NetIncomeLossAvailableToCommonStockholdersBasic` , `ProfitLoss` | — |
| FIN-021 | Preferred dividends | BK.pref_div: `DividendsPreferredStock` , `PreferredStockDividendsAndOtherAdjustments` , `DividendsPreferredStockCash` , `PaymentsOfDividendsPreferredStockAndPreferenceStock`; RE.pref_div: `DividendsPreferredStock` , `DividendsPreferredStockCash` , `PreferredStockDividendsAndOtherAdjustments` | — |
| FIN-022 | Preferred stock | BK.preferred: `PreferredStockValueOutstanding` , `PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount` , `PreferredStockIncludingAdditionalPaidInCapital`; IN.preferred: `PreferredStockValueOutstanding`; RE.pref_equity: `PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount` , `PreferredStockValueOutstanding` | PNC: latest year from the extraction store (flagged) |
| FIN-023 | Goodwill | — | Absent = 0 (C5) |
| FIN-024 | Intangibles | G.intangibles: `FiniteLivedIntangibleAssetsNet`; BK.intangibles: `FiniteLivedIntangibleAssetsNet`; IN.intangibles: `FiniteLivedIntangibleAssetsNet`; RE.intangibles_net: `FiniteLivedIntangibleAssetsNet` | Absent = 0 (C5) |
| FIN-030 | Investment gains | IN.gains_realized: `GainLossOnInvestments` , `DebtAndEquitySecuritiesGainLoss`; BK.securities_gain_loss: `DebtSecuritiesAvailableForSaleRealizedGainLoss` , `AvailableForSaleSecuritiesGainLossIncludingOtherThanTemporaryImpairment` , `MarketableSecuritiesRealizedGainLoss` , `GainLossOnSaleOfSecuritiesNet` , `DebtAndEquitySecuritiesGainLoss` , `GainLossOnSaleOfAvailableForSaleSecuritiesNet` , `GainLossOnInvestments` | Insurance: realized + fair-value investment gains in profit or loss; non-recurring gains also include FIN-031 |
| FIN-032 | Goodwill impairment | BK.goodwill_impairment: `GoodwillAndIntangibleAssetImpairment` , `GoodwillImpairmentLossNetOfTax`; IN.goodwill_impairment: `GoodwillAndIntangibleAssetImpairment`; G.impairments: `AssetImpairmentCharges` , `GoodwillAndIntangibleAssetImpairment` | Positive number = loss; added back in insurance normalized operating profit (C.B3.4-INS) and in BANK V5 |
| FIN-033 | AOCI by component | — | Components read from the equity-statement members of the inline XBRL and classified: AFS, discount rate and own credit removed; FX, pension and hedges kept |
| FIN-040 | Rental revenue | RE.rental_revenue: `LeaseIncome` | Company extension elements (PLD `RentalRevenue`, BXP `RentalRevenueTotal`); PSA from the extracted income-statement line |
| FIN-041 | Other property revenue | — | No standard tag; PLD extension `OtherRealEstateRevenue`; otherwise extraction |
| FIN-042 | Property operating expenses | RE.prop_opex: `CostOfOtherPropertyOperatingExpense`; RE.re_tax: `RealEstateTaxesAndInsurance` | Components per company (FIN-176); EQIX = total revenue − cost of revenue (proxy, flagged); PSA from the extracted line |
| FIN-045 | Growth capital | RE.acq_real_estate: `PaymentsToAcquireCommercialRealEstate` , `PaymentsToAcquireOtherRealEstate` | Net growth capital = acquisitions + development − disposal proceeds (t−4 … t−1) |
| FIN-046 | Dispositions | RE.sale_proceeds: `ProceedsFromSaleOfProductiveAssets` | Gross disposals over t−4 … t for the 10% test |
| FIN-047 | Gross real estate at cost | RE.re_gross: `RealEstateInvestmentPropertyAtCost`; RE.re_net: `PropertyPlantAndEquipmentNet` | Materiality base for the NOI_PROXY when there is no economic value (RE22) |
| FIN-050 | Interest expense | G.interest_expense: `InterestExpenseNonoperating` , `InterestExpenseDebt` , `InterestExpenseLongTermDebt` , `InterestAndDebtExpense`; IN.interest_expense: `InterestExpenseDebt` , `InterestExpenseOperating` , `InterestExpenseNonoperating` , `InterestExpenseLongTermDebt` , `InterestExpenseSubordinatedNotesAndDebentures`; RE.interest_expense: `InterestExpenseDebt` , `InterestExpenseNonoperating` , `InterestExpenseOperating` , `InterestExpenseBorrowings`; RE.interest_capitalized: `InterestPaidCapitalized` , `InterestCostsCapitalizedAdjustment` | — |
| FIN-051 | Market capitalization | — | Used in the WACC proxy |
| FIN-060 | Revenue | G.revenue: `RevenueFromContractWithCustomerExcludingAssessedTax` , `RevenueFromContractWithCustomerIncludingAssessedTax` , `SalesRevenueNet` , `SalesRevenueGoodsNet` , `SalesRevenueServicesNet`; RE.total_revenue: `RevenueFromContractWithCustomerExcludingAssessedTax` , `RevenueFromContractWithCustomerIncludingAssessedTax`; IN.premiums: `PremiumsEarnedNetPropertyAndCasualty` | Bank revenue = net interest income + noninterest income; insurance operating revenue = total revenue − realized gains (computed) |
| FIN-061 | Cost of revenue / gross profit | G.cost_of_revenue: `CostOfGoodsAndServicesSold` | Derived: gross profit = revenue − cost of revenue; cost from goods + services components only when both exist; claims expense added (C4, C13) |
| FIN-062 | Diluted EPS | G.eps: `EarningsPerShareBasicAndDiluted`; IN.eps: `EarningsPerShareBasicAndDiluted` | Split-adjusted with the price provider's split history |
| FIN-070 | Normalized FFO | — | Full definition: D.5a |
| FIN-080 | CFO | G.cfo: `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` | — |
| FIN-081 | Capex | G.capex: `PaymentsToAcquireProductiveAssets` , `PaymentsForCapitalImprovements` , `PaymentsToAcquireOtherPropertyPlantAndEquipment` | Inline-XBRL fallback `PaymentsForProceedsFromPropertyPlantAndEquipment`. Excludes acquisitions |
| FIN-082 | D&A | G.da: `DepreciationAmortizationAndAccretionNet` , `DepreciationAndAmortization` , `DepreciationAmortizationAndOther`; RE.da_total: `DepreciationDepletionAndAmortization` , `DepreciationAmortizationAndAccretionNet` , `Depreciation` , `OtherDepreciationAndAmortization` | Selection per C9: the largest total tag; replaced by the components (FIN-166) when no total exists or the total is below 50% of their sum |
| FIN-083 | Amortization of acquired intangibles | G.acq_amort: `FiniteLivedIntangibleAssetsAmortizationExpense` | Absent = total D&A used, flagged |
| FIN-084 | SBC | G.sbc: `AllocatedShareBasedCompensationExpense`; RE.sbc: `AllocatedShareBasedCompensationExpense` | Three states: found / reported none (no SBC tag in any year, cash flow retrieved) / not found |
| FIN-085 | Current assets | — | Customer funds removed (C3) |
| FIN-086 | Current liabilities | — | Customer funds removed (C3); TECH: deferred revenue at cost (C11) |
| FIN-087 | Dividends paid | G.dividends: `PaymentsOfDividends` , `PaymentsOfOrdinaryDividends`; BK.dividends: `PaymentsOfOrdinaryDividends` , `PaymentsOfDividends`; IN.dividends: `PaymentsOfDividends` , `PaymentsOfOrdinaryDividends`; RE.dividends: `PaymentsOfDividends` , `PaymentsOfOrdinaryDividends` , `DividendsCommonStock` | Absent = 0 (C5). SPG / FRT / PSA extension elements |
| FIN-088 | Buybacks | G.buybacks: `PaymentsForRepurchaseOfEquity`; BK.buybacks: `PaymentsForRepurchaseOfEquity`; IN.buybacks: `PaymentsForRepurchaseOfEquity` | Absent = 0 (C5) |
| FIN-089 | Acquisitions | G.acquisitions: `PaymentsToAcquireBusinessesGross` , `PaymentsToAcquireBusinessesAndInterestInAffiliates`; BK.acquisitions: `PaymentsToAcquireBusinessesGross`; IN.acquisitions: `PaymentsToAcquireBusinessesGross` | C6: goodwill acquired in the year (FIN-160) as a lower-bound proxy (flagged) |
| FIN-090 | Average share price | — | Fallback: static price file |
| FIN-091 | Period-end shares | — | Cover-page count (FIN-163) when the balance-sheet tag is missing; scale guard C14 (incl. ×1,000,000 below 100,000) |
| FIN-092 | Weighted diluted shares | G.shares: `WeightedAverageNumberOfSharesOutstandingBasicAndDiluted` | RE28: SPG shares + OP units from the extraction store |
| FIN-093 | Deferred revenue, current | G.deferred_rev_current: `DeferredRevenueCurrent` | — |
| FIN-100 | Provision for credit losses | BK.provision: `ProvisionForLoanLossesExpensed` , `ProvisionForLoanAndLeaseLosses` | — |
| FIN-101 | Loans | BK.loans: `FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossFeeAndLoanInProcess` , `NotesReceivableGross` , `LoansAndLeasesReceivableNetOfDeferredIncome` , `LoansAndLeasesReceivableGrossCarryingAmount` | Latest year may come from the extraction store or the loan-category sum |
| FIN-103 | NCO | BK._nco_net: `FinancingReceivableAllowanceForCreditLossWriteoffAfterRecovery` , `AllowanceForLoanAndLeaseLossesWriteoffsNet`; BK._wo_gross: `FinancingReceivableAllowanceForCreditLossesWriteOffs` , `AllowanceForLoanAndLeaseLossesWriteOffs`; BK._recoveries: `FinancingReceivableAllowanceForCreditLossesRecovery` | NCO = net write-off tag, else gross write-offs − recoveries; latest year may come from the extraction store. FR Y-9C history not yet implemented (H-13) |
| FIN-104 | ACL | BK.acl: `FinancingReceivableAllowanceForCreditLosses` , `LoansAndLeasesReceivableAllowance` | Latest year may come from the extraction store |
| FIN-105 | Nonaccrual loans | BK.nonaccrual: `FinancingReceivableRecordedInvestmentNonaccrualStatus` | Extracted nonaccrual loans take precedence; 90+ days past due is display only (D11) |
| FIN-106 | CET1 and required CET1 | — | V9 fallback |
| FIN-107 | LCR | — | Measurement type derived from the note (V10) |
| FIN-108 | DPS | G.dps: `CommonStockDividendsPerShareCashPaid`; BK.dps: `CommonStockDividendsPerShareCashPaid`; IN.dps: `CommonStockDividendsPerShareCashPaid`; RE.dps: `CommonStockDividendsPerShareCashPaid` | Fallback: dividends paid / weighted basic shares (C8, flagged); RE: replaced when the tag deviates from that ratio by more than 3x |
| FIN-110 | Insurance revenue | IN.premiums: `PremiumsEarnedNetPropertyAndCasualty` | Policy fees = `InsuranceCommissionsAndFees` |
| FIN-112 | Non-claims underwriting expenses | — | Not extracted as separate lines: the underwriting result uses the identity insurance revenue − (`BenefitsLossesAndExpenses` − interest on debt − interest credited) − MRB remeasurement. FIN-113 merged here (2026-10-17) |
| FIN-114 | Interest credited / accretion | IN.interest_credited: `InterestCreditedToPolicyOwnerAccount` | Accretion on future policy benefits (LDTI roll-forward) read from the inline XBRL (Q1) |
| FIN-116 | Float components | IN.reins_unpaid: `ReinsuranceRecoverableForUnpaidClaimsAndClaimsAdjustments` , `ReinsuranceRecoverables`; IN.fpb: `LiabilityForFuturePolicyBenefitAfterReinsurance`; IN.pab: `PolicyholderFunds` | Float = claims (net, else gross − recoverable) + future policy benefits + policyholder account balances + (unearned − prepaid reinsurance); + discount-rate AOCI add-back |
| FIN-118 | Prior-period development | IN.prior_year_dev: `SupplementalInformationForPropertyCasualtyInsuranceUnderwritersPriorYearClaimsAndClaimsAdjustmentExpense` , `SecSchedule1218SupplementalInformationPropertyCasualtyInsuranceUnderwritersPriorYearClaimAndClaimAdjustmentExpense` | Extraction store when untagged (adverse prior-year development; adverse LDTI remeasurement) |
| FIN-119 | Government yield (annual) | — | No Israel series yet (H-15) |
| FIN-120 | Straight-line rent | RE.straight_line: `StraightLineRentAdjustments` | PLD extension element; company AFFO line from the extraction store (incl. quarterly rows); data centers / residential / storage default 0 (flagged) |
| FIN-121 | Maintenance capex (RE) | — | PSA extension element; otherwise the extraction store (quarterly rows summed) |
| FIN-122 | TI/LC | RE.ti_lc_total: `PaymentsForLeasingCostsCommissionsAndTenantImprovements` | Income-preserving amount from the extraction store |
| FIN-123 | EBITDAre components | RE.gains_sale: `GainsLossesOnSalesOfInvestmentRealEstate` , `GainLossOnSaleOfPropertyPlantEquipment` , `GainLossOnDispositionOfAssets` , `GainLossOnDispositionOfAssets1` , `GainLossOnSaleOfOtherAssets`; RE.impairment: `AssetImpairmentCharges` , `ImpairmentOfLongLivedAssetsHeldForUse`; RE.da_total: `DepreciationDepletionAndAmortization` , `DepreciationAmortizationAndAccretionNet` , `Depreciation` , `OtherDepreciationAndAmortization`; RE.interest_expense: `InterestExpenseDebt` , `InterestExpenseNonoperating` , `InterestExpenseOperating` , `InterestExpenseBorrowings` | JV adjustments not yet included (H-21) |
| FIN-125 | Economic property value | — | No XBRL concept for US GAAP filers |
| FIN-130 | FX rates | — | Required, not yet implemented: revenue is assumed to be USD (H-11) |
| FIN-131 | First annual report date | — | Predecessor history not yet handled (H-10) |
| FIN-132 | Receivables | G.receivables: `ReceivablesNetCurrent` , `AccountsAndOtherReceivablesNetCurrent` , `PremiumsReceivableAtCarryingValue` , `PremiumsAndOtherReceivablesNet` | Insurer premium-receivable tags added (2026-10-13) |
| FIN-133 | Short-term borrowings | BK.st_borrow: `OtherShortTermBorrowings` | — |
| FIN-136 | Investment portfolio by category | — | Balance-sheet categories from the extraction store: cash, short-term, fixed maturities, equity, illiquid loans, real estate, other invested, total investments, investment-grade fixed income and its share |
| FIN-137 | Committed undrawn facilities | — | The standard concept `LineOfCreditFacilityRemainingBorrowingCapacity` is not used |
| FIN-138 | Debt maturities | — | The extraction store fills years without the tag |
| FIN-145 | Occupancy / utilization | — | Metric by asset type (table A) |
| PRC-001 | Share price | — | No refresh or freshness check yet (H-12) |
| FIN-151 | 10-year EPS history | G.eps: `EarningsPerShareBasicAndDiluted` | Up to 10 fiscal years from the annual companyfacts table |
| FIN-153 | NCI and OP units | RE.nci_redeemable: `TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests` , `RedeemableNoncontrollingInterestEquityRedemptionValue` | Extraction: OP-unit count and book value, whether diluted shares include OP units, share-basis override, weighted partnership units |

---

## Part F — ETL requirements

Implementation status (verification of 2026-10-15): E3, E6 and E12 implemented; the others in Part H.

| # | Requirement | Origin |
|---|---|---|
| E1 | **Prices refreshed at least daily**, with a freshness check: a price that did not update (delisting, merger, provider error) is flagged and the price score is not computed until reviewed | ETL issues (2026-10-14) |
| E2 | **Listed-entity check:** ticker ↔ filing entity (CIK) mapping; after a merger or reorganization the price score is "cannot be priced" until the successor reports its own financials | C16 (EQR → VMRK) |
| E3 | **Share-count scale guard:** values about 1,000× off their neighbours are rescaled and flagged; larger mismatches are missing | C14 (WRB) |
| E4 | **Government yields:** (a) annual average 10-year yield per currency and year (insurance cost of float; constants table, yearly); (b) latest monthly average 10-year yield per currency (RP2 cap rate; US FRED GS10, Israel Bank of Israel), refreshed monthly | INSURANCE; RP2 |
| E5 | **XBRL tag-continuity mapping:** one economic item across tag changes between years (insurance float components; interest-expense tags; D&A tags) | INSURANCE limitations; RE Q3 |
| E6 | **Company-extension and inline-XBRL tags** (module `sec_ixbrl`), e.g., Cigna capex, PLD straight-line element | Managed care; RE |
| E7 | **Quarterly XBRL** where an annual item is disclosed only quarterly (sum of four quarters, e.g., BXP FAD items) | RE round 3 |
| E8 | **FR Y-9C** charge-off history for US bank holding companies when XBRL history is short, with entity and definition checks | D13 |
| E9 | **Extraction store:** every extracted value with document, section, exact quote, verification flag, basis (group vs company share), and admin approval; reported figures (FFO, AFFO, EBITDAre, LCR, solvency) kept as reconciliation inputs | UI7; RE Q5 |
| E10 | **Profile recomputation** with every annual report; two-year stability; S3a borderline list | S3 |
| E11 | **Reconciliation flags:** computed vs reported FFO >10% (RE17); OE vs AFFO less SBC >15% (Q6); RE29b 5 pp control; insurer float components missing in a year (Q8a / Q10) | Sector files |
| E12 | Calibration data (e.g., FRED CORALACBS) is used once to justify thresholds and is not stored or scored | K1 |

---

## Part G — Decision log

| ID | Date | Decision (short) | Where in force |
|---|---|---|---|
| C2 | 2026-10-11 | Invested capital definition | B3.4-STD |
| Q8e | 2026-10-13 | Non-positive adjusted equity → ROE undefined; worst year = 0 | B3.4-INS |
| RE18 / RE22 / RE23 | 2026-10-14 | Proxy method, materiality on gross cost, weights 4 / 6 / 5 | B3.4-RE |
| RE31 | 2026-10-15 | Fixed 2.5% term; renamed after the second review | B3.4-RE |
| C4 / C13 | 2026-10-11 / 2026-10-14 | Gross profit derivation; claims expense in cost of revenue | B3.2-STD |
| D1 / D2 | 2026-10-12 | PPNR pretax limitation; share-count change years stay in | B3.5-BANK |
| D7 / D9–D12 | 2026-10-12 / 13 | Loan growth on valid years; LCR exemption, capital buffer by approach, nonaccrual only, LCR not found = missing | B3.6-BANK, B3.8-BANK |
| V9–V11 | 2026-10-13 | CET1 requirement fallback; LCR measurement type; LCR exemption by regulatory category | B3.6-BANK |
| Q1 / Q3 / Q4 / Q6–Q11 | 2026-10-13 | Insurance finance expense mapping; regulatory capital comparability; float rules; cost of float vs government yield | B3.5-INS, B3.6-INS |
| RE20 / RE20a / RE24 / RE28 | 2026-10-14 / 15 | OE components by asset type; straight-line sign; single basis | B3.5-RE |
| D3 / D4 / D15 | 2026-10-12 / 13 | Loan concentration on mapped loans; AI fallback; repo in wholesale funding | G3.2-BANK, G3.3-BANK |
| I6 / RE26 | 2026-10-13 / 14 | ALM as a flag; stress test scope | G3.2-INS, G3.3-RE |
| D5 / D6 | 2026-10-12 | Negative-to-positive TBVPS; allowance erosion in loss years | G3.7-BANK, G3.8-BANK |
| I8 / Q8b / Q8c | 2026-10-13 | HHI removed; missing credit table = missing; Σ net income ≤ 0 = 0 | G3.7-INS, G3.8-INS |
| RE27 | 2026-10-14 | Graham 3.8.2 validity | G3.8-RE |
| G1 / G2 / G3-C | 2026-10-14 | Base roll-forward only when latest ≥ median; Graham Number on 7–10-year EPS; unlevered owner earnings, debt subtracted once | D.1, D.2 |
| C15 / C16 / X1 | 2026-10-14 / 15 | Value ≤ 0; same listed entity; Graham quality gate unified | D.0 |
| V1–V8 | 2026-10-12 / 13 | Bank excess-returns model, Graham Number on TBVPS, loss-year classification | D.3 |
| P1–P5 | 2026-10-13 | Insurance excess-returns model, Graham Number on operating EPS, gate on insurance revenue | D.4 |
| RP1–RP5a, RE29–RE31 | 2026-10-14 / 15 | Real-estate DCF, NAV, guards, normalization | D.5 |
| D8 | 2026-10-12 | BANK pretax margin replaces operating margin | B3.2-BANK |
| CL1 | 2026-10-17 | Rulebook closed and made the source of truth; the governing files are superseded (S-06) | Header |
| C17 | 2026-10-17 | Partial-window scaling of "years of 5" / "transitions of 4" counts | A.2 |
| S-07 | 2026-10-17 | Dilution basis: C7 (period-end shares) governs the general-model rows that said diluted shares | A.2, B3.7, G3.8 |
| CL2 | 2026-10-17 | Engine edge rules adopted as written: share-count fallback; Σ FCF ≤ 0 in Buffett 3.7.3 / 3.7.4; EBITDA ≤ 0 in Buffett 3.8.4; missing interest and previous-5 median ≤ 0 in the Buffett DCF; Graham 3.6.3 / 3.8.4 turnarounds and the Tech multiple; EBIT derivation; D&A selection and the ×1,000,000 share guard; payout 100% when Σ net income ≤ 0; CRE test skipped without total capital; CAL basis | A.2, C cards, D.1–D.4, Part E |
| CL3 | 2026-10-17 | Insurance normalized operating profit: one-off losses (goodwill impairment) added back, as BANK V5 (the code subtracts them: H-02) | B3.4-INS |
| CL4 | 2026-10-17 | RP1a: coverage that cannot be computed = debt data missing; quality coverage below 80% removes only the buy price (M7) | D.5 |
| CL5 | 2026-10-17 | Real-estate Buffett 3.7.3: denominator always normalized FFO | B3.7 variants |
| CL6 | 2026-10-17 | Real-estate stage-1 growth: previous-5 median ≤ 0 → 0%, as the general model | D.5 RP1 |
| CL7 | 2026-10-17 | RP2 cap rate: annual-yield fallback flagged; no yield → cannot be valued (M6) | D.5 RP2 |
| CL8 | 2026-10-17 | BANK / INSURANCE value ≤ 0 → price score 0, as C15 | D.3, D.4 |
| CL9 | 2026-10-17 | Real-estate Buffett 3.1 keeps the five general AI questions | B3.1 |
| CL10 | 2026-10-17 | Part E: engine mapping replaces the indicative concepts; FIN-112 / FIN-113 merged; FIN-160 to FIN-185 added; FIN-130 and TXT-001 to TXT-005 kept as required | Part E |
| CL13 | 2026-10-20 | FIN-186 net investment income added: read by the INSURANCE engine but missing from the dictionary (found in code stage K2) | Part E |
| CL12 | 2026-10-19 | C5 extended to preferred stock and preferred dividends (absent line in a retrieved statement = 0, flagged); found in the DB stage: without it ROTCE of a bank without preferred stock would be missing | A.2 |
| CL11 | 2026-10-17 | Omissions added from the sources: RE20 tenant concentration N/A, FFO / normalized FFO definition, catastrophe flag, RE21 basis, Graham quality labels, Q10 / I18 | A.6, B3.5-INS, G3.7-RE, D.5a |

---

## Part H — Known limitations and items to implement

The book governs. The items below are where the current engine, data or ETL does not yet do what the book says (verification of 2026-10-15). They are implemented in the database stage (stage 2) and the code stage (stage 3). None of them changes a rule.

### H.1 Code alignment (stage 3)

| # | Item | Book rule | Code today | Ref. |
|---|---|---|---|---|
| H-01 | Graham price score, BANK / INSURANCE | Shown, labelled; buy price "not suitable" below Graham quality 55 (A.5) | Hidden below 55 | C-11, C-12 |
| H-02 | Insurance normalized operating profit | Goodwill impairment added back (C.B3.4-INS) | Subtracted (a 1.0bn impairment lowers the profit by 1.0bn); flows into operating ROE, margin, operating EPS and the Graham Number. Needs a test with impairment ≠ 0 | C-16 |
| H-03 | Real-estate leverage guard | Quality coverage below 80% removes only the buy price (RP1a, M7) | Also blocks the price score | C-18 |
| H-04 | Real-estate Buffett 3.7.3 | Σ corporate acquisitions / Σ normalized FFO | Divides by Σ OE when OE exists in all 5 years | C-19 |
| H-05 | Real-estate stage-1 growth | Previous-5 median ≤ 0 → 0% (RP1) | Falls back to R14 smoothed growth | C-24 |
| H-06 | Real-estate cap rate without any yield | "Cannot be valued" (RP2, M6) | 6% floor | C-23 |
| H-07 | BANK / INSURANCE value ≤ 0 | Price score 0 (C15, D.3, D.4) | Price score "not applicable" | C-14 |
| H-08 | Real-estate Buffett 3.1 AI questions | The five general questions | Different placeholder names (AI not run yet) | C-26 |
| H-09 | **Profile router (most important)** | Part B: STANDARD / TECH_ASSET_LIGHT rule 5b, UNSUPPORTED exclusions (mortgage REITs, BDCs), two-year stability, manual override (P1) | BANK and INCOME_REAL_ESTATE tests exist; INSURANCE test in a script; STANDARD / TECH / UNSUPPORTED chosen by company lists in the runners | C-27, E10 |
| H-10 | Predecessor years after a spin-off or merger | Count in Graham 3.1 #2 | Not checked (flagged) | C-03 |
| H-11 | Revenue in USD (R15) | Graham 3.1 #1 at the year's average rate (FIN-130) | Revenue assumed USD — needed for non-USD filers (Israel) | C-02 |

### H.2 ETL and data (stages 2–3)

| # | Requirement | Status | What is missing |
|---|---|---|---|
| H-12 | E1 daily prices and freshness | Not implemented | Daily refresh, staleness test and flag, no price score until reviewed |
| H-13 | E8 FR Y-9C charge-off history | Not implemented | Loader, entity and definition checks |
| H-14 | E2 listed-entity check | Partial | Automatic ticker ↔ CIK comparison (today entered by hand) |
| H-15 | E4 government yields | Partial | Israel (Bank of Israel) series; scheduled monthly refresh |
| H-16 | E5 tag continuity | Partial | Explicit continuity table (insurance float components across tag changes) |
| H-17 | E7 quarterly XBRL | Partial | Quarters from quarterly XBRL facts, not only the extraction store |
| H-18 | E9 extraction store | Partial | Database table; basis field (group vs company share); admin-approval field |
| H-19 | E11 reconciliation flags | Partial | Q6 15% test inside the engine (today only in the runner scripts) |
| H-20 | FIN-130, TXT-001 to TXT-005 | Not implemented | FX table; text retrieval for the AI questions |

### H.3 Real estate outside the US (with the Israel stage)

| # | Item | Ref. |
|---|---|---|
| H-21 | IFRS FFO and EBITDAre; EBITDAre JV adjustments and proportionate JV debt; WACC tax shield for taxable companies (Kd × (1 − 25%)); stabilized NOI with the non-stabilized share separated; reported IFRS fair value on display | C-20, C-21, C-22, C-25 |

### H.4 Extraction gaps (not rules)

| # | Item |
|---|---|
| H-22 | Towers, Graham 3.7: 3.7.1 is N/A and 3.7.2 is not extracted, so the criterion has 2 of 6 points and is invalid (M2). Fix: extract the towers' organic revenue growth |

---

## Part V — Verification result (closed 2026-10-17)

The book was verified on 2026-10-15 against the source files (every card) and the engine code (Claude Code report `rulebook_verification_2026-10-15.md`). No numeric difference was found between the book and the source files. Every gap was decided on 2026-10-17 (Part G) and is now either in the book or in Part H.

| Group | Result | Where |
|---|---|---|
| S-01 to S-09 (source ↔ book) | Omissions added (S-01 G3.7-RE; S-02 D.5a and FIN-070; S-03 and S-08 B3.5-INS; S-04 D.5a and FIN-044 / FIN-145; S-05 A.6; S-09 FIN-160, FIN-170); S-06 sources superseded; S-07 decided by C7 | Header, A.6, C cards, D.5a, Part E, Part G |
| C-01 to C-27 (code ↔ book) | C-04 → C17; C-01, C-05 to C-10, C-13, C-15, C-17 written into the cards and the dictionary; C-11, C-12, C-14, C-16, C-18, C-19, C-23, C-24, C-26 decided for the book and listed for the code; C-02, C-03, C-20 to C-22, C-25, C-27 are implementation items | A.2, C, D, E, H.1–H.3 |
| V-01 | Buffett 3.3 RE mapping confirmed (revenue = total revenue) | C.B3.3 variants |
| V-02 | Engine mapping in Part E; 26 items added; FIN-112 / FIN-113 merged | Part E |
| V-03 | FCF = CFO − capex; SBC **not** deducted in the quality cards (owner earnings and Graham Tech deduct it) | Confirmed, no change |
| V-04 | INSURANCE Buffett 3.8.3: ≤0% = 0, ≥10% = 3 | C.B3.8 variants |
| V-05 | RE 3.8.4 / 3.8.5 and BANK 3.8.5 confirmed | C.B3.8 variants |
| V-06 | RE Graham 3.4 / 3.6 mapping confirmed | C.G3.4-RE, C.G3.6-RE |
| V-07 | RE Graham 3.5.3: STANDARD thresholds kept (payouts 55%–81% of normalized FFO; no REIT scores 0) | C.G3.5 variants |
| V-08 | INSURANCE Graham 3.7.3 without the credit table = missing (Q8b), as the book | Confirmed, no change |
| V-09 | Graham 3.8.2 by period-end shares (C7); fallback written into C7 | A.2 |
| V-10 | Normalization after N/A (M1) matches the engine in every case; towers G3.7 → H-22 | Confirmed |
| V-11 | ETL: 3 implemented, 6 partial, 3 not implemented | Part F, H.2 |
