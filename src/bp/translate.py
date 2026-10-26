"""Translation of short free phrases (AI skills 2026-10-26_10-30, 3.2.5): ``core_activity``, product-line names and segment names, once each, into ``term_translations``.

The provider is Google Cloud Translation (key ``GOOGLE_TRANSLATE_API_KEY`` from .env, never printed; at most ``MAX_PHRASES`` phrases per run). Without a key nothing is translated and nothing falls back
to the model: the phrase stays "awaiting translation". Before the call every glossary term and every name is replaced by a placeholder and put back after it; the result is checked (no foreign script,
names back in Latin letters, length within +-50%).
"""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = ROOT / "src" / "ai" / "skills" / "t1_glossary.yaml"
ENDPOINT = "https://translation.googleapis.com/language/translate/v2"
MAX_PHRASES = 200
PREFIX = "The company "
_FOREIGN = re.compile("[Ѐ-ӿ؀-ۿ฀-๿Ͱ-Ͽ぀-ヿ㐀-鿿가-힯]")
_HEB = re.compile("[֐-׿]")


class NoKey(RuntimeError):
    pass


def phrase_key(en: str) -> str:
    return re.sub(r"\s+", " ", (en or "").strip()).lower()


def glossary_pairs(path: Path = GLOSSARY) -> list:
    """[(english variant, hebrew variant)] of the T1 glossary; variants correspond by position."""
    out = []
    for t in yaml.safe_load(path.read_text(encoding="utf-8"))["terms"]:
        ens, hes = [x.strip() for x in t["en"].split(" / ")], [x.strip() for x in t["he"].split(" / ")]
        for i, en in enumerate(ens):
            out.append((en, hes[i] if i < len(hes) else hes[0]))
    return out


# ---------------------------------------------------------------- term protection
def auto_names(phrase: str) -> list:
    """Tokens of a phrase that are names or acronyms (an upper-case letter after the first, two or more capitals, a digit): kept in Latin letters."""
    out = []
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9&'\.\-]*", phrase):
        t = tok.strip(".-'")
        if t and (re.search(r"[A-Z].*[A-Z]", t) or re.search(r"\d", t) or re.search(r"[a-z][A-Z]", t)):
            out.append(t)
    return out


def protect(phrase: str, names: list, gloss: list) -> tuple:
    """-> (text with placeholders, {placeholder: replacement}). ``names`` come back as written, glossary terms as their Hebrew term. Longest first, whole words only, case-insensitive for glossary."""
    mapping: dict = {}
    text = phrase
    items = [(n, n, False) for n in names if n] + [(en, he, True) for en, he in gloss]
    for src, repl, ci in sorted(items, key=lambda x: -len(x[0])):
        pat = re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(src), re.I if ci else 0)
        if not pat.search(text):
            continue
        ph = f"ZQ{len(mapping) + 1}Z"
        text = pat.sub(ph, text)
        mapping[ph] = repl
    return text, mapping


def restore(text: str, mapping: dict) -> tuple:
    """Put the Hebrew terms / names back. -> (text, missing placeholders)."""
    t = re.sub(r'<span[^>]*translate="no"[^>]*>(.*?)</span>|<span[^>]*notranslate[^>]*>(.*?)</span>', lambda m: m.group(1) or m.group(2), text)
    missing = []
    for ph, repl in mapping.items():
        if ph in t:
            t = t.replace(ph, repl)
        else:
            missing.append(ph)
    return html.unescape(re.sub(r"\s+", " ", t)).strip(), missing


def check_translation(en: str, he: str, names: list, gloss_used: list, mapping: Optional[dict] = None) -> list:
    """The reasons a translation is rejected for (empty = accepted): foreign script, no Hebrew, a name not in Latin letters, a glossary term missing, length outside +-50% of the English words."""
    reasons = []
    if not he:
        return ["empty"]
    if _FOREIGN.search(he):
        reasons.append("foreign_script")
    if not _HEB.search(he):
        reasons.append("no_hebrew")
    for n in names:
        if n and n not in he:
            reasons.append(f"name_lost ({n})")
    for _en, hz in gloss_used:
        if hz and hz not in he:
            reasons.append(f"glossary_term_lost ({hz})")
    ne, nh = len(en.split()), len(he.split())
    if abs(nh - ne) > 1 and not (0.5 * ne <= nh <= 1.5 * ne):
        reasons.append(f"length_out_of_range ({nh} words for {ne})")
    return reasons


# ---------------------------------------------------------------- the provider
class GoogleTranslate:
    """Google Cloud Translation v2 over HTTPS; the key goes in a header and is never printed or logged. ``calls`` counts phrases (the stage cap is ``MAX_PHRASES``)."""

    def __init__(self, key: Optional[str] = None, cap: int = MAX_PHRASES, post=None):
        self.key = key if key is not None else (os.environ.get("GOOGLE_TRANSLATE_API_KEY") or "")
        self.cap, self.calls, self._post = cap, 0, post

    @property
    def available(self) -> bool:
        return bool(self.key)

    def translate(self, text: str) -> str:
        if not self.key:
            raise NoKey("GOOGLE_TRANSLATE_API_KEY is missing from .env")
        if self.calls >= self.cap:
            raise RuntimeError(f"Google Translate cap of {self.cap} phrases reached")
        self.calls += 1
        body = {"q": text, "source": "en", "target": "he", "format": "html"}
        if self._post:
            return self._post(body)
        import requests
        from src.net import retry_network
        r = retry_network(lambda: requests.post(ENDPOINT, json=body, headers={"X-goog-api-key": self.key}, timeout=60))
        if r.status_code >= 400:
            raise RuntimeError(f"Google Translate HTTP {r.status_code}")      # the body can echo the request: only the code is reported
        return r.json()["data"]["translations"][0]["translatedText"]


def wrap(text: str) -> str:
    return re.sub(r"(ZQ\d+Z)", r'<span translate="no">\1</span>', text)


def translate_phrase(en: str, provider: GoogleTranslate, names: Optional[list] = None, whole_sentence: bool = False, gloss: Optional[list] = None) -> dict:
    """-> {"he": str or None, "reasons": [...]}. ``whole_sentence`` (core_activity): translated as "The company <phrase>" so that the verbs agree with a feminine noun, then "החברה" is removed."""
    gloss = glossary_pairs() if gloss is None else gloss
    names = list(dict.fromkeys((names or []) + auto_names(en)))
    src = (PREFIX + en) if whole_sentence else en
    protected, mapping = protect(src, names, gloss)
    gloss_used = [(e, h) for e, h in gloss if h in mapping.values() and re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(e), en, re.I)]
    raw = provider.translate(wrap(protected))
    he, missing = restore(raw, mapping)
    reasons = [f"placeholder_lost ({m})" for m in missing]
    if whole_sentence:
        if he.startswith("החברה "):
            he = he[len("החברה "):].strip()
        else:
            reasons.append("sentence_prefix_not_found")
    reasons += check_translation(en, he, [n for n in names if n in mapping.values()], gloss_used)
    return {"he": he if not reasons else None, "reasons": reasons, "raw": he}
