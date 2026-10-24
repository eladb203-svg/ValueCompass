---
title: "ValueCompass — AI Skills: Classification, Extraction, Content, Search (B1–B15, C1, D1–D2, S1–S2)"
subtitle: "2026-10-23_15-00 · prompts in English · approved"
---

# AI Skills: Classification, Extraction, Content

**עברית — מה במסמך:** שאר הסקילים של ק5, באותו מבנה של סקילי הניקוד (A1–A14): תבנית משותפת לכל סוג + בלוק נתונים לכל סקיל. **C1** — סיווג ענף (#15). **B1–B15** — חילוץ נתונים (#16–#29, כולל החילוץ הכללי). **D1** — רקע על החברה (#30). **D2** — ניתוח תוצאות (#31). **עדכון 23.10.2026:** נוספו סעיף 3.3 — ניסוח אחיד ויציב לניתוח (D2): נכתב פעם אחת לכל ריצה; רק ערכים שלא תלויים במחיר היומי; מילון מונחים, מילות חוזק ומיקום מול עמיתים מחושבים בקוד, תבניות משפט, דוגמה, ושורת "מה השתנה" — וסעיף 5 — חיפוש חכם (S1, ‏#32) וזיהוי עמודות בקובץ ברוקר (S2, ‏#33), עם מפתח Gemini נפרד. שמות הנתונים (`item_key`) הם השמות במילון ב-DB; ההגדרות — מחלק ה בספר הכללים 2026-10-20_23-21. כללי האישור — לפי ההחלטה מ-21.10.2026.

**Source:** Rulebook 2026-10-20_23-21 (Parts B.1, C, D, E); AI Layer Specification 2026-10-20_23-23; Scoring skills 2026-10-21_12-17.

## 1. Classification — C1 (#15)

### 1.1 Template
```
SYSTEM
You assist ValueCompass. Choose the ONE industry, from the closed list below, that best
describes the company's main business, using ONLY the annual-report text provided.
Rules: use only the text; quote 1–3 exact sentences that show the main business; if the
text does not allow a choice, return industry = null and insufficient_evidence = true.
Return ONLY the JSON object under OUTPUT.

INDUSTRIES (ValueCompass, Rulebook Part B.1 — choose exactly one name as written)
{industry_list_with_definitions}

COMPANY: {company_name} ({ticker}) · FISCAL YEAR: {fiscal_year}
SIC: {sic} {sic_description} · PROVIDER INDUSTRY: {provider_industry}
TEXT (TXT-001 Business, filing {accession}):
<<<
{section_text}
>>>

OUTPUT
{"skill_id": "CLS-1", "version": {version}, "industry": "<name>" | null,
 "insufficient_evidence": true | false, "reasoning": "<at most 3 sentences>",
 "quotes": [{"text": "<exact quote>", "section": "TXT-001"}]}
```

### 1.2 Block
```yaml
skill_id: CLS-1
version: 1
when: only when tiers 1–2 of Part B.1 did not decide (ambiguous SIC, or provider industry marked tier3)
industry_definitions:   # sent with the list; the two that most need a boundary
  Internet platforms and advertising: search, social networks, online marketplaces that connect buyers and sellers; NOT online retail that holds its own inventory and logistics (that is Other)
  Payments: card networks, payment processing and digital wallets
decision_by_code: agrees with the provider industry → decided; disagrees → admin approval; until then STANDARD with "classification pending"
approval: only on disagreement (always reviewed then)
```
SIC and provider industry are shown to the AI as context only; the answer must rest on the quoted text.

## 2. Extraction — B1–B15 (#16–#29)

### 2.1 Template
```
SYSTEM
You assist ValueCompass. Extract the requested figures from the annual-report text below.
You do not compute, convert, estimate or fill gaps.
Rules:
1. Report each figure exactly as stated in the text, with its unit and scale
   (e.g., "in millions"). Do not convert units or currencies.
2. Every figure must come with a quote copied character for character that CONTAINS the figure.
3. If a figure is not disclosed, return value = null with value_state = "not_disclosed".
   If the text says it does not apply, value_state = "NA". Never guess.
4. Report the period the figure refers to (fiscal year end, or "Q4 average" etc. as stated).
5. When the text states the basis (consolidated / company share / group / a regulatory
   approach), report it in "basis".
6. Return ONLY the JSON object under OUTPUT.

TASK ({skill_id}, version {version})
{task}

ITEMS
{items_table}          # item_key — definition — expected unit — notes

COMPANY: {company_name} ({ticker}) · FISCAL YEAR: {fiscal_year} · PROFILE: {profile}
TEXT ({sections}, filing {accession}):
<<<
{section_text}
>>>

OUTPUT
{"skill_id": "{skill_id}", "version": {version}, "items": [
  {"item_key": "<key>", "period": "<as stated>", "value": <number | null>,
   "unit": "USD" | "percent" | "count" | "ratio" | "sq_ft" | "MW",
   "scale": 1 | 1000 | 1000000 | 1000000000, "basis": "<as stated or null>",
   "value_state": "value" | "NA" | "not_disclosed",
   "quote": {"text": "<exact quote containing the figure>", "section": "<section>"}} ]}
```
**Code checks (2026-10-20_23-23 §4.4):** quote found verbatim; the number appears in the quote after scale; unit allowed; period matches the fiscal year. Then the control and the approval rule of each block.

### 2.2 Blocks

#### B1 — Bank capital and liquidity (#16)
```yaml
skill_id: EXT-BANK-CAP
version: 1
profile: BANK
task: Extract the bank's regulatory capital and liquidity figures for the fiscal year end.
sections: [TXT-004, NOTE:regulatory_capital, LCR_disclosure]
items:
  - cet1_ratio_standardized / cet1_ratio_advanced: CET1 capital ratio under each approach reported (percent)
  - cet1_required_standardized / cet1_required_advanced: the CET1 requirement incl. buffers, per approach (percent) (V9)
  - total_capital_standardized / total_capital_advanced: total regulatory capital (USD) (FIN-141)
  - rwa_standardized / rwa_advanced: risk-weighted assets (USD) (FIN-144)
  - lcr_q4_average: liquidity coverage ratio, Q4 average; basis = measurement type as stated (V10); NA when exempt (V11)
  - scb, gsib_surcharge: stress capital buffer and G-SIB surcharge (percent) (FIN-171)
  - uninsured_deposits: (USD) display only (FIN-170)
control: CET1 ratio ≈ CET1 capital / RWA when both are disclosed (within 0.2 pp)
approval: automatic
```

#### B2 — Bank loan breakdown (#17)
```yaml
skill_id: EXT-BANK-LOANS
version: 1
profile: BANK
task: List the loan portfolio lines exactly as the bank reports them, with amounts, at fiscal year end.
sections: [NOTE:loans]
items:
  - loan_line: one row per reported line (name as stated, amount in USD); code maps lines to the 5 categories (residential mortgage; CRE and construction; C&I; consumer; other)
control: sum of lines = total loans reported (within 1%)
approval: automatic
```

#### B3 — Insurance capital and reserves (#18)
```yaml
skill_id: EXT-INS-CAP
version: 1
profile: INSURANCE
task: Extract the insurer's regulatory capital ratio and prior-year reserve development.
sections: [TXT-004, NOTE:statutory_capital, NOTE:reserve_rollforward]
items:
  - reg_capital_ratio: the ratio as reported (percent); basis = regime and level (e.g., "RBC % of ACL", "CAL", "SCR", "SMR"), entity (group / lead subsidiary), and period (Q3 rules: a stated floor is reported as the floor, flagged)
  - prior_year_dev: (un)favorable prior-period reserve development (USD; sign as stated)
  - ldti_remeasurement: adverse LDTI remeasurement (USD), when untagged
control: none beyond the checks
approval: automatic
```

#### B4 — Insurance investments, catastrophes, ALM (#19)
```yaml
skill_id: EXT-INS-INV
version: 1
profile: INSURANCE
task: Extract the investment portfolio by category and credit quality, catastrophe losses and whether ALM is disclosed.
sections: [NOTE:investments, NOTE:credit_quality, TXT-004]
items:
  - inv_cash, inv_short_term, inv_fixed_maturities, inv_equity, inv_illiquid_loans, inv_real_estate, inv_other: (USD)
  - inv_ig_fixed: investment-grade fixed income (USD) — BBB− / Baa3 or better, NAIC 1–2; unrated is NOT investment grade
  - inv_ig_share: investment-grade share of fixed income (percent), when stated instead of an amount
  - cat_loss_latest: catastrophe losses of the year (USD)
  - alm_disclosed: 1 when asset-liability (duration) matching is disclosed, else 0
control: categories sum to total investments (within 2%)
approval: automatic
```

#### B5 — Real-estate operating data (#20)
```yaml
skill_id: EXT-RE-OPS
version: 1
profile: INCOME_REAL_ESTATE
task: Extract occupancy, largest tenant, same-property NOI growth and new-investment yields.
sections: [TXT-001, TXT-004, supplemental]
items:
  - occupancy: the metric of Table A by asset type (percent; data centers: leased / available capacity); basis = the company's primary reported basis (RE21)
  - largest_tenant_share: largest independent tenant share of rent or NOI (percent); basis = rent or NOI
  - same_property_noi_growth: like-for-like NOI growth (percent); basis = the company's primary basis (RE21)
  - acquisition_yield, development_yield: stabilized yield (percent); acquisition_invested, development_invested: amounts (USD)
control: values within physical bounds (0–100%)
approval: automatic
```

#### B6 — Real-estate maintenance spending (#21)
```yaml
skill_id: EXT-RE-MAINT
version: 1
profile: INCOME_REAL_ESTATE
task: Extract recurring maintenance capital expenditure and income-preserving tenant improvements and leasing commissions, as the company defines them in its AFFO reconciliation.
sections: [AFFO_reconciliation, supplemental, NOTE:capex]
items:
  - maint_capex: recurring / maintenance capex (USD); towers: AFFO capital improvement + corporate capex (RE20a)
  - ti_lc: income-preserving TI and leasing commissions (USD); residential and self-storage: NA (RE20)
  - straight_line_rent_affo: straight-line rent adjustment as shown in the AFFO reconciliation (USD, sign as stated)
control: Q6 — OE per share vs (reported AFFO − SBC) per share, gap ≤ 15% (E11)
approval: automatic when Q6 passes; admin approval when Q6 is flagged
```

#### B7 — Real-estate property value (#22)
```yaml
skill_id: EXT-RE-VALUE
version: 1
profile: INCOME_REAL_ESTATE
task: Extract the disclosed fair value of investment property and the split between stabilized income property and development / land.
sections: [NOTE:fair_value, NOTE:real_estate, supplemental]
items:
  - fair_value_real_estate: economic property value (USD); basis REQUIRED (consolidated or company share; with or without joint ventures — RP2c)
  - stabilized_value, other_property_value: stabilized vs development / land (USD)
  - stabilized_noi: NOI of stabilized property (USD), when disclosed
control: basis stated in the quote, and fair value / gross real estate at cost within 0.5×–3×
approval: automatic when the control passes; admin approval otherwise
```

#### B8 — Real-estate liquidity (#23)
```yaml
skill_id: EXT-RE-LIQ
version: 1
profile: INCOME_REAL_ESTATE
task: Extract committed undrawn credit facilities and debt maturing in the next 12 and 24 months.
sections: [NOTE:debt, TXT-004 liquidity]
items:
  - committed_undrawn_facilities: committed AND available (undrawn) amount (USD) — not the total facility size
  - debt_maturity_year1, debt_maturity_year2: principal maturing within 12 / 13–24 months (USD)
control: RP1a 12-month coverage computed by code; if 0.8 ≤ coverage ≤ 1.25 the result is near the block threshold
approval: automatic outside 0.8–1.25; admin approval inside
```

#### B9 — Unencumbered NOI and assets (#24)
```yaml
skill_id: EXT-RE-UNENC
version: 1
profile: INCOME_REAL_ESTATE
task: Extract the share of NOI and of assets that is unencumbered (free of secured debt).
sections: [NOTE:debt, supplemental]
items:
  - unencumbered_noi_share, unencumbered_assets_share: (percent)
control: 0–100%
approval: automatic
```

#### B10 — NAV balance-sheet classification (#25)
```yaml
skill_id: EXT-RE-NAV
version: 1
profile: INCOME_REAL_ESTATE
task: Assign EVERY line of the balance sheet's asset side to one class of Rulebook RP2a. Report each line as stated, with its amount and the class.
sections: [balance_sheet, NOTE:real_estate]
classes:
  bsa_noi: already in the capitalized NOI → counted as 0 (real estate in place, acquired lease intangibles, straight-line rent receivable, deferred leasing costs, ground-lease right-of-use assets)
  bsa_carry: carrying value — development, construction in progress, land
  bsa_inre: carrying value — equity-method interests in real-estate joint ventures
  bsa_carryfin: carrying value — notes and loans receivable, financial investments
  bsa_wc: working capital — excluded (receivables, prepaid and other current assets; mixed lines that cannot be split)
  bsa_excl: excluded — cash (already in net debt), goodwill
  bsa_other: none of the above (unidentified)
output_per_line: line name as stated, amount (USD), class, quote
control: lines sum to total assets (within 0.5%); unidentified > 10% of total assets → no Graham price score (RP2a)
approval: ALWAYS (classification is interpretation; no external number to check against). Shown to the admin as a table of lines with the proposed class.
```

#### B11 — Operating-partnership units and single basis (#26)
```yaml
skill_id: EXT-RE-OPU
version: 1
profile: INCOME_REAL_ESTATE
task: Extract the operating-partnership (OP) units and the facts needed to put FFO, deductions and share count on one basis (RE28, RP2b).
sections: [NOTE:equity, NOTE:noncontrolling_interests, NOTE:EPS]
items:
  - op_units_count: OP units outstanding held by others (count)
  - op_units_book_value: carrying value of OP-unit noncontrolling interest (USD)
  - diluted_includes_op: 1 when diluted shares include OP units, else 0 (quote required)
  - partnership_units_weighted: weighted OP units (count), when stated
  - shares_basis_override: share basis stated by the company for per-share FFO (count), when it differs
  - inc_share_of_bplp: the company's share of the operating partnership's income (percent), when stated
control: none reliable
approval: ALWAYS (rare — only REITs with an operating partnership; directly moves value per share)
```

#### B12 — FFO normalization items (#27)
```yaml
skill_id: EXT-RE-FFO
version: 1
profile: INCOME_REAL_ESTATE
task: Extract the company's FFO reconciliation lines and the non-recurring items of RE30, each with the sign as it affects net income.
sections: [FFO_reconciliation, TXT-004, NOTE:gains, NOTE:impairments]
items:
  - recon_net_income, recon_re_da, recon_nci_jv, recon_gi_net: FFO reconciliation lines (USD, sign as shown)
  - reported_ffo, reported_core_ffo, reported_affo, reported_ebitdare: (USD); core FFO per share (USD/share) when stated
  - re29_re_sale_gains: gains / losses on sales of real estate incl. development property and land (RE29)
  - re29_nonre_impairments: impairments of non-real-estate assets and investments
  - re29a_nonre_inv: realized and unrealized results of non-real-estate investments (RE29a)
  - re29b_fx_net: unrealized FX remeasurement NET of the related hedging derivatives (RE29b); without a net line, the amount the company itself adds back
  - debt_extinguishment, transaction_costs: (USD, sign as stated) — RE30 item 5
note_to_ai: Report each amount as a gain (+) or loss (−) as it affects net income. Do not decide whether an item is already removed in the company's FFO — code does that.
control: E11 — computed FFO vs reported FFO gap ≤ 10%; RE29b 5 pp control
approval: automatic when both controls pass; admin approval when either is flagged
```

#### B13 — Profile-test inputs (#28)
```yaml
skill_id: EXT-PROFILE
version: 1
profile: any (router)
task: Extract the figures the profile router needs when they are not tagged.
sections: [balance_sheet, income_statement, NOTE:real_estate, NOTE:reserves]
items:
  - profile_total_assets, profile_property_value, profile_rental_revenue, profile_total_revenue: (USD) — real-estate test, every year in the window (RE11, RE15: property incl. acquired lease intangibles)
  - mortgage_loans_mbs: mortgage loans held + mortgage-backed securities (USD) (FIN-191)
  - insurance liability components when only in an extension tag: claims, future policy benefits, policyholder account balances, unearned premiums (USD)
control: the router test result's distance from its threshold
approval: automatic when the result is more than 5 pp from the threshold; admin approval inside the S3a band
```

#### B14 — General fallback extraction (#29)
```yaml
skill_id: EXT-GENERAL
version: 1
profile: any
when: code found no tag for a dictionary item in a year where the statement was retrieved, and the item is not covered by B1–B13
task: Extract ONE dictionary item for ONE fiscal year from the financial statements.
item: '{item_key} — {definition from Rulebook Part E} — {statement} — expected unit {unit}'
sections: [the statement named in the dictionary row, its notes]
control: compared with adjacent years — a value more than 3× or less than ⅓ of both neighbours is flagged
approval: automatic when the item feeds one sub-item and the control passes; admin approval when the item feeds value, buy price or profile, or when the control is flagged
```

#### B15 — Insurance-liability components (router) — folded into B13
Kept as a separate number in the skill list (#28) for traceability; implemented inside B13.

## 3. Content — D1, D2

### 3.1 D1 — Company background (#30)
```
SYSTEM
You assist ValueCompass. Write a short background of the company for investors, using
ONLY the annual-report text and the facts provided. Do not use outside knowledge. Do not
give opinions on the stock, its price or its score. Do not state any number that is not in
FACTS. Write in Hebrew, plain and neutral.

STRUCTURE (exactly these five parts, one or two sentences each; total at most 120 words)
1. What the company does and its main products or services.
2. Main segments.
3. Where it operates (main markets / geographies).
4. Business environment and main competitors (as named in the report).
5. Competitive advantage — use MOAT exactly as given; do not add or change it.

FACTS (from ValueCompass): industry {industry}; revenue {revenue} {currency} (FY{fiscal_year});
ONE SENTENCE: {b31_q5_one_sentence}; MOAT: {b32_q5_answer} / {moat_source} / {moat_reasoning}

TEXT (TXT-001, TXT-003, TXT-005, filing {accession}):
<<<
{section_text}
>>>

OUTPUT
{"skill_id": "BG-1", "version": {version}, "text_he": "<background>",
 "competitors": ["<as named>"], "quotes": [{"text": "<exact quote>", "section": "..."}]}
```
```yaml
when: once per annual report (with A1–A14)
code_checks: ≤ 120 words; every number in text_he appears in FACTS; competitors appear in the quotes; moat wording consistent with A7 (source matches)
approval: automatic
```

### 3.2 D2 — Results analysis (#31)
```
SYSTEM
You assist ValueCompass. Explain a company's ValueCompass results to an investor, using
ONLY the results provided below. Do not add facts, numbers or opinions that are not in
RESULTS. Do not tell the reader to buy or sell. Do not mention the current share price
(it changes daily). Write in Hebrew, plain and neutral.

STRUCTURE (two paragraphs, each at most 60 words)
1. Quality: what drove the Buffett and Graham quality scores — the strongest and weakest
   criteria, and the position versus peers as given in PEERS.
2. Value: what drove the Buffett and Graham values and what determines the buy price
   (margin of safety by quality; "not suitable" below quality 55; blocks or flags if any).
Refer to criteria by their names as given. Every number you write must appear in RESULTS or PEERS.

RESULTS (from the scoring run {run_id}; profile {profile}):
{results_json}      # scores, coverage, per-criterion points and max, key metric values, values, buy prices, states and flags
PEERS (computed by code; group {peer_group_definition}, n = {n}):
{peers_json}        # percentile of each quality score and of key metrics within the group

OUTPUT
{"skill_id": "AN-1", "version": {version}, "quality_he": "<paragraph 1>", "value_he": "<paragraph 2>",
 "criteria_cited": ["<criterion id>", ...]}
```
```yaml
when: once per scoring run (new annual report or rulebook change); stored and shown as is — not regenerated when the page is opened
code_checks: each paragraph ≤ 60 words (longer → regenerated, not cut); every number appears in RESULTS / PEERS; criteria_cited exist in the run; no price wording
peer_group (code, fixed): same profile and same ValueCompass industry; when fewer than 5 companies, same profile only; n and definition always shown
approval: automatic
```

### 3.3 D2 — uniform wording and stable text (added 2026-10-23)

**Stable text:** D2 is generated once per scoring run, stored with `run_id` and shown as is. Opening the page never calls the AI. A new text is generated only by a new run: a new annual report, a new Rulebook or calculation version, or a profile change. The daily price refresh is not a new run.

**Price-independent content (new rule):** D2 may cite only values that change with a new run:

- Quality scores and labels.
- Criteria and their points.
- Fair values and buy prices.
- The required margin of safety.
- Blocks and flags.

It must NOT cite anything that changes with the daily price, because the text would then contradict the table above it within days:

- The current price.
- The price score.
- The current margin of safety, discount or upside.
- The conclusion category.

**Uniform wording across companies.** Code prepares the words; the model only composes.

1. **Glossary.** RESULTS carries every criterion name, metric name and label in Hebrew, exactly as the screen shows them (Display Specification 2026-10-23_01-00). The model must use these strings verbatim and no synonyms (e.g., always "תשואה על ההון", never "ROE" or "רווחיות ההון").
2. **Strength words are computed by code, not chosen by the model.** Each criterion gets a word from its share of the maximum:

   | Share of the maximum | Word |
   |---|---|
   | ≥70% | חזק |
   | 40–69% | בינוני |
   | below 40% | חלש |

3. **Peer position is computed by code**, from the percentile:

   | Percentile | Wording |
   |---|---|
   | ≥75 | ברבע העליון |
   | 50–74 | מעל החציון |
   | 25–49 | מתחת לחציון |
   | below 25 | ברבע התחתון |

4. **Sentence frames.** The model fills the frames in this order, with at most one connecting sentence of its own per paragraph:
   - **Paragraph 1 (quality):** "ציון האיכות לפי באפט: {X}/100 ({label}); לפי גרהם: {Y}/100 ({label}). הקריטריונים החזקים: {…}. החלשים: {…}. ביחס ל-{n} עמיתים ({group}): {position}."
   - **Paragraph 2 (value):** "השווי לפי באפט: {value} ({method}); מחיר הקנייה: {buy price}, במרווח ביטחון נדרש של {mos}%. לפי גרהם: {value} ({method}); מחיר הקנייה: {buy price}." Then blocks, flags or "לא מתאים לרכישה" when they apply.
5. **One worked example** in the prompt: a fictional company, both paragraphs written to the frames. It shows the style, not the content.
6. **Score-change line (CHANGE).**
   - **When:** only when a previous run exists.
   - **Where:** one more line, at most 25 words, outside the two paragraphs: "לעומת הריצה הקודמת ({date}): {criterion} {עלה/ירד} מ-{a} ל-{b} — {reason}."
   - **Content:** code computes the changes and their reason (new annual report, changed data, rule version). The model only phrases.

**Additional code checks:**

- **Forbidden content:** no current price, price score, current margin, discount, upside or conclusion category. Checked against RESULTS: any of those numbers in the text → rejected.
- **Glossary:** criterion and metric names appear only in their glossary form.
- **Frames:** each frame's fixed words appear in order.
- **On failure:** one retry with the failure reason; still failing → `failed`, and the screen shows the section without text.

## 4. Language decision

Prompts in English (2026-10-20_23-23 §10.2). **User-facing text (D1, D2) is generated directly in Hebrew**; an English version can be generated later from the same inputs. Judgment and extraction answers stay in English (internal), with display labels translated by the UI.

## 5. Search and import — S1, S2 (added 2026-10-23)

These two skills run when a user acts, not in the loading queue.

- **Key:** a separate Gemini key from a separate Google project, with its own daily quota. They run inside a Supabase Edge Function, so the key is never in the browser.
- **Model:** the fixed model (`gemini-3.5-flash-lite`), temperature 0, seed 20261021.
- **Per-user daily limit:** to be set with the security stage.

### 5.1 S1 — Smart search (#32)

**Flow:**

1. **Code first.** When the text matches a ticker or a company name (typo-tolerant), the search runs without AI.
2. **Otherwise S1** turns the request into a structured filter.
3. **Code validates the filter, then queries the DB.** The AI never writes SQL and never sees the DB.
4. **The screen** shows the understood filter as editable chips, then the results.

```
SYSTEM
You assist ValueCompass. Turn the user's request into a filter over the fields listed below.
Use ONLY these fields, operators and values. Do not invent fields. Do not answer the question
yourself and do not name companies. If part of the request cannot be expressed with these
fields, put it in "unsupported". Return ONLY the JSON object under OUTPUT.

FIELDS (field — type — allowed values / range)
profile — enum — STANDARD, TECH_ASSET_LIGHT, BANK, INSURANCE, INCOME_REAL_ESTATE
industry — enum — {the ValueCompass industries}
country — enum — {countries in the DB}
buffett_quality, graham_quality — number 0–100
buffett_price, graham_price — number 0–10
quality_label_buffett, quality_label_graham — enum — {labels}
revenue_cagr_5y, net_income_cagr_5y, eps_cagr_5y — percent
roe_latest — percent; debt_to_equity_latest — ratio; fcf_latest — currency
market_cap — currency
price_vs_buy_price_buffett, price_vs_buy_price_graham — percent (negative = below the buy price)
in_my_portfolio, in_my_watchlist — boolean

OPERATORS: =, !=, <, <=, >, >=, between, in
SORT: any number field, asc | desc. LIMIT: 1–50 (default 20).

REQUEST (Hebrew or English): {user_text}

OUTPUT
{"skill_id": "S1", "version": 1,
 "filters": [{"field": "...", "op": "...", "value": ...}],
 "sort": {"field": "...", "dir": "asc|desc"} | null, "limit": 20,
 "understood_he": "<one Hebrew sentence: what will be searched>",
 "unsupported": ["<part of the request that could not be expressed>"]}
```

**Code checks:**

- Every field, operator and value is in the allow-list and within its range.
- Enum values are exact.
- At most 8 filters.
- A failed check removes that filter and adds it to `unsupported`; the request is never re-asked.
- An empty filter list → plain name/ticker search.
- `understood_he` is shown to the user.

**Example:** "בנקים עם ציון באפט מעל 80 וחוב נמוך" → `profile = BANK`, `buffett_quality > 80`, and `unsupported: ["חוב נמוך"]`. For banks the leverage metric is CET1, which is not in the field list, so the screen says so instead of guessing.

### 5.2 S2 — Broker file column mapping (#33)

**Flow:**

1. **Code reads the uploaded file** (CSV / Excel).
2. **Only the header row and the first 5 data rows are sent to S2.** The rest of the file never leaves the code.
3. **S2 proposes which column holds which field.**
4. **Code applies the mapping to all rows and validates it.**
5. **The screen shows a preview.** The user corrects it before saving.

```
SYSTEM
You assist ValueCompass. A user uploaded a broker export of their holdings. Map its columns
to the fields below, using the header row and the sample rows. Do not change or compute values.
If no column fits a field, map it to null. Return ONLY the JSON object under OUTPUT.

FIELDS: ticker (symbol), quantity (number of shares), avg_price (average purchase price per share),
purchase_date, currency, ignore

HEADER: {header_row}
SAMPLE ROWS (up to 5): {rows}

OUTPUT
{"skill_id": "S2", "version": 1,
 "mapping": {"ticker": <column index | null>, "quantity": ..., "avg_price": ..., "purchase_date": ..., "currency": ...},
 "date_format": "<e.g., DD/MM/YYYY | null>", "decimal_separator": "." | ",",
 "notes_he": "<one Hebrew sentence, e.g., 'עמודת המחיר היא סך העלות ולא מחיר למניה'>"}
```

**Code checks:**

- Ticker values look like tickers and are matched to the DB or to SEC.
- Quantity and price parse as positive numbers.
- Dates parse with `date_format`.
- A failed column → that field left blank.
- Unknown tickers go to the automatic add.
- Empty fields are allowed (Display Specification 3.1).
