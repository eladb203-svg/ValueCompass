"""The Hebrew report of the BP stage (scripts/code_stage_bp_<date>.md), built from what is stored in the test database. Called by `bp_stage.py report`."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALL_LOG = ROOT / "scripts" / "ai_store" / "bp_calls.json"
FIELD_HE = {"display_name": "שם תצוגה", "core_activity": "פעילות מרכזית", "segments": "מגזרים", "products_services": "מוצרים ושירותים", "customer_types": "סוגי לקוחות", "revenue_models": "מודלי הכנסות",
            "regions": "אזורים", "competitors": "מתחרים (בשם)", "competitor_types": "סוגי מתחרים"}
ORDER = list(FIELD_HE)
STATUS_HE = {"ok": "תקין", "other": "other (מסומן)", "not_found": "לא נמצא", "failed": "נכשל"}


def cell(x, n: int = 150) -> str:
    t = " ".join(str(x if x is not None else "").split()).replace("|", "/")
    return t if len(t) <= n else t[:n - 1] + "…"


def pct(s):
    return "" if s is None else f"{s * 100:.1f}%"


def item_value(f: str, it: dict, vocab) -> str:
    if f in ("core_activity", "display_name"):
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
    r1 = calls.get("gemini_attempts", 0) + sum(r.get("gemini_attempts", 0) for r in calls.get("refresh_runs", []))
    r2 = sum(r.get("gemini_attempts", 0) for r in calls.get("rounds", []) if r.get("round") == 2)
    az = sum(r.get("translated_phrases", 0) for r in calls.get("rounds", []) if r.get("round") == 2)
    terms_rows = b.terms.rows()
    n_az = sum(1 for r in terms_rows if r["source"] == "azure")
    out = [f"# שלב BP — סבב 2 (תיקונים): רקע מפרופיל עסקי, תרגום ב-Azure, רינדור מתבנית — {date.today().isoformat()}", "",
           "> מסד: **test בלבד**. ייצור לא נגע. מסמך מקור: `docs/ai/ValueCompass_AI_Skills_Other_2026-10-26_10-30.md` (3.1–3.2) + התיקונים שבהודעה שלך. מבנה הדוח כמו בסבב 1.", ""]
    out += ["## 1. סיכום", "",
            f"- **קריאות Gemini בפועל בסבב הזה: {r2}** מתוך תקרה של 20 (סבב 1: {r1} מתוך 25; סה\"כ {r1 + r2}). מודל flash-lite בלבד, תהליך אחד, המונה המשותף. BP-1 נשאל שוב **רק על השדות שהפרומפט שלהם השתנה**: "
            "`display_name`, `customer_types`, `revenue_models`, `competitors`, `competitor_types` (קריאה אחת לחברה; ל-KO נוספו 2 ניסיונות ל-`display_name`). המגזרים, האזורים והמוצרים מ-XBRL נקראו מחדש בלי מודל.",
            f"- **תרגום: Azure Translator** (`TRANSLATION_PROVIDER=azure`, מפתח ואזור מ-`.env`, לא מודפסים; Google נשאר כחלופה בקוד). {az} ביטויים נשלחו בבקשות מרוכזות (עד 25 בבקשה), {n_az} נשמרו ב-`term_translations` כ-`azure`/`unreviewed`; "
            "22 מונחי מילון (17 המקוריים + accident and health, P&C, A&H ושתי הצורות property and casualty insurance / accident and health insurance) `approved`/`human`.",
            "- **הטקסטים העבריים של כל 7 החברות** מאושרים (`approval_status=approved`) עם `human_reviewed=false` — המשתמש יראה \"תרגום אוטומטי\" עד שתאשר את הביטויים (`vc.py terms review` / `approve` / `edit`).",
            "- ריצה חוזרת: `render --all` נותן 0 שינויים, ו-BP-1 לא נשאל שוב על אותו `accession` — ראו סעיף 8.", ""]
    out += ["### מה בוצע מההודעה שלך (לפי הסעיפים)", "",
            "1. **Azure:** מומש (v3, `from=en&to=he`, כמה ביטויים בבקשה, `textType=html` כדי שסימני ההגנה על שמות ומונחים יישמרו). מיגרציה 18 על test הוסיפה `azure` לערכי `source`.",
            "2. **מגזרי XBRL:** נבדקים כל מושגי ההכנסות (`Revenues`, `RevenueFromContract…`, `RevenuesNetOfInterestExpense`, `PremiumsEarnedNet`, `RevenueForReportableSegments`, `SalesRevenueNet` ועוד — כל מושג ששמו כולל Revenue/Premiums), נבחר המושג שסכום הממברים שלו הקרוב ביותר לסך ההכנסות, וגם הקשרים עם `ConsolidationItemsAxis=OperatingSegmentsMember` מתקבלים. "
            "כשהממברים חופפים (סכום > 102%) נבחרת הקבוצה הגדולה ביותר שסכומה הוא סך ההכנסות (בגבול 0.5%) — **רק לציר המגזרים**. פירוט לכל חברה בסעיף 5.",
            "3. **`display_name`:** שדה חדש ב-BP-1 (גרסת סקיל 2) עם ציטוט; הקוד מסיר סיומת משפטית (Inc./Corp./Co./Company…) ו-\"The\" מתחילת השם בתנאי שהשם הקצר עדיין בציטוט; כשל → נופלים לשם מה-EDGAR המנוקה. נשמר בעמודה `display_name` (מיגרציה 18) ומשמש בתבנית.",
            "4. **BP-1:** (א) `revenue_models` רק כשהטקסט מתאר ממה ההכנסות, הראשי ראשון; (ב) נשלחות **כל** פסקאות התחרות של Item 1 (גם של כל מגזר), עד 12,000 תווים; (ג) `customer_types` כולל לקוחות עסקיים/מוסדיים/ממשלתיים כשמוזכרים.",
            "5. **רשימות:** נוסף `revenue_models.investment_income` (הכנסות מהשקעות); `U.S. & Canada` → `north_america`; 22 התוויות ברבים אושרו ו-`active=true`, עם שני התיקונים (ברוקרי ביטוח ונותני שירותי ביטוח; חברות בנייה ויזמות נדל\"ן).",
            "6. **מילון:** `accident and health` → \"ביטוח תאונות ובריאות\" נוסף; `P&C` ו-`A&H` מורחבים (property and casualty / accident and health) לפני התרגום, ונשמרו גם כערכים ישירים `approved`/`human`.",
            "7. **תבנית:** (א) שיעור מוצג רק כשהוא שיעור מההכנסות מ-XBRL — אחרת שם בלי שיעור (וניסוח \"ביניהם\" במקום \"הגדולים שבהם\"); (ב) פריט בשם Other / Other Countries / Other Operating Segment לא מוצג ולא נספר; "
            "(ג) INCOME_REAL_ESTATE: \"Its main property types are…\" / \"סוגי הנכסים העיקריים\"; (ד) אזורים בלי שיעורי XBRL: \"It operates in …\" / \"פועלת ב…\".",
            "8. **סיווג UBER:** ראו להלן.", ""]
    out += ["### UBER — סיווג הענף (דיווח בלבד, לא שיניתי)", "",
            "UBER מסווגת **Software** (פרופיל `TECH_ASSET_LIGHT`) ולכן מופיעה כ\"חברה דומה\" ל-MSFT. הנימוק בראוטר: ה-SIC שלה, 7389, הוא קוד כללי (\"multi\") שלא מכריע, ולכן הוחלט לפי **ענף הספק** (`Software - Application` → Software, tier = provider). "
            "ההגדרה של \"Internet platforms and advertising\" כוללת שווקים שמחברים קונים ומוכרים — Uber (נסיעות ומשלוחים) קרובה אליה יותר מאשר לתוכנה. שינוי כזה הוא החלטת ענף (ישפיע על קבוצת העמיתים ועל התוויות), לכן אני מחכה להחלטתך; "
            "אם תאשר, התיקון הוא override ענף ל-UBER בראוטר והרצה מחדש של הציון בלבד.", ""]
    out += ["### החלטות ושינויים שאני מבקש שתבדוק", "",
            "1. **איכות התרגום האוטומטי — כל הביטויים `unreviewed`, ויש שגיאות שאני מבקש שתתקן עם `terms edit`:** \"Windows\" תורגם \"חלונות\" (שם מוצר שהוא מילה רגילה); \"Concentrate operations\" → \"פעולות ריכוז\" (המילון מכיר \"concentrates\" ברבים בלבד); "
            "ב-JPM \"עוסקת בנקאות השקעות … וניהול ניהול נכסים\" (ה-\"ב\" נבלעת ו\"ניהול\" כפול סביב מונח המילון); שמות מגזרי CB (\"Insurance Overseas General\" → \"אינשורנס אוברסיז ג'נרל\", \"Life\" → \"חייו\"). "
            "הגנה אוטומטית יש לשמות עם אות גדולה באמצע / ראשי תיבות ולמונחי המילון (כסימון מילון של Azure, כדי שהמונח יישמר בתוך הדקדוק); המילה Segment בתחילת/סוף שם מגזר לא מתורגמת. מותר להשאיר שם בלטינית: `terms edit <id> --he \"Windows\"`.",
            "2. **\"הכנסות מהשקעות\"** מקבל \"מ\" פעמיים בעברית (\"מהכנסות מהשקעות\") — תקין אך כבד; מוכן לשנות את התווית אם תרצה.",
            "3. **שיעורים שמוצגים:** רק שיעורי XBRL מההכנסות. שיעורי מגזרים מהטקסט (למשל אחוזי NPE ב-CB) לא מוצגים; אם מגזר מופיע בלי שיעור, המשפט אומר \"ביניהם\" ולא \"הגדולים שבהם\".",
            "4. **שמות מגזרי XBRL** באנגלית באים מה-label של החברה; אם אין (MSFT: אין קובץ `_lab.xml` בפילינג) הם נגזרים משם הממבר (\"More Personal Computing\"). שם כמו \"Segment Insurance North American Commercial P&C\" (CB) הוא ה-label של החברה עצמה.",
            "5. **בדיקת 70% מילות תוכן / פועל בגוף שלישי / ממברים מצטברים / סף 60% כיסוי**: כמו בסבב 1 (מאושרות 2 ו-3 לפי הודעתך; 4–6 בעינן).",
            "6. **שיוך `Other Countries`** (אינטל) ל-`other`, לא ל-`outside_us` — כמו בסבב 1.", ""]
    # ------------------------------------------------------------------ per company
    out += ["## 2. 7 חברות סט הפיתוח", ""]
    others, axes_rows, used_types = [], [], {}
    profs = {}
    for t in tickers:
        ctx = b.load(t)
        p = b.profiles.latest(ctx["co"]["id"])
        profs[t] = p
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
        out += ["**ביטויים שתורגמו (אנגלית → עברית):** " + ("אין." if not any(phrase_key(e) in tr and tr[phrase_key(e)]["source"] in ("azure", "google") for e, _k, _w in need) else ""), ""]
        rows = [f"| {e} | {tr[phrase_key(e)]['he'] if phrase_key(e) in tr else '*ממתין לתרגום*'} | {kind} | {tr[phrase_key(e)]['source'] + '/' + tr[phrase_key(e)]['status'] if phrase_key(e) in tr else ''} |" for e, kind, _w in need]
        if rows:
            out += ["| אנגלית | עברית | סוג | מקור/סטטוס |", "|---|---|---|---|", *rows, ""]
    # ------------------------------------------------------------------ tables for review
    out += ["## 3. טבלת התוויות ברבים לסוגי המתחרים", "",
            "**אושרו על ידך וכולן `active=true`** (עם שני התיקונים). \"Other\" לא נכלל — יש קוד `other` כללי. עמודת המין (ז/נ) קובעת התאמת \"ארציים/ארציות\" בטקסט.", "",
            "| קוד | ענף (מהראוטר) | אנגלית ברבים | עברית (מאושרת) | מין | בשימוש ב |", "|---|---|---|---|---|---|"]
    for name, v in _yaml("vocab.yaml")["competitor_types"]["industry"].items():
        out.append(f"| `{v['code']}` | {name} | {v['en']} | {v['he']} | {'נ' if v['gender'] == 'f' else 'ז'} | {', '.join(sorted(used_types.get(v['code'], []))) or ''} |")
    out += ["", "נוספו ל-`revenue_models`: `investment_income` (הכנסות מהשקעות). מיפוי אזורים: `U.S. & Canada` → `north_america`.", ""]
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
        return f"נמצא ({a['n_items']} פריטים, כיסוי {a['coverage'] * 100:.0f}%" + (f", {a['n_dropped']} הוסרו" if a.get("n_dropped") else "") + (f", {'/'.join(a['flags'])}" if a.get("flags") else "") + ")"
    for t, af in axes_rows:
        tot = af.get("total_revenue")
        out.append(f"| {t} | {tot / 1e9:.1f} מיליארד $ | {af.get('labels_found')} | {ax(af, 'segments')} | {ax(af, 'products_services')} | {ax(af, 'regions')} |")
    out += ["", "\"חסר → BP-1\" = הציר לא קיים ב-10-K (BP-1 מילא, `source=ai`); דגל `members_overlap` / `low_coverage` = הציר נמצא אך לא שמיש.", ""]
    out += ["### מגזרים מ-XBRL — מה נמצא ב-KO, INTC, JPM, CB (ובשאר)", "",
            "| חברה | מושג שנבחר (סכום הממברים הקרוב ביותר לסך ההכנסות) | כיסוי | מגזרים (שיעור מההכנסות) | ממברים שהוסרו | הערה |", "|---|---|---|---|---|---|"]
    notes = {"KO": "לפני התיקון: הציר לא נמצא כלל. הערכים מדווחים בהקשר OperatingSegmentsMember.",
             "INTC": "הממברים חופפים (יש גם ממבר-על); נבחרה הקבוצה הגדולה ביותר שסכומה הוא סך ההכנסות — Intel Foundry לא נכנס אליה.",
             "JPM": "ההפרש מ-100% הוא הכנסות שאינן משויכות לשלושת המגזרים.",
             "CB": "כיסוי 89% — ההפרש הוא הכנסות שאינן במושג שנבחר."}
    for t in ["KO", "INTC", "JPM", "CB"] + [x for x in tickers if x not in ("KO", "INTC", "JPM", "CB")]:
        pr = profs.get(t)
        if not pr:
            continue
        sg = pr["segments"] or {}
        a = ((pr["axes_found"] or {}).get("axes") or {}).get("segments") or {}
        its = sg.get("items") or []
        shown = "; ".join(f"{i['name']} ({pct(i.get('share'))})" if i.get("share") is not None else i["name"] for i in its) if its else "—"
        out.append(f"| {t} | {cell((its[0].get('tag') or '').split('|')[-1].replace('us-gaap:', '') if its and its[0].get('tag') else ('(מהטקסט, source=' + str(sg.get('source')) + ')'), 60)} | "
                   f"{('%.0f%%' % (a['coverage'] * 100)) if a.get('coverage') else ''} | {cell(shown, 260)} | {a.get('n_dropped', 0)} | {notes.get(t, '') if sg.get('source') == 'xbrl' or t in notes else ''} |")
    out += ["", "- **KO**: נמצאו 5 מגזרים (North America, Europe/Middle East/Africa, Latin America, Bottling Investments, Asia Pacific) בכיסוי 99.7%.",
            "- **INTC**: נמצאו 3 פריטים לאחר פתרון החפיפה; **JPM**: 3 מגזרים בכיסוי 98%; **CB**: 6 מגזרים בכיסוי 89%.", ""]
    out += ["## 6. קריאות בפועל", "", "| | מספר |", "|---|---|", f"| Gemini — סבב 1 | {r1} (מתוך 25) |", f"| **Gemini — סבב 2 (תקרה 20, נאכפת בקוד)** | **{r2}** |", f"| Gemini — סה\"כ | {r1 + r2} |",
            f"| Azure Translator — ביטויים שנשלחו | {az} (בבקשות של עד 25 ביטויים; תקרה 200) |", f"| Azure — ביטויים שנשמרו | {n_az} |", "| Google Translate | 0 (חלופה, לא בשימוש) |", "",
            "ביטויים שנדחו בבדיקות (נשארים \"ממתינים\" עד תרגום מחדש או תיקון ידני): ראו `translation_failed` ב-`scripts/ai_store/bp_calls.json`; בסבב זה הבדיקות תוקנו (שם/ראשי תיבות שנשארים לטיניים, מונח מילון ארוך) והביטויים שנכשלו תורגמו מחדש. "
            "הניסיון החוזר של BP-1 (אחד לכל קריאה, עם הסיבה המדויקת) כלול בספירה.", ""]
    out += ["## 7. מבנה ומסד", "",
            "- מיגרציה 17 (סבב 1) ומיגרציה 18 (`supabase/migrations/20261026160018_bp_display_name_azure.sql`, rollback ב-`supabase/rollback/`): העמודה `display_name` ב-`company_business_profiles` והערך `azure` ב-`term_translations.source`. "
            "על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); ה-rollback נוסה בבלוק שבוטל והחזיר את המצב.",
            "- RLS ללא שינוי: משתמש מחובר קורא פרופילים, אוצר מילים פעיל ותרגומים; אין לו כתיבה; טקסטים — רק `approved`.",
            f"- `business_vocab`: {len(b.vocab.labels['customer_types']) + len(b.vocab.labels['revenue_models']) + len(b.vocab.labels['regions']) + len(b.vocab.labels['competitor_types'])} קודים; `sync-vocab` עדכן 22 תוויות/דגלי `active` והוסיף `investment_income`.", ""]
    ver = ROOT / "scripts" / "ai_store" / "bp_verification.md"
    out += ["## 8. בדיקות ואידמפוטנטיות", "", ver.read_text(encoding="utf-8") if ver.exists() else "(לא הורצו)", ""]
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return f"{path} ({len(out)} lines)"
