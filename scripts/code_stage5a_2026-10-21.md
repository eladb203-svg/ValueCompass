# שלב קוד ק5א — תשתית ה-AI וסקילי הניקוד — 2026-10-21

**היקף:** `src/ai/` (חלוקה לפרקים, סקילים כנתון, תבנית אחת, לקוח Gemini, בדיקות קוד, אחסון בקבצים), חיבור התשובות למנועי האיכות, ומדרגה 3 של הנתב (C1). בלי DB, בלי commit. מפתחות לא הודפסו. מקורות: `docs/ai/` (מפרט 23-23, סקילי ניקוד 12-17, סקילים אחרים 12-39 — C1 בלבד), רולבוק 23-21.
**הערה:** בתיקייה קיים גם מפרט מאושר חדש יותר (`ValueCompass_AI_Spec_2026-10-21_10-37`: אין אישור מנהל לשיפוטי איכות; סקילי חילוץ עם בקרה). עבדתי לפי המפרט שציינת (23-23); ההבדל היחיד הרלוונטי — שיפוטי איכות נכנסים מיד לאחר בדיקות הקוד — זהה בשניהם.

## 0. תקציר

| נושא | תוצאה |
|---|---|
| pytest מלא | **500 עברו** (469 קודם + 31 ב-`tests/test_ai.py`). ללא תשובות AI כל התוצאות זהות (כל ה-golden ללא שינוי; ה-hook ריק כברירת מחדל) |
| מודל | **`gemini-3.5-flash-lite`** (קבוע בקוד, נרשם בכל תשובה; ניתן לעקוף ב-`VC_AI_MODEL`). המודל שב-`.env` (`gemini-3.8-flash`) החזיר `504 DEADLINE_EXCEEDED` אחרי 90 שניות על בקשה טריוויאלית (פעמיים); `3.7-flash` – 64 ש'; `3.6-flash`/`3.5-flash` – 503 "high demand"; `3.5-flash-lite` – כשנייה. לא שיניתי את `.env` |
| הרצה | 10 חברות (MSFT, KO, INTC, UBER, JPM, CB, PGR, O, AMT; ABNB רק C1 כי אינה ב-golden): **108 שאלות × 2 הרצות** = 216 קריאות + 3 קריאות C1 + כ-30 קריאות בדיקה/פיתוח |
| בדיקות קוד | 96% מהתשובות עברו (104/108); 4 נדחו → `insufficient_evidence` עם סיבה. ציטוטים שנמצאו מילה במילה: **98%** (190/194) |
| יציבות (שתי הרצות, טמפרטורה 0) | זהה ב-**89%** (96/108); בזוגות שנענו פעמיים: 92 זהים, 3 שונים בנקודה אחת, אף אחד בהפרש 2 |
| זמן ועלות | זמן מודל מצטבר (הרצה ראשית) 339 ש'; שעה ורבע בערך שעון קיר עם ניהול הקצב (719 ש' המתנה בחצי האחרון). 1.65M טוקני קלט + 23K פלט להרצה; תוכנית חינמית: $0 |
| השפעה על ציוני האיכות | לכל 9 חברות ה-golden — טבלה בסעיף 7. 45 החברות האחרות: **0 הבדלים** (נבדק בהשוואת golden) |

## 1. חלוקה לפרקים — `src/ai/sections.py`

פרקים: TXT-001 (Item 1), TXT-002 (Item 1A), TXT-003 (סעיף Competition בתוך Item 1), TXT-004 (Item 7 + Item 9A), TXT-005 (ביאור מגזרים). מימוש: כותרות Item בטקסט (עם דילוג על תוכן עניינים — הטווח הארוך ביותר עד כותרת Item כלשהי), ו-fallback לפי נושאים ל-10-K בפורמט אינדקס (INTC, C, WFC). פרק שלא נמצא ← `section_not_found`; פרק ארוך מהתקרה (150K/120K/200K תווים לפי פרק) נחתך מהסוף ומסומן `trimmed` (T בטבלה). פרק ראשי חסר ← השאלה `insufficient_evidence` בלי קריאה; פרק משני חסר (למשל Competition) מסומן בלבד.
ביאורים (`NOTE:…` ב-A8, A13, A14) **לא חולצו בשלב זה** — מסומן `note_not_included` בכל תשובה; ל-A13 ו-A8 נשלחו עובדות הקוד (רווח נקי / רכישות) בבלוק נפרד.

**תוצאה לכל 54 החברות (+BKNG, ABNB)** — האורך בתווים; `T` = נחתך; `NOT FOUND`; "not in cache" = אין 10-K בקאש (ה-10-K של MSFT/KO/INTC/UBER/ABNB/BKNG הורדו עכשיו, 14 בקשות SEC; MSFT FY2025 נוספה). בדוח זה המסמך האחרון בקאש (ל-MSFT זה FY2026; בהרצת ה-AI נבחר המסמך שתואם לשנה האחרונה של המנוע).
סיכום: מ-56 החברות — 41 עם דוח בקאש, 15 בלי (10 חברות כלליות + 5 managed care שלא הורדו); מבין ה-41: TXT-001 נמצא ב-40, TXT-002 ב-39, TXT-003 ב-34, TXT-004 ב-37, TXT-005 ב-28. חסרים בולטים: WFC/C/EQR (10-K בפורמט הפניות/נספח), USB (1A, 7), BAC (7), JPM (TXT-004 רק 2,246 תווים — Item 7 הפנייה), ביאור מגזרים ב-13 חברות.

