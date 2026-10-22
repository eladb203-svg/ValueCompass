# דוח שלב ק5ג (קוד בלבד) — קבוצת עמיתים, רקע (D1), ניתוח (D2)

תאריך: 2026-10-22 · **אפס קריאות ל-Gemini** · בלי Supabase · `.env` ו-golden לא שונו · המשימה המתוזמנת של ק5ב והדוח `code_stage5b_2026-10-22.md` לא נגעו.

## 1. מה נבנה

| רכיב | קובץ |
|---|---|
| קבוצת עמיתים ואחוזונים (טהור) | `src/scoring/peers.py` |
| רשומות חברה מקבצי golden (בק6 — מה-DB), מדדי מפתח לפי פרופיל, בניית `RESULTS` | `src/scoring/peer_source.py` |
| תבניות D1/D2, מילות חפיר בעברית, מילים אסורות (נתונים) | `src/ai/skills/content.yaml` |
| פרומפטים, בדיקות קוד, יצירה עם ניסיון חוזר אחד, אחסון בקובץ במבנה `ai_texts` | `src/ai/content.py` |
| הרצה (`--companies`, `--no-calls`) | `scripts/run_ai_k5c.py` |
| בדיקות (21) | `tests/test_peers.py`, `tests/test_content.py` |

**קבוצת עמיתים:** אותו פרופיל ואותו ענף ValueCompass (ללא החברה עצמה); פחות מ-5 → אותו פרופיל בלבד (`fallback`). נשמרת לכל ריצה ב-`scripts/ai_store/k5c/peer_groups.jsonl` (מזהי חברות, הגדרה, `n`, `fallback`, `run_id`). **אחוזון** = חלק הקבוצה (כולל החברה) שמתחת לערך, שוויון נספר חצי; במדד שבו נמוך = טוב (מינוף: חוב/הון, מינוף פיננסי, חוב נקי/EBITDAre) האחוזון הוא של "טוב"; בבנק מדד "המינוף" הוא יחס CET1 (גבוה = טוב). ציון בטווח (לא סופי) נכנס עם אמצע הטווח ומסומן `range_midpoint`. שישה מדדי המפתח (מפרט התצוגה, פרק 1, השנה האחרונה): הכנסות, רווח נקי, EPS, ROE (בבנק ROTCE, בביטוח Operating ROE, בנדל"ן לא מוצג), FCF (בבנק/ביטוח אין; בנדל"ן Owner earnings), מינוף.

**D1:** קלט מהקוד — ענף, הכנסות + מטבע + שנה (מה-golden), `one_sentence` מ-A5 (B3.1-Q5), תשובת/מקור/נימוק החפיר מ-A7 (B3.2-Q5) מתוך התשובות השמורות; מקטעים TXT-001/003/005. בדיקות: עד 120 מילים; כל מספר בטקסט מופיע ב-FACTS (נרמול פסיקים, "מיליארד"/"מיליון"/"bn", אחוזים, שנת הדוח); כל מתחרה ב-`competitors` מופיע בציטוט שנמצא מילה במילה; מקור החפיר שנמצא ב-A7 מופיע בטקסט בעברית (מילות מפתח למקור; `none` ← "אין חפיר"); בלי מילים אסורות. כלל הציטוט: קטע רציף אחד, בלי `...`. כשל → ניסיון חוזר אחד עם הסיבות; עדיין כשל → `state=failed`, `text=null`, הסיבות נשמרות.

**D2:** `RESULTS` נבנה מהריצה: ציונים, טווח, כיסוי, נקודות מול מקסימום לכל קריטריון (מזהים `B-3.1`/`G-3.1`), מדדי מפתח, מחיר קנייה, מרווח ביטחון, ערך למניה, מצבים וסימונים — **בלי מחיר המניה**. `PEERS` מהקוד. בדיקות: כל פסקה עד 60 מילים (ארוך → ניסיון חוזר, **לא נחתך**); כל מספר מופיע ב-RESULTS/PEERS (עיגול לספרות שנכתבו; שבר כאחוז); `criteria_cited` קיימים בריצה; אין "לקנות/למכור/כדאי לרכוש/מומלץ/מחיר המניה הנוכחי" וכד' ("מחיר קנייה" מותר). נשמר פעם אחת לכל `run_id` ולא נוצר מחדש בפתיחת עמוד.

