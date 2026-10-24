"""Builds scripts/code_stage5b2_5c_2026-10-23.md (Hebrew): extraction fixes before / after, remaining differences with a verdict, INTC A11 and USB, the D1 / D2 texts of the dev set."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts" / "ai_store"
load = lambda p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E731


def stats(name):
    R = load(S / name / "extraction" / "items.jsonl")
    C = json.loads((S / name / "extraction" / "compare.json").read_text(encoding="utf-8"))
    return R, C


R0, C0 = stats("k5b")
R1, C1 = stats("k5b2")
cnt = lambda C: Counter(c["result"] for c in C)  # noqa: E731
c0, c1 = cnt(C0), cnt(C1)
rej = lambda R: Counter(x for r in R if r["state"] == "rejected" for x in r["reasons"])  # noqa: E731
flg = Counter(f.split(" (")[0] for r in R1 for f in r["flags"])

# verdict per remaining difference: who is right according to the quote
VERDICT = {
    ("AMT", "recon_nci_jv", 2024): "ה-AI נאמן לשורה בציטוט (352.7−); ה-CSV מסכם כמה שורות (NCI + יחידות לא מאוחדות) — הבדל הגדרה, לא טעות",
    ("CB", "cat_loss_latest", 2025): "ה-CSV צודק: ה-AI לקח שורה מטבלה של פעילות אחת (584); סך הקטסטרופות של השנה 2,805",
    ("CB", "inv_fixed_maturities", 2025): "ה-CSV צודק: ה-AI לקח עמודת שווי הוגן מתת-טבלה (122,680); המאזן 130,771",
    ("CB", "inv_other", 2025): "ה-CSV צודק: ה-AI לקח 'Total' של תת-טבלה (10,749) במקום סך ההשקעות האחרות",
    ("JPM", "loan_line", 2025): "ה-CSV צודק: 'Loans retained' 1,408,905; סכום ה-AI כולל שורות נוספות",
    ("O", "op_units_count", 2025): "ה-AI נאמן לציטוט (2,681,808 יחידות); ה-CSV כנראה ממוצע/מועד אחר — לא ניתן להכריע מהציטוט",
    ("O", "recon_nci_jv", 2024): "שורות שונות: ה-AI לקח 'Proportionate share of adjustments for unconsolidated entities'; ה-CSV את התאמת ה-NCI — פריט מורכב משתי שורות, ה-AI החזיר אחת",
    ("O", "recon_nci_jv", 2025): "כנ״ל",
    ("O", "recon_re_da", 2024): "ה-AI נאמן לשורה (2,395,644); ה-CSV 2,421.9 מדד רחב יותר — לא הוכרע",
    ("O", "recon_re_da", 2025): "ה-AI נאמן לשורה (2,524,200); ה-CSV 2,554.9 — לא הוכרע",
    ("O", "acquisition_invested", 2025): "ה-AI נאמן לשורה (4,152.1); ה-CSV 6.3 מיליארד כולל כנראה פיתוח/קרקע מה-supplemental — לא הוכרע",
    ("O", "acquisition_yield", 2025): "ה-AI נאמן לציטוט (7.0%); ה-CSV 7.3% ממקור אחר — לא הוכרע",
    ("O", "occupancy", 2025): "ה-CSV מדויק יותר (98.9); בציטוט רק 99 מעוגל",
    ("PLD", "op_units_count", 2025): "לא הוכרע: ה-AI 14.9 מיליון מהציטוט; ה-CSV 21.76 (כנראה כולל מחלקות נוספות)",
    ("PLD", "re29b_fx_net", 2024): "תואם בסימן אחרי התיקון; ההבדל 0.5% הוא עיגול (ה-AI במיליונים: 68 מול 67.3)",
    ("PLD", "re29b_fx_net", 2025): "תואם בסימן אחרי התיקון; הבדל עיגול (125 מול 125.7)",
    ("PLD", "recon_re_da", 2024): "ה-AI נאמן לשורה (2,504); ה-CSV 2,999 מדד רחב — לא הוכרע",
    ("PLD", "recon_re_da", 2025): "ה-AI נאמן לשורה (2,539); ה-CSV 3,090 — לא הוכרע",
    ("PLD", "development_invested", 2024): "לא הוכרע: ציטוט TEI בלי כותרת שנה; ה-CSV ערך אחר לגמרי",
    ("PLD", "development_invested", 2025): "לא הוכרע (כנ״ל)",
    ("PLD", "committed_undrawn_facilities", 2025): "ה-AI צודק: 'Current availability' 6,431 הוא הזמין; ה-CSV 6,500 היקף המסגרות",
}
diff = [c for c in C1 if c["result"] == "differ"]
rows = ["| חברה | בלוק | פריט | שנה | AI | CSV | מי צודק לפי הציטוט |", "|---|---|---|---|---|---|---|"]
for c in diff:
    rows.append(f"| {c['ticker']} | {c['block']} | {c['item']} | {c['year']} | {c['ai']:,.5g} | {c['csv']:,.5g} | {VERDICT.get((c['ticker'], c['item'], c['year']), 'לא נבדק')} |")
cls = ["| חברה | שורה | AI | CSV | הכרעה לפי הגדרות RP2a |", "|---|---|---|---|---|"]
CLSV = {"consolidated": ""}
for c in C1:
    if c["result"] == "class_differs":
        cls.append(f"| {c['ticker']} | {c['line']} | {c['item']} | {c['csv_class']} | pending (B10 תמיד לאישור) |")

# ---- D1 / D2 texts
T, FIRST, SECOND = {}, {}, {}
for r in load(S / "k5c" / "texts.jsonl"):
    pv, kd = str(r["prompt_version"]), r["kind"]
    if (kd == "background" and pv == "1") or (kd == "analysis" and pv == "2"):
        FIRST[(r['ticker'], kd)] = r
    elif (kd == "background" and pv == "2") or (kd == "analysis" and pv == "3"):
        SECOND[(r['ticker'], kd)] = r
    else:
        T[(r["ticker"], r["kind"])] = r
second_rows = ["| חברה | סוג | תוצאה (אחרי בדיקה חוזרת/ניסיון) | סיבות כשל |", "|---|---|---|---|"]
for r in SECOND.values():
    second_rows.append(f"| {r['ticker']} | {'D1' if r['kind'] == 'background' else 'D2'} | {r['state']} | {r['checks']['attempts'][-1]['reasons'] if r['state'] != 'stored' else ''} |"[:300])
first_rows = ["| חברה | סוג | תוצאה | סיבות כשל (ניסיון אחרון) |", "|---|---|---|---|"]
for r in FIRST.values():
    first_rows.append(f"| {r['ticker']} | {'D1' if r['kind'] == 'background' else 'D2'} | {r['state']} | {r['checks']['attempts'][-1]['reasons'] if not r['checks']['ok'] else ''} |"[:400])
n_first_calls = sum(len(r["checks"]["attempts"]) for r in FIRST.values())
usage = json.loads((S / "usage.json").read_text(encoding="utf-8"))
texts = []
total_calls = 0
for t in ["KO", "MSFT", "JPM", "CB", "O", "AMT", "INTC"]:
    d1, d2 = T.get((t, "background")), T.get((t, "analysis"))
    texts.append(f"### {t}\n")
    for name, r in (("D1 — רקע", d1), ("D2 — ניתוח", d2)):
        if not r:
            texts.append(f"**{name}:** לא הורץ\n")
            continue
        att = r["checks"]["attempts"]
        total_calls += len(att)
        words = len((r["text"] or "").split())
        texts.append(f"**{name}** — מצב `{r['state']}`; {words} מילים; ניסיונות {len(att)}; בדיקות שנכשלו: {r['checks']['reasons'] or 'אין'}; "
                     f"אורך פרומפט {att[-1].get('prompt_chars') or r.get('prompt_chars')} תווים" + (f"; נחתך: {r['trimmed']}" if r.get("trimmed") else "") + "\n")
        if r.get("text"):
            texts.append("> " + r["text"].replace("\n\n", "\n>\n> ") + "\n")
        elif r.get("raw_answer"):
            texts.append("תשובה שנדחתה (לא מוצגת למשתמש):\n```\n" + r["raw_answer"][:1500] + "\n```\n")
        if name.startswith("D2") and r.get("change_he"):
            texts.append(f"שורת \"מה השתנה\": {r['change_he']}\n")
        if len(att) > 1:
            texts.append("ניסיונות: " + "; ".join(f"#{a['attempt']} {'עבר' if a['ok'] else 'נכשל: ' + ', '.join(a['reasons'])}" for a in att) + "\n")

md = f"""# דוח ק5ב-2 / ק5ג — תיקוני חילוץ, ניסוח אחיד ל-D2, והרצת רקע וניתוח

