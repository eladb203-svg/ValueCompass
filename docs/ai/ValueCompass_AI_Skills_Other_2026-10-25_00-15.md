---
title: "ValueCompass — AI Skills: Classification, Extraction, Content, Search (B1–B15, C1, D1, T1, D2, S1–S2)"
subtitle: "2026-10-25_00-15 · prompts in English · approved"
---

# AI Skills: Classification, Extraction, Content

**עברית — מה במסמך:** שאר הסקילים של ק5, באותו מבנה של סקילי הניקוד (A1–A14): תבנית משותפת לכל סוג + בלוק נתונים לכל סקיל. **C1** — סיווג ענף (#15). **B1–B15** — חילוץ נתונים (#16–#29, כולל החילוץ הכללי). **D1** — רקע על החברה (#30). **D2** — ניתוח תוצאות (#31). **עדכון 25.10.2026 (אחרי ריצות ק5ג):** ברקע (D1) — "כ-90–100 מילים" ובדיקה עד 140; עד 5 מתחרים; כשהדוח לא נוקב בשמות — עד 4 סוגי מתחרים במילות הדוח, בציטוט (בעיקר בנקים ומבטחים); ניסיון חוזר עם משוב מדויק (מספר המילים בפועל, מקור החפיר החסר). בתרגום (T1) — כל כתב שאינו עברית או לטינית נדחה (נמצאו אותיות תאילנדיות ויווניות). שנה בעברית מותרת; data / infrastructure / location לא נחשבים מקור חפיר נוסף. תקרת קריאות נאכפת בקוד. **איכות העברית:** מילון מונחי ענף בתרגום (הקוד שולח רק את המונחים שמופיעים בטקסט, ובודק שהתרגום שלהם הופיע); בטעינה הראשונה כל רקע עברי ממתין לאישור של אלעד ולא מוצג עד אז; תיקון ידני נשמר ונבדק מחדש בקוד; אחר כך — רקע לדוח שנתי חדש מוצג אוטומטית כשהבדיקות עוברות.

**עדכון 24.10.2026:** סעיף 3 נכתב מחדש — הרקע (D1) נכתב באנגלית ומתורגם לעברית (T1, ‏#34), עם בדיקות "עברית בלבד" ובלי כתבים מעורבים; היתרון התחרותי לפי רמת A7; ניתוח התוצאות (D2) נוצר בקוד מתבניות, בלי AI, עם מילון הקריטריונים והתוויות, טווח "משוער", "הנמוך ביותר", השוואה לעמיתים רק עם ≥5 עמיתים סופיים, מספרים ושמות שיטה מהקוד.

**עדכון 23.10.2026:** נוספו סעיף 3.3 — ניסוח אחיד ויציב לניתוח (D2): נכתב פעם אחת לכל ריצה; רק ערכים שלא תלויים במחיר היומי; מילון מונחים, מילות חוזק ומיקום מול עמיתים מחושבים בקוד, תבניות משפט, דוגמה, ושורת "מה השתנה" — וסעיף 5 — חיפוש חכם (S1, ‏#32) וזיהוי עמודות בקובץ ברוקר (S2, ‏#33), עם מפתח Gemini נפרד. שמות הנתונים (`item_key`) הם השמות במילון ב-DB; ההגדרות — מחלק ה בספר הכללים 2026-10-20_23-21. כללי האישור — לפי ההחלטה מ-21.10.2026.

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

## 3. Content — D1, T1, D2 (revised 2026-10-24)

**Language (decided 2026-10-24):**

- **D1** is written by the AI in English. All checks run on the English text against the report.
- **T1** translates D1 to Hebrew. Both versions are stored (`ai_texts.language` = `en` / `he`).
- **D2** is generated by **code**, directly in Hebrew. No AI.
- **Reason:** composing Hebrew from long English text produced mixed-script errors with the fixed model (e.g., "תרכיزي", "משכirה").

**Stable text:** D1 is written once per annual report and D2 once per scoring run. Both are stored and shown as is. Opening a page never generates text.

### 3.1 D1 — Company background (#30), in English

```
SYSTEM
You assist ValueCompass. Write a short background of the company for investors, in English,
using ONLY the annual-report text and the facts provided. Do not use outside knowledge. Do not
give opinions on the stock, its price or its score. Every number must appear in FACTS or in the
TEXT. Write plain, neutral English; your final text, not your thinking process.

STRUCTURE (exactly these five parts, one sentence each; about 90–100 words in total)
1. What the company does and its main products or services.
2. Main segments.
3. Where it operates (main markets / geographies).
4. Business environment and main competitors:
   a. If the report NAMES competitors → at most 5 main ones, by name as written.
   b. If it names none but describes the competition → at most 4 TYPES of competitors, in the
      report's own words (e.g., "other banks, broker-dealers and fintech companies").
   c. If it does not describe the competition → "The report does not describe its competition."
   Never mix names and types. Every name or type you use must appear in one of your quotes.
5. Competitive advantage — use MOAT exactly as given:
   level 2 → "A clear competitive advantage: <source>"; level 1 → "A competitive advantage that is
   not proven: <source>"; level 0 → "No identifiable competitive advantage." One source only.

FACTS (from ValueCompass, formatted by code): company name {display_name}; industry {industry};
revenue {revenue_formatted} (FY{fiscal_year}); ONE SENTENCE: {a5_one_sentence};
MOAT: level {a7_answer}, source {moat_source}

TEXT (TXT-001 up to 35,000 characters, TXT-003 up to 12,000, TXT-005 up to 12,000; filing {accession}):
<<<
{section_text}
>>>

OUTPUT
{"skill_id": "BG-1", "version": 3, "text_en": "<background>",
 "competitors": ["<as named>"], "competitor_types": ["<as written>"], "quotes": [{"text": "<exact quote>", "section": "..."}]}
```

**Code checks (English text):**

- At most 140 words, five sentences (the prompt asks for about 90–100; models do not count exactly).
- Every number appears in FACTS or verbatim in the TEXT sent.
- At most 5 competitors, or at most 4 competitor types; never both.
- Every competitor and every competitor type appears in a quote (several quotes are allowed).
- At least one quote when competitors or types are given.
- The moat sentence matches the A7 level and `moat_source`. Generic words such as data, infrastructure or location are not counted as an extra source.
- The company name appears as `display_name`.
- No deliberation words.
- A year written as a number is allowed (also in the Hebrew text).
- Valid JSON.
- **On failure:** one retry with a precise reason: the actual word count and "shorten to about 100 words"; the missing moat source to use; the names that have no quote. Still failing → `failed`, no background is shown, and the K6 AI queue retries later.
- **Call cap:** enforced in code, per stage and per day.

### 3.2 T1 — Translation to Hebrew (#34)

```
SYSTEM
Translate the company background below from English to Hebrew. Plain, neutral Hebrew.
Keep every number exactly as written. Keep company and competitor names in Latin letters exactly
as written (do not transliterate). Use the GLOSSARY for the moat sentence and fixed terms.
Return ONLY the JSON object under OUTPUT.

GLOSSARY: "A clear competitive advantage" → "יתרון תחרותי ברור"; "A competitive advantage that is
not proven" → "יתרון תחרותי לא מוכח"; "No identifiable competitive advantage" → "אין יתרון תחרותי
מזוהה"; moat sources: brand → מותג, switching_costs → עלויות מעבר, scale → יתרון לגודל,
network_effect → אפקט רשת, regulation → רגולציה, data → נתונים, infrastructure → תשתית,
location → מיקום
INDUSTRY TERMS (from `t1_glossary.yaml`; code sends only the terms found in TEXT_EN):
{industry_terms}

TEXT_EN: {text_en}
NAMES: {display_name}, {competitors}

OUTPUT
{"skill_id": "TR-1", "version": 1, "text_he": "<Hebrew text>"}
```

**Code checks (Hebrew text):**

- The same set of numbers as `text_en`.
- Every name from NAMES appears in Latin letters.
- **Hebrew only.** Latin is allowed only for NAMES, tickers and glossary acronyms. No run of 4 or more Latin words.
- **No mixed-script word** (Hebrew with Latin letters inside one word).
- **No foreign script at all:** any letter that is not Hebrew or Latin (Arabic, Cyrillic, Greek, Thai, etc.) → rejected.
- Length within ±40% of the English word count.
- **Industry terms:** for every term sent in INDUSTRY TERMS, its Hebrew form appears in the text (inflections allowed: a prefix letter ו/ה/ב/ל/מ/ש/כ).
- **On failure:** one retry with the reason; still failing → `failed`, and only the English is stored. **The screen then shows no background.** Damaged text is never shown, and code never edits letters.

**Industry glossary (`t1_glossary.yaml`, maintained in code, starting set):**

| English | Hebrew |
|---|---|
| bottlers / bottling partners | יצרני בקבוקים / שותפי המילוי |
| concentrates | תרכיזים |
| syrups | סירופים |
| deposits | פיקדונות |
| wealth management / asset management | ניהול עושר / ניהול נכסים |
| investment banking | בנקאות השקעות |
| underwriting | חיתום |
| property and casualty | ביטוח רכוש וחבויות |
| reinsurance | ביטוח משנה |
| net lease | שכירות נטו |
| communications towers | מגדלי תקשורת |
| data centers | מרכזי נתונים |
| semiconductors | מוליכים למחצה |
| foundry | שירותי ייצור שבבים (foundry) |
| cloud | ענן |

A term is added whenever a review finds a wrong word (below). The code proposes the addition from the correction; Elad approves it.

**Review of Hebrew backgrounds (decided 2026-10-25):**

- **First load of a company:** the Hebrew background is stored with `approval_status = pending_review` and is **not shown** until Elad approves it in the approval queue.
- **Approve as is, or correct:** a corrected text is stored with `edited_by = human`. Code re-runs the Hebrew checks (numbers, names, script). A wrong word that was corrected is proposed for the glossary.
- **Later backgrounds** (a new annual report): shown automatically when all checks pass. Elad can still send any text back to review.
- **English text:** stored and checked; not shown on the screen.

### 3.3 D2 — Results analysis (#31), generated by code (no AI)

When: once per scoring run, **after all AI tasks of the company are done** (no `ai_pending`). Code fills the frames below from the run. Peer statistics come from PEER.

**Paragraph 1 — quality:**

> ציון האיכות לפי באפט: {X}/100 ({label}); לפי גרהם: {Y}/100 ({label}). הקריטריונים החזקים: {criteria at ≥70%, or "אין קריטריון ברמה חזקה"}. הנמוך ביותר: {lowest criterion} ({strength word}). ביחס ל-{n} עמיתים ({group}): {position}.

- **A score that is still a range:** "{a}–{b}/100, משוער" (never the midpoint).
- **The peer sentence:** only when the company's score is final and at least 5 peers have final scores; otherwise it is omitted.

**Paragraph 2 — value:**

> השווי לפי באפט: {value} ({method name}); מחיר הקנייה: {buy price}, במרווח ביטחון נדרש של {mos}. לפי גרהם: {value} ({method name}); מחיר הקנייה: {buy price}.

- **States replace numbers:** "לא מתאים לרכישה", "לא ניתן לתמחר כרגע", "חסום: {guard}", "לא רלוונטי".
- **Blocks and flags** are added as one short sentence.

**Change line** (only when a previous run exists):

> לעומת הריצה הקודמת ({date}): {item} {עלה/ירד} מ-{a} ל-{b} — {reason}.

- The largest change only.
- The reason comes from code: a new annual report, changed data, a new rule version, new AI answers.

**Fixed rules:**

- **Never cited** (they change with the daily price): the current price, the price score, the current margin of safety, the discount, the upside, the conclusion category.
- **Strength words:**

  | Share of the criterion's maximum | Word |
  |---|---|
  | ≥70% | חזק |
  | 40–69% | בינוני |
  | <40% | חלש |

- **Peer position:**

  | Percentile | Wording |
  |---|---|
  | ≥75 | ברבע העליון |
  | 50–74 | מעל החציון |
  | 25–49 | מתחת לחציון |
  | <25 | ברבע התחתון |

- **Numbers:** formatted by code, e.g., "331.8 מיליארד $", "$33.16", "21.0%".
- **Method names:** the real method of the profile (e.g., "תזרים מהוון", "מספר גרהם", "NAV שמרני", "מספר גרהם תפעולי", "תשואה עודפת דו-שלבית").

**Glossary — criteria (the scorecards' names; the same title in profiles where the card is replaced):**

| | Buffett | Graham |
|---|---|---|
| 3.1 | עסק פשוט ומובן | גודל חברה ויציבות עסקית |
| 3.2 | יתרון תחרותי / חפיר | מצב פיננסי ונזילות |
| 3.3 | רווחיות עקבית | חוב נמוך ושמרנות מאזנית |
| 3.4 | תשואה גבוהה על ההון / הון מושקע | יציבות רווחים |
| 3.5 | תזרים מזומנים חופשי / רווחי בעלים | היסטוריית דיבידנד |
| 3.6 | מאזן חזק וחוב סביר | צמיחת רווחים מתונה |
| 3.7 | הנהלה והקצאת הון | איכות ההון והנכסים |
| 3.8 | צמיחה איכותית וברת קיימא | איכות רווחים ודילול מניות |

**Quality labels:**

| Model | 85–100 | 70–84 | 55–69 | Below 55 |
|---|---|---|---|---|
| Buffett | עסק מצוין | עסק טוב | עסק בינוני | עסק חלש |
| Graham (Rulebook A.6) | שמרנית וחזקה מאוד | טובה ויציבה | גבולית | לא מתאימה לגישה הדפנסיבית |

## 4. Language decision (revised 2026-10-24)

Prompts are in English. D1 is written in English and translated to Hebrew (T1); D2 is generated by code in Hebrew. Judgment and extraction answers stay in English (internal), with display labels translated by the UI. An English UI later can use the stored English D1 and an English version of the D2 frames.

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