**אחסון:** `scripts/ai_store/k5c/texts.jsonl` — שורה לכל (חברה, שנת כספים, `kind` = `background`/`analysis`, `language`=he, `prompt_version`, `run_id`): טקסט, מודל, ציטוטים, תוצאות בדיקות וניסיונות, `state`.

**מכסה:** הלקוח האמיתי משתמש במונה היומי המשותף (תקרה 450) ובנעילת תהליך אחד; `--no-calls` לא יוצר לקוח.

## 2. קבוצות העמיתים — סט הפיתוח (מ-54 חברות ה-golden)

| חברה | הגדרת הקבוצה | n | גיבוי (פרופיל בלבד) | חברי הקבוצה |
|---|---|---|---|---|
| KO | profile STANDARD and industry Other | 5 | לא | DOW, HD, KHC, MCD, NUE |
| MSFT | profile STANDARD and industry Software | 5 | לא | ADBE, CRM, INTU, ORCL, UBER |
| JPM | profile BANK and industry Banks | 10 | לא | BAC, C, FITB, FLG, KEY, MTB, PNC, TFC, USB, WFC |
| CB | profile INSURANCE and industry Insurance carriers | 11 | לא | AFL, AIG, ALL, CINF, HIG, MET, PGR, PRU, RNR, TRV, WRB |
| O | profile INCOME_REAL_ESTATE and industry Property REITs and income real estate | 9 | לא | AMT, ARE, BXP, EQIX, EQR, FRT, PLD, PSA, SPG |
| AMT | profile INCOME_REAL_ESTATE and industry Property REITs and income real estate | 9 | לא | ARE, BXP, EQIX, EQR, FRT, O, PLD, PSA, SPG |
| INTC | profile STANDARD (fewer than 5 companies in industry Semiconductors: profile only) | 19 | כן | ADBE, AVGO, CI, CNC, CRM, DOW, ELV, HD, HUM, INTU, KHC, KO, MCD, MOH, MSFT, NUE, ORCL, UBER, UNH |

INTC: בענף Semiconductors יש רק 2 חברות ב-golden ⇒ נפילה לפרופיל STANDARD כולו (19 חברות). שאר הקבוצות מלאות. בכל פרופיל יש לפחות 5 חברות, אך ענף "Investment banks and brokers" (חברה אחת, פרופיל BANK) ייפול תמיד לגיבוי.

## 3. טבלת אחוזונים לדוגמה — INTC (קבוצה: profile STANDARD (fewer than 5 companies in industry Semiconductors: profile only), n = 19)

| מדד | ערך | אחוזון בקבוצה | n תקף |
|---|---|---:|---:|
| איכות buffett | 21.7 (אמצע טווח) | 2.5 | 19 |
| איכות graham | 46.6 (אמצע טווח) | 17.5 | 19 |
| Revenue | 5.285e+10 | 52.5 | 19 |
| Net income | -2.67e+08 | 17.5 | 19 |
| Diluted EPS | -0.06 | 17.5 | 19 |
| ROE | -0.002501 | 18.4 | 18 |
| Free cash flow | -4.949e+09 | 7.5 | 19 |
| Debt / equity | 0.4076 (נמוך = טוב) | 71.1 | 18 |

ציוני האיכות של ה-golden הם **טווחים** (שאלות ה-AI עדיין `ai_pending` שם), ולכן נכנסו עם אמצע הטווח. בהרצה האמיתית הציונים יגיעו מריצת הניקוד עם תשובות ה-AI והטווח יצטמצם.

## 4. פרומפט D1 לדוגמה — INTC