תאריך: 2026-10-23 · מודל מקובע `gemini-3.5-flash-lite` · בלי Supabase, `.env` לא שונה, golden קיים לא שונה (golden חדש: `scripts/output_k5c/golden`).

## 0. ניקוי מסמכים

נמחקו (`git rm`): `AI_Skills_Other_2026-10-21_12-39`, `K6_Spec_2026-10-22_14-39_*`, `Display_Spec_2026-10-19_09-59_*`, `…_2026-10-19_13-31_*`, `…_2026-10-22_14-58_*` (לא היה ב-git — נמחק מהדיסק), `…_2026-10-23_00-51_*` (כנ״ל), `DB_Structure_2026-10-19_09-59_HE.*`. נוספו: `AI_Skills_Other_2026-10-23_15-00`, `K6_Spec_2026-10-23_14-59`, `Display_Spec_2026-10-23_01-00`.

## 1. תיקוני חילוץ (ק5ב-2) — על 502 שורות מהתשובות השמורות, בלי קריאה למודל

| מדד | לפני | אחרי |
|---|---|---|
| שורות | {len(R0)} | {len(R1)} (USB B14 +3 משוחזרות; שורות סכום −4) |
| התאמה ל-CSV | {c0['match']} | {c1['match']} |
| הבדלים | {c0['differ']} | {c1['differ']} |
| הבדלי סיווג (B10) | {c0['class_differs']} | {c1['class_differs']} |
| חסר ב-AI / חסר ב-CSV | {c0['missing_in_ai']} / {c0['missing_in_csv']} | {c1['missing_in_ai']} / {c1['missing_in_csv']} |
| דחיות לפי סיבה | {dict(rej(R0))} | {dict(rej(R1))} |
| דגלים חדשים | | {dict(flg)} |