| ticker | filing | TXT-001 | TXT-002 | TXT-003 | TXT-004 | TXT-005 |
| BAC | 0000070858-26-000157 | 38,337 | 117,247 | 1,335 | NOT FOUND | 24,999 |
| C | 0000831001-26-000011 | 150,000T | 120,000T | NOT FOUND | 143,630 | NOT FOUND |
| FITB | 0000035527-26-000124 | 41,438 | 81,535 | 856 | 200,000T | 25,000 |
| FLG | 0000910073-26-000025 | 82,709 | 83,904 | 1,528 | 79,918 | 24,999 |
| GS | 0000886982-26-000091 | 150,000T | 120,000T | 7,244 | 200,000T | 25,000 |
| JPM | 0001628280-26-008131 | 39,907 | 112,694 | 1,457 | 2,246 | NOT FOUND |
| KEY | 0001628280-26-010546 | 87,863 | 96,138 | 1,994 | 178,142 | NOT FOUND |
| MTB | 0000036270-26-000010 | 77,712 | 90,306 | 1,188 | 191,295 | 24,999 |
| PNC | 0000713676-26-000020 | 58,987 | 100,693 | 2,146 | 200,000T | 24,999 |
| TFC | 0000092230-26-000030 | 70,588 | 120,000T | 2,883 | 178,648 | NOT FOUND |
| USB | 0000036104-26-000011 | 83,812 | NOT FOUND | 2,037 | NOT FOUND | NOT FOUND |
| WFC | 0000072971-26-000133 | 150,000T | 120,000T | NOT FOUND | NOT FOUND | NOT FOUND |
| ADBE | not in cache | - | - | - | - | - |
| AVGO | not in cache | - | - | - | - | - |
| CRM | not in cache | - | - | - | - | - |
| DOW | not in cache | - | - | - | - | - |
| HD | not in cache | - | - | - | - | - |
| INTC | 0000050863-26-000011 | 82,407 | 9,125 | 649 | 60,005 | NOT FOUND |
| INTU | not in cache | - | - | - | - | - |
| KHC | not in cache | - | - | - | - | - |
| KO | 0001628280-26-010047 | 55,225 | 92,331 | 3,364 | 110,970 | NOT FOUND |
| MCD | not in cache | - | - | - | - | - |
| MSFT | 0001193125-26-323660 | 41,207 | 81,221 | 1,326 | 57,993 | 25,000 |
| NUE | not in cache | - | - | - | - | - |
| ORCL | not in cache | - | - | - | - | - |
| UBER | 0001543151-26-000015 | 30,941 | 120,000T | 2,443 | 87,514 | NOT FOUND |
| AFL | 0001628280-26-011402 | 45,448 | 80,412 | NOT FOUND | 154,381 | NOT FOUND |
| AIG | 0000005272-26-000023 | 43,526 | 111,670 | 938 | 200,000T | 13,372 |
| ALL | 0000899051-26-000031 | 60,493 | 55,190 | 468 | 200,000T | 24,999 |
| CB | 0000896159-26-000005 | 80,842 | 70,855 | 868 | 196,266 | 24,999 |
| CINF | 0000020286-26-000008 | 92,469 | 55,847 | NOT FOUND | 200,000T | 24,999 |
| HIG | 0000874766-26-000012 | 65,847 | 79,382 | 1,840 | 200,000T | 4,288 |
| MET | 0001099219-26-000013 | 103,330 | 75,544 | 3,709 | 200,000T | 22,041 |
| PGR | 0000080661-26-000086 | 61,792 | 72,321 | NOT FOUND | 1,614 | 24,998 |
| PRU | 0001137774-26-000048 | 82,884 | 74,728 | 959 | 200,000T | 25,000 |
| RNR | 0000913144-26-000012 | 132,461 | 59,835 | 1,218 | 193,848 | 24,282 |
| TRV | 0000086312-26-000065 | 150,000T | 81,396 | 1,126 | 200,000T | 13,306 |
| WRB | 0000011544-26-000005 | 100,377 | 66,021 | 2,608 | 91,693 | NOT FOUND |
| CI | 0001739940-26-000006 | 91,679 | 77,163 | 1,399 | 78,289 | 25,000 |
| CNC | not in cache | - | - | - | - | - |
| ELV | not in cache | - | - | - | - | - |
| HUM | not in cache | - | - | - | - | - |
| MOH | not in cache | - | - | - | - | - |
| UNH | not in cache | - | - | - | - | - |
| AMT | 0001053507-26-000035 | 49,173 | 73,890 | 2,052 | 127,440 | 19,746 |
| ARE | 0001035443-26-000013 | 25,088 | 120,000T | 1,957 | 200,000T | 25,000 |
| BXP | 0001037540-26-000006 | 71,550 | 98,425 | 1,996 | 156,430 | 21,718 |
| EQIX | 0001101239-26-000032 | 37,815 | 120,000T | 2,263 | 67,420 | 9,524 |
| EQR | 0001193125-26-083364 | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND |
| FRT | 0000034903-26-000017 | 20,464 | 57,815 | 1,019 | 76,120 | 15,050 |
| O | 0000726728-26-000011 | 44,036 | 84,424 | NOT FOUND | 81,461 | 5,903 |
| PLD | 0001193125-26-051453 | 40,866 | 52,879 | 2,087 | 68,934 | 24,999 |
| PSA | 0001628280-26-007696 | 31,223 | 50,361 | 1,210 | 114,174 | 4,591 |
| SPG | 0001104659-26-019419 | 30,729 | 84,303 | 1,268 | 99,470 | 9,246 |
| BKNG | 0001075531-26-000009 | 22,287 | 86,088 | 1,490 | 60,242 | NOT FOUND |
| ABNB | 0001559720-26-000004 | 22,379 | 120,000T | 590 | 51,529 | 23,203 |

## 2. סקילים כנתון ותבנית אחת

`src/ai/skills/scoring.yaml` — A1–A14 (מזהה, גרסה, כרטיס, שאלה, סקאלה **מילה במילה מהכרטיס**, מוקד ראיות, פרקים, שער, פלט נוסף, הערות פרופיל, טבלת נקודות) + התבנית המשותפת. `classification.yaml` — C1. `src/ai/prompt.py` מרכיב את ה-prompt מתבנית אחת. בדיקות: הסקאלה של כל סקיל מופיעה ברולבוק 23-21 (מילה במילה), וטבלת הנקודות בקובץ זהה לטבלה בקוד המנועים.
**ללא סטיות מהמסמכים.** תוספות שלי: בלוק `FACTS GIVEN BY CODE` (A8, A13) וסימון פרק לכל קטע בטקסט (`[TXT-001]`); ב-C1 רשימת הענפים נשלחת כשמות בלבד ו"גבולות" בבלוק נפרד (גרסה ראשונה עם "שם: הגדרה" גרמה למודל להחזיר את כל השורה כענף — נדחה).

## 3. לקוח Gemini — `src/ai/client.py`

מפתח מ-`.env` (לא מודפס); מודל קבוע; טמפרטורה 0; פלט JSON; ניסיון חוזר עד 6 פעמים (429 – השהיה לפי השרת והורדת הקצב בחצי; 5xx/timeouts/שגיאות רשת – גיבוי מעריכי; ניתוק רשת באמצע הרצה ראשונה הפיל אותה – תוקן והורצה ממשיכה). ניהול קצב: `GEMINI_RPM` (הרצתי 12), `GEMINI_TPM` (200K, הערכת טוקנים = תווים/3), `GEMINI_RPD`.
**מגבלות התוכנית החינמית:** דף המגבלות הרשמי (`ai.google.dev/gemini-api/docs/rate-limits`, עודכן 2026-10-15) **אינו מפרסם טבלה** של RPM/TPM/RPD לפי מודל; הוא אומר שהמגבלות תלויות בפרויקט ובמודל ונצפות ב-AI Studio. הכללים שפורסמו: מגבלות לפי **פרויקט** (לא לפי מפתח), RPD מתאפס בחצות שעון פסיפיק, מודלי preview מוגבלים יותר. מקורות לא רשמיים (פורום) מדווחים על ירידות חדות במכסת ה-RPD בחינמי, ולכן לא הסתמכתי עליהם. בפועל: לא התקבלה אף שגיאת 429 ב-216 הקריאות (RPM 12); הגבלה אמיתית שנתקלתי בה היא **זמינות המודלים** (504/503 לעיל). לדעת את המכסות המדויקות יש לפתוח את `aistudio.google.com/rate-limit` בחשבון.

## 4. בדיקות קוד (מפרט §4.4) — `src/ai/checks.py`

JSON תקין (ניסיון חוזר אחד); ערך מותר (2/1/0/null, תעשייה מהרשימה, עקביות `insufficient_evidence`); **ציטוט מילה במילה** אחרי נרמול (רווחים, כל סוגי הגרשיים/מירכאות, מקפים, מפריד תא טבלה `|`, ו-U+FFFD — סימן שאבד בקבצי הקאש במקום גרש); ציטוט אחד לפחות; ללא `...`/`…` בתוך ציטוט וללא ציטוט קצר מ-12 תווים; פלט נוסף: A5 (משפט ≤25 מילים כש-2, חובה), A4 (2–4 סיכונים כש-2), A7 (מקור ה-moat מהרשימה), A11 (חשיפה מרשימת הסוגים), A13 (רשימת פריטים). נדחה ← `insufficient_evidence` עם סיבה ב-`evidence.reasons`.
**סטיות/החלטות שלי:** (1) ציטוט כמחרוזת פשוטה מתקבל (עדיין נבדק מילה במילה) עם דגל `quote_as_string`; (2) תווית פרק שגויה בציטוט שנמצא בטקסט מתוקנת לפרק שבו הוא נמצא (דגל `quote_section_label_corrected`) — לא נדחית (המפרט דורש רק מציאת הטקסט); (3) לאחר הרצה ראשונה שינוי הנרמול (מפריד טבלה, פרק) הופעל מחדש על התשובות השמורות **בלי קריאה למודל** (`scripts/ai_recheck.py`): 8 שורות שהשתנו בהרצה הראשית, 4 בחוזרת.