```
SYSTEM
You assist ValueCompass. Write a short background of the company for investors, using
ONLY the annual-report text and the facts provided. Do not use outside knowledge. Do not
give opinions on the stock, its price or its score. Do not state any number that is not in
FACTS. Write in Hebrew, plain and neutral.
Every competitor you name must be named in the report text and quoted. Copy each quote as one continuous passage, exactly as it
appears in the TEXT, without shortening or joining passages; quotes must come from the report text, never from FACTS.

STRUCTURE (exactly these five parts, one or two sentences each; total at most 120 words)
1. What the company does and its main products or services.
2. Main segments.
3. Where it operates (main markets / geographies).
4. Business environment and main competitors (as named in the report).
5. Competitive advantage - use MOAT exactly as given; do not add or change it.

FACTS (from ValueCompass): industry Semiconductors; revenue 52,853,000,000 (52.85 billion) USD (FY2025);
ONE SENTENCE: Intel designs, manufactures, and sells semiconductor products and provides foundry services to global customers and enterprises to generate revenue.; MOAT: 2 / network_effect / The company possesses concrete moat sources including a deep and extensive established software ecosystem around its x86 architecture, and intellectual property/infrastructure as the only company conducting leading-edge semiconductor logic R&D and high-volume manufacturing in the U.S.

TEXT (TXT-001, TXT-003, TXT-005, filing 0000050863-26-000011):
<<<
[TXT-001]
| Overview
 |
We are a global designer and manufacturer of semiconductor products. The CPUs and other semiconductor solutions that we design, manufacture, market, sell and service are incorporated in computing and related end products and services, and utilized globally by consumers, enterprises, governments and educational organizations. Our customers primarily include OEMs, ODMs, CSPs, and other manufacturers and service providers, such as industrial and communication equipment manufacturers. We market and sell our products through a combination of direct sales through our global sales organization and indirect channels, including distributors, resellers, retailers and OEM partners. 
As a U.S.-based integrated design manufacturer, or IDM, in addition to designing CPUs and other semiconductor products, we develop leading-edge semiconductor manufacturing process technologies, or nodes, and advanced packaging technologies and predominantly manufacture our semiconductor products at our manufacturing and assembly and test facilities, many of which are in the U.S. We are the only company undertaking research, design and development of leading-edge and next generation semiconductor manufacturing technologies and high-volume manufacturing of logic semiconductors utilizing leading-edge nodes in the U.S., making us a strategically important company from both a national economic and national security perspective. In addition to manufacturing our own products, we offer third-party foundry services to external customers and aim to establish this business as a leading external foundry.
 | | | | |
Our Strategy
 |
For more than 50 years, we have contributed to the advancement of computing technology that powers the digital world. Building on our legacy of innovation, we are
[... הטקסט חתוך בדוח; בפרומפט המלא 97,476 תווים ...]
>>>

OUTPUT
{"skill_id": "BG-1", "version": 1, "text_he": "<background>",
 "competitors": ["<as named>"], "quotes": [{"text": "<exact quote>", "section": "..."}]}

```

## 5. פרומפט D2 לדוגמה — INTC