1. **סימן לפי פריט** (`src/ai/ext_norm.py`, מוסכמה ב-`extraction.yaml`: `sign_rules`): `maint_capex`, `ti_lc`, `transaction_costs`, `cat_loss_latest` — גודל חיובי; `re29_re_sale_gains`, `re29_nonre_impairments`, `re29a_nonre_inv`, `re29b_fx_net`, `debt_extinguishment` — השפעה על רווח נקי (רווח +, הפסד −) לפי נוסח השורה ("losses (gains)": ערך מודפס חיובי = הפסד; "gains (losses)": חיובי = רווח; רק "gain": רווח; רק "loss/impairment": הפסד), לא לפי הסימן שהמודל בחר; `straight_line_rent_affo` — חיובי = GAAP מעל מזומן (שורה שמוצגת בסוגריים כניכוי). **12 שורות תוקנו** (`sign_normalized`): O straight_line (2) ו-re29_re_sale_gains (2); PLD re29_re_sale_gains (2), re29b_fx_net (2), debt_extinguishment (2); AMT straight_line (2). כל ההבדלים בסימן ב-O/PLD נעלמו (PLD re29b נשאר הבדל עיגול של 0.5%). שורות של אותו פריט (AMT: capital improvement + corporate capex; straight-line revenue + expense) **מסוכמות** לשורה אחת (`summed_lines`, 4 שורות): AMT maint_capex תואם כעת ל-CSV.
2. **שיוך שנה לפי כותרת העמודות:** הקוד מוצא את כותרת השנים בטבלה שנשלחה, מזהה באיזו עמודה הערך ומשייך שנה; אם שונה — `period_corrected` (לא דוחה). בלי כותרת: סדר 10-K (חדש ראשון) רק כשהערך בעמודה אחת ויש 2–3 תאים ואין תא ריק. **תוצאה: 0 תיקוני שנה** — השנים שהמודל דיווח תאמו את העמודות בכל המקרים שאפשר היה לאמת (20 אומתו לפי סדר עמודות; 84 לא ניתנים לאימות — דגל `period_unverified`: ערך זהה בכמה עמודות, כותרת חסרה או עמודות שאינן שנים). טיוטה ראשונה של הכלל תיקנה בטעות 5 שורות (JPM LCR רבעוני, CB inv_equity עמודות עלות/רווחים, O goodwill זהה בשתי שנים, AMT tenant 19/19/19) — לכן נוספו התנאים (ערך חד-משמעי, בלי תא ריק, שמירת שנת המודל כשהיא אחת העמודות התואמות). **ההבדלים שנשארו ב-PLD/O אינם בעיית שנה** (ראו סעיף 1.1).
3. **USB B14:** הסיבה לא הייתה גודל הרשימה (פריט אחד) אלא שהמודל החזיר **מערך עירום** ללא אובייקט עוטף — כעת מתקבל (`bare_list_accepted`) ושוחזר מהתשובה השמורה: 3 שורות (`goodwill_impairment`: not_disclosed ל-3 שנים), **בלי קריאה חדשה**. בנוסף B14 מפוצל לקבוצות של עד 15 פריטים בקריאה (`ask_block(part=…)`).
4. **INTC A11:** שני תיקונים. (א) בדיקת העקביות נתפסה לציטוט הסקאלה בנימוק ("Level 0 includes … a single product …") כאילו זו תלות אחרת של החברה — כעת משפטים שמצטטים את הסקאלה לא נספרים. (ב) נימוק עם "Wait / Hmm / Actually," → דחייה `reasoning_deliberation` וניסיון חוזר אחד; הוספתי לתבנית "reasoning: your final explanation, not your thinking process"; ניסיון חוזר אחד משותף ל-`exposure_inconsistent`, `reasoning_deliberation`, `quote_not_found` (הערה לכל סיבה). הערת A11 כוללת עכשיו את הכלל הנגזר מה-share_pct ("a customer at 10%-25% is level 1…") — **חריגה קלה מהנוסח במסמך**, שבלעדיה המודל חזר על 0 (ניסוי: שתי קריאות בלי הכלל נתנו שוב 0 עם נימוק מהסס). **תוצאה: INTC A11 = 1** (ציפייה 1), נימוק נקי, ניסיון חוזר אחד. נשמר ב-store של ק5ב (`assessments.jsonl`, השורה האחרונה גוברת); golden ק5ג נבנה איתו.