## 5. אחסון — `scripts/ai_store/`

`assessments.jsonl` (הרצה ראשית) ו-`assessments_repeat.jsonl` (חוזרת): שורה לכל (חברה, שנת דוח, שאלה, גרסה) במבנה `ai_assessments`: `answer`, `state`, `evidence` (ציטוטים עם `found`, נימוק, פלט נוסף, דגלים, סיבות דחייה, `check_ok`, פרקים שנשלחו), `model`, `prompt_version`, `accession`, `approval_status` (approved), וכן `raw_answer`, `usage`. תשובה קיימת לאותה חברה/שנה/גרסה **אינה נשאלת שוב** (נבדק; גם `ask` עם כוח הוא רק לחוזרת).

## 6. חיבור למנוע

- `src/scoring/ai_items.py`: `ai_item(inp, skill, …)` מחליף את `ai_pending` ב-25 אתרים בחמשת הקבצים (`buffett`, `graham`, `bank`, `insurance`, `realestate`): תשובה ← `scored` (נקודות מהקוד: ×1, A7 ×0.5, A14 2→3 / 1→1.5 / 0→0); `insufficient_evidence` ← `missing` (דגל `ai_insufficient_evidence`, R16); אין תשובה ← `ai_pending` כמקודם. `ai_answers` נוסף לארבעת מחלקות הקלט ול-Views.
- **שערים:** A8 – רק כשהמנוע פתח את השער (`ai_pending` ב-3.7.3 קיים רק כשהרכישות מהותיות); A13 – רק ב-STANDARD/TECH (בבנק/ביטוח/נדל"ן אין פריט `ai_pending` כזה); A14 – רק בבנק בלי פירוט הלוואות. ה-runner שואל רק את מה שהמנוע השאיר כ-`ai_pending`, ולכן השערים נשמרים בשלמותם.
- `scripts/ai_runner.py` (`attach_ai`, פעיל רק עם `VC_AI_STORE`) מחבר את התשובות ל-runners; golden רגיל לא משתנה.
- **C1 ← נתב מדרגה 3:** `classify_industry` + `router.classify(..., ai=AIAnswer)`: מדרגה 3 מכריעה אוטומטית כשהיא מסכימה עם תוצאת ה-SIC (Other), אחרת `classification_pending` עד אישור מנהל. תוצאות:

| חברה | SIC | ענף ספק | לפני | תשובת AI (C1) | אחרי |
|---|---|---|---|---|---|
| ABNB | 7340 | Travel Services | Other, classification_pending | Other (ציטוט נמצא, נימוק: שוק מקוון להשכרות/חוויות שאינו קמעונאות סחורות ואינו תוכנה/פיננסי) | Other, decided (מדרגה AI, מסכים עם SIC), STANDARD |
| BKNG | 4700 | Travel Services | Other, classification_pending | Other (לאחר תיקון פורמט הרשימה; בהרצה הראשונה "שם + הגדרה" נדחה) | Other, decided, STANDARD |

הערה: בדוח ק4ב רשמתי SIC 7011 ל-ABNB מהזיכרון; ה-SIC בפועל 7340.

## 7. תשובות, בדיקות והשפעה על הציונים

### Answers per company and question


**MSFT** (filing 0001193125-26-323660, FY2026)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | Our products include operating systems, server applications, business solution applications, software developm… | The company clearly describes its products and services in plain words, such as operating systems, software development tools, video games, PCs, table… |
| B3.1-Q2 | 2 | 2 | yes | ok | Direct sales activities serve customers ranging from large multinational enterprises and public sector organiz… | The annual report clearly identifies the main customer types across various segments, explicitly mentioning consumers, businesses, and government enti… |
| B3.1-Q3 | 2 | insufficient | NO | ok | We operate our business and report our financial performance using three segments: Productivity and Business P… | The company's revenue sources are organized into clear and understandable segments, namely Productivity and Business Processes, Intelligent Cloud, and… |
| B3.1-Q4 | 2 | insufficient | NO | ok | We face intense competition across all markets for our products and services, which could adversely affect our… | The risk factors clearly delineate distinct, concrete business challenges such as intense market and platform competition, substantial capital and ope… |
| B3.1-Q5 | 2 | 2 | yes | ok | Founded in 1975, we develop and support software, services, devices, and solutions that deliver new value for … | The company develops and supports software, services, devices, and solutions for individuals and businesses, making money through cloud solutions, sub… |
| B3.2-Q4 | 2 | 2 | yes | ok | Our cloud business benefits from three economies of scale: datacenters that deploy computational resources at … | Microsoft is described as a market leader with a broad portfolio of technology solutions across cloud computing, AI, and productivity, leveraging sign… |
| B3.2-Q5 | 2 | 2 | yes | ok | Our cloud business benefits from three economies of scale: datacenters that deploy computational resources at … | The company benefits from clear economies of scale in its cloud business through datacenters that deploy computational resources at significantly lowe… |
| B3.7-Q3 | insufficient | insufficient | yes | ok (model: insufficient evidence) |  | The provided text does not contain sufficient information discussing the integration, stated results, growth generation, or goodwill impairments of ac… |
| B3.7-Q5 | 2 | 2 | yes | ok | Based on that evaluation, the Chief Executive Officer and Chief Financial Officer have concluded that these di… | Management demonstrates transparent, conservative, and consistent reporting with clear disclosures, effective internal controls, and no restatements o… |
| B3.8-Q6 | 2 | 2 | yes | ok | Our goal is to lead the industry in several distinct areas of technology over the long term, which we expect w… | Microsoft's growth is driven by clear and durable factors such as expanding market opportunities in cloud computing and artificial intelligence, new p… |
| G3.1-Q3 | 2 | 2 | yes | ok | We operate our business and report our financial performance using three segments: Productivity and Business P… | The company offers a broad portfolio of technology solutions across multiple segments (Productivity and Business Processes, Intelligent Cloud, and Mor… |
| G3.1-Q4 | 2 | 2 | yes | ok | Founded in 1975, we develop and support software, services, devices, and solutions that deliver new value for … | Microsoft is one of the central players in the technology industry, with a history dating back to 1975 and a broad portfolio spanning cloud computing,… |
| G3.8-Q3 | 1 | 0 | NO | ok | Other income (expense), net included $6.5 billion of net gains and $4.8 billion of net losses for fiscal years… | Reported earnings are impacted by material one-time items in multiple years, specifically net gains and losses from investments in OpenAI, which amoun… |

**KO** (filing 0001628280-26-010047, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | The Coca-Cola Company is a total beverage company, and beverage products bearing our trademarks, sold in the U… | The company clearly describes its main products and services in simple words, identifying itself as a total beverage company that owns, licenses, and … |
| B3.1-Q2 | 2 | 2 | yes | ok | We make our branded beverage products available to consumers throughout the world through our network of indep… | The annual report explicitly identifies the main customer types, including consumers, businesses, and retail establishments, as well as intermediaries… |
| B3.1-Q3 | 2 | 2 | yes | ok | Our Company operates in two lines of business: concentrate operations and finished product operations. | The company operates in clear, straightforward lines of business, generating revenues primarily through concentrate operations (selling beverage conce… |
| B3.1-Q4 | 2 | 2 | yes | ok | Unfavorable general economic and geopolitical conditions could negatively impact our financial results. | The annual report clearly details several concrete business risks, such as unfavorable macroeconomic and geopolitical conditions, increased competitio… |
| B3.1-Q5 | 2 | 2 | yes | ok | Our concentrate operations typically generate net operating revenues by selling beverage concentrates, sometim… | The business can be concisely explained in a single sentence of under 25 words detailing what is sold, to whom, and how money is made. |
| B3.2-Q4 | 2 | 2 | yes | ok | We own and market several of the world’s largest nonalcoholic sparkling soft drink brands, including Coca-Cola… | The company describes itself as a market leader possessing several of the world's largest nonalcoholic sparkling soft drink brands and leading brands … |
| B3.2-Q5 | 2 | 2 | yes | ok | Our competitive strengths include leading brands with high levels of consumer recognition and loyalty; a world… | The company possesses a concrete moat source through its leading global brands with high consumer recognition and loyalty, alongside a massive worldwi… |
| B3.7-Q5 | 2 | 2 | yes | ok | Management has discussed the development, selection and disclosure of critical accounting policies and estimat… | Management demonstrates clear reporting, consistent strategy, and discussion of critical policies with the Audit Committee, with no reported restateme… |
| B3.8-Q6 | 2 | 2 | yes | ok | Despite the dynamic world in which we are currently operating, we believe we are well positioned to create val… | Management describes clear and durable growth drivers across multiple categories and regions, including an expanding portfolio, ongoing pricing initia… |
| G3.1-Q3 | 2 | 2 | yes | ok | beverage products bearing our trademarks, sold in the United States since 1886, are now sold in more than 200 … | The company operates in more than 200 countries and territories with numerous brands, and no single customer exceeds 10% of revenue, nor is there a cr… |
| G3.1-Q4 | 2 | 2 | yes | ok | The Coca-Cola Company is a total beverage company, and beverage products bearing our trademarks, sold in the U… | The company operates globally in more than 200 countries and territories, with beverage products sold since 1886. It owns several of the world's large… |
| G3.8-Q3 | 0 | insufficient | NO | ok | These charges consisted of $960 million related to the impairment of our BodyArmor trademark, $97 million rela… | Reported earnings rely on material one-time items and impairments in most years, such as the $960 million BodyArmor trademark impairment and other cha… |

**INTC** (filing 0000050863-26-000011, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | We are a global designer and manufacturer of semiconductor products. | The company explicitly states that it is a global designer and manufacturer of semiconductor products, including CPUs, GPUs, and other semiconductor s… |
| B3.1-Q2 | 2 | 2 | yes | ok | The CPUs and other semiconductor solutions that we design, manufacture, market, sell and service are incorpora… | The annual report clearly identifies the main customer types, stating that products are utilized globally by consumers, enterprises, governments, and … |
| B3.1-Q3 | 2 | 2 | yes | ok | We are a global designer and manufacturer of semiconductor products. The CPUs and other semiconductor solution… | The company operates with a clear and understandable model, primarily generating revenue by designing, manufacturing, and selling semiconductor produc… |
| B3.1-Q4 | insufficient | insufficient | yes | ok (model: insufficient evidence) |  | The provided text only contains biographical information about executive officers, stock performance details, and share repurchase authorizations, but… |
| B3.1-Q5 | 2 | 2 | yes | ok | We are a global designer and manufacturer of semiconductor products. | The company provides a concise one-sentence description defining what is sold (CPUs and other semiconductor products), to whom (consumers, enterprises… |
| B3.2-Q4 | 2 | 2 | yes | ok | We are a global leader in the design and manufacturing of CPUs and other semiconductor products. | Intel is described as a global leader in the design and manufacturing of CPUs and other semiconductor products, and it maintains a leading market and … |
| B3.2-Q5 | 2 | 2 | yes | ok | Our x86 architecture and related CPU offerings have served as a foundational computing platform for over four … | The company possesses a concrete moat source in its established x86 architecture and extensive software ecosystem, which provides interoperability and… |
| B3.7-Q3 | 0 | 0 | yes | ok | $3.1 billion of non-cash charges associated with the impairment of goodwill for certain of our reporting units… | The provided text indicates material goodwill impairments and restructuring charges associated with acquisitions and business units in recent years, i… |
| B3.7-Q5 | insufficient | 1 | NO | REJECTED: quote_not_found | Adjusted Free Cash Flow is a non-GAAP financial measure and an additional means used by management to evaluate… | The company relies heavily on non-GAAP metrics such as Adjusted Free Cash Flow and discusses various adjusted metrics, alongside frequent restructurin… |
| B3.8-Q6 | 1 | insufficient | NO | ok | CCG revenue decreased $1.1 billion from 2024. Client revenue (collectively notebook and desktop) was $27.6 bil… | Growth partly depends on cyclicality, inventory level reductions, and wafer fabrication supply constraints that limit the company's ability to fully m… |
| G3.1-Q3 | 2 | 2 | yes | ok | While our IP rights are important to our success, our business as a whole is not significantly dependent on an… | The company states that its business as a whole is not significantly dependent on any single patent, copyright or other IP right, and the text provide… |
| G3.1-Q4 | 2 | 2 | yes | ok | We are a global designer and manufacturer of semiconductor products. | The company is recognized as a global leader and the only U.S.-based integrated design manufacturer undertaking leading-edge logic R&D and high-volume… |
| G3.8-Q3 | 0 | 0 | yes | ok | The Altera divestiture resulted in a pre-tax gain of $5.6 billion recognized within interest and other, net | Reported earnings rely significantly on one-time items across multiple fiscal years, such as large restructuring charges, asset impairments, and mater… |

**UBER** (filing 0001543151-26-000015, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | We connect consumers (“Rider(s)”) with independent providers of ride services (“Mobility Driver(s)”) for rides… | The company's main products and services are clearly described and can be named in simple words, such as ridesharing, meal delivery, grocery delivery,… |
| B3.1-Q2 | 2 | 2 | yes | ok | We connect consumers (“Rider(s)”) with independent providers of ride services (“Mobility Driver(s)”) for rides… | The annual report clearly identifies the main customer and user types on the platform, explicitly defining consumers, merchants, and business shippers… |
| B3.1-Q3 | 1 | 1 | yes | ok | As of December 31, 2025, we had three operating and reportable segments: Mobility, Delivery and Freight. | The company operates multiple segments including Mobility, Delivery, and Freight, and includes various offerings such as financial partnerships produc… |
| B3.1-Q4 | 2 | 2 | yes | ok | •Our business would be adversely affected if Drivers were classified as employees, workers or quasi-employees … | The annual report explicitly details several concrete business risks, such as driver employment classification, intense competition within the mobilit… |
| B3.1-Q5 | 2 | 2 | yes | ok | We connect consumers (“Rider(s)”) with independent providers of ride services (“Mobility Driver(s)”) for rides… | The annual report explicitly states what Uber sells, to whom, and how it makes money through connecting consumers, drivers, merchants, and shippers ac… |
| B3.2-Q4 | 2 | 2 | yes | ok | We believe our global leadership position—and the vast amount of marketplace data that comes along with it—mea… | The company states that it holds a global leadership position in its Mobility offering and benefits from scale and marketplace data. |
| B3.2-Q5 | 2 | 2 | yes | ok | Our massive, efficient, and intelligent network consists of hundreds of millions of Drivers, consumers, Mercha… | The company describes its massive network consisting of hundreds of millions of users, drivers, merchants, shippers, and carriers, which becomes smart… |
| B3.7-Q3 | 1 | 2 | NO | ok | Net cash used in investing activities was $3.6 billion for the year ended December 31, 2025, primarily consist… | The company has engaged in acquisitions over the past five years, including cash paid of $2,314 million in FY2021, $59 million in FY2022, and $815 mil… |
| B3.7-Q5 | 2 | 2 | yes | ok | Based upon that evaluation, our Chief Executive Officer and Chief Financial Officer concluded that, as of the … | The company exhibits clear reporting with an effective internal control over financial reporting as of December 31, 2025, no restatements reported, an… |
| B3.8-Q6 | 2 | insufficient | NO | ok | Overall Gross Bookings increased by $30.7 billion in 2025, up 19%, or 20% on a constant currency basis, compar… | The company exhibits clear and durable growth drivers across its multiple segments (Mobility, Delivery, and Freight), supported by expanding market pr… |
| G3.1-Q3 | 2 | 2 | yes | ok | As of December 31, 2025, we had three operating and reportable segments: Mobility, Delivery and Freight. Mobil… | The company operates in three large, fragmented segments (Mobility, Delivery, and Freight) across over 70 countries and does not report any customer a… |
| G3.1-Q4 | 2 | 2 | yes | ok | We believe our global leadership position—and the vast amount of marketplace data that comes along with it—mea… | The company explicitly states its global leadership position in its Mobility segment and highlights its massive, efficient, and intelligent network op… |
| G3.8-Q3 | 0 | 0 | yes | ok | Net income attributable to Uber Technologies, Inc. was $10.1 billion, which includes: (i) a $5.0 billion benef… | Reported earnings rely significantly on material one-time items and large non-operating fluctuations across the majority of the reported fiscal years,… |

**JPM** (filing 0001628280-26-008131, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | The Firm is a leader in investment banking, financial services for consumers and small businesses, commercial … | The annual report clearly identifies the company's main lines of business and services in simple terms, such as investment banking, financial services… |
| B3.1-Q2 | 2 | 2 | yes | ok | Under the J.P. Morgan and Chase brands, the Firm serves millions of customers, predominantly in the U.S., and … | The annual report clearly identifies the main customer types and segments served by the firm, including consumers, small businesses, and corporate, in… |
| B3.1-Q3 | 1 | 1 | yes | ok | For management reporting purposes, the Firm has three reportable business segments - Consumer & Community Bank… | The company operates across multiple segments including Consumer & Community Banking, Commercial & Investment Bank, Asset & Wealth Management, and Cor… |
| B3.1-Q4 | 2 | 2 | yes | ok | •Legal and Regulatory risks, including the impact of extensive supervision and regulation, as well as changes … | The annual report explicitly details and categorizes multiple concrete business risks, notably legal and regulatory risks, market risks, credit risks,… |
| B3.1-Q5 | 2 | 2 | yes | ok | The Firm is a leader in investment banking, financial services for consumers and small businesses, commercial … | The annual report clearly outlines that JPMorgan Chase is a financial services firm providing investment banking, consumer and small business financia… |
| B3.2-Q4 | 2 | insufficient | NO | ok | JPMorgan Chase & Co. (“JPMorganChase” or the “Firm”, NYSE: JPM), a financial holding company incorporated unde… | The company explicitly identifies itself as a market leader across multiple core areas of financial services. Furthermore, it operates in highly compe… |
| B3.2-Q5 | 2 | 2 | yes | ok | Under the J.P. Morgan and Chase brands, the Firm serves millions of customers, predominantly in the U.S., and … | The report highlights the Firm's prominent scale and leadership across multiple financial services sectors globally, operating under recognized brands… |
| B3.7-Q5 | 2 | 2 | yes | ok | Based on that evaluation, the Chairman and Chief Executive Officer and the Chief Financial Officer concluded t… | Management evaluated the disclosure controls and procedures and concluded they were effective as of December 31, 2025. Additionally, there were no cha… |
| B3.8-Q6 | insufficient | insufficient | yes | ok (model: insufficient evidence) |  | The provided text from the annual report outlines business overviews, regulatory environments, human capital statistics, and controls, but it does not… |
| G3.1-Q3 | 2 | 2 | yes | ok | Under the J.P. Morgan and Chase brands, the Firm serves millions of customers, predominantly in the U.S., and … | The company operates as a diversified financial services firm with multiple reportable business segments and serves millions of customers predominantl… |
| G3.1-Q4 | 2 | 2 | yes | ok | JPMorgan Chase & Co. (“JPMorganChase” or the “Firm”, NYSE: JPM), a financial holding company incorporated unde… | The company is a leading financial services firm with multi-trillion dollar assets and operates as a central player across multiple segments including… |

**CB** (filing 0000896159-26-000005, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | With operations in 54 countries and territories, Chubb provides commercial and consumer P&C insurance, A&H, re… | The company clearly describes its main products and services in plain words throughout the Business section, specifically identifying commercial and c… |
| B3.1-Q2 | 2 | 2 | yes | ok | We serve multinational corporations, mid-size and small businesses with property and casualty insurance and ri… | The annual report clearly identifies the main customer types, including businesses (such as multinational corporations, mid-size and small businesses)… |
| B3.1-Q3 | 1 | 1 | yes | ok | We generate earnings from three primary sources of income: P&C underwriting income, investment income, and lif… | The company generates earnings from three primary sources of income (P&C underwriting income, investment income, and life segment income) and operates… |
| B3.1-Q4 | 2 | 2 | yes | ok | Our results of operations or financial condition could be adversely affected by the occurrence of natural and … | The filing clearly outlines several concrete business risks, such as natural and man-made disasters, loss reserve inadequacies, and investment perform… |
| B3.1-Q5 | insufficient | insufficient | yes | REJECTED: quote_not_found | Chubb Limited... [is] a global insurance and reinsurance organization, serving the needs of a diverse group of… | The sentence clearly states what is sold (commercial and consumer P&C, A&H, reinsurance, and life insurance), to whom (a diverse group of clients worl… |
| B3.2-Q4 | 2 | 2 | yes | ok | We have grown our business through increased premium volume, expansion of product offerings and geographic rea… | Chubb describes itself as a global property and casualty leader with operations across 54 countries and territories, and maintains a stable market pos… |
| B3.2-Q5 | 2 | 2 | yes | ok | Our international operations have the distinct advantage of being part of one of the few international insuran… | The company has a clear competitive advantage derived from its global infrastructure and network of licensed companies enabling locally admitted polic… |
| B3.7-Q3 | 2 | 2 | yes | ok | Based on our impairment testing for 2025, we determined no impairment was required and none of our reporting u… | The annual report indicates that acquisitions were integrated and generated growth, and there were no goodwill impairments. |
| B3.7-Q5 | 2 | 2 | yes | ok | The facilities noted above require that we maintain certain covenants, all of which have been met at December … | The reporting is clear with consistent strategy and no restatements or governance disputes, fitting the criteria for a score of 2. |
| B3.8-Q6 | 2 | 2 | yes | ok | We have grown our business through increased premium volume, expansion of product offerings and geographic rea… | Management describes recurring growth drivers including increased premium volume, expansion of product offerings and geographic reach across 54 countr… |
| G3.1-Q3 | 2 | 2 | yes | ok | With operations in 54 countries and territories, Chubb provides commercial and consumer P&C insurance, A&H, re… | The company operates across multiple diversified insurance segments globally, with no single customer accounting for over 10% of revenue, and no criti… |
| G3.1-Q4 | 2 | 2 | yes | ok | Chubb was incorporated in 1985 at which time it opened its first business office in Bermuda and continues to m… | Chubb Limited is described as a global property and casualty leader with operations spanning 54 countries and territories, ranking it as a central pla… |

**PGR** (filing 0000080661-26-000086, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | Our insurance subsidiaries write personal and commercial auto insurance, personal residential property insuran… | The company clearly describes its main products and services in plain words, specifically detailing various types of insurance such as personal and co… |
| B3.1-Q2 | 2 | 2 | yes | ok | Progressive’s vision is to become consumers’, agents’, and business owners’ number one destination for insuran… | The annual report clearly identifies the main customer types, including consumers, businesses, and agency intermediaries, across multiple segments suc… |
| B3.1-Q3 | 2 | 2 | yes | ok | Our insurance subsidiaries write personal and commercial auto insurance, personal residential property insuran… | The company earns money primarily through insurance premiums from Personal Lines and Commercial Lines, alongside investment income from its portfolio.… |
| B3.1-Q4 | 2 | 2 | yes | ok | Our risk categories include: •Insurance Risks - risks associated with assuming, or indemnifying for, the losse… | Management divides the company's risks into five broad categories in Item 1A, including Insurance Risks, Operating Risks, and Market Risks, making the… |
| B3.1-Q5 | 2 | 2 | yes | ok | The Progressive Corporation, an insurance holding company, has insurance and non-insurance subsidiaries and af… | The company can be explained in a single sentence under 25 words that covers what is sold, to whom, and how money is made. |
| B3.2-Q4 | 2 | 2 | yes | ok | We ranked second in market share in the U.S. private passenger auto insurance market, based on 2024 premiums w… | The company holds leading market positions, ranking second in the U.S. private passenger auto insurance market and number one in the U.S. commercial a… |
| B3.2-Q5 | 2 | 2 | yes | ok | We have a substantial amount of “know-how” developed from years of experience with usage-based insurance, and … | The company has established significant competitive advantages through its proprietary data assets and know-how derived from usage-based insurance, as… |
| B3.7-Q5 | 2 | 2 | yes | ok | Based on that review and evaluation, the Chief Executive Officer and Chief Financial Officer concluded that ou… | Management evaluated the company's disclosure controls and procedures and concluded they were effective, with no material weaknesses or changes affect… |
| B3.8-Q6 | 2 | 2 | yes | ok | We seek to refine our product segmentation, underwriting models, and pricing over time, and we regularly eleva… | The company describes clear and durable growth drivers, including recurring product enhancements, expanding market segmentation, pricing power through… |
| G3.1-Q3 | 2 | 2 | yes | ok | The Personal Lines segment accounted for 87% of our total net premiums written in 2025, 85% in 2024, and 84% i… | The company operates across multiple insurance segments and markets without any individual customer accounting for more than 10% of revenue, and no si… |
| G3.1-Q4 | 2 | 2 | yes | ok | We ranked second in market share in the U.S. private passenger auto insurance market, based on 2024 premiums w… | The company holds a central and prominent player status in its industry, explicitly ranking second in market share in the U.S. private passenger auto … |

**O** (filing 0000726728-26-000011, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | Our primary business is the acquisition, ownership, and active management of freestanding commercial propertie… | The company's primary business activities are clearly described in plain words as the acquisition, ownership, and active management of freestanding co… |
| B3.1-Q2 | insufficient | 2 | NO | REJECTED: quote_not_found | Our primary business is the acquisition, ownership, and active management of freestanding commercial propertie… | The company clearly identifies its customers as tenants and operators of commercial properties under net lease agreements, spanning specific industrie… |
| B3.1-Q3 | 2 | 2 | yes | ok | Our primary business is the acquisition, ownership, and active management of freestanding commercial propertie… | The company's primary business model is the ownership and active management of freestanding commercial properties leased under long-term net lease agr… |
| B3.1-Q4 | 2 | 2 | yes | ok | The success of our business is dependent on the financial stability of the clients occupying our properties. A… | The risk factors section clearly identifies and highlights several distinct, concrete business risks, such as client financial stability and bankruptc… |
| B3.1-Q5 | 2 | 2 | yes | ok | Our primary business is the acquisition, ownership, and active management of freestanding commercial propertie… | The company's primary business of acquiring and leasing freestanding commercial properties under net lease agreements to commercial operators to gener… |
| B3.2-Q4 | 2 | 2 | yes | ok | Realty Income (NYSE: O), an S&P 500 company, is real estate partner to the world's leading companies®. | Realty Income is identified as an S&P 500 company and a market leader in net lease real estate, possessing substantial scale with over 15,500 properti… |
| B3.2-Q5 | 2 | 2 | yes | ok | We believe that our large U.K. and European net lease real estate presence provides us with a meaningful compe… | The company possesses concrete moat sources including scale advantages, proprietary data analytics, and operational capabilities that would be difficu… |
| B3.7-Q5 | 2 | 2 | yes | ok | Based on the foregoing, our Chief Executive Officer and Chief Financial Officer concluded that as of December … | Management demonstrates clear reporting and consistent strategy, explicitly noting effective disclosure controls and procedures as well as effective i… |
| B3.8-Q6 | 2 | 2 | yes | ok | Under a net lease structure, clients are typically responsible for most or all property-level operating expens… | The company's growth drivers are clear and durable, supported by embedded contractual rent escalations within net lease agreements, geographic expansi… |
| G3.1-Q3 | 2 | 2 | yes | ok | No individual client’s revenue represented more than 10% of our total revenue for each of the years ended Dece… | The company explicitly discloses that no individual client exceeds 10% of total revenue. Furthermore, the portfolio is highly diversified across over … |
| G3.1-Q4 | 2 | 2 | yes | ok | Realty Income (NYSE: O), an S&P 500 company, is real estate partner to the world's leading companies®. Founded… | The company is an S&P 500 company founded in 1969 with over 15,500 properties, positioning it as one of the central players in its industry. |

**AMT** (filing 0001053507-26-000035, FY2025)

| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |
|---|---|---|---|---|---|---|
| B3.1-Q1 | 2 | 2 | yes | ok | Our primary business is the leasing of space on communications sites to wireless service providers, radio and … | The company's primary business and products can be clearly named in plain words, as it operates as a real estate investment trust primarily leasing sp… |
| B3.1-Q2 | insufficient | 2 | NO | REJECTED: quote_not_found | Our primary business is the leasing of space on communications sites to wireless service providers, radio and … | The annual report clearly identifies the main types of customers, including wireless service providers, broadcast companies, government agencies, and … |
| B3.1-Q3 | 2 | 2 | yes | ok | Our primary business is the leasing of space on communications sites to wireless service providers, radio and … | The company's primary revenue source is the leasing of space on multitenant communications sites and data centers, representing a clear property leasi… |
| B3.1-Q4 | 2 | 2 | yes | ok | A significant decrease in leasing demand for our communications infrastructure would materially and adversely … | The risk factors clearly delineate specific business risks, including leasing demand reduction, customer concentration and financial strength, and the… |
| B3.1-Q5 | 2 | 2 | yes | ok | Our primary business is the leasing of space on communications sites to wireless service providers, radio and … | The business can be concisely explained in a single sentence covering what is sold, to whom, and how money is made, using exact terms from the text. |
| B3.2-Q4 | 2 | 2 | yes | ok | We are one of the largest global real estate investment trusts and a leading independent owner, operator and d… | The company states that it is one of the largest global real estate investment trusts and a leading independent owner, operator, and developer of mult… |
| B3.2-Q5 | 2 | 2 | yes | ok | Rental payments vary considerably depending upon numerous factors, including, but not limited to, amount, type… | The company benefits from irreplaceable asset locations and high switching costs for tenants due to the lack of suitable alternative sites and the hig… |
| B3.7-Q3 | 2 | 2 | yes | ok | During the year ended December 31, 2025, we grew our portfolio of communications real estate through the acqui… | The company successfully completed corporate acquisitions and construction of communications sites while maintaining performance, with no material goo… |
| B3.7-Q5 | 2 | 2 | yes | ok | Based on this assessment, management concluded that, as of December 31, 2025, our internal control over financ… | The company exhibits clear reporting, effective internal controls without material weaknesses, and consistent strategy execution, with management conc… |
| B3.8-Q6 | 2 | 2 | yes | ok | Our property operations have generated consistent growth in revenue and typically have low cash flow volatilit… | The company's growth drivers are clear and durable, supported by long-term tenant leases with contractual rent escalations, consistent demand driven b… |
| G3.1-Q3 | 1 | 0 | NO | ok | T-Mobile 18 % 19 % 19 % AT&T 17 % 18 % 18 % Verizon Wireless 14 % 13 % 14 % Telefónica 10 % 10 % 10 % | The company discloses individual customers representing between 10% and 25% of consolidated operating revenues, specifically T-Mobile at 18%, AT&T at … |
| G3.1-Q4 | 2 | 2 | yes | ok | We are one of the largest global real estate investment trusts and a leading independent owner, operator and d… | The company is one of the largest global real estate investment trusts and a leading independent owner, operator, and developer of multitenant communi… |

### Totals

- Rows: 108 (calls made: 108; no call because the primary section was not found: 0); answered 101, insufficient evidence 7.
- Check pass rate (rows with a call): 104/108 = 96%.
- Quotes found verbatim: 190/194 = 98% (all quotes, including those of rejected answers).
- Answer distribution (answered): {0: 4, 1: 7, 2: 90}.
- Stability (same state and answer in both runs): 96/108 = 89%; among pairs answered twice: differences {0: 92, 1: 3}.
- Model time (sum of call latencies, main run): 339 s; tokens in 1,650,724 / out 23,175.

### Effect on the quality scores (before = golden 2026-10-20, after = golden with the AI answers)

| Company | Model | Criterion | Before: normalized | After: normalized | Before: min–max | After: min–max |
|---|---|---|---:|---:|---|---|
| MSFT | buffett | 3.1 Simple, understandable business | - | 10.00 | 0.00–10.00 | 10.00–10.00 |
| MSFT | buffett | 3.2 Moat | 9.73 | 9.81 | 6.81–9.81 | 9.81–9.81 |
| MSFT | buffett | 3.7 Management and capital allocation | 9.54 | 9.66 | 5.73–9.73 | 7.73–9.73 |
| MSFT | buffett | 3.8 Quality, sustainable growth | 12.79 | 13.08 | 11.08–13.08 | 13.08–13.08 |
| MSFT | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| MSFT | graham | 3.8 Earnings quality and dilution | 8.31 | 7.65 | 6.65–8.65 | 7.65–7.65 |
| KO | buffett | 3.1 Simple, understandable business | - | 10.00 | 0.00–10.00 | 10.00–10.00 |
| KO | buffett | 3.2 Moat | 8.92 | 9.25 | 6.25–9.25 | 9.25–9.25 |
| KO | buffett | 3.7 Management and capital allocation | 8.20 | 8.56 | 6.56–8.56 | 8.56–8.56 |
| KO | buffett | 3.8 Quality, sustainable growth | 10.64 | 11.22 | 9.22–11.22 | 11.22–11.22 |
| KO | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| KO | graham | 3.8 Earnings quality and dilution | 8.34 | 6.67 | 6.67–8.67 | 6.67–6.67 |
| INTC | buffett | 3.1 Simple, understandable business | - | 10.00 | 0.00–10.00 | 8.00–10.00 |
| INTC | buffett | 3.2 Moat | 1.66 | 4.16 | 1.16–4.16 | 4.16–4.16 |
| INTC | buffett | 3.7 Management and capital allocation | 3.33 | 2.50 | 2.00–6.00 | 2.00–4.00 |
| INTC | buffett | 3.8 Quality, sustainable growth | 2.03 | 2.76 | 1.76–3.76 | 2.76–2.76 |
| INTC | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| INTC | graham | 3.8 Earnings quality and dilution | 3.75 | 3.00 | 3.00–5.00 | 3.00–3.00 |
| UBER | buffett | 3.1 Simple, understandable business | - | 9.00 | 0.00–10.00 | 9.00–9.00 |
| UBER | buffett | 3.2 Moat | 3.33 | 6.00 | 2.00–6.00 | 6.00–6.00 |
| UBER | buffett | 3.7 Management and capital allocation | 7.32 | 7.39 | 4.39–8.39 | 7.39–7.39 |
| UBER | buffett | 3.8 Quality, sustainable growth | 11.54 | 12.00 | 10.00–12.00 | 12.00–12.00 |
| UBER | graham | 3.1 Company size and business stability | 8.32 | 8.99 | 4.99–8.99 | 8.99–8.99 |
| UBER | graham | 3.8 Earnings quality and dilution | 5.98 | 4.78 | 4.78–6.78 | 4.78–4.78 |
| JPM | buffett | 3.1 Simple, understandable business | - | 9.00 | 0.00–10.00 | 9.00–9.00 |
| JPM | buffett | 3.2 Moat | 6.67 | 8.00 | 4.00–8.00 | 8.00–8.00 |
| JPM | buffett | 3.7 Management and capital allocation | 8.33 | 8.67 | 6.67–8.67 | 8.67–8.67 |
| JPM | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| CB | buffett | 3.1 Simple, understandable business | - | 8.75 | 0.00–10.00 | 7.00–9.00 |
| CB | buffett | 3.2 Moat | 9.49 | 9.70 | 5.70–9.70 | 9.70–9.70 |
| CB | buffett | 3.7 Management and capital allocation | 8.98 | 9.39 | 5.39–9.39 | 9.39–9.39 |
| CB | buffett | 3.8 Quality, sustainable growth | 15.00 | 15.00 | 12.69–15.00 | 15.00–15.00 |
| CB | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| PGR | buffett | 3.1 Simple, understandable business | - | 10.00 | 0.00–10.00 | 10.00–10.00 |
| PGR | buffett | 3.2 Moat | 7.64 | 8.58 | 4.58–8.58 | 8.58–8.58 |
| PGR | buffett | 3.7 Management and capital allocation | 9.94 | 9.95 | 7.45–9.95 | 9.95–9.95 |
| PGR | buffett | 3.8 Quality, sustainable growth | 15.00 | 15.00 | 12.69–15.00 | 15.00–15.00 |
| PGR | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| O | buffett | 3.1 Simple, understandable business | - | 10.00 | 0.00–10.00 | 8.00–10.00 |
| O | buffett | 3.2 Moat | 8.19 | 9.18 | 3.72–9.18 | 9.18–9.18 |
| O | buffett | 3.7 Management and capital allocation | 6.67 | 7.50 | 5.00–7.50 | 7.50–7.50 |
| O | buffett | 3.8 Quality, sustainable growth | 8.74 | 9.58 | 7.58–9.58 | 9.58–9.58 |
| O | graham | 3.1 Company size and business stability | 10.00 | 10.00 | 6.00–10.00 | 10.00–10.00 |
| AMT | buffett | 3.1 Simple, understandable business | - | 10.00 | 0.00–10.00 | 8.00–10.00 |
| AMT | buffett | 3.2 Moat | 7.80 | 9.00 | 3.55–9.00 | 9.00–9.00 |
| AMT | buffett | 3.7 Management and capital allocation | 8.48 | 9.09 | 5.09–9.09 | 9.09–9.09 |
| AMT | buffett | 3.8 Quality, sustainable growth | 8.40 | 9.28 | 7.28–9.28 | 9.28–9.28 |
| AMT | graham | 3.1 Company size and business stability | 10.00 | 9.00 | 6.00–10.00 | 9.00–9.00 |

| Company | Model | Score before | Score after | Range before | Range after | Coverage before | Coverage after | Buy price before | Buy price after |
|---|---|---:|---:|---|---|---|---|---|---|
| MSFT | buffett | 96.18 | 97.05 | 78.12–97.12 | 95.12–97.12 | full 1.00 | full 0.98 | 306.03 | 307.09 |
| MSFT | graham | 94.04 | 93.38 | 88.38–94.38 | 93.38–93.38 | full 1.00 | full 1.00 | 85.74 | 85.50 |
| KO | buffett | 84.57 | 87.38 | 70.38–87.38 | 87.38–87.38 | full 1.00 | full 1.00 | 26.43 | 26.79 |
| KO | graham | 68.89 | 67.23 | 63.23–69.23 | 67.23–67.23 | full 1.00 | full 1.00 | 11.57 | 11.27 |
| INTC | buffett | 15.92 | 26.72 | 12.22–31.22 | 24.22–28.22 | full 1.00 | full 0.96 | - | - |
| INTC | graham | 48.39 | 47.64 | 43.64–49.64 | 47.64–47.64 | full 1.00 | full 1.00 | - | - |
| UBER | buffett | 61.82 | 67.84 | 49.84–69.84 | 67.84–67.84 | full 1.00 | full 1.00 | 5.51 | 5.85 |
| UBER | graham | 41.73 | 41.21 | 37.21–43.21 | 41.21–41.21 | full 1.00 | full 1.00 | - | - |
| JPM | buffett | 91.40 | 92.93 | 76.04–94.04 | 91.04–93.04 | full 1.00 | full 0.98 | 241.97 | 243.47 |
| JPM | graham | 87.03 | 87.03 | 83.03–87.03 | 87.03–87.03 | full 1.00 | full 1.00 | 122.36 | 122.36 |
| CB | buffett | 92.75 | 92.85 | 71.67–94.24 | 90.90–93.12 | full 0.90 | full 0.88 | 282.09 | 282.20 |
| CB | graham | 89.64 | 89.64 | 84.94–89.64 | 89.64–89.64 | full 0.85 | full 0.85 | 148.82 | 148.82 |
| PGR | buffett | 91.56 | 93.56 | 72.67–93.56 | 93.56–93.56 | full 0.90 | full 0.90 | 119.13 | 120.10 |
| PGR | graham | 90.40 | 90.40 | 85.06–90.40 | 90.40–90.40 | partial 0.75 | partial 0.75 | - | - |
| O | buffett | 79.38 | 84.93 | 59.27–85.10 | 80.39–85.10 | full 0.83 | full 0.81 | 46.95 | 49.23 |
| O | graham | 84.76 | 84.76 | 76.50–85.39 | 80.94–85.39 | full 0.86 | full 0.86 | 31.24 | 31.24 |
| AMT | buffett | 78.29 | 84.01 | 56.59–84.19 | 79.48–84.19 | full 0.83 | full 0.81 | 101.93 | 107.08 |
| AMT | graham | 92.14 | 90.81 | 86.81–92.14 | 90.81–90.81 | partial 0.75 | partial 0.75 | - | - |

## 8. הערות ובעיות

1. **כל 2 כמעט תמיד** (90 מתוך 101 תשובות): `3.5-flash-lite` נוטה לתת 2 על שאלות שבהן הפרק ארוך ומחמיא; בולט ב-B3.1 (CB 8.75, UBER 9.0, JPM 9.0 – הציונים הנמוכים היחידים). מומלץ סט ייחוס ידני (מפרט §9.1) לפני שמסתמכים על הציון; שדרוג מודל כשהזמינות תאפשר.
2. **G3.8-Q3** מוריד ציונים של Graham (MSFT, KO, INTC, UBER): התשובות 0–1 מצטטות רווחים/הפסדים אחרים מהותיים ב-MD&A. שים לב: הביאורים לא נשלחו.
3. **דחיות:** 4 תשובות ראשיות נדחו (quote_not_found – ציטוט עם `...`/שורת טבלה). 7 שורות `insufficient_evidence` בסך הכול; ב-INTC המודל מצא "insufficient evidence" לכמה שאלות (פרק 1A של INTC 9K תווים בלבד – fallback נושאי).
4. **זמינות:** המודל שב-`.env` אינו שמיש בחינמי כרגע; להחלטתך: להישאר ב-`3.5-flash-lite`, או לשלם/להמתין ל-3.8.
5. **ביאורים:** `NOTE:` לא חולצו; ל-A8/A13/A14 תשובות על בסיס MD&A + עובדות הקוד. נדרש חילוץ ביאורים לפני אישור סופי.
6. **חברות בלי 10-K בקאש** (10 כלליות + 5 managed care): לא נשאלו; הורדה = בקשה נפרדת.
7. תיקיית `scripts/ai_store/` אינה ב-gitignore (נבחר לא להוסיף); להחליט אם לשמור את התשובות ב-git.
8. לא נוצר commit. קבצים חדשים: `src/ai/*`, `src/scoring/ai_items.py`, `scripts/{ai_runner,run_ai_k5a,run_ai_cls,ai_recheck,ai_report_k5a,ai_sections_report}.py`, `tests/test_ai.py`, `scripts/ai_store/*`; ושינויים בחמשת קבצי המנועים, `inputs.py`, ארבעת ה-runners, `requirements.txt` (`pyyaml`).

## 9. כיצד חוזרים על הבדיקות

```
.venv/Scripts/python -m pytest -q -p no:cacheprovider
GEMINI_RPM=12 .venv/Scripts/python scripts/run_ai_k5a.py            # 10 חברות, שתי הרצות (קורא ל-Gemini)
GEMINI_RPM=12 .venv/Scripts/python scripts/run_ai_cls.py ABNB BKNG  # C1
VC_AI_STORE=scripts/ai_store/assessments.jsonl .venv/Scripts/python tests/golden/2026-10-20/make_golden.py --as-of=2026-10-20 --stub-yfinance <raw> <golden>
.venv/Scripts/python scripts/ai_report_k5a.py <golden>
```
