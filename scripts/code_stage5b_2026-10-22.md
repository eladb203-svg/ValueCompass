# דוח שלב ק5ב — תבנית 3.1 לשאלות הניקוד, וחילוץ נתונים ב-AI (B1–B14)

תאריך: 2026-10-22 · מודל מקובע: `gemini-3.5-flash-lite` (טמפרטורה 0, seed 20261021) · **הדוח חלקי: הרצות המודל נעצרו בגלל מכסה יומית (ראו סעיף 0).**

## עדכון לאחר ההחלטות (22.10, ‏~15:00) — הוחל בקוד, **עדיין לא נבדק מול המודל**

1. **commits:** שני ה-commits בוצעו (ההודעה השנייה: "model runs pending"). מסמך הסקילים הנוכחי: `docs/ai/ValueCompass_AI_Skills_Scoring_2026-10-22_14-49.*`; הגרסאות 21-19-28 ו-13-52 הוסרו; מפרט K6 — נשארה 14-39 (14-20 הוסר; 14-33 לא נגעתי בה).
2. **A11:** `share_pct` = אחוז מההכנסות כפי שדווח (לא נפח), נוסח בפלט של `scoring.yaml`. הסט של KO נשאר 2.
3. **ציטוטים:** כלל הציטוט נוסח בלי הסימן `...` ("Copy each quote as one continuous passage..."); ניסיון חוזר אחד כשהסיבה היחידה היא `quote_not_found`, עם ההערה "Quote not found verbatim: <120 תווים ראשונים>. Copy one continuous passage exactly as it appears in the TEXT." (גם ב-`extraction.yaml`). בדיקה חדשה ב-`tests/test_ai.py`.
4. **מכסה:** `src/ai/usage.py` — מונה יומי משותף בקובץ (`scripts/ai_store/usage.json`, יום לפי שעון פסיפיק, תקרה **450** לכל התהליכים יחד, כל ניסיון בקשה נספר) ונעילת תהליך יחיד (`run.lock`; תהליך חדש לא מתחיל כשיש פעיל ורענן). פעיל בלקוח אמיתי בלבד (לא בבדיקות). אותחל ל-500 להיום (מוצה).
5. **B14:** `src/ai/b14.py` — הרשימה נגזרת ממילון Part E לפי פרופיל: פריטי מנוע על דוח רווח והפסד / מאזן / תזרים (נוסף מקטע `X-CF`), נשלפים בקוד מתג (לא C5), שאינם מכוסים ב-B1–B13, וחסרי ערך מתג באותה שנה (מאזן: שתי שנים אחרונות). כולם בקריאה אחת לדוח. ספירה (פריט-שנה, 3 שנים אחרונות): JPM 66 נדרשו / 63 מכוסים בתגים / 3 נשאלים; USB 66/63/3; CB 87/80/7; PGR 87/65/22; O 93/73/20; AMT 93/71/22; PLD 93/79/14. פריט B14 שאינו ברשימת "מזין תת-פריט יחיד" → `pending`.

## 0. מצב השלב בקצרה

| חלק | מצב |
|---|---|
| סעיף 1 — קוד: תבנית 3.1 כברירת מחדל, עובדות A8 כולל פעילות מופסקת, בדיקת עקביות A11 + בדיקות | **הושלם**, כל הבדיקות עוברות (525 + בדיקות החילוץ, ראו סעיף 7) |
| סעיף 2 — הרצת ניקוד, 9 חברות | **חלקי**: 36 תשובות ייחודיות מתוך ~108 (MSFT 13, KO 12, INTC 11). UBER, JPM, CB, PGR, O, AMT לא הורצו. אין חישוב השפעה על הציון |
| סעיף 3 — תשתית חילוץ (yaml, מקטעים לפי כותרת, בדיקות, בקרות, אישורים, אחסון, תור אישורים, חיבור למנוע) | **הושלם ונבדק בלי קריאות מודל** (בדיקות יחידה + ריצה יבשה על 7 החברות) |
| סעיף 4 — מיפוי עמודות ה-CSV לבלוקים | **הושלם** (בלי קריאות מודל) |
| סעיף 5 — הרצת חילוץ על 7 חברות והשוואה ל-CSV | **לא הורץ** — המכסה היומית נגמרה |
| סעיף 6 (תוצאות חילוץ, השפעה על ציון) | **תלוי בסעיפים 2 ו-5** — לא קיים |
| סעיף 7 — commits | **לא בוצע** (ממתין להחלטה, ראו סעיף 8) |

