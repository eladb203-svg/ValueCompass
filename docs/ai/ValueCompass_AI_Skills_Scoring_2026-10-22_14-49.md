---
title: "ValueCompass — AI Scoring Skills (A1–A14)"
subtitle: "2026-10-22_14-49 · prompts in English (decision: AI spec §10.2) · approved"
---

# AI Scoring Skills A1–A14 — template 3.1

**גרסה 2 (21.10.2026):** כיול אחרי ק5א — 90 מתוך 101 תשובות היו 2, ו-INTC קיבלה 2 במעמד תחרותי. נוספו לתבנית כללים 6–8 (תיאור עצמי = טענה ולא ראיה; 2 דורש ראיה ספציפית; בין שתי רמות — הנמוכה; עקביות עם עובדות הקוד), ובלוק FACTS GIVEN BY CODE. ל-A6, ‏A7, ‏A10, ‏A12 נוספו עובדות מהנתונים (מגמות הכנסות, מרווחים, תשואה על ההון), ול-A6 ו-A12 גם פרק הדירקטוריון. כל הסקילים עלו לגרסה 2.

**גרסה 3 (21.10.2026, ספר 2026-10-21_19-26):** ‏A3 — סקאלה חדשה (CL17: המודל הרגיל של הפרופיל = מודל אחד). ‏A12 — בודק ביסוס בלבד; 0 = כבר לא שחקנית משמעותית (CL18); הכיוון נשאר רק ב-A6. ‏A7 — רק מקור החפיר והראיות מהדוח; התשואה העקבית נספרת בקוד בסעיף 3 של הכרטיס ולא כאן (בלי ספירה כפולה). שלושתם עלו לגרסה 3.

**תבנית 3.1 (22.10.2026, אושרה אחרי ק5א-3):** התאמה לסט הייחוס 82% → 86%, יציבות 100%. (1) שדה חובה `facts_check` לפני `answer` כשנשלחו FACTS — משפט אחד: מה העובדות מראות והאם הן תומכות ברמה שנבחרה. (2) כלל 3 הורחב: ציטוט = קטע רצוף אחד מטקסט הדוח בלבד, לעולם לא משורת FACTS. (3) A8 — העובדות כוללות גם ירידות ערך ורווח/הפסד ממכירה שנרשמו בפעילויות שהופסקו (AMT). (4) A11 — בדיקת עקביות בקוד בין `share_pct` לרמה. גרסאות הסקילים לא השתנו (הסקאלות זהות); גרסת התבנית נשמרת כ-`prompt_version` = ‏`<גרסת הסקיל>.1`. מודל קבוע: `gemini-3.5-flash-lite`, טמפרטורה 0, ‏seed ‏20261021.

**עדכון 22.10.2026 (אחרי ק5ב חלקי):** (1) כלל הציטוט נוסח מחדש בלי הסימן '...' עצמו ("העתק כל ציטוט כקטע רצוף אחד בדיוק כפי שהוא מופיע, בלי לקצר ובלי לחבר קטעים"); (2) ניסיון חוזר אחד בקוד כשהציטוט לא נמצא, עם הציטוט שנכשל; (3) ‏A11 — ‏`share_pct` = אחוז מההכנסות כפי שדווח, לא נפח מכירות (KO: נפח בקבוק אינו הכנסות). גרסאות הסקילים והסקאלות לא השתנו.

**עברית — מה במסמך:** כאן כתובים 14 סקילי הניקוד (שאלות האיכות 2 / 1 / 0) בדיוק כפי שהקוד ישלח אותם ל-Gemini. כל סקיל = תבנית משותפת (סעיף 1) + בלוק נתונים קצר (סעיף 3). הסקאלה בכל בלוק מועתקת **מילה במילה** מכרטיס בספר הכללים 2026-10-21_19-26; שינוי בכרטיס → גרסת הסקיל עולה. ה-prompts באנגלית (החלטה 2 במפרט ה-AI); ההסברים בעברית. בק5 הבלוקים יישמרו כקובץ נתונים (`src/ai/skills/scoring.yaml`), לא כקוד.

**Source:** Rulebook 2026-10-21_19-26 (Part C cards; R1, R2, R13, R16, R18); AI Layer Specification 2026-10-21_16-00 (§2–§5).

