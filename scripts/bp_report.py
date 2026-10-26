"""The Hebrew report of the BP stage (scripts/code_stage_bp_<date>.md), built from what is stored in the test database. Called by `bp_stage.py report`."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALL_LOG = ROOT / "scripts" / "ai_store" / "bp_calls.json"
FIELD_HE = {"core_activity": "פעילות מרכזית", "segments": "מגזרים", "products_services": "מוצרים ושירותים", "customer_types": "סוגי לקוחות", "revenue_models": "מודלי הכנסות",
            "regions": "אזורים", "competitors": "מתחרים (בשם)", "competitor_types": "סוגי מתחרים"}
ORDER = list(FIELD_HE)
STATUS_HE = {"ok": "תקין", "other": "other (מסומן)", "not_found": "לא נמצא", "failed": "נכשל"}


def cell(x, n: int = 150) -> str:
    t = " ".join(str(x if x is not None else "").split()).replace("|", "/")
    return t if len(t) <= n else t[:n - 1] + "…"


def pct(s):
    return "" if s is None else f"{s * 100:.1f}%"


def item_value(f: str, it: dict, vocab) -> str:
    if f == "core_activity":
        return it["value"]
    if f in ("customer_types", "revenue_models"):
        lab = vocab.label(f, it["code"], "he") if it["code"] in vocab.labels[f] else it["code"]
        return f"{it['code']} ({lab})" + (f" — «{it['other_text']}»" if it.get("other_text") else "")
    if f == "regions":
        code = it.get("code")
        lab = vocab.label("regions", code, "he") if code in vocab.labels["regions"] else code
        extra = f" — «{it.get('other_text') or ', '.join(it.get('members') or [])}»" if code == "other" else (f" [{', '.join(it['members'])}]" if it.get("members") else "")
        return f"{it.get('name') or ''}{' → ' if it.get('name') else ''}{code} ({lab}) {pct(it.get('share'))}{extra}".strip()
    if f == "competitor_types":
        return f"{it['industry']}" + (f" / {it['scope']}" if it.get("scope") else "")
    if f == "competitors":
        return it["name"]
    return f"{it['name']}" + (f" [{it['kind']}]" if it.get("kind") else "") + (f" {pct(it.get('share'))}" if it.get("share") is not None else "")


def profile_table(p: dict, vocab) -> str:
    rows = ["| שדה | ערך | מקור | ציטוט / תגית | סטטוס |", "|---|---|---|---|---|"]
    for f in ORDER:
        fld = p[f] or {}
        items = fld.get("items") or []
        st = fld.get("status")
        if not items:
            rows.append(f"| {FIELD_HE[f]} | — | {fld.get('source', '')} | {cell('; '.join(fld.get('reasons') or []))} | {STATUS_HE.get(st, st)} |")
            continue
        for k, it in enumerate(items):
            rows.append(f"| {FIELD_HE[f] if k == 0 else ''} | {cell(item_value(f, it, vocab), 110)} | {it.get('source', '')} | {cell(it.get('quote') or it.get('tag'), 130)} | "
                        f"{('נכשל (פריט חלקי, לא נכתב בטקסט): ' + cell('; '.join(fld.get('reasons') or []), 90)) if st == 'failed' else STATUS_HE.get(it.get('status'), it.get('status'))} |")
    return "\n".join(rows)


def write_report(path: Path, tickers: list) -> str:
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from bp_stage import make_builder
    from src.bp import render as R
    from src.bp.pipeline import phrases_needed
    from src.bp.translate import phrase_key
    from src.bp.vocab import Vocab, _yaml
    b, _ = make_builder(0, False)
    vocab = b.vocab
    calls = json.loads(CALL_LOG.read_text(encoding="utf-8")) if CALL_LOG.exists() else {}
    first = calls.get("gemini_attempts", 0)
    refresh = sum(r.get("gemini_attempts", 0) for r in calls.get("refresh_runs", []))
    out = [f"# שלב BP — רקע מפרופיל עסקי (XBRL + BP-1), אוצר מילים סגור, תרגום ביטויים, רינדור מתבנית — {date.today().isoformat()}", "",
           "> מסד: **test בלבד**. ייצור לא נגע. החליף את D1/T1 בתור. מסמך מקור: `docs/ai/ValueCompass_AI_Skills_Other_2026-10-26_10-30.md` (3.1–3.2).", ""]
    # ------------------------------------------------------------------ summary
    out += ["## 1. סיכום", "",
            f"- **קריאות Gemini בפועל: {first + refresh}** מתוך תקרה של 25 לשלב ({first} בריצה הראשונה על 7 החברות, {refresh} בריצות תיקון); מודל flash-lite בלבד, תהליך אחד, המונה המשותף.",
            "- **קריאות Google Translate בפועל: 0.** **חסר `GOOGLE_TRANSLATE_API_KEY` ב-`.env`** (יש שם רק משתני Azure: `TRANSLATION_PROVIDER`, `AZURE_TRANSLATOR_*`). לפי ההנחיה לא השתמשתי במודל במקום, ולא ב-Azure. "
            "הטקסט האנגלי נוצר ואושר; **הטקסט העברי של כל 7 החברות מסומן \"ממתין לתרגום\"** (`state=awaiting_translation`, `approval_status=pending_review`, לא מוצג למשתמשים) — "
            "בכל חברה יש לפחות ביטוי אחד בלי תרגום (פעילות מרכזית, שמות קווי מוצרים או שמות מגזרים). מה שמתורגם מהמילון הקיים (17 מונחי `t1_glossary.yaml`, נטענו כ-`approved`/`human`) נמצא, אבל לא מספיק.",
            "- **איך משלימים:** להוסיף את המפתח ל-`.env` ולהריץ `python scripts/vc.py ai-queue` (או `bp_stage.py recheck`); הביטויים יתורגמו (עד 200), יסומנו `unreviewed`, והטקסטים העבריים ירונדרו מחדש. "
            "`human_reviewed` יהיה `true` רק אחרי `terms approve`/`terms edit` לכל הביטויים שבטקסט.",
            "- ריצה שנייה לא מבקשת שוב מ-BP-1 (אותו `accession`) ורינדור שני נותן 0 שינויים — ראו סעיף 8.", ""]
    out += ["### החלטות ושינויים שאני מבקש שתבדוק", "",
            "1. **ספק התרגום:** המסמך (3.2.5) כותב Azure; ההנחיה שלך כותבת Google. פעלתי לפי ההנחיה (Google Cloud Translation v2, מפתח בכותרת הבקשה, לא מודפס). אם תרצה לעדכן את המסמך — לא נגעתי בו.",
            "2. **שמות מגזרים מתורגמים:** ההנחיה מפרטת רק `core_activity` ושמות קווי מוצרים; המסמך (3.2.4–3.2.5) מוסיף שמות מגזרים. עשיתי לפי המסמך (\"הם הקובעים\") — עד 3 מגזרים, ורק כשיש 2 מגזרים או יותר.",
            "3. **בדיקת \"70% ממילות התוכן בציטוט\" ב-`core_activity`:** המסמך לא מגדיר התאמת מילים. הגדרתי השוואה לפי גזע + משפחת מילים (designs ~ designer, manages ~ management); בלי זה ביטוי תקין כמו \"designs and manufactures semiconductor products\" נפסל. "
            "הוספתי גם בדיקה שהמילה הראשונה היא פועל בגוף שלישי יחיד (\"manufactures\", לא \"designer\" / \"develop\") — כי הרינדור הוא \"חברת X {פעילות}\" והתרגום תלוי בזה. זה לא כתוב במסמך.",
            "4. **ציר XBRL שלא משמש:** ציר נחשב \"לא שמיש\" כשהממברים מכסים פחות מ-60% מההכנסות או חופפים (סכום > 102%) — אז BP-1 משלים (`source=ai`). קרה ב-MSFT (ציר מוצרים חופף).",
            "5. **ממברים מצטברים:** ממבר נפסל אם שמו מצטבר (`Total`, `Corporate and other`, `Eliminations` וכו') או אם הוא שווה לסכום של 2–8 ממברים אחרים (סטייה עד 0.1%, לפחות מיליון).",
            "6. **שיוך אזורים:** \"Other Countries\" אינו \"מחוץ לארה\"ב\" (באינטל זה מופיע לצד סינגפור וטאיוואן) — מסומן `other` עם הטקסט המקורי. רק Non-US / International / Rest of world / Foreign → `outside_us`.",
            "7. **שדה שנכשל לא נכתב בטקסט** (גם אם נשארו בו פריטים חלקיים בפרופיל). `segments` של KO נכשל (ציטוט של EMEA לא נמצא בטקסט) ולכן אין משפט מגזרים ב-KO.",
            "8. **ניסוח אזורים בעברית:** \"מחוץ לארה\"ב\" לא מקבל \"מ\" נוספת (\"60% מההכנסות מחוץ לארה\"ב ו-40% מארצות הברית\").",
            "9. **`human_reviewed` באנגלית** נשאר `false` (אין שם ביטויים לסקירה, ואף אחד לא קרא אותו); בעברית `true` רק כשכל הביטויים שבטקסט `approved`.",
            "10. **הכנסות** נלקחות מאותם מספרים שהציון משתמש בהם (ה-result שנבנה מ-`financial_facts`), לא משאילתה נפרדת לטבלה; החפיר מ-A7 (`B3.2-Q5`) ב-`ai_assessments`.",
            "11. **ריצות הרקע (D1/T1) הקודמות:** סומנו `superseded` (לא נמחקו). התור: `ai_background` מריץ עכשיו BP-1 → פרופיל → תרגום → רינדור; קוד D1/T1 נשאר מסומן deprecated.",
            "12. **מקור הדוחות:** הדוחות הם ה-10-K האחרון שב-cache המקומי (MSFT: FY2026, שנה פיסקלית שנגמרת ב-30.6.2026). תוויות החברה (`label linkbase`) נשלפו מ-SEC לכל חברה שיש לה קובץ כזה; ל-MSFT אין קובץ כזה ושמות הממברים נגזרים משמם.", ""]
    # ------------------------------------------------------------------ per company
    out += ["## 2. 7 חברות סט הפיתוח", ""]
    others, axes_rows, used_types = [], [], {}
    per_company_calls = {t: v.get("gemini_attempts", 0) for t, v in (calls.get("per_company") or {}).items()}
    for t in tickers:
        ctx = b.load(t)
        p = b.profiles.latest(ctx["co"]["id"])
        out += [f"### {t} — {ctx['co']['company_name']}  (FY{ctx['fy']}, accession `{p['accession']}`, פרופיל #{p['id']}, מודל `{p['model']}`, גרסת סקיל {p['skill_version']})", ""]
        out += [profile_table(p, vocab), ""]
        for f in ORDER:
            for it in (p[f] or {}).get("items") or []:
                if it.get("status") == "other":
                    others.append((t, f, item_value(f, it, vocab), it.get("other_text") or ", ".join(it.get("members") or [])))
                if f == "competitor_types":
                    used_types.setdefault(it["industry"], set()).add(t)
        af = p["axes_found"] or {}
        axes_rows.append((t, af))
        tr = b.terms.map()
        inp = b.render_inputs(ctx, p, tr)
        en, _ = R.render(inp, "en")
        he_strict, info = R.render(inp, "he")
        he_prev, _ = R.render(inp, "he", preview=True)
        txt_he = b.texts.get(t, ctx["fy"], "background", "bp", "", "he") or {}
        txt_en = b.texts.get(t, ctx["fy"], "background", "bp", "", "en") or {}
        out += ["**הטקסט באנגלית** (מאושר, `ai_texts` kind=background, template_version=" + str(txt_en.get("template_version")) + ", profile_id=" + str(txt_en.get("profile_id")) + "):", "", *[f"> {ln}" if ln else ">" for ln in en.split("\n")], ""]
        out += [f"**הטקסט בעברית** — מצב: `{txt_he.get('state')}` / `{txt_he.get('approval_status')}`"
                + (" — **ממתין לתרגום** (לא מוצג למשתמשים)" if txt_he.get("state") == "awaiting_translation" else "") + ". להלן תצוגה מקדימה: מקומות שבהם ביטוי עדיין לא מתורגם מסומנים `[ממתין: ...]`; "
                "מה ששמור בפועל במסד הוא הגרסה בלי המשפטים האלה.", "", *[f"> {ln}" if ln else ">" for ln in he_prev.split("\n")], ""]
        need = phrases_needed(p)
        out += ["**ביטויים שתורגמו (אנגלית → עברית):** " + ("אין — לא בוצעה אף קריאה ל-Google (חסר מפתח)." if not any(phrase_key(e) in tr and tr[phrase_key(e)]["source"] == "google" for e, _k, _w in need) else ""), ""]
        rows = [f"| {e} | {tr[phrase_key(e)]['he'] if phrase_key(e) in tr else '*ממתין לתרגום*'} | {kind} | {tr[phrase_key(e)]['source'] + '/' + tr[phrase_key(e)]['status'] if phrase_key(e) in tr else ''} |" for e, kind, _w in need]
        if rows:
            out += ["| אנגלית | עברית | סוג | מקור/סטטוס |", "|---|---|---|---|", *rows, ""]
    # ------------------------------------------------------------------ tables for review
    out += ["## 3. טבלת התוויות ברבים לסוגי המתחרים — לסקירה שלך", "",
            "כל הענפים של ValueCompass (21 ענפים; \"Other\" לא נכלל — יש קוד `other` כללי). **`active=false` עד שתאשר.** אנא תקן את העברית בעמודה \"הצעה\" ואת המין (ז/נ — קובע התאמה של \"ארציים/ארציות\").", "",
            "| קוד | ענף (מהראוטר) | אנגלית ברבים | הצעה בעברית | מין | בשימוש ב |", "|---|---|---|---|---|---|"]
    for name, v in _yaml("vocab.yaml")["competitor_types"]["industry"].items():
        out.append(f"| `{v['code']}` | {name} | {v['en']} | {v['he']} | {'נ' if v['gender'] == 'f' else 'ז'} | {', '.join(sorted(used_types.get(v['code'], []))) or ''} |")
    out += ["", "תחומי הפעולה (scope) והסוגים הכלליים נטענו `active=true` כפי שכתבת: " + ", ".join(f"`{c}`" for c in ("local", "regional", "national", "international", "private_companies", "private_label", "startups", "government_entities", "other")) + ".", ""]
    out += ["## 4. ערכי `other` שנמצאו", ""]
    if others:
        out += ["| חברה | שדה | ערך | הטקסט המקורי |", "|---|---|---|---|", *[f"| {t} | {FIELD_HE[f]} | {cell(v, 80)} | {cell(o, 100)} |" for t, f, v, o in others], "",
                "כלל ההצעה (אותו `other` ב-3 חברות ומעלה → קוד חדש) לא הופעל — יש 7 חברות בלבד."]
    else:
        out.append("לא נמצאו.")
    out += ["", "## 5. צירי XBRL שנמצאו או חסרו", "", "| חברה | סה\"כ הכנסות (XBRL) | תוויות ב-linkbase | מגזרים | מוצרים ושירותים | אזורים |", "|---|---|---|---|---|---|"]

    def ax(af, k):
        a = (af.get("axes") or {}).get(k) or {}
        if not a.get("found"):
            return "חסר → BP-1"
        return f"נמצא ({a['n_items']} פריטים, כיסוי {a['coverage'] * 100:.0f}%" + (f", {a['n_dropped']} מצטברים הוסרו" if a.get("n_dropped") else "") + (f", {'/'.join(a['flags'])}" if a.get("flags") else "") + ")"
    for t, af in axes_rows:
        tot = af.get("total_revenue")
        out.append(f"| {t} | {tot / 1e9:.1f} מיליארד $ | {af.get('labels_found')} | {ax(af, 'segments')} | {ax(af, 'products_services')} | {ax(af, 'regions')} |")
    out += ["", "\"חסר → BP-1\" = הציר לא קיים ב-10-K; \"נמצא\" עם דגל `members_overlap` / `low_coverage` = לא שמיש, BP-1 השלים (`source=ai`).", ""]
    # ------------------------------------------------------------------ calls
    out += ["## 6. קריאות בפועל", "", "| | מספר |", "|---|---|", f"| Gemini — ריצה ראשונה (7 חברות) | {first} |", f"| Gemini — תיקון שדות שנכשלו (`refresh`) | {refresh} |",
            f"| **Gemini — סה\"כ (תקרה 25, נאכפת בקוד)** | **{first + refresh}** |", "| Google Translate | 0 (אין מפתח) |", "", "לפי חברה (ריצה ראשונה): " + ", ".join(f"{t}={n}" for t, n in per_company_calls.items()) + ".", "",
            "ניסיונות החוזרים (retry) הקבועים בסקיל: אחד לכל קריאה, עם הסיבה המדויקת. `refresh` הוא ניסיון חוזר נוסף שמבקש רק את מה שנכשל, עם הסיבה כבר בניסיון הראשון.", ""]
    out += ["## 7. מבנה ומסד", "",
            "- מיגרציה 17 (`supabase/migrations/20261026103017_business_profile.sql`, rollback ב-`supabase/rollback/`): `company_business_profiles`, `business_vocab`, `term_translations`; ל-`ai_texts` נוספו `template_version`, `profile_id` והסטטוס `superseded`.",
            "- בדיקות על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); גם עמודות ה-`ai_texts` הישנות; rollback נוסה בבלוק שבוטל והחזיר את המצב המקורי (md5 של `ai_texts` זהה, שלוש הטבלאות נעלמו).",
            "- RLS: משתמש מחובר קורא פרופילים, אוצר מילים פעיל (`active`) ותרגומים; אין לו כתיבה. טקסטים: רק `approved` (כמו קודם) — הטקסט העברי הממתין לתרגום והטקסטים `superseded` לא מוצגים.",
            "- נטען: 62 שורות `business_vocab`, 17 מונחי מילון → `term_translations` (`approved`/`human`).", ""]
    ver = ROOT / "scripts" / "ai_store" / "bp_verification.md"
    out += ["## 8. בדיקות ואידמפוטנטיות", "", ver.read_text(encoding="utf-8") if ver.exists() else "(לא הורצו)", ""]
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return f"{path} ({len(out)} lines)"
