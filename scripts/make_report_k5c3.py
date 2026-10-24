"""Builds scripts/code_stage5c3_2026-10-24.md (Hebrew): the last D1 round for KO, JPM, O, INTC (words 90-100 / limit 140, at most 5 competitors, retry notes with the word count and the source)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ai import content as C  # noqa: E402

S = ROOT / "scripts" / "ai_store"
rows = [json.loads(l) for l in (S / "k5c" / "texts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
D1 = {(r["ticker"], r["language"]): r for r in rows if r["kind"] == "background" and str(r["prompt_version"]) == "4"}
usage = json.loads((S / "usage.json").read_text(encoding="utf-8"))
ROUND = ["KO", "JPM", "O", "INTC", "MSFT"]
ALL = ["KO", "MSFT", "JPM", "CB", "O", "AMT", "INTC"]
out = []
for t in ROUND:
    out.append(f"### {t}\n")
    for lang, name in (("en", "אנגלית (שלב א׳)"), ("he", "עברית (שלב ב׳)")):
        r = D1.get((t, lang))
        if r is None:
            out.append(f"**{name}:** לא הורץ — שלב א׳ נכשל\n")
            continue
        att = [a for a in r["checks"]["attempts"] if isinstance(a["attempt"], int)]
        last = att[-1]["reasons"] if att and not att[-1]["ok"] else []
        out.append(f"**{name}** — `{r['state']}`; {C.count_words(r['text'] or '')} מילים; קריאות {len(att)}" + (f"; סיבות כשל: {last}" if last else "") + "\n")
        if r.get("text"):
            out.append("> " + r["text"] + "\n")
        if len(att) > 1:
            out.append("ניסיונות: " + "; ".join(f"#{a['attempt']} {'עבר' if a['ok'] else 'נכשל: ' + ', '.join(a['reasons'])[:200]}" for a in att) + "\n")
ok = [t for t in ROUND if D1.get((t, "he")) and D1[(t, "he")]["state"] == "stored"]
bad = [t for t in ROUND if t not in ok]
md = f"""# דוח ק5ג-3 — סבב אחרון ל-D1 (KO, JPM, O, INTC)

תאריך: 2026-10-24 · תקרה קשיחה בקוד: 16 קריאות · בפועל: **16** (11 בהרצה ל-KO/JPM/O/INTC + 5 לתרגום מחדש של MSFT ו-INTC) · מונה היום: {usage['calls']} מתוך 450.

## מה שונה
1. פרומפט שלב א׳: "about 90–100 words", חמישה חלקים של משפט אחד; בדיקה: עד 140 מילים (גם בתרגום). בניסיון החוזר על אורך הקוד כותב למודל את מספר המילים בפועל ומבקש לקצר לכ-100.
2. מתחרים: עד 5 עיקריים; כל אחד מופיע באחד הציטוטים (מותרים כמה ציטוטים); יותר מ-5 נדחה.
3. בניסיון חוזר על מקור חפיר חסר, ההערה כוללת את הביטוי של הרמה ואת המקור שצריך להופיע (באנגלית ובעברית).
4. טקסט שנכשל גם הפעם נשאר `failed`, לא מוצג, ותור ה-AI בק6 ינסה שוב.

## תוצאה
* **עברו שני שלבים:** {', '.join(ok) or 'אין'} · **נשארו `failed`:** {', '.join(bad) or 'אין'}.
* **מצב סופי ל-7 החברות** (עברית `stored`): {', '.join(t for t in ALL if D1.get((t, 'he')) and D1[(t, 'he')]['state'] == 'stored')} ; `failed` (ממתינות לתור ק6): {', '.join(t for t in ALL if not (D1.get((t, 'he')) and D1[(t, 'he')]['state'] == 'stored'))}.
* **ממצא באמצע:** בקריאת הטקסטים התברר שתרגומי INTC ו-MSFT שעברו את הבדיקות הכילו אותיות תאילנדיות/יווניות בתוך מילה עברית ("ופาวנדרי", "חκέ") — הבדיקה כיסתה עברית/לטינית/קירילית/ערבית בלבד. הוספתי בדיקת "אותיות מכתב זר" (`foreign_script_letters`), בדיקה חוזרת על התשובות השמורות הורידה את שני הטקסטים ל-`failed`, ותרגומם נשאל מחדש בחמש הקריאות הנותרות מהתקרה (שניהם עברו; O לא הספיק — `skipped_budget`).
* **מה הבדיקות עדיין לא תופסות:** איכות התרגום עצמו — ב-KO מופיעות מילים עבריות מומצאות או שגויות ("למרזלים" במקום "ליצרני בקבוקים", "תרכובות" במקום "תרכיזים", "ביקבוק"). המספרים והשמות נשמרים, אך העברית אינה מלוטשת; בדיקה כזו מצריכה מילון או סקירה אנושית (שאלה לק6).
* סיבת הכשל של מה שנשאר: JPM — המודל ממשיך למנות קטגוריות ("other banks", "hedge funds", …) כמתחרים ולחרוג מהאורך (206 מילים); O — בתרגום הופיע המספר 5,749,377 (מספר גולמי של 7 ספרות) במקום "5.7 מיליארד $", ונדחה בבדיקת העיצוב.

## הטקסטים

{chr(10).join(out)}
"""
(ROOT / "scripts" / "code_stage5c3_2026-10-24.md").write_text(md, encoding="utf-8")
print(ok, bad)