### מה קרה עם המכסה
* בדיקה ישירה מול ה-API (קריאה אחת, "OK") החזירה `429 RESOURCE_EXHAUSTED`: **`generate_content_free_tier_requests, limit: 500, model: gemini-3.5-flash-lite`**, "retry in 19h22m" — כלומר האיפוס הוא ב-23.10.2026 סביב 10:00 שעון ישראל (חצות שעון הפסיפיק).
* **המכסה האמיתית היא 500 קריאות ליום למודל, לא 200.** המגבלה בקוד (`DEFAULT_RPD = 200`, `--rpd`) נשארה כפי שהיא, אבל היא **מונה לכל תהליך בנפרד** ולא ליום: ק5א-3 הריץ היום 434 קריאות (216 + 218), ואלה נספרות בנפרד מהמונה של התהליך.
* **טעות שלי:** הפעלתי את הרצת הניקוד פעמיים במקביל (ההפעלה הראשונה לא מתה כשהמעטפת שלה הסתיימה, והפעלתי שוב). שני תהליכים שאלו אותן שאלות זה לצד זה כ-8 דקות, עד שזיהיתי ועצרתי את השני: 23 מתוך 59 השורות בקובץ הן כפילויות (36 ייחודיות), כלומר ~23 קריאות מבוזבזות. סה"כ היום: ~434 (ק5א-3) + ~59 + בדיקה אחת ≈ 500.
* ההרצה נתקעה בשאלה INTC G3.1-Q4 (המכסה כבר נגמרה; שכבת הלקוח ממשיכה לנסות מחדש), עצרתי את התהליכים. **שום דבר לא נכתב ל-Supabase, `.env` לא שונה, לא נמחק דבר.**
* המלצה: מונה יומי משותף בקובץ (`scripts/ai_store/usage_<תאריך פסיפיק>.json`) שכל תהליך קורא ומעדכן, כך ש-`--rpd` הוא תקרה לכל היום ולא לתהליך. לא יישמתי — זה משנה את משמעות המגבלה שביקשתם להשאיר.

## 1. תבנית 3.1 כברירת מחדל (סעיף 1) — הושלם

**קוד**
* `src/ai/prompt.py`: `build_prompt(..., variant="3.1")` — ברירת המחדל 3.1; שדה `facts_check` לפני `answer` רק כשיש FACTS; כלל הציטוט המעודכן (קטע רציף אחד, לעולם לא `...`, לא מתוך FACTS). `prompt_version` נשמר `<גרסת skill>.1` (`assess.prompt_version_of`).
* `src/ai/skills/scoring.yaml` נוצר מחדש מהמסמך `ValueCompass_AI_Skills_Scoring_2026-10-22_13-52` (A8: עובדות כולל פעילות מופסקת ו"לא דווח"; A11: `code_check`). בדיקת הסקאלה מילה במילה מול Rulebook 19-26 נשארה ועוברת.
* **A8 — עובדות:** `src/ai/facts.py` — שנה שאינה בסדרה מוצגת **"not reported"** ולא 0; סריקה דטרמיניסטית של הערת הרכישות/הפעילות המופסקת (`discontinued_facts`): ירידות ערך ורווחי/הפסדי מכירה שנרשמו בפעילות מופסקת. דוגמת AMT (הפלט שהמודל יקבל כ-FACTS):
  ```
  Goodwill impairment (USD) per fiscal year, continuing operations: FY2021..FY2025: not reported
  Recorded in DISCONTINUED operations (from the notes; not in the series above): year not stated: loss on the sale 1.20bn; 2023: goodwill impairment 0.32bn.
  ```
  שני הפריטים שנדרשו נמצאו (הפסד המכירה של ATC TIPL, 1.2 מיליארד; ירידת ערך הודו 322 מיליון ב-2023). **מגבלה:** בהערה, משפט הפסד המכירה אינו כולל שנה, ולכן מוצג "year not stated" (לא ניחשתי את 2024). ל-MSFT: "none found".
