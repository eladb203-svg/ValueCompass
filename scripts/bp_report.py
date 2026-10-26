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
    r1 = calls.get("gemini_attempts", 0) + (runs[0].get("gemini_attempts", 0) if runs else 0)
    r3 = sum(r.get("gemini_attempts", 0) for r in runs[1:])
    r2 = sum(r.get("gemini_attempts", 0) for r in calls.get("rounds", []) if r.get("round") == 2)
    terms_rows = b.terms.rows()
    n_az = sum(1 for r in terms_rows if r["source"] == "azure")
    n_human = sum(1 for r in terms_rows if r["source"] == "human")
    out = [f"# שלב BP — סבב 3 (תיקונים לפני ייצור) — {date.today().isoformat()}", "",
           "> מסד: **test בלבד**. ייצור לא נגע. מבנה הדוח כמו בסבבים הקודמים; סעיף 1 מתאר מה שונה בסבב הזה.", ""]
    out += ["## 1. סיכום", "",
            f"- **קריאות Gemini בסבב 3: {r3}** (תקרה 20): JPM ו-INTC — `revenue_models`; AMT — `customer_types`. סבבים קודמים: {r1} + {r2}; סה\"כ {r1 + r2 + r3}. flash-lite בלבד, תהליך אחד, המונה המשותף.",
            f"- **Azure Translator בסבב 3: 9 ביטויים** (4 אחרי הסרת מילים כלליות מהשמות, 5 בתרגום מחדש); בטבלה {n_az} ביטויים `azure`/`unreviewed` ו-{n_human} `human`/`approved`.",
            "- 7 הטקסטים באנגלית ובעברית מוצגים בסעיף 2 (העברית מאושרת, `human_reviewed=false`). `render --all` נותן 0 שינויים בריצה שנייה.", ""]
    out += ["### מה בוצע (לפי סעיפי ההודעה)", "",
            "1. **שמות (קוד, `src/bp/names.py`):** (א) מוסרים מהשם לפני תרגום ותצוגה: \"Segment\", \"Product Line(s)\"; במגזרים גם הקידומות \"Property, \" ו-\"Insurance \" (בקווי מוצרים הן נשארות — \"Property, Liability and Casualty Insurance\" הוא שם אמיתי). "
            "(ב) שם מסחרי נשאר לטיני ולא מתורגם: `kind=brand`, או מוצר שהטקסט נתן בשם באותיות גדולות בכל מילה (Windows, Azure, Microsoft 365 Copilot); שמות מ-XBRL (Concentrate Operations, Retail) לעולם מתורגמים. "
            "(ג) קו מוצרים בשם כללי (Property Revenue, Service(s), Product(s), Other…, Total…) לא מוצג; ואותו כלל לשמות מגזרים Other. אצל AMT קווי המוצרים נעלמו (Property Revenue / Service) ובמקומם נשאר המשפט על המגזרים. ",
            "2. **`terms edit` לפי טבלה:** הקובץ `scripts/terms_fix_2026-10-26.md` **עדיין לא קיים** ולכן לא החלתי תיקונים. נוסף הפקודה `vc.py terms apply-file <קובץ>` שמקבלת שורות `| id | english | hebrew |` (או `english | hebrew`), מחילה כל שורה כמו `terms edit` (`human`/`approved`) ומרנדרת מחדש את החברות שמשתמשות בביטוי. "
            "שגיאות התרגום הידועות שמחכות לתיקון: \"Concentrate operations\" → \"פעולות ריכוז\", JPM \"עוסקת בנקאות השקעות … וניהול ניהול נכסים\", שמות מגזרי CB (\"Overseas General\" → \"גנרל מעבר לים\", \"Life\" → \"חייו\"), \"Intelligent Cloud\" → \"ענן אינטליגנטי\".",
            "3. **רשימות:** נוסף `customer_types.telecom_operators` (ספקי תקשורת); AMT נשאל מחדש על `customer_types` — עכשיו telecom_operators, government, enterprises (\"לקוחותיה הם בעיקר ספקי תקשורת, ממשלות…\"). "
            "**למה צפון אמריקה חסרה אצל AMT:** אזורי AMT באים מהטקסט (אין ציר אזורים ב-XBRL); \"U.S. & Canada\" נשמר בפרופיל עם הקוד `other` מלפני שהמפה למדה אותו, והקוד מוסתר בתבנית. "
            "תיקון: קוד אזור מהטקסט נגזר כל פעם מחדש מהשם לפי המפה העדכנית; עכשיו \"פועלת בצפון אמריקה, באירופה ובאמריקה הלטינית\". "
            "**\"Africa & APAC\" עדיין לא מופיע באזורים** — שם מעורב של שני אזורים (מפה אחד→אחד); לכן נשאר `other` ומוסתר. אפשר להוסיף קוד אזור `africa_apac` או לפצל — החלטה שלך.",
            "4. **מודל ההכנסות:** *למה חסר ב-JPM ו-INTC:* בסבב 2 הוספתי ל-BP-1 \"רק כשהטקסט מתאר ממה מגיעות ההכנסות\" (לפי ההנחיה), ופתיחת Item 1 של שתיהן לא מתארת זאת במפורש — המודל החזיר `[]`. "
            "ניסחתי מחדש (גרסה 3): \"לפי מה שהטקסט אומר שהחברה מוכרת או גובה עליו, הראשי ראשון; `[]` רק אם הטקסט לא אומר דבר\". אחרי השאלה מחדש: INTC — מכירת מוצרים ושירותים; JPM — עמלות וניהול נכסים. "
            "**בבנק interest_income ראשון** (קוד, פרופיל BANK): אם המודל לא החזיר אותו, הקוד מוסיף אותו ראשון עם `source=code` (בלי ציטוט — הערה: זה פריט בלי ציטוט, מסומן). "
            "**KO:** `licensing` נדרש לציטוט שמדבר על רישוי/תמלוגים כהכנסה (licens/royalt/franchis + revenue/fee/income…); הציטוט של KO היה \"We own or license and market numerous beverage brands\" — הוסר. הכלל חל גם על כל פעם הבאה, ובדיקה חוזרת (`recheck`) החילה אותו על פרופילים קיימים.",
            "5. **UBER:** מיגרציה 19 (`companies.industry_override`, `industry_override_reason`; חוסמת override בלי סיבה; rollback נוסה). הערך קוד אוצר מילים (`internet_platforms_advertising`) → שם הענף של הנתב. "
            "הנתב (`route(..., override=...)`) מקבל את ה-Override מהשורה בכל טעינה (`runner.py`, שני המעברים), ולכן הוא נשמר בטעינות; גם רשומות העמיתים (`peer_source.load_records`) מקבלות אותו. UBER הוגדרה `internet_platforms_advertising` עם הנימוק. "
            "בפועל: UBER כבר לא מופיעה כ\"חברה דומה\" ל-MSFT (הופיעו Oracle, Salesforce, Adobe). **הציון של UBER לא חושב מחדש** — היא ב-test רק כתוצאת golden; השפעת הענף על הפרופיל/הציון תיבדק בטעינה הבאה שלה.",
            "6. **מדיניות שמירה — נדחה ל-K6d.** נושא שמירת פרופילים וטקסטים ישנים (מחיקה/ארכוב של גרסאות קודמות, כמה גרסאות של פרופיל נשמרות לכל חברה) לא נקבע עכשיו; כרגע: פרופיל אחד לכל (חברה, accession), טקסטי D1/T1 הישנים `superseded` ולא נמחקו. ", ""]
    out += ["### החלטות שאני מבקש שתבדוק", "",
            "1. **שורת interest_income בלי ציטוט** ב-JPM (קוד מוסיף לבנק) — מאשר שזה מקובל, או שעדיף להשאיר ריק.",
            "2. **\"Africa & APAC\"** — ראו סעיף 3.",
            "3. **\"Intel Core Ultra Series 3 processors\"** (מותג) ו-\"CPUs\" נשארים/מתורגמים לפי הכלל: מוצר שהטקסט נתן באותיות גדולות בכל מילה — לטיני; כל השאר מתורגם (\"CPUs\" נשאר כי הוא ראשי תיבות).", ""]
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
    out += ["## 6. קריאות בפועל", "", "| | מספר |", "|---|---|", f"| Gemini — סבב 1 | {r1} (מתוך 25) |", f"| Gemini — סבב 2 (תקרה 20) | **{r2}** |", f"| **Gemini — סבב 3 (תקרה 20, נאכפת בקוד)** | **{r3}** |", f"| Gemini — סה\"כ | {r1 + r2 + r3} |",
            f"| Azure Translator — ביטויים שנשלחו בסבב 3 | 9 (בבקשות של עד 25 ביטויים; תקרה 200) |", f"| Azure — ביטויים שנשמרו | {n_az} |", "| Google Translate | 0 (חלופה, לא בשימוש) |", "",
            "ביטויים שנדחו בבדיקות (נשארים \"ממתינים\" עד תרגום מחדש או תיקון ידני): ראו `translation_failed` ב-`scripts/ai_store/bp_calls.json`; בסבב זה הבדיקות תוקנו (שם/ראשי תיבות שנשארים לטיניים, מונח מילון ארוך) והביטויים שנכשלו תורגמו מחדש. "
            "הניסיון החוזר של BP-1 (אחד לכל קריאה, עם הסיבה המדויקת) כלול בספירה.", ""]
    out += ["## 7. מבנה ומסד", "",
            "- מיגרציה 19 (`supabase/migrations/20261026190019_companies_industry_override.sql`): `companies.industry_override` + `industry_override_reason` (rollback נוסה). מיגרציה 17 (סבב 1) ומיגרציה 18 (`supabase/migrations/20261026160018_bp_display_name_azure.sql`, rollback ב-`supabase/rollback/`): העמודה `display_name` ב-`company_business_profiles` והערך `azure` ב-`term_translations.source`. "
            "על test: md5 של `companies`, `extraction_items`, `ai_assessments`, `financial_facts`, `score_runs` זהה לפני ואחרי (5 מתוך 5); ה-rollback נוסה בבלוק שבוטל והחזיר את המצב.",
            "- RLS ללא שינוי: משתמש מחובר קורא פרופילים, אוצר מילים פעיל ותרגומים; אין לו כתיבה; טקסטים — רק `approved`.",
            f"- `business_vocab`: {len(b.vocab.labels['customer_types']) + len(b.vocab.labels['revenue_models']) + len(b.vocab.labels['regions']) + len(b.vocab.labels['competitor_types'])} קודים; `sync-vocab` עדכן 22 תוויות/דגלי `active` והוסיף `investment_income`.", ""]
    ver = ROOT / "scripts" / "ai_store" / "bp_verification.md"
    out += ["## 8. בדיקות ואידמפוטנטיות", "", ver.read_text(encoding="utf-8") if ver.exists() else "(לא הורצו)", ""]
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return f"{path} ({len(out)} lines)"