## 1. Common template (all A-skills)

Code assembles the prompt from this template and one skill block. Placeholders in `{braces}` are filled by code.

```
SYSTEM
You assist ValueCompass, a value-investing scoring system. You answer ONE predefined
question about ONE company, using ONLY the annual-report text provided below.
Rules:
1. Use only the text provided. Do not use outside knowledge, news, or your memory of the company.
2. Apply the SCALE exactly as written. Choose the single level that fits best.
3. Every answer except insufficient evidence must be supported by 1–3 quotes copied
   character for character from the TEXT section. Copy each quote as one continuous passage,
   exactly as it appears, without shortening or joining passages. Quotes must come from the
   report text, never from FACTS GIVEN BY CODE; you may refer to FACTS in your reasoning.
4. If the text does not allow an answer, return answer = null and insufficient_evidence = true.
   Do not guess. Do not default to 1.
5. Do not compute scores, give investment opinions, or mention prices.
6. A company's description of itself ("leader", "strong position", "well positioned") is a CLAIM,
   not evidence. Count it only when supported by specific facts in the text or in FACTS GIVEN BY CODE
   (rankings, market shares, customer numbers, trends).
7. Level 2 requires specific evidence. When the evidence fits two levels, choose the LOWER one.
8. When FACTS GIVEN BY CODE are provided, they are correct; your answer must be consistent with them
   (e.g., declining revenue and margins do not fit "stable or improving position").
9. Return ONLY the JSON object described under OUTPUT. No text before or after it.

QUESTION ({skill_id}, version {version})
{question}

SCALE (ValueCompass Rulebook, card {card} — apply exactly)
2 = {scale_2}
1 = {scale_1}
0 = {scale_0}

WHAT TO LOOK FOR
{evidence_focus}
{profile_note}

FACTS GIVEN BY CODE (when provided; from ValueCompass data, already verified)
{facts}

COMPANY: {company_name} ({ticker}) · FISCAL YEAR: {fiscal_year} · PROFILE: {profile}
TEXT ({sections}, filing {accession}):
<<<
{section_text}
>>>

OUTPUT
{"skill_id": "{skill_id}", "version": {version},
 "facts_check": "<one sentence: what the FACTS show and whether they support the chosen level>",
 "answer": 2 | 1 | 0 | null, "insufficient_evidence": true | false,
 "reasoning": "<at most 3 sentences>",
 "quotes": [{"text": "<exact quote>", "section": "<TXT-00x>"}]{extra_output}}
```

**Model settings:** `gemini-3.5-flash-lite`, temperature 0, seed 20261021, max output 8192 tokens; model and `prompt_version` recorded per answer; one call per skill per company per fiscal year. `facts_check` is sent only when FACTS are provided; it must come before `answer`.

## 2. Code checks and points (reminder from 2026-10-21_16-00 §4.4)

Code rejects an answer when: invalid JSON (one retry), answer not in {2, 1, 0, null}, any quote not found verbatim in the text sent (after whitespace / quote-mark normalization), no quote for a non-null answer, `extra` missing when required, a quote found only in FACTS (`quote_from_facts`), `facts_check` missing or empty when FACTS were sent, or (A11) `largest_exposure.share_pct` inconsistent with the level (see A11). **Quote retry (2026-10-22):** when the only failure is `quote_not_found`, code makes ONE retry with the note "Quote not found verbatim: <first 120 characters of the quote>. Copy one continuous passage exactly as it appears in the TEXT." Still not found → rejected. Rejected → "insufficient evidence" (missing, R16). Points = code, per the card (column "Points" below).

| Skill | Card / sub-item | Points from answer (code) |
|---|---|---|
| A1–A5 | Buffett 3.1 #1–#5 | answer × 1 (each 0–2; criterion = sum, 0–10) |
| A6 | Buffett 3.2 #4 | answer × 1 (0–2) |
| A7 | Buffett 3.2 #5 | answer × 0.5 (0–1) |
| A8 | Buffett 3.7 #3 | answer × 1 (0–2) — only when the gate sends it to AI |
| A9 | Buffett 3.7 #5 | answer × 1 (0–2) |
| A10 | Buffett 3.8 #6 | answer × 1 (0–2) |
| A11 | Graham 3.1 #3 | answer × 1 (0–2) |
| A12 | Graham 3.1 #4 | answer × 1 (0–2) |
| A13 | Graham 3.8 #3 | answer × 1 (0–2) |
| A14 | Graham 3.3-BANK #4 | 2 → 3, 1 → 1.5, 0 → 0 — only without a loan breakdown |