* **A11 — בדיקת עקביות בקוד:** `checks.exposure_consistent` — לקוח >25% מאפשר 0; 10–25% מאפשר 1 (או 0 רק עם תלות אחרת מוצהרת: מוצר/רישיון/שוק); <10% מאפשר 2 (או תלות אחרת). אי-עקביות → ניסיון חוזר אחד עם ההערה "Your share_pct does not match the level you chose"; עדיין לא עקבי → נדחה עם `exposure_inconsistent`.
* `scripts/run_ai_k5a3.py`: ברירת מחדל `--prompt-version 3.1`; מזין `discontinued` ל-FACTS של A8.

**בדיקות** (`tests/test_ai.py`, 45 בדיקות): 3.1 ברירת מחדל ו-`facts_check` רק עם FACTS; גרסה 3 במפורש; שמירה תחת `prompt_version` ‏`2.1`; עובדות A8 (פעילות מופסקת, "not reported", "none found"); A11 — כל הרמות, ניסיון חוזר אחד עם ההערה, דחייה כשנשאר לא עקבי, וקבלה כשהניסיון השני עקבי.

## 2. ניקוד עם תבנית 3.1 — חלקי (59 תשובות)

אחסון: `scripts/ai_store/k5b/scoring/gemini-3.5-flash-lite/v3.1/assessments.jsonl` (לא ב-git). 59 שורות בקובץ, **36 ייחודיות** (23 כפילויות מההרצה הכפולה; הטוען לוקח את האחרונה): MSFT 13, KO 12, INTC 11 (עד G3.1-Q3). חסרות: UBER, JPM, CB, PGR, O, AMT, וגם INTC G3.1-Q4 ו-G3.8-Q3.

התאמה לקבוצת הייחוס v2 — **רק החברות שהושלמו**, מול ק5א-3 (v3.1):

| חברה | ק5א-3 (v3.1) | ק5ב (3.1 ברירת מחדל) |
|---|---|---|
| MSFT | 10/12 | 8/12 |
| KO | 11/12 | 10/12 |
| INTC | 9/13 | 6/13 (2 שורות חסרות בגלל המכסה) |

**אין להסיק מכאן אחוז כולל** — 3 חברות בלבד ואחת חלקית. אבל יש ממצאים מהותיים:

1. **דחיות: 8 מתוך 36 תשובות ייחודיות (7 × `quote_not_found`, 1 × `exposure_inconsistent`); על אותן 36 שאלות ב-ק5א-3 (v3.1): 2 דחיות.** בולט במיוחד: MSFT A3, A4, A5; INTC A1, A7, A8 (גם A5/B3.2-Q5). בחלק מהן המודל עדיין מכניס `...` לתוך הציטוט (למשל `"Threat actors... continuously undertake attacks"`, `"...As a result of our impairment tests"`) למרות שהוראת הציטוט החדשה אוסרת זאת במפורש ("never '...'"); באחרות הציטוט מרכיב שני קטעים שאינם סמוכים. ההוראה החדשה לא מונעת את ההתנהגות; הבדיקה בקוד תופסת אותה, אבל אלה תשובות שנזרקות (`insufficient_evidence`). ההרצה אינה זהה מבחינת המדגם (36 שאלות, 3 חברות), אך הכיוון ברור: **נסיגה**. נדרש ניסוי נוסף (למשל ניסוח מחדש, או ניסיון חוזר אחד על `quote_not_found` מסוג `...`) — לא נעשה בלי מכסה.
2. **A11 — KO נדחה `exposure_inconsistent`:** המודל קבע שלקוח (בקבוק) אחד הוא 10% מההכנסות וענה 2; לפי בדיקת הקוד 10–25% מאפשר 1 בלבד, ולכן אחרי ניסיון חוזר אחד התשובה נדחתה. ציפיית קבוצת הייחוס ל-KO היא 2. הכלל במסמך הניקוד סותר את שורת הייחוס; צריך להחליט איזה מהם נכון (ראו שאלות פתוחות).
3. **A11 — INTC:** ק5א-3 ענה 0 (לא תואם); ק5ב ענה **1 (תואם לציפייה 1)** — שלושה לקוחות מעל 10% (19%, 12%, 12%). זו התוצאה שהבדיקה אמורה לתקן.
4. **שורות הבדיקה הנוספות:** AMT A8, UBER A13, O A10 — **לא הורצו**. INTC A8 נדחה (`quote_not_found`, אותה בעיית `...`); ב-ק5א-3 ענה 0 (תואם).
5. MSFT A13: ק5ב ענה 0 (ציפייה 2; חלופה 1) לעומת 2 בק5א-3 — שינוי תשובה אחד, ללא דחייה.

