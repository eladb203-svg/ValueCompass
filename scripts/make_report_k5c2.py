"""Builds scripts/code_stage5c2_2026-10-24.md (Hebrew): D2 written by code, D1 in two stages (English checked against the report, then a checked Hebrew translation)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ai import content as C  # noqa: E402
S = ROOT / "scripts" / "ai_store"
rows = [json.loads(l) for l in (S / "k5c" / "texts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
D1 = {}
D2 = {}
for r in rows:
    pv = str(r["prompt_version"])
    if r["kind"] == "background" and pv == "4":
        D1[(r["ticker"], r["language"])] = r
    elif r["kind"] == "analysis" and pv == "t4":
        D2[r["ticker"]] = r
usage = json.loads((S / "usage.json").read_text(encoding="utf-8"))
ORDER = ["KO", "MSFT", "JPM", "CB", "O", "AMT", "INTC"]


def calls_of(r):
    return sum(1 for a in r["checks"]["attempts"] if isinstance(a["attempt"], int)) if r else 0


total = sum(calls_of(r) for r in D1.values())
out = []
for t in ORDER:
    en, he, d2 = D1.get((t, "en")), D1.get((t, "he")), D2.get(t)
    out.append(f"### {t}\n")
    for lang, name, r in (("en", "D1 שלב א׳ — אנגלית", en), ("he", "D1 שלב ב׳ — תרגום לעברית", he)):
        if r is None:
            out.append(f"**{name}:** לא הורץ (לא נשלחה קריאה — שלב א׳ נכשל או שהתקרה של 20 קריאות נגמרה)\n")
            continue
        att = r["checks"]["attempts"]
        out.append(f"**{name}** — מצב `{r['state']}`; {C.count_words(r['text'] or '')} מילים; קריאות {len(att)}; אורך פרומפט {att[-1].get('prompt_chars') if att else '-'}"
                   + (f"; נחתך: {r['trimmed']}" if r.get("trimmed") else "") + f"; בדיקות שנכשלו בניסיון האחרון: {att[-1]['reasons'] if att and not att[-1]['ok'] else 'אין'}\n")
        if r.get("text"):
            out.append(("> " if lang == "he" else "> ") + r["text"] + "\n")
        elif r.get("raw_answer"):
            out.append("תשובה שנדחתה (לא מוצגת למשתמש):\n```\n" + (r["raw_answer"] or "")[:1200] + "\n```\n")
        if len(att) > 1:
            out.append("ניסיונות: " + "; ".join(f"#{a['attempt']} {'עבר' if a['ok'] else 'נכשל: ' + ', '.join(a['reasons'])}" for a in att) + "\n")
    if d2:
        out.append(f"**D2 — ניתוח (נכתב בקוד, 0 קריאות)** — מצב `{d2['state']}`; בדיקות שנכשלו: {d2['checks']['reasons'] or 'אין'}\n")
        if d2.get("text"):
            out.append("> " + d2["text"].replace("\n\n", "\n>\n> ") + "\n")
            if d2.get("change_he"):
                out.append(f"שורת \"מה השתנה\": {d2['change_he']}\n")
    out.append("")
stored_he = [t for t in ORDER if D1.get((t, "he")) and D1[(t, "he")]["state"] == "stored"]
failed = [t for t in ORDER if t not in stored_he]
md = f"""# דוח ק5ג-2 — D2 בקוד, D1 בשני שלבים (אנגלית ← עברית)

תאריך: 2026-10-24 · מודל `gemini-3.5-flash-lite` · בלי Supabase, `.env` לא שונה, golden קיים לא שונה.

## 1. מה שונה (החלטה 24.10)