## 3. Skill blocks

### A1 — B3.1-Q1 · What the company sells
```yaml
skill_id: B3.1-Q1
version: 2
card: C.B3.1 #1
question: Is it clear what the company sells?
scale_2: The main products or services can be named in simple words
scale_1: Generally clear, but many products or very technical ones
scale_0: Unclear what is actually sold (holdings, complex financial products)
evidence_focus: The description of products and services in the Business section; whether the main ones can be named in plain words.
sections: [TXT-001]
when: always
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: The "products" are the property types leased (e.g., offices, warehouses, apartments). Consider asset types and lease structure.
```

### A2 — B3.1-Q2 · Who the customers are
```yaml
skill_id: B3.1-Q2
version: 2
card: C.B3.1 #2
question: Is it clear who the customers are?
scale_2: The main customer types can be identified (consumers, businesses, governments)
scale_1: Several different customer types, or sales through intermediaries that hide the customer
scale_0: Unclear who pays
evidence_focus: Statements naming customer types, distribution channels and who ultimately pays.
sections: [TXT-001]
when: always
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: Customers are the tenants; consider tenant types and industries.
```

### A3 — B3.1-Q3 · Revenue sources
```yaml
skill_id: B3.1-Q3
version: 3
card: C.B3.1 #3
question: Are the revenue sources simple to understand?
scale_2: Few main sources, each with a model that can be explained in one line (sale, subscription, fee, rent, premium, interest margin); the profile's standard model counts as one model (BANK: interest, investment income and fees; INSURANCE: premiums and investment income; INCOME_REAL_ESTATE: rent)
scale_1: Several sources that differ in nature, or a material part of revenue (about a quarter or more) depends on something hard to see from outside (trading gains, fair-value remeasurement, gain-on-sale, complex contracts)
scale_0: Many unrelated sources that cannot be summarized together, or a non-transparent model
evidence_focus: How the company earns money — revenue streams, segments and the revenue model of each; whether an outsider can see what the customer pays for and when revenue arises. Estimate the share of revenue from hard-to-see sources when reported.
sections: [TXT-001, TXT-005]
when: always
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: Rental income, recoveries and other property income; note corporate complexity (joint ventures, operating partnership) if it obscures the model.
```

### A4 — B3.1-Q4 · Main risks
```yaml
skill_id: B3.1-Q4
version: 2
card: C.B3.1 #4
question: Are the main risks clear?
scale_2: 2–4 concrete business risks can be named
scale_1: Very generic risks, or so many that they cannot be ranked
scale_0: The business depends on a factor that cannot be assessed (single clinical trial, commodity price, open regulation)
evidence_focus: Risk Factors — whether a few concrete business risks stand out from boilerplate.
sections: [TXT-002]
when: always
extra_output: '"main_risks": ["<risk 1>", "<risk 2>", ...]   (2–4 items, plain words; required when answer = 2)'
profile_notes: {}
```