השפעה על ציון (9 חברות): **לא חושבה** — נדרשת ההרצה המלאה. הפקודה מוכנה (ראו סעיף 9).

## 3. תשתית החילוץ (סעיף 3) — הושלם, נבדק בלי קריאות מודל

| רכיב | קובץ |
|---|---|
| skill-ים B1–B14 כנתונים: תבנית 2.1 + כללי ציטוט 3.1, פריטים (`item_key`), בקרה, כלל אישור, מפרט מקטעים | `src/ai/skills/extraction.yaml` |
| מקטעים חדשים **לפי כותרת** (הערה ממוספרת לפי כותרתה) ובחזרה ל**עוגנים** (חלונות טקסט סביב ביטויים) — הון/נזילות בנק, הון סטטוטורי ורול-פורוורד עתודות, השקעות ואיכות אשראי, חוב ופדיונות, שווי הוגן נדל"ן, הון/NCI/EPS, FFO/AFFO ב-MD&A, מאזן ודוח רווח והפסד | `src/ai/sections.py` (`ext_section`, `ext_sections`) |
| בדיקות פריט: JSON תקין (כולל הצלה של תשובה שנחתכה), ציטוט מילה במילה, המספר מופיע בציטוט אחרי המרת סקאלה (מיליון/אלף/מיליארד, סוגריים = שלילי, אחוזים), יחידה מותרת, התקופה שייכת לדוח, `value_state` עקבי (null רק עם NA/not_disclosed) | `src/ai/ext_checks.py` |
| בקרות בלוק: B1 (CET1 מול RWA ±0.2pp), B2 (סכום שורות = סך הלוואות ±1%), B4 (קטגוריות = סך השקעות ±2%), B5/B9 (גבולות 0–100%), B10 (שורות = סך נכסים ±0.5%; לא מזוהה >10% → ללא ציון מחיר גרהם), B14 (פי 3 משכנים); בקרות מנוע (נדל"ן) — Q6 (B6), רצועת כיסוי 0.8–1.25 (B8), E11 + RE29b (B12), טווח שווי/עלות 0.5–3× ובסיס (B7), רצועת הראוטר 5pp (B13) | `src/ai/ext_checks.py`, `src/scoring/ext_items.py` (`re_controls`) |
| קריאה לכל skill לדוח, אחסון קריאות (התשובה הגולמית נשמרת → בדיקות/בקרות/אישורים ניתנים להרצה מחדש בלי קריאה), אישורים, תור אישורים | `src/ai/extract.py` |
| חיבור למנוע: המרת פריטים ל-`reg` בצורת טוענות ה-CSV; `attach_ext` — **no-op בלי `VC_AI_EXT_STORE`**; פריטי `pending` נכנסים רק עם `VC_AI_EXT_UNAPPROVED=1` ומסמנים `extraction_unapproved` | `src/scoring/ext_items.py` |
| ריצה / השוואה / מיפוי | `scripts/run_ai_k5b_extract.py`, `scripts/ai_k5b_compare.py`, `scripts/ai_k5b_csv_map.py`, `scripts/ai_report_k5b.py` |

**סטטוסי אישור (ספק §7), כפי שמומשו:** `approved` (אוטומטי לפי כלל הבלוק) או `pending`; **תמיד `pending`:** B10, B11; **לפי בקרה:** B6 (Q6), B7 (בסיס + טווח), B8 (כיסוי מחוץ ל-0.8–1.25 = אוטומטי), B12 (E11 ו-RE29b), B13 (רחוק >5pp מהסף); **B14:** פריט שמזין שווי/מחיר קנייה/פרופיל, או שהבקרה סימנה אותו → `pending`. בלוק "אוטומטי" שבקרתו נכשלה → `pending` (החמרה שלי — המסמך לא מגדיר מה קורה אז). בקרה שאי אפשר לחשב (`na`) בבלוק "לפי בקרה" → `pending`. פריט שנדחה בבדיקות → `rejected` (נשמר עם הסיבה). `not_disclosed` של פריט שמופיע בדרך כלל רק ב-supplemental (תפוסה, תשואות, unencumbered, מכסת CapEx ועוד) מסומן `supplemental_only` — לא הורדתי 8-K.

**B14 (חילוץ כללי):** שאלה אחת לחברה לדוח, עם הפריטים החסרים בלבד. ספירה: לכל חברה נספרים פריטי-שנה (3 שנים אחרונות) מרשימת פריטי מנוע שיש להם תג XBRL במקרים רגילים; רק חוסר בתג נשאל. הרשימה (`B14_CANDIDATES` ב-`run_ai_k5b_extract.py`) היא רשימת הפריטים שזיהיתי כחסרים ב-golden; **לא גזרתי אותה ממילון Part E** (יש שם 190+ שורות; זו החלטה שצריך לאשר).

**בדיקות:** `tests/test_ai_extract.py` — 11 בדיקות (14 הבלוקים קיימים; הנחיה; בדיקות פריט עם כל סיבת דחייה; המרות מספר/סקאלה/סוגריים/אחוזים; כל הבקרות; כללי אישור; הצלת תשובה חתוכה; `ask_block` שומר קריאה פעם אחת ושורות נושאות בדיקה/בקרה/אישור; מקטעים לפי כותרת ולפי עוגן; מיפוי CSV; `to_reg`/`attach_ext`). **ריצה יבשה** (`run_ai_k5b_extract.py --no-calls`) על 7 החברות רצה עד הסוף, כולל חישוב בקרות מנוע הנדל"ן על קלט ריק.

**מקטעים (אורך בתווים) — בדיקה על 7 החברות:** כל המקטעים נמצאו (לאחר תיקון חיפוש המאזן/דוח רווח והפסד לטבלאות בלי `|`); הפרומפט הגדול ביותר ~64K תווים (~16K טוקנים). רוב המקטעים נחתכו ל-cap (`trimmed`) — סיכון: נתון שאינו בחלון לא יימצא; נדרש כיול לאחר הרצה אמיתית.

## 4. מיפוי עמודות ה-CSV לבלוקים (סעיף 4) — בלי קריאות מודל

הפלט המלא בנספח א׳ (ובקובץ `scripts/ai_store/k5b/csv_map.md`). סיכום:

| קובץ | שורות (פריט-שנה) | שמות פריטים | מכוסות בבלוק | לא מכוסות |
|---|---|---|---|---|
| `bank_regulatory.csv` | 268 (12 בנקים; שנה אחת, 2025) | 114 | 209 — B1: 102, B2: 107 | 59 שורות: funding:* (33), nonaccrual_loans, past_due_90_accruing:*, nco, avg_loans, acl_loans, preferred_stock |
| `insurance_regulatory.csv` | 127 (12 מבטחות; 2023–2025 רק ב-`adverse_prior_year_dev`) | 20 | 117 — B3: 18, B4: 99 | 10 שורות: total_fixed_income (6), debt_total (2), structural_event:* (2) |
| `realestate_extracted.csv` | 871 (11 חברות; 2020–2025 + רבעונים) | 210 | 791 — B5: 98, B6: 137, B7: 10, B8: 30, B9: 14, B10: 150, B11: 33, B12: 305, B13: 14 | 80 שורות: affo_br__*/affo_addback_* (גשר AFFO, ~55), rental_revenue_extracted, property_opex_extracted, bs_check__*, debt_total_bs, secured_debt, same_store_revenue_growth |

מועמדי B14 / מחוץ לבלוקים: כל מה שבעמודת "לא מכוסות" (לא ידוע אם המנוע זקוק להם בהכרח; `funding:*` ו-`nonaccrual`/`past_due` נכנסו לרשימת B14 של הבנקים). הערות: (א) שורות רבעוניות (`*_q`) ב-RE מסוכמות בטוען ל-שנה; ה-AI מחלץ שנתי — ההשוואה מדלגת על `_q`. (ב) `alm_disclosed` ב-CSV הוא טקסט, ב-AI 1/0. (ג) ב-B12, `recon_jv_other_adjust` ו-`recon_nci_adjust` ממופים ל-`recon_nci_jv` (שני עמודות CSV → פריט אחד ב-AI) ולכן השוואה לפי סכום.

## 5. הרצת חילוץ (סעיף 5) — לא הורצה

תכנון ההרצה (חברות: JPM, USB; CB, PGR; O, AMT, PLD; דוח אחרון בלבד כולל תקופות ההשוואה): בנק 2 בלוקים + B14 = 3 קריאות; מבטחת 2 + B14 = 3; נדל"ן 9 בלוקים (B5–B13) + B14 = 10. סה"כ **42 קריאות** (+ ניסיונות חוזרים), מתחת ל-70. הפקודה (אחרי איפוס המכסה):

```bash
.venv/Scripts/python.exe scripts/run_ai_k5b_extract.py --rpm 20 --rpd 70
.venv/Scripts/python.exe scripts/ai_k5b_compare.py
```

## 6. ספירת קריאות והערכת קיבולת (הערכה, לא מדידה)

קריאות לחברה, דוח אחרון: בנק ומבטחת — 3 (2 בלוקי פרופיל + B14); נדל"ן — 10; חברה כללית — 1 (B14, ואם אין פריט חסר — 0). טעינה ראשונית של 5 שנים: הדוח האחרון מכסה 3 שנים (דוח רווח והפסד) / 2 (מאזן), ולכן דרוש דוח אחד נוסף לשנים 4–5 בבלוקים רב-שנתיים (B5, B6, B12, B13, B14) — בערך פי 1.5–2 קריאות: בנק/מבטחת ~5–6, נדל"ן ~15–18. ועוד ~12 קריאות ניקוד + 1 סיווג לחברה. לכן חברה: כללית ~13; בנק/מבטחת ~19; נדל"ן ~30. **חברות ליום:** עם 200 קריאות (תקרת הקוד) ≈ 6–15; עם 500 (המכסה האמיתית שנמדדה) ≈ 16–38. **ללא אימות** — נדרשת הרצת סעיף 5 כדי לקבל ממוצע אמיתי.

## 7. בדיקות

`pytest` מלא: **525 עברו** (אחרי כל השינויים, כולל `tests/test_ai.py` 45 ו-`tests/test_ai_extract.py` 11).

## 8. החלטות ושאלות פתוחות

1. **להמתין לאיפוס (מומלץ) ולהשלים את סעיפים 2 ו-5 לפני ה-commits, או לבצע commit לקוד עכשיו (בלי תוצאות מודל)?** פירוט: commit א׳ (תבנית 3.1, עובדות A8, בדיקת A11) מוכן; commit ב׳ (תשתית החילוץ) מוכן אך לא נבדק מול תשובות מודל אמיתיות — ייתכנו תיקונים (כיול מקטעים, ניסוח).
2. **שורת הייחוס של KO ב-A11 (ציפייה 2) מול כלל העקביות (10% → רמה 1):** אחד מהם צריך להשתנות.
3. **`...` בציטוטים:** הוראה כתובה לא מספיקה (8 דחיות מתוך 36 לעומת 2 בק5א-3). רוצים ניסיון חוזר אחד על דחיית `quote_not_found` מסוג `...`?
4. **מונה מכסה יומי משותף** (סעיף 0) — מאשרים?
5. **רשימת B14:** לאשר את הרשימה הצרה, או לגזור ממילון Part E.

## 9. קבצים ופקודות

**חדשים:** `src/ai/ext_checks.py`, `src/ai/extract.py`, `src/ai/skills/extraction.yaml`, `src/scoring/ext_items.py`, `tests/test_ai_extract.py`, `scripts/run_ai_k5b_extract.py`, `scripts/ai_k5b_compare.py`, `scripts/ai_k5b_csv_map.py`, `scripts/ai_report_k5b.py`, `docs/ai/ValueCompass_AI_Skills_Scoring_2026-10-22_13-52.{md,docx}` (לא מעוקב עד כה), דוח זה.
**שונו:** `src/ai/prompt.py`, `src/ai/assess.py`, `src/ai/checks.py`, `src/ai/facts.py`, `src/ai/sections.py`, `src/ai/skills/scoring.yaml`, `scripts/run_ai_k5a3.py`, `tests/test_ai.py`. **לא נגע:** golden, `.env`, Supabase. `scripts/ai_store/**` ב-gitignore.

**commits מוצעים:** (א) "code K5b: scoring template 3.1, A8 facts incl. discontinued ops, A11 consistency check" — `prompt.py`, `assess.py`, `checks.py`, `facts.py`, `scoring.yaml`, `run_ai_k5a3.py`, `tests/test_ai.py`, מסמך ה-Skills Scoring. (ב) "code K5b: AI extraction B1–B14, checks, approvals, CSV comparison" — `ext_checks.py`, `extract.py`, `extraction.yaml`, `ext_items.py`, `sections.py`, `tests/test_ai_extract.py`, סקריפטי k5b, דוח זה.

**להשלמה אחרי האיפוס (23.10 ~10:00):**
```bash
GEMINI_RPM=20 .venv/Scripts/python.exe -u scripts/run_ai_k5a3.py --model gemini-3.5-flash-lite --prompt-version 3.1 --rpm 20 --rpd 200 --no-repeat --no-cls --out-root scripts/ai_store/k5b/scoring
```
(ממשיך מהמקום שנעצר: ~72 קריאות). בנוסף — ב**תהליך אחד בלבד**.

---

## נספח א׳ — מיפוי CSV → בלוק (פלט `ai_k5b_csv_map.py`)


## bank_regulatory.csv - 268 item-year rows, 114 distinct item names, 12 companies

Covered by a block: 209 rows (91 item names); not covered by any block: 59 rows (14 item groups).

| block | rows | AI item_keys | CSV years |
|---|---|---|---|
| B1 | 102 | cet1_capital, cet1_ratio_advanced, cet1_ratio_standardized, cet1_required_advanced, cet1_required_standardized, lcr_q4_average, rwa_advanced, rwa_standardized, scb, total_capital_advanced, total_capital_standardized, uninsured_deposits | 2025 |
| B2 | 107 | loan_line, total_loans | 2025 |

Not covered (B14 candidates / outside the blocks):

- `funding:deposits:*`: 11 rows
- `funding:long_term:*`: 10 rows
- `nonaccrual_loans`: 8 rows
- `funding:short_term:*`: 8 rows
- `past_due_90_accruing:total`: 7 rows
- `funding:repo:*`: 4 rows
- `nco_YYYY`: 3 rows
- `avg_loans_YYYY`: 2 rows
- `past_due_90_accruing:credit card`: 1 rows
- `past_due_90_accruing:wholesale`: 1 rows
- `past_due_90_accruing:government-insured mortgage`: 1 rows
- `past_due_90_accruing:consumer`: 1 rows
- `acl_loans_YYYY`: 1 rows
- `preferred_stock_YYYY`: 1 rows

## insurance_regulatory.csv - 127 item-year rows, 20 distinct item names, 12 companies

Covered by a block: 117 rows (16 item names); not covered by any block: 10 rows (4 item groups).

| block | rows | AI item_keys | CSV years |
|---|---|---|---|
| B3 | 18 | prior_year_dev, reg_capital_ratio | 2023, 2024, 2025 |
| B4 | 99 | alm_disclosed, cat_loss_latest, inv_cash, inv_equity, inv_fixed_maturities, inv_ig_fixed, inv_ig_share, inv_illiquid_loans, inv_other, inv_real_estate, inv_short_term, inv_total | 2025 |

Not covered (B14 candidates / outside the blocks):

- `total_fixed_income`: 6 rows
- `debt_total`: 2 rows
- `structural_event:FY2024`: 1 rows
- `structural_event:FY2023`: 1 rows

## realestate_extracted.csv - 871 item-year rows, 210 distinct item names, 11 companies

Covered by a block: 791 rows (183 item names); not covered by any block: 80 rows (27 item groups).

| block | rows | AI item_keys | CSV years |
|---|---|---|---|
| B5 | 98 | acquisition_invested, acquisition_yield, development_invested, development_yield, largest_tenant_share, occupancy, same_property_noi_growth | 2021, 2021-2025, 2022, 2022-2024, 2023, 2024, 2025 |
| B6 | 137 | maint_capex, straight_line_rent_affo, ti_lc | 2021, 2021-2025, 2021Q1, 2021Q2, 2021Q3, 2021Q4, 2022, 2022Q1, 2022Q2, 2022Q3, 2022Q4, 2023, 2023Q1, 2023Q2, 2023Q3, 2023Q4, 2024, 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025, 2025Q1, 2025Q2, 2025Q3, 2025Q4 |
| B7 | 10 | fair_value_real_estate | 2025 |
| B8 | 30 | committed_undrawn_facilities, debt_maturity_year1, debt_maturity_year2 | 2025 |
| B9 | 14 | unencumbered_assets_share, unencumbered_noi_share | 2021, 2023, 2024, 2025 |
| B10 | 150 | bsa_carry, bsa_carryfin, bsa_excl, bsa_inre, bsa_noi, bsa_other, bsa_wc | 2025 |
| B11 | 33 | diluted_includes_op, inc_share_of_bplp, op_units_book_value, op_units_count, partnership_units_weighted, shares_basis_override | 2021, 2022, 2023, 2024, 2025 |
| B12 | 305 | core_ffo_ps_reported, re29_nonre_impairments, re29_re_sale_gains, re29a_nonre_inv, re29b_fx_net, recon_gi_net, recon_nci_jv, recon_net_income, recon_re_da, reported_affo, reported_core_ffo, reported_ebitdare, reported_ffo | 2020, 2021, 2021Q1, 2021Q2, 2021Q3, 2021Q4, 2022, 2022Q1, 2022Q2, 2022Q3, 2022Q4, 2023, 2023Q1, 2023Q2, 2023Q3, 2023Q4, 2024, 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025, 2025Q1, 2025Q2, 2025Q3, 2025Q4 |
| B13 | 14 | profile_property_value, profile_rental_revenue, profile_total_assets, profile_total_revenue | 2025 |

Not covered (B14 candidates / outside the blocks):

- `rental_revenue_extracted`: 6 rows
- `property_opex_extracted`: 6 rows
- `affo_addback_non_re_depr`: 5 rows
- `affo_addback_amortization`: 5 rows
- `affo_br__straight_line_revenue`: 4 rows
- `affo_br__straight_line_expense`: 4 rows
- `affo_br__deferred_tax`: 4 rows
- `affo_br__non_re_da`: 4 rows
- `affo_br__amort_financing`: 4 rows
- `affo_br__other_expense`: 4 rows
- `affo_br__other_operating`: 4 rows
- `affo_br__capital_improvement`: 4 rows
- `affo_br__corporate_capex`: 4 rows
- `affo_br__unconsolidated_nci`: 4 rows
- `debt_total_bs`: 2 rows
- `affo_br__discontinued`: 2 rows
- `affo_br__nci_dividends`: 2 rows
- `affo_br__retirement_loss`: 2 rows
- `affo_br__consolidated_to_attributable`: 2 rows
- `same_store_revenue_growth`: 1 rows
- `secured_debt`: 1 rows
- `bs_check__finance_lease_current`: 1 rows
- `bs_check__finance_lease_noncurrent`: 1 rows
- `bs_check__mortgage_current`: 1 rows
- `bs_check__senior_notes_current`: 1 rows
- `bs_check__mortgage_noncurrent`: 1 rows
- `bs_check__senior_notes_noncurrent`: 1 rows