### 1.1 ההבדלים שנשארו מול ה-CSV ({len(diff)}) ומי צודק

{chr(10).join(rows)}

סיכום: במקרים שניתן להכריע — ה-CSV צודק ב-5 (CB cat_loss/inv_fixed_maturities/inv_other, JPM loan_line, O occupancy: ה-AI בחר שורה/עמודה/תת-טבלה לא נכונה או עיגול), ה-AI צודק ב-1 (PLD committed_undrawn); ב-4 הבדלי הגדרה (AMT/O recon_nci_jv — פריט מורכב משתי שורות; recon_re_da — ה-CSV מדד רחב יותר); ובשאר לא ניתן להכריע מהציטוט. **המסקנה:** אין כאן בעיית שנה או סימן שנשארה; נשארות בעיות בחירת שורה בטבלאות מורכבות (ביטוח) והבחנות הגדרה. לכן הפריטים האלה נשארים `pending` או נבדקים בבקרות.

הבדלי סיווג B10 ({c1['class_differs']}):
{chr(10).join(cls)}

לפי הגדרות RP2a: O/PLD "Investment in unconsolidated entities" — ה-AI (`bsa_inre`) צודק; AMT מזומן — ה-CSV (`bsa_excl`) צודק; AMT "notes receivable and other" — ה-CSV (`bsa_wc`, שורה מעורבת) צודק; PLD "assets held for sale" — ה-CSV (`bsa_noi`) צודק. B10 תמיד `pending`.

## 2. D2 — ניסוח אחיד (סעיף 3.3)

מומש: `src/ai/d2.py` + `content.yaml` (גרסה 2): מילון בעברית (שמות 16 הקריטריונים מהספר העברי — **מפרט התצוגה 01-00 אינו כולל מילון קריטריונים**, רק מדדים ותוויות; שמות המדדים מנספח א׳, התוויות מסעיף 5), מילת חוזק מהקוד (≥70% חזק, 40–69% בינוני, <40% חלש), מיקום מול עמיתים מהאחוזון (≥75 ברבע העליון, 50–74 מעל החציון, 25–49 מתחת, <25 ברבע התחתון), תבניות המשפט ודוגמה בדויה בפרומפט, `RESULTS` בלי מחיר נוכחי/ציון מחיר/מרווח נוכחי/דיסקאונט/אפסייד/מסקנה, שורת "מה השתנה" (≤25 מילים; מחושבת בקוד מול הריצה הקודמת = golden 2026-10-20), ובדיקות: מספרים, מספר תלוי-מחיר, מילים אסורות (כולל קטגוריות המסקנה), צורת המילון (אין ROE/EPS וכד׳), מסגרות לפי הסדר, מחיר קנייה/מצב כשאין, קריטריונים מצוטטים קיימים ושמם מופיע. D1: חיתוך לפי עדיפות (TXT-001 → TXT-003 → TXT-005) כשהפרומפט מעל 60,000 תווים, עם `trimmed`. בדיקות יחידה: `tests/test_content.py` (17), `tests/test_ai_extract.py`, `tests/test_ai.py`.