### A5 — B3.1-Q5 · One sentence
```yaml
skill_id: B3.1-Q5
version: 2
card: C.B3.1 #5
question: Can the business be explained in one sentence?
scale_2: 'A sentence of up to 25 words: what, for whom, and how it makes money'
scale_1: Needs two sentences, or the sentence omits a central part
scale_0: Not possible
evidence_focus: Write the sentence yourself from the text; it must say what is sold, to whom, and how the company makes money.
sections: [TXT-001]
when: always
extra_output: '"one_sentence": "<the sentence; code checks ≤ 25 words when answer = 2>"'
profile_notes: {}
```
Code check: when answer = 2, `one_sentence` ≤ 25 words; otherwise the answer is rejected. The sentence is also reused by the company background (skill #30).

### A6 — B3.2-Q4 · Competitive position
```yaml
skill_id: B3.2-Q4
version: 2
card: C.B3.2 #4
question: Is the competitive position stable?
scale_2: Market leader or among the largest, with a stable or improving position
scale_1: Stable but not leading, or mixed signals
scale_0: Losing market share, or the position is eroding (new entrants, price war)
evidence_focus: Evidence of the position and its DIRECTION — rankings, market shares, competitive wins and losses, and the revenue and margin trend in FACTS. Self-descriptions alone are not enough for 2.
sections: [TXT-001, TXT-003, TXT-004]
facts_from_code: revenue for each of the last 5 years and its CAGR; gross and operating margin, first 2 vs last 2 years; segment revenue trend when reported
when: always
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: Judge the durability of the location and asset advantage; do not treat a temporarily rising property market as a stable competitive position.
```

### A7 — B3.2-Q5 · Moat
```yaml
skill_id: B3.2-Q5
version: 3
card: C.B3.2 #5
question: Is there a clear moat?
scale_2: A concrete moat source can be named (brand, switching costs, scale, network effect, regulation, data, infrastructure), with evidence from the report
scale_1: A plausible but generic or unproven moat
scale_0: No identifiable moat, commodity product
evidence_focus: The moat source and specific evidence for it in the report — market share, number of users or customers, switching costs, retention, pricing power, licences, cost advantage. A source named only in the company's own words fits 1. Do not judge return persistence: code scores it in sub-item 3 of this card.
sections: [TXT-001, TXT-003]
when: always
extra_output: '"moat_source": "brand" | "switching_costs" | "scale" | "network_effect" | "regulation" | "data" | "infrastructure" | "location" | "none"'
profile_notes:
  INCOME_REAL_ESTATE: A location or irreplaceable-asset advantage counts ("location"); a rising market does not.
```
The moat answer is reused by the company background (skill #30), so the two never contradict.

### A8 — B3.7-Q3 · M&A value
```yaml
skill_id: B3.7-Q3
version: 2
card: C.B3.7 #3
question: Did M&A create value?
scale_2: Acquisitions were integrated and generated growth, with no material goodwill impairments
scale_1: Mixed picture, or too early to judge a large recent acquisition
scale_0: Material goodwill impairments, overpayment, or acquisitions outside the core business
evidence_focus: Acquisitions of the last 5 years, their stated results, integration, and any goodwill impairments.
sections: [TXT-004, NOTE:business_combinations, NOTE:goodwill]
when: only when code finds acquisitions material (Σ acquisitions / Σ FCF ≥ 10%, or Σ FCF ≤ 0 with acquisitions; BANK / INSURANCE on net income)
inputs_from_code: the acquisitions and goodwill-impairment amounts per year, INCLUDING impairments and gains/losses on sale recorded in discontinued operations (given as facts, not to be recomputed); a year with no data is shown as 'not reported', never as 0
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: Corporate acquisitions only (mergers, purchases of companies or platforms) — not purchases of individual properties.
```

### A9 — B3.7-Q5 · Management
```yaml
skill_id: B3.7-Q5
version: 2
card: C.B3.7 #5
question: Is management transparent, conservative and consistent?
scale_2: Clear reporting, consistent strategy, no restatements or governance disputes
scale_1: 'Mixed signals: heavy use of "adjusted" metrics, frequent strategy changes'
scale_0: Restatements, governance problems, aggressive accounting
evidence_focus: MD&A tone and consistency, use of non-GAAP metrics, restatements, material weaknesses (Item 9A), governance disputes.
sections: [TXT-004]
when: always
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: Also consider equity issuance relative to value per share and the use of disposal proceeds.
```

### A10 — B3.8-Q6 · Sustainable growth
```yaml
skill_id: B3.8-Q6
version: 2
card: C.B3.8 #6
question: Does the growth look sustainable?
scale_2: 'Clear, durable growth drivers: expanding market, new products, pricing power; not reliant on one-off events'
scale_1: Growth partly depends on acquisitions, cyclicality or a single product
scale_0: Growth from one-off events, a shrinking market, or only from acquisitions and debt
evidence_focus: The growth drivers management describes and whether they are recurring, checked against the actual growth record in FACTS (organic vs acquired where stated).
sections: [TXT-001, TXT-004]
facts_from_code: revenue and EPS for each of the last 5 years with CAGR; acquisitions per year
when: always
extra_output: none
profile_notes:
  INCOME_REAL_ESTATE: Distinguish organic growth (same-property NOI, rents) from acquisition-led and revaluation-led growth.
```

### A11 — G3.1-Q3 · Dependence
```yaml
skill_id: G3.1-Q3
version: 2
card: C.G3.1 #3
question: Is there a critical dependence on one product, customer or market?
scale_2: No customer above 10% of revenue, and no product or license whose loss would threaten the business; a single reported segment does not by itself reduce the score
scale_1: A customer at 10%–25%, or a central product, but with a significant additional revenue base
scale_0: A customer above 25%, a single product, or dependence on one license or market
evidence_focus: Largest customer share (>10% disclosure), largest product or segment, dependence on a license, patent or single market.
sections: [TXT-001, TXT-005]
when: always
extra_output: '"largest_exposure": {"type": "customer" | "product" | "license" | "market" | "none", "name": "<as stated>", "share_pct": <number or null>}' — share_pct = percent of total REVENUE as disclosed (not unit volume, not a share of a segment); null when the report gives no revenue share
code_check: when type = customer and share_pct is given — share_pct > 25 allows 0; 10–25 allows 1 (or 0 only with another stated dependence: single product, license or market); < 10 allows 2 or a product/license/market reason. Inconsistent → one retry with the note "Your share_pct does not match the level you chose"; still inconsistent → rejected (insufficient evidence).
profile_notes: {}
```

### A12 — G3.1-Q4 · Business position
```yaml
skill_id: G3.1-Q4
version: 3
card: C.G3.1 #4
question: Does the company have a proven business position in its industry?
scale_2: One of the central players in its industry or niche, with evidence
scale_1: A mid-sized player with a stable but not prominent position
scale_0: Young company, development stage, or no longer a significant player
evidence_focus: How established the position is — years in the industry, market share or ranking where reported, scale versus competitors, long-standing material customers. Do not judge the direction (gaining or losing): that is A6 (rulebook CL18).
sections: [TXT-001, TXT-003]
facts_from_code: years since the first annual report; latest-year revenue in USD
when: always
extra_output: none
profile_notes: {}
```

### A13 — G3.8-Q3 · One-time items
```yaml
skill_id: G3.8-Q3
version: 2
card: C.G3.8 #3
question: Do reported earnings depend on one-time items?
scale_2: Immaterial (below ~10% of net income every year)
scale_1: One material item, or recurring "one-time" items
scale_0: Material items in most years, or earnings rely on them
evidence_focus: Impairments, restructuring, asset-sale gains, legal settlements and one-off tax items over the last 5 years, and their size relative to net income.
sections: [TXT-004, NOTE:income_statement_items]
when: STANDARD and TECH_ASSET_LIGHT
inputs_from_code: net income for each of the 5 years (given as facts, so the AI judges materiality against them)
extra_output: '"items": [{"year": <FY>, "description": "<as stated>", "amount": <number or null>}]'
profile_notes: {}
```

### A14 — G3.3B-Q4 · Loan diversification (banks)
```yaml
skill_id: G3.3B-Q4
version: 2
card: C.G3.3-BANK #4
question: Is the loan book diversified?
scale_2: Spread across loan types, industries and regions; no dominant exposure
scale_1: A prominent but not dominant exposure to one type, industry or region
scale_0: A dominant exposure (CRE, one industry, region or borrower)
evidence_focus: Descriptions of the loan portfolio by type, industry and geography, and any stated concentrations.
sections: [TXT-001, TXT-004, NOTE:loans]
when: BANK only, and only when no numeric loan breakdown is available (D4)
extra_output: none
profile_notes: {}
```

## 4. What is fixed and what is filled

| Fixed in the skill file | Filled by code at call time |
|---|---|
| Question, scale (verbatim from the card), evidence focus, sections, gate, extra output, profile notes, version | Company, ticker, fiscal year, profile, filing accession, section text, facts given to the AI (A8, A13) |

**Versioning:** any change to a skill block raises `version`; stored answers with an older version are recomputed at the next run (R18).