```
SYSTEM
You assist ValueCompass. Explain a company's ValueCompass results to an investor, using
ONLY the results provided below. Do not add facts, numbers or opinions that are not in
RESULTS. Do not tell the reader to buy or sell. Do not mention the current share price
(it changes daily). Write in Hebrew, plain and neutral.

STRUCTURE (two paragraphs, each at most 60 words)
1. Quality: what drove the Buffett and Graham quality scores - the strongest and weakest
   criteria, and the position versus peers as given in PEERS.
2. Value: what drove the Buffett and Graham values and what determines the buy price
   (margin of safety by quality; "not suitable" below quality 55; blocks or flags if any).
Refer to criteria by their names as given. Every number you write must appear in RESULTS or PEERS.

RESULTS (from the scoring run 2026-10-20:INTC; profile STANDARD):
{
 "run_id": "2026-10-20:INTC",
 "profile": "STANDARD",
 "industry": "Semiconductors",
 "fiscal_year": "FY2025",
 "quality": {
  "buffett": {
   "score": 15.9,
   "range": [
    12.2,
    31.2
   ],
   "status": "full",
   "coverage": 1.0,
   "criteria": [
    {
     "id": "B-3.1",
     "name": "Simple, understandable business",
     "points": 0.0,
     "range": [
      0.0,
      10.0
     ],
     "max": 10
    },
    {
     "id": "B-3.2",
     "name": "Moat",
     "points": 1.2,
     "range": [
      1.2,
      4.2
     ],
     "max": 10.0
    },
    {
     "id": "B-3.3",
     "name": "Consistent profitability",
     "points": 2.0,
     "range": [
      2.0,
      2.0
     ],
     "max": 15
    },
    {
     "id": "B-3.4",
     "name": "High return on capital",
     "points": 0.1,
     "range": [
      0.1,
      0.1
     ],
     "max": 15
    },
    {
     "id": "B-3.5",
     "name": "FCF / owner earnings",
     "points": 0.8,
     "range": [
      0.8,
      0.8
     ],
     "max": 15
    },
    {
     "id": "B-3.6",
     "name": "Strong balance sheet, reasonable debt",
     "points": 4.5,
     "range": [
      4.5,
      4.5
     ],
     "max": 10.0
    },
    {
     "id": "B-3.7",
     "name": "Management and capital allocation",
     "points": 2.0,
     "range": [
      2.0,
      6.0
     ],
     "max": 10
    },
    {
     "id": "B-3.8",
     "name": "Quality, sustainable growth",
     "points": 1.8,
     "range": [
      1.8,
      3.8
     ],
     "max": 15
    }
   ]
  },
  "graham": {
   "score": 48.4,
   "range": [
    43.6,
    49.6
   ],
   "status": "full",
   "coverage": 1.0,
   "criteria": [
    {
     "id": "G-3.1",
     "name": "Company size and business stability",
     "points": 6.0,
     "range": [
      6.0,
      10.0
     ],
     "max": 10
    },
    {
     "id": "G-3.2",
     "name": "Financial condition and liquidity",
     "points": 13.5,
     "range": [
      13.5,
      13.5
     ],
     "max": 15
    },
    {
     "id": "G-3.3",
     "name": "Low debt and balance-sheet conservatism",
     "points": 6.0,
     "range": [
      6.0,
      6.0
     ],
     "max": 15
    },
    {
     "id": "G-3.4",
     "name": "Earnings stability",
     "points": 5.0,
     "range": [
      5.0,
      5.0
     ],
     "max": 15
    },
    {
     "id": "G-3.5",
     "name": "Dividend history",
     "points": 0.0,
     "range": [
      0.0,
      0.0
     ],
     "max": 10
    },
    {
     "id": "G-3.6",
     "name": "Moderate earnings growth",
     "points": 0.3,
     "range": [
      0.3,
      0.3
     ],
     "max": 15
    },
    {
     "id": "G-3.7",
     "name": "Quality of equity and assets",
     "points": 9.8,
     "range": [
      9.8,
      9.8
     ],
     "max": 10
    },
    {
     "id": "G-3.8",
     "name": "Earnings quality and dilution",
     "points": 3.0,
     "range": [
      3.0,
      5.0
     ],
     "max": 10
    }
   ]
  }
 },
 "price": {
  "buffett": {
   "buy_price": null,
   "buy_price_state": "not_suitable",
   "margin_of_safety": null,
   "value_per_share": 1.32,
   "flags": [
    "growth_clipped (-42.8% -> 0.0%)",
    "growth_gate_failed (a: revenue rose in only 0 of 4 transitions; b: EPS fell >10% in 3 of 4",
    "G1_no_roll_latest_owner_earnings_below_5y_median"
   ]
  },
  "graham": {
   "buy_price": null,
   "buy_price_state": "not_suitable",
   "margin_of_safety": null,
   "value_per_share": null,
   "flags": []
  }
 },
 "key_metrics": {
  "Revenue": 52853000000.0,
  "Net income": -267000000.0,
  "Diluted EPS": -0.06,
  "ROE": -0.0025,
  "Free cash flow": -4949000000.0,
  "Debt / equity": 0.4076
 }
}

PEERS (computed by code; group profile STANDARD (fewer than 5 companies in industry Semiconductors: profile only), n = 19):
{
 "quality": {
  "buffett": {
   "score": 21.7,
   "range_midpoint": true,
   "percentile": 2.5,
   "n": 19
  },
  "graham": {
   "score": 46.6,
   "range_midpoint": true,
   "percentile": 17.5,
   "n": 19
  }
 },
 "metrics": {
  "revenue": {
   "label": "Revenue",
   "value": 52853000000.0,
   "percentile": 52.5,
   "n": 19,
   "lower_is_better": false
  },
  "net_income": {
   "label": "Net income",
   "value": -267000000.0,
   "percentile": 17.5,
   "n": 19,
   "lower_is_better": false
  },
  "eps": {
   "label": "Diluted EPS",
   "value": -0.06,
   "percentile": 17.5,
   "n": 19,
   "lower_is_better": false
  },
  "roe": {
   "label": "ROE",
   "value": -0.0025005736334646057,
   "percentile": 18.4,
   "n": 18,
   "lower_is_better": false
  },
  "fcf": {
   "label": "Free cash flow",
   "value": -4949000000.0,
   "percentile": 7.5,
   "n": 19,
   "lower_is_better": false
  },
  "leverage": {
   "label": "Debt / equity",
   "value": 0.4076355649670549,
   "percentile": 71.1,
   "n": 18,
   "lower_is_better": true
  }
 }
}

OUTPUT
{"skill_id": "AN-1", "version": 1, "quality_he": "<paragraph 1>", "value_he": "<paragraph 2>",
 "criteria_cited": ["<criterion id>", ...]}

```