## 3. הרצת ק5ג — סט הפיתוח

**הרצה ראשונה ({n_first_calls} קריאות)** חשפה בעיות בתבניות ובבדיקות שלי, ותוקנו לפני ההרצה השנייה:
{chr(10).join(first_rows)}

מה נמצא: (1) D1 — המודל העתיק למשפט העברי את נימוק החפיר באנגלית ("The company possesses…") ולכן מילת מקור החפיר בעברית לא הופיעה; (2) D1 — `competitors` כללו קטגוריות ("other banks", "large national carriers") ולא שמות; (3) D1 — חריגה מ-120 מילים (122–159); (4) D2 — "/100" שבמסגרת לא הופיע ב-RESULTS (נוסף `score_scale_max`); (5) D2 — המודל רשם ב-`criteria_cited` את כל הקריטריונים ובדיקת "שם הקריטריון מופיע בטקסט" נכשלה — הבדיקה שלי הייתה מחמירה מהמסמך (המסמך: "קיימים בריצה") והוסרה, והפרומפט מבקש לצטט רק מה שנזכר. תיקונים: התבנית של D1 (עברית מלאה, משפט אחד לכל חלק, `competitors` בשם בלבד, מונח חפיר בעברית נתון מהקוד), גרסאות D1=2 ו-D2=3; טקסט שנכשל נשאל מחדש בהרצה הבאה.

**הרצה שנייה (D1=2, D2=3)** — 12 מתוך 14 עברו; JPM ו-CB (D1) עברו רק אחרי הקלת `no_quote` ושינוי seed:
{chr(10).join(second_rows)}

## 3א. הרצה שלישית — אחרי ההכרעות של 24.10 (D1=3, D2=4)

תוקן לפי ההכרעות: (1) ציון טווח נכתב כטווח עם "משוער" ו-D2 נוצר רק כשאין שאלות `ai_pending` (נבדק בקוד; לחברות הפיתוח אין); (2) בדיקת עברית בלבד — 4+ מילים לטיניות רצופות, מילה עם כתבים מעורבים או אות קירילית נדחות; שם החברה חייב להופיע באותיות לטיניות (לא תעתיק); (3) חיתוך D1 לפי מכסה לפרק: TXT-001 35,000, TXT-003 12,000, TXT-005 12,000; (4) מילון הקריטריונים לפי שמות כרטיסי הניקוד שנקבעו; (5) D1 — היתרון התחרותי לפי רמת A7 ("יתרון תחרותי ברור:" / "יתרון תחרותי לא מוכח:" / "אין יתרון תחרותי מזוהה") ומקור יחיד, בבדיקת קוד; (6) D2 — תמיד "הנמוך ביותר: X (מילת חוזק)" לכל מודל; (7) השוואה לעמיתים רק כשהציון של החברה סופי ויש ≥5 עמיתים עם ציון סופי (לא מתקיים באף אחת מ-7 חברות הפיתוח, כי ב-golden רוב החברות עדיין עם טווח — ייבדק בק6); (8) מספרים מעוצבים בקוד ("331.8 מיליארד $", "$33.16", "21.0%"), מספר של 7 ספרות ומעלה נדחה; (9) שם שיטת השווי האמיתי לפי הפרופיל (NAV שמרני, מספר גרהם תפעולי, תשואה עודפת דו-שלבית, …), ושיטה לא מוכרת נכשלת.

**תוצאות הרצה שלישית:**

מקור הציונים: `scripts/output_k5c/golden` (golden ק5ב + תשובת INTC A11 המתוקנת); `one_sentence` ו-A7 מתשובות ק5ב. שימו לב: אין שאלות `ai_pending` באף אחת מ-7 החברות (לכן D2 נוצר), אך ציון שנשאר טווח (KO גרהם, O, AMT באפט, INTC באפט) נובע מפריטים במצב `missing` (תשובת AI שנדחתה או נתון חילוץ חסר) — הוא נכתב כטווח עם "משוער".