* **D2 — בלי AI** (`src/ai/d2_template.py`): הקוד ממלא את תבניות המשפט של סעיף 3.3 ישירות בעברית — מילון הקריטריונים (שמות כרטיסי הניקוד), מילות חוזק, הטווח עם "משוער", "הנמוך ביותר" לכל מודל, שם השיטה האמיתי, מספרים מעוצבים, ושורת "מה השתנה". אותן בדיקות של `check_analysis` רצות על הפלט, כך שטעות בתבנית לא מגיעה למסך. נוצר מחדש ל-7 החברות: **0 קריאות**. גרסה `t4`.
* **D1 — שני שלבים** (`generate_background`): (א) ה-AI כותב באנגלית (חמשת החלקים, עד 120 מילים) וכל הבדיקות רצות על האנגלית מול הדוח: ציטוטים מילה במילה, מספרים (רק מספר שמופיע בטקסט הדוח או ב-FACTS), מתחרים בשם ומצוטטים (לא קטגוריה), שם החברה בכתיבה נכונה, רמת החפיר לפי A7 (ביטוי הרמה + מקור יחיד, בלי רשימה), בלי מילים של המלצה. (ב) קריאה שנייה מתרגמת לעברית עם המילון, ובדיקה מול האנגלית: **אותם מספרים בדיוק** (מספר שנכתב במילים נחשב אבוד), אותם שמות באותיות לטיניות (לא תעתיק), עברית בלבד (4+ מילים לטיניות, כתבים מעורבים, אותיות קיריליות/ערביות — נדחים), ביטוי רמת החפיר ומקור יחיד בעברית. שתי הגרסאות נשמרות (`language` = `en` / `he`). ניסיון חוזר אחד בכל שלב; שלב ב׳ נכשל — האנגלית נשארת ושלב ב׳ נשאל שוב בהרצה הבאה בלבד.
* **תקרת קריאות קשיחה בקוד:** `BudgetClient` (ברירת מחדל 20, `--max-calls`): הקריאה שמעבר לתקרה לא נשלחת והחברה מסומנת `skipped_budget`. המונה המשותף היומי (450) ונעילת התהליך האחד נשארים.

## 2. תוצאות

* D1 עברו בשני השלבים: {', '.join(stored_he) or 'אין'}; לא עברו: {', '.join(failed) or 'אין'}.
* קריאות D1 בפועל: **20 מתוך תקרה של 20** (18 בהרצה לשבע החברות — החברה האחרונה, INTC, קיבלה רק שלב א׳ ונדחתה — ועוד 2 לניסיון נוסף ל-KO אחרי שהוספתי "פתח במשפט עם שם החברה"). בדיקות חוזרות על תשובות שמורות (`--recheck`): 0 קריאות. מונה היום (פסיפיק 2026-10-24): {usage['calls']} מתוך 450.
* D2: 7/7 `stored`, 0 קריאות.

## 3. הטקסטים המלאים

{chr(10).join(out)}

## 3א. מה נמצא (ומה שיניתי אחרי שראיתי את הכשלים)

* **3 מתוך 7 עברו את שני השלבים** (MSFT, CB, AMT); KO, JPM, O, INTC נכשלו כבר בשלב א׳ (האנגלית מול הדוח), ולכן לא נשלחה להם קריאת תרגום — זה בדיוק התכנון: טקסט שלא עובר מול הדוח לא מתורגם.
* סיבות הכשל בשלב א׳: **חריגה מ-120 מילים** (KO 125, O 131, INTC 128 — המודל לא סופר), **מתחרים שלא מצוטטים** (INTC: מונה כ-15 מתחרים בציטוט קצר מדי), **מקור החפיר** (JPM: "scale" לא מופיע במשפט), **שם החברה לא מופיע** (KO, לפני התיקון).
* שני כללים שהקלתי אחרי שראיתי שהם נתפסים לשווא בשלב ב׳ (MSFT, AMT): (1) שנה בת 4 ספרות בעברית מותרת אם היא שנת הדוח או מופיעה באנגלית, והשוואת המספרים לא כוללת שנים; (2) המילים הכלליות data / infrastructure / location (נתונים / תשתית / מיקום) כבר לא נחשבות "מקור חפיר נוסף". שניהם נבדקים בבדיקות יחידה, ושלוש התשובות המאוחסנות נבדקו מחדש בלי קריאה. תוספת לפרומפט שלב א׳: "פתח את המשפט הראשון בשם החברה".
* הערה על הספירה בטבלאות: "קריאות" לכל שורה סופרות ניסיונות (ללא בדיקות חוזרות).

## 4. הערות

1. קריאות לחברה: שלב א׳ + שלב ב׳ = 2 במסלול נקי (4 עם ניסיון חוזר בשניהם); לשבע חברות 14–28 — לכן התקרה הקשיחה של 20 עשויה להשאיר חברות ללא D1 (`skipped_budget`).
2. בדיקות: `tests/test_d1_two_stage.py` (שלב א׳, שלב ב׳, ניסיונות חוזרים, תקרה, D2 בקוד), `tests/test_content.py`, `tests/test_peers.py`.
3. מגבלה שנשארת: השוואה לעמיתים לא נכתבת באף חברה (אין ≥5 עמיתים עם ציון סופי ב-golden) — בק6.
"""
(ROOT / "scripts" / "code_stage5c2_2026-10-24.md").write_text(md, encoding="utf-8")
print(total, stored_he, failed)