## 6. הרצה יבשה — גדלי פרומפטים וקלטים חסרים

גדלים (תווים): KO: D1 70,021 / D2 5,638, MSFT: D1 74,065 / D2 5,656, JPM: D1 60,557 / D2 5,567, CB: D1 108,424 / D2 5,532, O: D1 51,614 / D2 6,157, AMT: D1 72,914 / D2 6,077, INTC: D1 97,476 / D2 5,797. הפרומפט הגדול ביותר (CB, D1) ~108K תווים (~30K טוקנים) — בגלל TXT-001 (עד 150K). קלטי D1 חסרים בתשובות השמורות של ק5א-3: MSFT: B3.1-Q5 (one_sentence) (שאלה שנדחתה בבדיקות; D1 ירוץ עם "not available" ל-one_sentence, או שיש להריץ שוב את A5 קודם — בהרצה האמיתית אחרי ק5ב יהיו תשובות חדשות).

## 7. הערכת קריאות להרצה האמיתית

חברה: D1 = 1 קריאה, D2 = 1 קריאה; עם ניסיון חוזר אחד בכל אחד — עד 4. לסט הפיתוח (7 חברות): 14 קריאות (עד 28). ל-54 חברות ה-golden: 108 (עד 216). קלט D1 גדול (עד ~30K טוקנים), פלט קטן. מכסה פנויה אחרי ק5ב מחר: 450 − כ-180 ≈ 270.

## 8. פקודה להרצה אחרי שהרצות ק5ב יסתיימו

```bash
.venv/Scripts/python.exe scripts/run_ai_k5c.py --answers scripts/ai_store/k5b/scoring/gemini-3.5-flash-lite/v3.1/assessments.jsonl --golden <golden שנוצר עם תשובות ק5ב>
```
(`--companies KO MSFT JPM CB O AMT INTC` ברירת מחדל; תהליך אחד בלבד; ללא `--no-calls`.) ה-`--golden` כאן חייב להיות ה-golden שנבנה עם `VC_AI_STORE`, כך שהציונים סופיים ולא טווחים.

## 9. מגבלות ושאלות פתוחות

1. מקור הציונים בק5ג: golden ללא תשובות AI ⇒ טווחים (מסומנים). ההרצה האמיתית דורשת golden חדש (תיקייה חדשה, בלי שינוי ב-golden הקיים).
2. מילות החפיר בעברית ורשימת המילים האסורות — נקודת מוצא; ייתכן שיידרש כיול אחרי הרצה אמיתית (טקסט תקין שנדחה בגלל ניסוח).
3. בדיקת "מקור החפיר בטקסט" היא לפי מילות מפתח — לא הבנת משמעות.
4. מדד ה-ROE של נדל"ן לא מוצג (אין הון ב-golden); FCF של בנק/ביטוח לא מוצג — כמו במפרט התצוגה.