{chr(10).join(texts)}

## 4. קריאות (לפי המונה המשותף)

* שלב ק5ב-2/ק5ג הקודם (22–24.10): 61 קריאות (INTC A11: 8; ק5ג: 53).
* **ההרצה הנוכחית (החלטות 24.10): 60 קריאות — תקרה של 60 מוצתה:** הרצה מלאה 20, השלמת MSFT/JPM/O/AMT 6, הרצה מחדש של כל הסט אחרי תיקוני התבניות 16, הרצת D1 מחדש עם בדיקות המקרא/אותיות 10, ועוד 8 עם שם החברה בכתיבה מתוקנת. בדיקות חוזרות (`--recheck`) בלי קריאות: 0. מונה היום (פסיפיק 2026-10-24): {usage['calls']} מתוך 450.
* ממוצע: 7 חברות × (D1 + D2) = ~4.3 קריאות לחברה כולל ניסיונות חוזרים ושחזורים.

## 5. מצב סופי ומה שנשאר

| טקסט | מצב |
|---|---|
| D2 (גרסה 4) | **7/7 `stored`** — נשמרו, עברו את כל הבדיקות |
| D1 (גרסה 3) — MSFT, JPM, CB, INTC | `stored` |
| D1 — **KO, O, AMT** | **`failed`** — הנוסח השמור נכשל בבדיקות העדכניות (KO: אותיות ערביות בתוך מילים עבריות, שם בלי אות גדולה; O ו-AMT: שם החברה באותיות קטנות — "realty income corp", "american tower corp /ma/"). ניסיונות מחדש (ארבעה) לא עברו את הבדיקות, והמכסה של השלב נגמרה. הטקסט **לא מוצג**; ההרצה הבאה תשאל אותם שוב אוטומטית (טקסט `failed` נשאל מחדש). |

הערה על שמות: `d1_facts` נותן עכשיו שם מוצג בכתיבה נכונה (`Coca Cola`, `Realty Income`, `American Tower`, `JPMorgan Chase`), והבדיקה דורשת אותו באותיות לטיניות ובאות גדולה (לא תעתיק, לא אותיות קטנות, לא כל האותיות גדולות). הטקסטים של MSFT ו-INTC נוצרו עם התבנית הסופית; KO/O/AMT נכשלו לפני שהוחל השם המוצג על כולם — סביר שיעברו בהרצה הבאה.

## 6. מה הבדיקות עדיין לא תופסות (נקרא בטקסטים)

1. **איכות העברית של flash-lite:** CB — "ביטוח רכוש ופגיעות" (casualty), "ארצות וטריטוריות"; INTC — "מול מתחרות כגון". תקין תחבירית לרוב, אבל לא מקצועי; אין בדיקה לזה.
2. **D2 של CB** מונה בחלק "החזקים" את כל שמונת הקריטריונים של באפט (90 מילים בסך הכול, כל פסקה בגבול) — מאורך אך תקין; RESULTS נותן רק שני הראשונים.
3. **D2:** "הנמוך ביותר: יתרון תחרותי / חפיר (חזק)" ב-CB — כשהכול חזק, ה"נמוך ביותר" הוא עדיין חזק; הניסוח עובד כמוגדר, אך נקרא מוזר.
4. **השוואה לעמיתים:** לא נכתבה באף חברה (אין ≥5 עמיתים עם ציון סופי ב-golden) — כצפוי; ייבדק בק6.
5. D1 מתעלם לפעמים מהמגבלה "שם מתחרה רק מהדוח": MSFT ו-CB כתבו שהדוח לא מציין מתחרים בשם (תקין).
6. **ניסוח ציון משוער** ב-D2 עובד ("65.2–67.2/100, משוער"); אבל התווית מוצגת רק כשכל קצות הטווח באותה רצועה (KO גרהם: "גבולית").

## 7. שאלות פתוחות

1. להריץ שוב D1 של KO/O/AMT בהרצה הבאה (3–6 קריאות)?
2. לאפשר ל-D1 שם חברה כפי שהוא בדוח ("The Coca-Cola Company") במקום שם מוצג מקוצר ("Coca Cola")?
3. בדיקת איכות עברית (למשל רשימת תרגומים אסורים: "פגיעות" ל-casualty) — לבנות מילון?
"""
(ROOT / "scripts" / "code_stage5b2_5c_2026-10-23.md").write_text(md, encoding="utf-8")
print(len(md), total_calls)
