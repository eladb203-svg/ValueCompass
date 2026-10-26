"""The background of a company, end to end (AI skills 2026-10-26_10-30): XBRL axes -> BP-1 -> profile -> phrase translation -> rendered texts. Replaces the D1 / T1 chain.

``BackgroundBuilder.run(ticker)`` is the queue task. Every step is idempotent: a profile exists once per (company, accession) and BP-1 is not asked again for it; a phrase that has a translation is
not translated again; a render that gives the same text changes nothing in the database.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from src.ai import content as C
from src.scoring import peer_source as PS

from . import bp1, render as R, xbrl_axes as X
from .similar import pick_similar, size_of
from .stores import PROFILE_FIELDS, ProfileStore, TermStore
from .translate import GoogleTranslate, NoKey, phrase_key, translate_phrase
from .vocab import Vocab

PROMPT_VERSION = "bp"            # ai_texts.prompt_version of the rendered background (template_version changes in place)
MIN_COVERAGE = 0.6               # an XBRL axis whose members cover less of the revenue is not used: BP-1 completes the field


def pretty_name(edgar_name: str) -> str:
    """The display name of a company: the EDGAR name without the legal suffix and the state code ("/DE/", "/MN"), small words in lower case ("Bank of America")."""
    n = re.sub(r"\s*/[A-Za-z]{2}/?(?=\s|$)", "", edgar_name or "")
    out = C.display_name(n)
    return " ".join(w.lower() if (k and w in ("Of", "And", "The")) else w for k, w in enumerate(out.split()))


def fetch_labels(sec, filing_path: str, cik) -> Optional[str]:
    """The filing's label linkbase (company extension labels), through the rate-limited SEC client; None when the filing has none."""
    m = re.match(r"(\d{18})_(.+)\.htm$", Path(filing_path).name)
    if not m or sec is None or not cik:
        return None
    acc, stem = m.groups()
    cik = int(cik)                                   # the company's CIK (the accession prefix is the filer agent, not always the company)
    try:
        return sec.get_text(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{stem}_lab.xml", f"{acc}_{stem}_lab.xml")
    except Exception:   # noqa: BLE001 - member names then come from the member names themselves
        return None


def latest_end(j: dict) -> str:
    if j.get("fiscal_years"):
        return str(sorted(j["fiscal_years"].values())[-1])[:10]
    return str(j["inputs"]["end"][-1])[:10]


def moat_of(ai_store, ticker: str, fy: int) -> tuple:
    """A7 (B3.2-Q5): -> (level 0/1/2 or None, source or None)."""
    rows = [r for r in ai_store.rows(ticker) if r["fiscal_year"] == fy and r["question_id"] == "B3.2-Q5" and r["state"] == "answered"]
    if not rows:
        return None, None
    a = rows[-1]
    extra = (a.get("evidence") or {}).get("extra") or {}
    return a.get("answer"), extra.get("moat_source") or ("none" if a.get("answer") == 0 else None)


def phrases_needed(profile: dict) -> list:
    """The free phrases the Hebrew text uses: [(english phrase, kind, whole_sentence)] - core_activity, up to 3 product lines, up to 3 segment names (when there are 2 or more segments)."""
    out = []
    ok = lambda f: [] if (profile.get(f) or {}).get("status") == "failed" else ((profile.get(f) or {}).get("items") or [])   # noqa: E731
    ca = ok("core_activity")
    if ca:
        out.append((ca[0]["value"].strip().rstrip("."), "core_activity", True))
    prods = [i for i in ok("products_services") if i.get("kind", "product_line") != "brand"][:R.MAX_LINES]
    out += [(i["name"], "product_line", False) for i in prods]
    segs = ok("segments")
    if len(segs) >= 2:
        out += [(i["name"], "segment", False) for i in segs[:R.MAX_SEGMENTS]]
    return list(dict.fromkeys(out))


def protected_names(profile: dict, company_name: str) -> list:
    names = [i["name"] for i in (profile.get("competitors") or {}).get("items") or []]
    names += [i["name"] for i in (profile.get("products_services") or {}).get("items") or [] if i.get("kind") == "brand"]
    names += [t for t in re.findall(r"[A-Za-z][A-Za-z&'\-]+", company_name) if len(t) > 2]
    return names


class BackgroundBuilder:
    def __init__(self, client, ai_store, texts, gemini=None, translator: Optional[GoogleTranslate] = None, results_dir: Optional[Path] = None, sec=None,
                 ensure_filing: Optional[Callable] = None, vocab: Optional[Vocab] = None, find_filing: Optional[Callable] = None, companies=None):
        from src.pipeline import scoring as S
        from src.repositories.company_repository import CompanyRepository
        self.client, self.ai_store, self.texts, self.gemini = client, ai_store, texts, gemini
        self.translator = translator if translator is not None else GoogleTranslate()
        self.results_dir = Path(results_dir) if results_dir else S.RESULTS_DIR
        self.sec, self._ensure = sec, ensure_filing
        self.profiles, self.terms = ProfileStore(client), TermStore(client)
        self.vocab = vocab or Vocab.from_db(client)
        self.companies = companies or CompanyRepository(client)
        if find_filing is None:
            from src.ai.sections import find_filing as find_filing   # noqa: F811
        self.find_filing = find_filing
        self.log: dict = {"profiles_built": 0, "profiles_reused": 0, "translated": [], "translation_failed": [], "translation_skipped_no_key": 0}

    # ---------------------------------------------------------------- inputs
    def load(self, ticker: str) -> dict:
        co = self.companies.get_by_symbol(ticker, "US")
        if not co:
            raise RuntimeError(f"{ticker} is not in the companies table")
        records = PS.load_records(self.results_dir)
        rec = next((r for r in records if r["ticker"] == ticker), None)
        if rec is None:
            raise RuntimeError(f"no score result for {ticker}")
        j, _eng = PS.load_json(self.results_dir, ticker)
        end = latest_end(j)
        if self._ensure:
            self._ensure(ticker, co.get("cik"))
        filing = self.find_filing(ticker, end)
        if filing is None:
            raise RuntimeError(f"the 10-K of {ticker} (period end {end}) is not in the local filings cache")
        return {"co": co, "rec": rec, "records": records, "json": j, "filing": filing, "fy": int(rec["fiscal_year"][2:])}

    # ---------------------------------------------------------------- the profile
    def xbrl_fields(self, filing, cik=None) -> dict:
        """-> {"axes": axes result or None, "fields": {segments, products_services, regions}, "usable": {field: bool}}."""
        path = Path(filing.path)
        if path.suffix.lower() != ".htm" or not path.exists():
            return {"axes": None, "fields": {}, "usable": {}, "note": "no inline XBRL document in the cache"}
        ax = X.extract_axes(path.read_text(encoding="utf-8", errors="replace"), fetch_labels(self.sec, filing.path, cik))
        fields = {"segments": X.segments_field(ax), "products_services": X.products_field(ax), "regions": X.regions_field(ax)}
        usable = {}
        for f, key in (("segments", "segments"), ("products_services", "products_services"), ("regions", "regions")):
            a = ax["axes"][key]
            ok = bool(fields[f]["items"]) and (a["coverage"] or 0) >= MIN_COVERAGE and "members_overlap" not in a["flags"]
            if fields[f]["items"] and not ok:
                fields[f] = {**fields[f], "status": "not_found", "reasons": fields[f].get("reasons", []) + ["axis_not_usable (coverage / overlap)"]}
            usable[f] = ok
        return {"axes": ax, "fields": fields, "usable": usable}

    def build_profile(self, ctx: dict, force: bool = False, seed_base: int = 0) -> dict:
        co, filing = ctx["co"], ctx["filing"]
        existing = self.profiles.get(co["id"], filing.accession)
        if existing and not force and existing["skill_version"] == bp1.SKILL_VERSION:
            self.log["profiles_reused"] += 1
            return existing
        if self.gemini is None:
            from src.ai.content import BudgetExceeded
            raise BudgetExceeded("no model budget for BP-1")
        xb = self.xbrl_fields(filing, co.get("cik"))
        usable = xb["usable"]
        sections, err = bp1.select_text(filing.text, need_products=not usable.get("products_services", False))
        wanted = bp1.fields_wanted(usable.get("segments", False), usable.get("products_services", False), usable.get("regions", False))
        fields: dict = {}
        attempts: list = []
        model = getattr(self.gemini, "model", "")
        if err:
            fields = {f: {"status": "failed", "source": "ai", "items": [], "reasons": [err]} for f in wanted}
        else:
            out = bp1.run(self.gemini, self.vocab, filing.accession, sections, wanted, C.display_name(co["company_name"]), seed_base)
            fields, attempts, model = out["fields"], out["attempts"], out["model"]
        row_fields = {}
        for f in PROFILE_FIELDS:
            if usable.get(f):
                row_fields[f] = xb["fields"][f]
            else:
                r = fields.get(f) or {"status": "not_found", "source": "code", "items": [], "reasons": []}
                if f in xb["fields"] and r["status"] != "failed":
                    r = {**r, "reasons": r.get("reasons", []) + (xb["fields"][f].get("reasons") or [])}
                row_fields[f] = r
        ax = xb["axes"]
        axes_found = {"end": str(ax["end"]) if ax and ax["end"] else None, "total_revenue": ax["total_revenue"] if ax else None, "labels_found": ax["labels_found"] if ax else 0,
                      "axes": {k: {"found": v["found"], "concept": v["concept"], "coverage": v["coverage"], "flags": v["flags"], "n_items": len(v["items"]), "n_dropped": len(v["dropped"])}
                               for k, v in (ax["axes"] if ax else {}).items()},
                      "bp1_fields": wanted, "attempts": attempts, "sections_sent": [s for s, _ in sections], "note": xb.get("note")}
        row = {"company_id": co["id"], "accession": filing.accession, "fiscal_year": ctx["fy"], "source_market": "US", "model": model, "skill_version": bp1.SKILL_VERSION,
               **row_fields, "axes_found": axes_found}
        saved = self.profiles.put(row)
        self.log["profiles_built"] += 1
        return saved

    def refresh_failed(self, ticker: str, seed_base: int = 0) -> dict:
        """One new BP-1 call for a stored profile whose AI fields failed, or no longer pass the current checks (the stored core_activity is checked again, no call); the first attempt already carries the
        exact reasons. Only the fields that failed are replaced, and only by a result that passes. Nothing happens (no call) when no field needs it."""
        if self.gemini is None:
            from src.ai.content import BudgetExceeded
            raise BudgetExceeded("no model budget for BP-1")
        ctx = self.load(ticker)
        co, filing = ctx["co"], ctx["filing"]
        p = self.profiles.get(co["id"], filing.accession)
        if p is None:
            raise RuntimeError(f"{ticker} has no business profile for {filing.accession}")
        af = dict(p["axes_found"] or {})
        sections, err = bp1.select_text(filing.text, need_products="TXT-PRD" in (af.get("sections_sent") or []))
        failing = {f: (p[f].get("reasons") or []) for f in PROFILE_FIELDS if (p[f] or {}).get("status") == "failed" and (p[f] or {}).get("source") == "ai"}
        ca = (p["core_activity"] or {}).get("items") or []
        if ca and (p["core_activity"] or {}).get("status") == "ok":
            r = bp1.check_core({"value": ca[0]["value"], "quote": ca[0]["quote"]}, bp1.normalize(bp1.sent_text(sections)), sections)
            if r["status"] == "failed":
                failing["core_activity"] = r["reasons"]
        if err or not failing:
            return {"refreshed": [], "kept_failed": [], "attempts": 0}
        out = bp1.run(self.gemini, self.vocab, filing.accession, sections, af.get("bp1_fields") or list(bp1.ALWAYS), C.display_name(co["company_name"]), seed_base,
                      note0=bp1.retry_note({f: {"reasons": r} for f, r in failing.items()}))
        refreshed = [f for f in failing if out["fields"][f]["status"] != "failed"]
        for f in refreshed:
            p[f] = out["fields"][f]
        af.setdefault("refreshes", []).append({"fields": list(failing), "refreshed": refreshed, "attempts": out["attempts"]})
        p["axes_found"] = af
        saved = self.profiles.put({k: v for k, v in p.items() if k not in ("created_at",)})
        return {"profile_id": saved["id"], "refreshed": refreshed, "kept_failed": [f for f in failing if f not in refreshed], "attempts": len(out["attempts"])}

    def recheck_stored(self, ticker: str) -> dict:
        """No model call: the fields of a stored profile that failed (or no longer pass) are checked again, with the current checks, against the stored raw answers of its BP-1 attempts, newest first;
        the first answer that passes replaces the field. -> {"adopted": [...], "still_failed": [...]}."""
        ctx = self.load(ticker)
        co, filing = ctx["co"], ctx["filing"]
        p = self.profiles.get(co["id"], filing.accession)
        if p is None:
            raise RuntimeError(f"{ticker} has no business profile for {filing.accession}")
        af = dict(p["axes_found"] or {})
        sections, _err = bp1.select_text(filing.text, need_products="TXT-PRD" in (af.get("sections_sent") or []))
        raws = [a["raw"] for a in reversed((af.get("attempts") or []) + [x for r in af.get("refreshes") or [] for x in r["attempts"]]) if a.get("raw")]
        from src.ai.checks import parse_json
        answers = [x for x in (parse_json(r) for r in raws) if x]
        adopted, still = [], []
        xb = self.xbrl_fields(filing, co.get("cik"))                       # the XBRL fields are read again (names, shares): no model, no change of which source a field has
        for f, new in xb["fields"].items():
            if (p[f] or {}).get("source") == "xbrl" and xb["usable"].get(f) and new != p[f]:
                p[f] = new
                adopted.append(f)
        for f in PROFILE_FIELDS:
            fld = p[f] or {}
            if fld.get("source") != "ai" or f not in (af.get("bp1_fields") or []):
                continue
            bad = fld.get("status") == "failed"
            if not bad and f == "core_activity" and fld.get("items"):
                bad = bp1.check_core({"value": fld["items"][0]["value"], "quote": fld["items"][0]["quote"]}, bp1.normalize(bp1.sent_text(sections)), sections)["status"] == "failed"
            if not bad:
                continue
            for a in answers:
                r = bp1.validate(a, self.vocab, sections, [f], C.display_name(co["company_name"]))[f]
                if r["status"] != "failed":
                    p[f] = r
                    adopted.append(f)
                    break
            else:
                still.append(f)
        if adopted:
            af.setdefault("rechecks", []).append({"adopted": adopted, "still_failed": still})
            p["axes_found"] = af
            self.profiles.put({k: v for k, v in p.items() if k != "created_at"})
        return {"adopted": adopted, "still_failed": still}

    # ---------------------------------------------------------------- translation
    def translate(self, profile: dict, company_name: str) -> dict:
        """Translate the phrases of the profile that have no translation yet (Google only; no key -> nothing, reported)."""
        have = self.terms.map()
        todo = [p for p in phrases_needed(profile) if phrase_key(p[0]) not in have]
        res = {"needed": len(phrases_needed(profile)), "already": len(phrases_needed(profile)) - len(todo), "translated": [], "failed": [], "pending": []}
        if not todo:
            return res
        if not self.translator.available:
            res["pending"] = [p[0] for p in todo]
            self.log["translation_skipped_no_key"] += len(todo)
            return res
        names = protected_names(profile, company_name)
        for en, _kind, whole in todo:
            try:
                out = translate_phrase(en, self.translator, names, whole_sentence=whole)
            except NoKey:
                res["pending"].append(en)
                continue
            except Exception as e:   # noqa: BLE001 - a failed phrase stays awaiting translation
                res["failed"].append({"en": en, "reasons": [f"{type(e).__name__}: {e}"[:160]]})
                continue
            if out["he"]:
                self.terms.put(en, out["he"], "google", "unreviewed")
                res["translated"].append({"en": en, "he": out["he"]})
            else:
                res["failed"].append({"en": en, "reasons": out["reasons"], "raw": out.get("raw")})
        self.log["translated"] += res["translated"]
        self.log["translation_failed"] += res["failed"]
        return res

    # ---------------------------------------------------------------- render
    def similar_names(self, ctx: dict) -> list:
        rec, records = ctx["rec"], ctx["records"]
        sizes, js = {}, {}
        pool = [r for r in records if r["profile"] == rec["profile"] and r.get("industry") == rec.get("industry")]
        for r in pool:
            try:
                js[r["ticker"]], _ = PS.load_json(self.results_dir, r["ticker"])
            except KeyError:
                js[r["ticker"]] = None
            sizes[r["ticker"]] = size_of(r, js[r["ticker"]])
        return [pretty_name(r["name"]) if r.get("name") and r["name"] != r["ticker"] else r["ticker"] for r in pick_similar(rec, records, sizes)]

    def render_inputs(self, ctx: dict, profile: dict, translations: dict) -> R.RenderInput:
        co, rec = ctx["co"], ctx["rec"]
        level, src = moat_of(self.ai_store, co["symbol"], ctx["fy"])
        names = (profile.get("competitors") or {}).get("items") or []
        return R.RenderInput(name=pretty_name(co["company_name"]), profile=profile, vocab=self.vocab, revenue=(rec.get("metrics") or {}).get("revenue"), fiscal_year=ctx["fy"],
                             moat_level=level, moat_source=src, similar=[] if names else self.similar_names(ctx), translations=translations)

    def render_store(self, ctx: dict, profile: dict) -> dict:
        co = ctx["co"]
        tr = self.terms.map()
        inp = self.render_inputs(ctx, profile, tr)
        out = {}
        changed = 0
        for lang in ("en", "he"):
            text, info = R.render(inp, lang)
            awaiting = lang == "he" and bool(info["missing"])
            human = lang == "he" and not awaiting and not info["unreviewed"]
            row = {"ticker": co["symbol"], "fiscal_year": ctx["fy"], "kind": "background", "language": lang, "text": text or None, "model": "code-template", "prompt_version": PROMPT_VERSION,
                   "run_id": "", "accession": profile["accession"], "state": "awaiting_translation" if awaiting else "stored",
                   "approval_status": "pending_review" if (awaiting or not text) else "approved", "edited_by": "ai", "human_reviewed": human, "quotes": [],
                   "checks": {"ok": bool(text) and not awaiting, "missing_phrases": info["missing"], "unreviewed_phrases": info["unreviewed"], "sentences": info["sentences"]},
                   "template_version": R.TEMPLATE_VERSION, "profile_id": profile["id"], "generator": "template"}
            old = self.texts.get(co["symbol"], ctx["fy"], "background", PROMPT_VERSION, "", lang)
            same = old and all(old.get(k) == row.get(k) for k in ("text", "state", "approval_status", "human_reviewed", "template_version", "profile_id", "accession"))
            if not same:
                row = self.texts.put(row)
                changed += 1
            else:
                row = old
            out[lang] = {"text": text, "info": info, "row": row}
        out["changed"] = changed
        out["superseded"] = self.supersede_old(co["id"])
        return out

    def supersede_old(self, company_id: int) -> int:
        """The D1 / T1 texts of the company (no template_version) are marked superseded: they stay in the table and are not shown."""
        n = 0
        for r in self.client.table("ai_texts").select("*").eq("company_id", company_id).eq("kind", "background").execute().data:
            if r.get("template_version") is None and r["approval_status"] != "superseded":
                self.client.table("ai_texts").update({"approval_status": "superseded"}).eq("id", r["id"]).execute()
                n += 1
        return n

    # ---------------------------------------------------------------- the queue task
    def run(self, ticker: str, force_profile: bool = False, seed_base: int = 0) -> dict:
        ctx = self.load(ticker)
        profile = self.build_profile(ctx, force_profile, seed_base)
        tr = self.translate(profile, C.display_name(ctx["co"]["company_name"]))
        rendered = self.render_store(ctx, profile)
        return {"profile_id": profile["id"], "translation": {k: (len(v) if isinstance(v, list) else v) for k, v in tr.items()}, "he_state": rendered["he"]["row"].get("state"),
                "texts_changed": rendered["changed"], "superseded": rendered["superseded"]}

    def render_only(self, ticker: str) -> dict:
        """`render`: re-render the stored profile without any model or translation call."""
        ctx = self.load(ticker)
        profile = self.profiles.get(ctx["co"]["id"], ctx["filing"].accession) or self.profiles.latest(ctx["co"]["id"])
        if profile is None:
            raise RuntimeError(f"{ticker} has no business profile yet")
        r = self.render_store(ctx, profile)
        return {"profile_id": profile["id"], "texts_changed": r["changed"], "he_state": r["he"]["row"].get("state")}
