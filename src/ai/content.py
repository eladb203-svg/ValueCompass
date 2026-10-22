"""D1 (company background) and D2 (results analysis): prompts, code checks, generation with one retry, file store (code stage K5c; the same structure as the K6 table ``ai_texts``).

Checks (skills document "Other" 3.1 / 3.2): D1 - at most 120 words; every number of the Hebrew text appears in FACTS; every competitor appears in a verified quote; the moat wording matches the
source A7 found; quotes verbatim. D2 - each paragraph at most 60 words (longer -> regenerated, never cut); every number appears in RESULTS or PEERS; ``criteria_cited`` exist in the run; no advice
and no current-price wording. A failure -> one retry with the reasons; still failing -> state ``failed`` (nothing shown).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import checks
from .prompt import _load

MULT = {"טריליון": 1e12, "מיליארד": 1e9, "מיליארדי": 1e9, "מיליון": 1e6, "מיליוני": 1e6, "אלף": 1e3, "אלפי": 1e3, "trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mm": 1e6,
        "thousand": 1e3}
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*)(%|[A-Za-z֐-׿]+)?")


def content_cfg() -> dict:
    return _load("content.yaml")


def count_words(text: str) -> int:
    return sum(1 for t in (text or "").split() if re.search(r"[\w֐-׿]", t))


def numbers_in(text: str) -> list:
    """[(value, decimals, multiplier, percent?)] of every number in a text; a Hebrew / English scale word right after a number is its multiplier."""
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        dec = len(raw.split(".")[1]) if "." in raw else 0
        word = (m.group(2) or "")
        mult = MULT.get(word, MULT.get(word.lower(), 1.0))
        out.append((float(raw), dec, mult, word == "%"))
    return out


def supported(n: tuple, sources: list, years: tuple = ()) -> bool:
    """A number of the text is supported when a source number gives it after rounding to the decimals written, in the scale written (a fraction source also as a percent)."""
    v, dec, mult, pct = n
    if dec == 0 and mult == 1.0 and 1900 <= v <= 2100 and int(v) in years:
        return True
    for sv, _sd, smult, _p in sources:
        full = sv * smult
        cands = [full / mult]
        if pct or mult == 1.0:
            cands += [sv * 100.0 if abs(sv) <= 1.5 else sv]
        cands.append(sv)
        if any(abs(round(c, dec) - v) < 1e-9 or abs(abs(round(c, dec)) - v) < 1e-9 for c in cands):
            return True
    return False


def unsupported_numbers(text: str, source_text: str, years: tuple = ()) -> list:
    src = numbers_in(source_text)
    return [n[0] for n in numbers_in(text) if not supported(n, src, years)]


def forbidden_in(text: str) -> list:
    return [w for w in content_cfg()["forbidden_words"] if w in (text or "")]


# ---------------------------------------------------------------- prompts
def d1_facts(industry: str, revenue: Optional[float], currency: str, fiscal_year, one_sentence: str, moat_answer, moat_source: str, moat_reasoning: str) -> dict:
    rev = "not available" if revenue is None else f"{revenue:,.0f} ({revenue / 1e9:,.2f} billion)"
    return {"industry": industry, "revenue": rev, "currency": currency, "fiscal_year": fiscal_year, "one_sentence": one_sentence or "not available",
            "moat_answer": moat_answer, "moat_source": moat_source or "none", "moat_reasoning": moat_reasoning or ""}


def d1_facts_text(f: dict) -> str:
    return (f"industry {f['industry']}; revenue {f['revenue']} {f['currency']} (FY{f['fiscal_year']}); ONE SENTENCE: {f['one_sentence']}; "
            f"MOAT: {f['moat_answer']} / {f['moat_source']} / {f['moat_reasoning']}")


def build_d1_prompt(facts: dict, accession: str, sections: dict, note: str = "") -> tuple:
    d1 = content_cfg()["d1"]
    sent = [(s, sections[s]) for s in d1["sections"] if sections.get(s)]
    text = "\n\n".join(f"[{s}]\n{t}" for s, t in sent)
    p = d1["template"].format(industry=facts["industry"], revenue=facts["revenue"], currency=facts["currency"], fiscal_year=facts["fiscal_year"], one_sentence=facts["one_sentence"],
                              moat_answer=facts["moat_answer"], moat_source=facts["moat_source"], moat_reasoning=facts["moat_reasoning"], sections=", ".join(s for s, _ in sent),
                              accession=accession, section_text=text, version=d1["version"])
    return (p + f"\nNOTE: {note}\n" if note else p), text, [s for s, _ in sent]


def build_d2_prompt(results: dict, peers: dict, note: str = "") -> str:
    d2 = content_cfg()["d2"]
    g = peers.get("group", {})
    p = d2["template"].format(run_id=results["run_id"], profile=results["profile"], results_json=json.dumps(results, ensure_ascii=False, indent=1),
                              peer_group_definition=g.get("definition"), n=g.get("n"), peers_json=json.dumps({k: v for k, v in peers.items() if k != "group"}, ensure_ascii=False, indent=1),
                              version=d2["version"])
    return p + f"\nNOTE: {note}\n" if note else p


# ---------------------------------------------------------------- checks
def check_background(raw: str, facts_text: str, text_sent: str, sent: list, moat_source: str, fiscal_year: Optional[int] = None) -> checks.CheckResult:
    res = checks.CheckResult(False, "failed")
    d = checks.parse_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    res.parsed = d
    d1 = content_cfg()["d1"]
    if d.get("skill_id") != d1["skill_id"]:
        res.reasons.append("skill_id_mismatch")
    text = d.get("text_he")
    if not isinstance(text, str) or not text.strip():
        res.reasons.append("text_missing")
        return res
    if count_words(text) > 120:
        res.reasons.append(f"over_120_words ({count_words(text)})")
    bad = unsupported_numbers(text, facts_text, (fiscal_year,) if fiscal_year else ())
    if bad:
        res.reasons.append("number_not_in_facts (" + ", ".join(str(int(b) if b == int(b) else b) for b in bad) + ")")
    res.quotes = checks._check_quotes(d.get("quotes"), checks.normalize(text_sent), sent, res.reasons, res.flags)
    if not res.quotes:
        res.reasons.append("no_quote")
    comps = d.get("competitors")
    if not isinstance(comps, list) or not all(isinstance(c, str) for c in comps):
        res.reasons.append("competitors_invalid")
        comps = []
    qtext = " ".join(checks.normalize(q["text"]).casefold() for q in res.quotes if q["found"])
    for c in comps:
        if checks.normalize(c).casefold() not in qtext:
            res.reasons.append(f"competitor_not_in_quote ({c})")
    words = content_cfg()["moat_words"]
    own = words.get(moat_source or "none", [])
    if own and not any(w in text for w in own):
        res.reasons.append(f"moat_source_not_in_text ({moat_source})")
    elif moat_source != "none" and not own:
        res.flags.append("moat_source_unknown")
    res.reasons += [f"forbidden_word ({w})" for w in forbidden_in(text)]
    res.extra = {"competitors": comps, "words": count_words(text)}
    res.ok = not res.reasons
    res.state = "stored" if res.ok else "failed"
    return res


def check_analysis(raw: str, results_text: str, peers_text: str, criteria_ids: set) -> checks.CheckResult:
    res = checks.CheckResult(False, "failed")
    d = checks.parse_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    res.parsed = d
    if d.get("skill_id") != content_cfg()["d2"]["skill_id"]:
        res.reasons.append("skill_id_mismatch")
    src = results_text + "\n" + peers_text
    words = {}
    for k in ("quality_he", "value_he"):
        t = d.get(k)
        if not isinstance(t, str) or not t.strip():
            res.reasons.append(f"{k}_missing")
            continue
        words[k] = count_words(t)
        if words[k] > 60:
            res.reasons.append(f"{k}_over_60_words ({words[k]})")           # regenerated, not cut
        bad = unsupported_numbers(t, src)
        if bad:
            res.reasons.append(f"{k}_number_not_in_results (" + ", ".join(str(int(b) if b == int(b) else b) for b in bad) + ")")
        res.reasons += [f"{k}_forbidden_word ({w})" for w in forbidden_in(t)]
    cited = d.get("criteria_cited")
    if not isinstance(cited, list) or not all(isinstance(c, str) for c in cited):
        res.reasons.append("criteria_cited_invalid")
    else:
        res.reasons += [f"criterion_not_in_run ({c})" for c in cited if c not in criteria_ids]
    res.extra = {"words": words, "criteria_cited": cited if isinstance(cited, list) else []}
    res.ok = not res.reasons
    res.state = "stored" if res.ok else "failed"
    return res


def criteria_ids_of(results: dict) -> set:
    return {c["id"] for m in results["quality"].values() for c in m["criteria"]}


# ---------------------------------------------------------------- store
class TextStore:
    """texts.jsonl in the structure of ``ai_texts``: one row per (company, fiscal year, kind, language, prompt version, run_id). Generated once and shown as is."""

    def __init__(self, path: Path):
        self.path, self._rows = Path(path), {}
        if self.path.exists():
            for ln in self.path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    self._rows[self.key(r)] = r

    @staticmethod
    def key(r: dict) -> tuple:
        return (r["ticker"], int(r["fiscal_year"]), r["kind"], r["language"], str(r["prompt_version"]), r.get("run_id") or "")

    def get(self, ticker, fiscal_year, kind, prompt_version, run_id="", language="he"):
        return self._rows.get((ticker, int(fiscal_year), kind, language, str(prompt_version), run_id or ""))

    def put(self, row: dict) -> dict:
        row = {**row, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._rows[self.key(row)] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def rows(self) -> list:
        return list(self._rows.values())


# ---------------------------------------------------------------- generation
def _call(client, prompt: str, seed_offset: int):
    return client.generate(prompt, seed_offset=seed_offset)


def generate_background(co, facts: dict, sections: dict, moat_source: str, client, store: TextStore, force: bool = False) -> dict:
    """D1 once per annual report. ``co`` needs ticker, fiscal_year, filing.accession."""
    d1 = content_cfg()["d1"]
    pv = str(d1["version"])
    ex = None if force else store.get(co.ticker, co.fiscal_year, "background", pv)
    if ex is not None:
        return ex
    facts_text = d1_facts_text(facts)
    note, attempts = "", []
    for attempt in (1, 2):
        prompt, text_sent, sent = build_d1_prompt(facts, co.filing.accession, sections, note)
        rep = _call(client, prompt, attempt - 1)
        res = check_background(rep.text, facts_text, text_sent, sent, moat_source, co.fiscal_year)
        attempts.append({"attempt": attempt, "ok": res.ok, "reasons": list(res.reasons)})
        if res.ok:
            break
        note = "Your previous answer failed these checks: " + "; ".join(res.reasons) + ". Fix them and answer again."
    p = res.parsed or {}
    return store.put({"ticker": co.ticker, "fiscal_year": co.fiscal_year, "kind": "background", "language": "he", "text": p.get("text_he") if res.ok else None, "model": rep.model,
                      "prompt_version": pv, "run_id": "", "state": res.state, "accession": co.filing.accession, "quotes": res.quotes, "competitors": res.extra.get("competitors", []),
                      "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": attempts}, "raw_answer": rep.text})


def generate_analysis(ticker: str, fiscal_year: int, results: dict, peers: dict, client, store: TextStore, force: bool = False) -> dict:
    """D2 once per scoring run (keyed by run_id); never regenerated when a page is opened."""
    d2 = content_cfg()["d2"]
    pv = str(d2["version"])
    ex = None if force else store.get(ticker, fiscal_year, "analysis", pv, results["run_id"])
    if ex is not None:
        return ex
    results_text = json.dumps(results, ensure_ascii=False)
    peers_text = json.dumps(peers, ensure_ascii=False)
    ids = criteria_ids_of(results)
    note, attempts = "", []
    for attempt in (1, 2):
        rep = _call(client, build_d2_prompt(results, peers, note), attempt - 1)
        res = check_analysis(rep.text, results_text, peers_text, ids)
        attempts.append({"attempt": attempt, "ok": res.ok, "reasons": list(res.reasons)})
        if res.ok:
            break
        note = "Your previous answer failed these checks: " + "; ".join(res.reasons) + ". Rewrite (shorter where a paragraph was too long; do not cut) and answer again."
    p = res.parsed or {}
    text = (p.get("quality_he", "") + "\n\n" + p.get("value_he", "")) if res.ok else None
    return store.put({"ticker": ticker, "fiscal_year": fiscal_year, "kind": "analysis", "language": "he", "text": text, "quality_he": p.get("quality_he") if res.ok else None,
                      "value_he": p.get("value_he") if res.ok else None, "criteria_cited": res.extra.get("criteria_cited", []), "model": rep.model, "prompt_version": pv,
                      "run_id": results["run_id"], "state": res.state, "quotes": [], "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": attempts},
                      "raw_answer": rep.text})
