"""Builds scripts/code_stage5c_code_2026-10-22.md from the dry run (scripts/ai_store/k5c/dry_run.jsonl). No model calls."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = {r["ticker"]: r for r in (json.loads(l) for l in (ROOT / "scripts" / "ai_store" / "k5c" / "dry_run.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
f = lambda v: "—" if v is None else (f"{v:,.4g}" if isinstance(v, (int, float)) else str(v))  # noqa: E731

groups = ["| חברה | הגדרת הקבוצה | n | גיבוי (פרופיל בלבד) | חברי הקבוצה |", "|---|---|---|---|---|"]
for t, r in rows.items():
    g = r["peer_group"]
    groups.append(f"| {t} | {g['definition']} | {g['n']} | {'כן' if g['fallback'] else 'לא'} | {', '.join(g['ids'])} |")

i = rows["INTC"]["peers"]
pct = ["| מדד | ערך | אחוזון בקבוצה | n תקף |", "|---|---|---:|---:|"]
for m in ("buffett", "graham"):
    q = i["quality"][m]
    pct.append(f"| איכות {m} | {q['score']}{' (אמצע טווח)' if q['range_midpoint'] else ''} | {q['percentile']} | {q['n']} |")
for k, v in i["metrics"].items():
    pct.append(f"| {v['label']} | {f(v['value'])}{' (נמוך = טוב)' if v['lower_is_better'] else ''} | {v['percentile']} | {v['n']} |")

d1 = rows["INTC"]["d1_prompt"]
d1 = re.sub(r"(<<<\n)(.{1800}).*?(\n>>>)", lambda m: m.group(1) + m.group(2) + f"\n[... הטקסט חתוך בדוח; בפרומפט המלא {len(rows['INTC']['d1_prompt']):,} תווים ...]" + m.group(3), d1, flags=re.S)
d2 = rows["INTC"]["d2_prompt"]
d2 = re.sub(r'("criteria": \[).*?(\]\s*\n\s*\}\s*,\s*\n\s*"graham")', r"\1 ...[קריטריונים חתוכים בדוח]... \2", d2, count=1, flags=re.S) if len(d2) > 9000 else d2

sizes = ", ".join(f"{t}: D1 {r['d1_prompt_chars']:,} / D2 {r['d2_prompt_chars']:,}" for t, r in rows.items())
miss = "; ".join(f"{t}: {', '.join(r['d1_missing_inputs'])}" for t, r in rows.items() if r["d1_missing_inputs"]) or "אין"

md = f"""# דוח שלב ק5ג (קוד בלבד) — קבוצת עמיתים, רקע (D1), ניתוח (D2)

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

{chr(10).join(groups)}

INTC: בענף Semiconductors יש רק 2 חברות ב-golden ⇒ נפילה לפרופיל STANDARD כולו (19 חברות). שאר הקבוצות מלאות. בכל פרופיל יש לפחות 5 חברות, אך ענף "Investment banks and brokers" (חברה אחת, פרופיל BANK) ייפול תמיד לגיבוי.

## 3. טבלת אחוזונים לדוגמה — INTC (קבוצה: {i['group']['definition']}, n = {i['group']['n']})

{chr(10).join(pct)}

ציוני האיכות של ה-golden הם **טווחים** (שאלות ה-AI עדיין `ai_pending` שם), ולכן נכנסו עם אמצע הטווח. בהרצה האמיתית הציונים יגיעו מריצת הניקוד עם תשובות ה-AI והטווח יצטמצם.

## 4. פרומפט D1 לדוגמה — INTC

```
{d1}
```

## 5. פרומפט D2 לדוגמה — INTC

```
{d2}
```

## 6. הרצה יבשה — גדלי פרומפטים וקלטים חסרים

גדלים (תווים): {sizes}. הפרומפט הגדול ביותר (CB, D1) ~108K תווים (~30K טוקנים) — בגלל TXT-001 (עד 150K). קלטי D1 חסרים בתשובות השמורות של ק5א-3: {miss} (שאלה שנדחתה בבדיקות; D1 ירוץ עם "not available" ל-one_sentence, או שיש להריץ שוב את A5 קודם — בהרצה האמיתית אחרי ק5ב יהיו תשובות חדשות).

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
"""
(ROOT / "scripts" / "code_stage5c_code_2026-10-22.md").write_text(md, encoding="utf-8")
print(len(md))
