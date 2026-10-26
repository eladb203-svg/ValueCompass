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
    runs = calls.get("refresh_runs", [])
    g_total = calls.get("gemini_attempts", 0) + sum(r.get("gemini_attempts", 0) for r in runs) + sum(r.get("gemini_attempts", 0) for r in calls.get("rounds", []))
    terms_rows = b.terms.rows()
    n_az = sum(1 for r in terms_rows if r["source"] == "azure")
    n_unrev = sum(1 for r in terms_rows if r["status"] == "unreviewed")
    n_human = sum(1 for r in terms_rows if r["source"] == "human")
    out = [f"# שלב BP — סבב 5: העלאה לייצור (אחרי סבבי התיקונים 1–4) — {date.today().isoformat()}", "",
           "> מסד: **test בלבד**. ייצור לא נגע. בסבב הזה **לא בוצעה אף קריאת Gemini ואף קריאת תרגום** (סה\"כ Gemini בכל השלבים: " + str(g_total) + ").", ""]
    out += ["## 0. ייצור (אושר על ידך בצ'אט)", "",
            "**תוצאה:** מיגרציות 17, 18, 19 הוחלו בייצור (`zwpftrjryxyymrxsprqh`), אוצר המילים והתרגומים נטענו, 7 הפרופילים הועתקו מ-test, הטקסטים רונדרו בייצור, וטקסטי D1/T1 הישנים (17) סומנו `superseded`. **0 קריאות Gemini ו-0 קריאות תרגום בייצור.** "
            "יש **אי-התאמה אחת** מול test (MSFT) — ראו להלן.", "",
            "| שלב | תוצאה |", "|---|---|",
            "| תיקונים ב-test לפני הייצור | `CPUs` → \"מעבדים\" (כלל חדש: ראשי תיבות רבים כלליים כמו CPUs/GPUs מתורגמים; AWS נשאר לטיני); `terms approve` לפעילות המרכזית של INTC ו-AMT; נמחקו 18 שורות `term_translations` שלא בשימוש והשלב יצר; נשארו 55 שורות, כולן `approved`; `render --all` ואז ריצה שנייה — 0 שינויים |",
            "| (א) fingerprint | 23 הטבלאות הקיימות — מבנה עמודות, אילוצים, אינדקסים, מדיניות RLS ומצב RLS — **זהים בייצור ובtest** פרט לשינויים של 17–19 (העמודות והאילוצים החדשים ב-`ai_texts`/`companies` והטבלאות החדשות הוצאו מהשוואה). אי-התאמה — אין |",
            "| (ב) מיגרציות | 17 → 18 → 19 לפי הסדר. md5 של `companies`, `ai_assessments`, `extraction_items`, `financial_facts`, `score_runs` ושל עמודות `ai_texts` הישנות **זהה לפני ואחרי** (6 מתוך 6; ב-`companies` בלי שתי העמודות החדשות, שהן NULL). **rollback נוסה בייצור** בבלוק שבוטל (מחיקת העמודות/הטבלאות של 19, 18, 17 לפי הסדר ההפוך): md5 של `companies` ושל `ai_texts` חזר בדיוק למקור, ושלוש הטבלאות נעלמו; אחרי הביטול המיגרציות נשארו מוחלות |",
            "| RLS בייצור כ-`authenticated` | 7 פרופילים, 64 שורות אוצר מילים (כולן פעילות), 55 תרגומים, 14 טקסטי רקע חדשים גלויים; **0** שורות `pending_review` / `superseded` / `failed` גלויות; 0 טקסטי D1/T1 ישנים גלויים; הכנסה ועדכון נדחו |",
            "| (ג) טעינה | `business_vocab`: 64 שורות; `term_translations`: 55 שורות `approved` בלבד (0 `unreviewed` ב-test, ולכן לא הועתק דבר שלא אושר) |",
            "| (ד) 7 החברות | הפרופילים הועתקו מ-test (KO, MSFT, INTC, JPM, CB, O, AMT; אותם `accession`), טקסטים רונדרו בייצור, 17 טקסטי D1/T1 הישנים `superseded` (לא נמחקו) |",
            "| (ה) אימות | 6 מתוך 7 חברות: טקסט אנגלי ועברי **זהים ל-test**, `human_reviewed=true`, `approved`; רינדור שני = 0 שינויים בכל 7; `v_company_status`: 7 חברות `complete`, `background_status=approved`, `background_human_reviewed=true` |", "",
            "**אי-ההתאמה (MSFT):** משפט \"חברות דומות\" שונה — בייצור: Oracle, Uber Technologies, Salesforce; ב-test: Oracle, Salesforce, Adobe. הסיבה: UBER קיימת בייצור **רק** כתוצאת golden בקובץ ואינה שורה ב-`companies`, ולכן `industry_override` (שהוא עמודה בשורת החברה) לא קיים בייצור והיא עדיין מסווגת Software. "
            "לא יצרתי שורת חברה ל-UBER בייצור (זה היה מוסיף חברה בלי נתונים מחוץ לסט הפיתוח). התיקון יתקיים מעצמו כשתיטען UBER לייצור עם ה-override, או שאוכל להוסיף שורה ריקה עם ה-override אם תאשר. שאר הטקסט של MSFT זהה.", ""]
    out += ["## 1. סיכום סבב 4 (קודם)", "",
            f"- **`scripts/terms_fix_2026-10-26.md` הוחל:** 37 שורות עודכנו ל-`human`/`approved` (שורות שהשם בהן נוקה בסעיף 1 הותאמו לשם המנוקה; \"(להשאיר בלטינית)\" נשמר כערך באנגלית: Windows, Azure, Microsoft 365 Copilot). `render --all` הורץ; ריצה שנייה — 0 שינויים בכל 7 החברות.",
            "- **שורות שלא נמצאו (2):** (א) `INTC | Intel Core Ultra Series 3 processors (מותג)` — שם מותג אינו ביטוי מתורגם; ביצעתי את ההוראה על הפרופיל עצמו: שם הפריט שונה ל-\"Intel Core Ultra\" (המקור נשמר ב-`name_original`). "
            "(ב) `AMT | Europe (Property, …)` — אין ביטוי כזה בטבלה: הטקסט העברי מתרגם רק 3 מגזרים ראשונים (US and Canada, Latin America, Africa & APAC), \"Europe\" אינו ביניהם.",
            "- **חפיפה בטבלה:** \"Latin America\" מופיע ב-KO וב-AMT וגם \"Europe, Middle East, Africa\" — מפתח הביטוי משותף, ולכן התיקון חל על שתיהן; שורת \"Accident and Health Insurance\" ושורת \"Data Centers\" התאימו לשורות המילון הקיימות (אותו תרגום) ולכן לא שינו דבר.",
            f"- **ביטויים שנשארו `unreviewed`:** {n_unrev} (ראו סעיף 2א, עם התרגום הנוכחי). `human`/`approved`: {n_human}. נותרו {n_az} שורות `azure` — מהן {n_unrev} עדיין לא נסקרו. בטקסט העברי של חברה `human_reviewed=true` רק כשכל הביטויים שבו `approved` (סעיף 2א מציין).",
            "- **interest_income בבנק (סעיף 2 בהודעה):** הקוד מוסיף את `interest_income` כראשון רק כשהכנסות הריבית נטו ≥ 30% מהכנסות הבנק (שניהם מתוצאת הציון, כלומר מ-`financial_facts`); הפריט `source=code`, עם תגית (\"financial_facts: net_interest_income / bank revenue = X%\") והשיעור. אחרת לא מוסיף, ופריט שהוסף בעבר בקוד ומפר את הכלל מוסר. "
            "JPM: הריבית נטו 95.4 מיליארד $ מתוך הכנסות 182.4 מיליארד $ = 52.3% — ולכן נוסף, והוא ראשון. אם המודל כבר החזיר אותו (בלי ציטוט קוד) הוא נשאר כפי שהוא.",
            "- **אזורים מעורבים (סעיף 3):** במפת האזורים נוסף מקטע `multi`: \"Africa & APAC\" → mea + asia_pacific; \"Europe, Middle East & Africa\" / EMEA → europe + mea, ועוד כמה צירופים. הפיצול קורה רק לפריט בלי שיעור (שיעור אי אפשר לפצל; ציר XBRL עם שיעור נשאר בקוד אחד, ו-EMEA ב-JPM ממשיך להיות europe). AMT: \"פועלת בצפון אמריקה, באמריקה הלטינית, …\" — ראו הטקסט.", ""]
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
    out += ["## 2א. ביטויים שנשארו `unreviewed` — עם התרגום הנוכחי", "", "| # | אנגלית | עברית (נוכחית, Azure) | בשימוש ב |", "|---|---|---|---|"]
    from src.bp.translate import phrase_key as _pk
    use = {}
    for t, pr in profs.items():
        for e, _k, _w in phrases_needed(pr):
            use.setdefault(_pk(e), set()).add(t)
    for r in sorted((x for x in b.terms.rows() if x["status"] == "unreviewed"), key=lambda x: x["id"]):
        out.append(f"| {r['id']} | {cell(r['en'], 90)} | {cell(r['he'], 110)} | {', '.join(sorted(use.get(_pk(r['en']), []))) or '(לא בשימוש בטקסט)'} |")
    reviewed_state = []
    for t in tickers:
        row = b.texts.get(t, profs[t]["fiscal_year"], "background", "bp", "", "he") or {}
        reviewed_state.append(f"{t}: {'כן' if row.get('human_reviewed') else 'לא'}")
    out += ["", "`human_reviewed` של הטקסט העברי: " + ", ".join(reviewed_state) + ". שורות \"(לא בשימוש בטקסט)\" הן שאריות של שמות לפני הניקוי (Segment, Product Line, \"Property, \"): הטקסט משתמש עכשיו בשם המנוקה, שתוקן בטבלה; השאריות לא משפיעות על שום טקסט. "
            "שני הביטויים היחידים שבשימוש ועדיין לא נסקרו הם פעילות מרכזית של INTC ושל AMT, ולכן הטקסט העברי שלהן `human_reviewed=false`.", ""]
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
    out += ["## 6. קריאות בפועל", "", "| | מספר |", "|---|---|", "| Gemini — סבב 1 | 23 (מתוך 25) |", "| Gemini — סבב 2 | 10 (מתוך 20) |", "| Gemini — סבב 3 | 3 (מתוך 20) |",
            "| **Gemini — סבב 4 (זה)** | **0** |", f"| Gemini — סה\"כ | {g_total} |", "| Azure Translator — סבב 4 | 0 |", f"| Azure — שורות `azure` בטבלה | {n_az} |", "| Google Translate | 0 (חלופה, לא בשימוש) |", ""]
    out += ["## 7. מבנה ומסד", "",
            "- מיגרציה 19 (`supabase/migrations/20261026190019_companies_industry_override.sql`): `companies.industry_override` + `industry_override_reason` (rollback נוסה). מיגרציה 17 (סבב 1) ומיגרציה 18 (`supabase/migrations/20261026160018_bp_display_name_azure.sql`, rollback ב-`supabase/rollback/`): העמודה `display_name` ב-`company_business_profiles` והערך `azure` ב-`term_translations.source`. "
            "על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); ה-rollback נוסה בבלוק שבוטל והחזיר את המצב.",
            "- RLS ללא שינוי: משתמש מחובר קורא פרופילים, אוצר מילים פעיל ותרגומים; אין לו כתיבה; טקסטים — רק `approved`.",
            f"- `business_vocab`: {len(b.vocab.labels['customer_types']) + len(b.vocab.labels['revenue_models']) + len(b.vocab.labels['regions']) + len(b.vocab.labels['competitor_types'])} קודים; `sync-vocab` עדכן 22 תוויות/דגלי `active` והוסיף `investment_income`.", ""]
    ver = ROOT / "scripts" / "ai_store" / "bp_verification.md"
    out += ["## 8. בדיקות ואידמפוטנטיות", "", ver.read_text(encoding="utf-8") if ver.exists() else "(לא הורצו)", ""]
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return f"{path} ({len(out)} lines)"
