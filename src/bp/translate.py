"""Translation of short free phrases (AI skills 2026-10-26_10-30, 3.2.5): ``core_activity``, product-line names and segment names, once each, into ``term_translations``.

The provider is chosen by ``TRANSLATION_PROVIDER`` in .env: ``azure`` (Azure Translator v3, ``AZURE_TRANSLATOR_KEY`` / ``AZURE_TRANSLATOR_REGION``; several phrases per request) or ``google`` (Cloud
Translation v2, ``GOOGLE_TRANSLATE_API_KEY``). Keys are never printed; at most ``MAX_PHRASES`` phrases per run. Without a key nothing is translated and nothing falls back to the model: the phrase
stays "awaiting translation". Abbreviations (P&C, A&H) are expanded before the call. Before the call every glossary term and every name is replaced by a placeholder and put back after it; the result is checked (no foreign script,
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
ABBREVIATIONS = {"P&C": "property and casualty", "A&H": "accident and health"}
BATCH = 25
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


def protect(phrase: str, names: list, gloss: list, record: Optional[dict] = None) -> tuple:
    """-> (text with placeholders, {placeholder: replacement}). ``names`` come back as written, glossary terms as their Hebrew term. Longest first, whole words only, case-insensitive for glossary."""
    mapping: dict = {}
    text = phrase
    items = [(n, n, False) for n in names if n] + [(en, he, True) for en, he in gloss]
    for src, repl, ci in sorted(items, key=lambda x: -len(x[0])):
        pat = re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(src), re.I if ci else 0)
        if not pat.search(text):
            continue
        ph = f"ZQ{len(mapping) + 1}Z"
        if record is not None:
            record[ph] = pat.search(text).group(0)                         # the English words this placeholder stands for
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
    if not _HEB.search(he) and not (he.strip().lower() == en.strip().lower() and len(en.split()) <= 2):       # a one- or two-word name that stays as it is (Azure, CPUs) is fine
        reasons.append("no_hebrew")
    for n in names:
        if n and n not in he:
            reasons.append(f"name_lost ({n})")
    for _en, hz in gloss_used:
        if hz and hz.lower() not in he.lower():
            reasons.append(f"glossary_term_lost ({hz})")
    ne, nh = len(en.split()), len(he.split())
    if abs(nh - ne) > 1 and not (0.5 * ne <= nh <= 1.5 * ne) and not gloss_used:           # a glossary term can be longer than its English
        reasons.append(f"length_out_of_range ({nh} words for {ne})")
    return reasons


# ---------------------------------------------------------------- the providers
def expand_abbreviations(text: str) -> str:
    for ab, full in ABBREVIATIONS.items():
        text = re.sub(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(ab), full, text)
    return text


class _Provider:
    name = ""

    def __init__(self, cap: int = MAX_PHRASES, post=None):
        self.cap, self.calls, self._post = cap, 0, post         # ``calls`` counts phrases (the stage cap is ``MAX_PHRASES``)

    @property
    def available(self) -> bool:
        return bool(self._key())

    def _key(self) -> str:
        return ""

    def _send(self, texts: list) -> list:
        raise NotImplementedError

    def translate_batch(self, texts: list) -> list:
        if not self._key():
            raise NoKey(f"the {self.name} translation key is missing from .env")
        out = []
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i + BATCH]
            if self.calls + len(chunk) > self.cap:
                raise RuntimeError(f"translation cap of {self.cap} phrases reached")
            self.calls += len(chunk)
            out += self._post(chunk) if self._post else self._send(chunk)
        return out

    def translate(self, text: str) -> str:
        return self.translate_batch([text])[0]


class AzureTranslate(_Provider):
    """Azure Translator v3 (``from=en&to=he``, HTML text type so that the placeholders stay); the key and region go in headers and are never printed."""
    name = "azure"
    supports_dictionary = True          # glossary terms go in as dynamic-dictionary markup
    URL = "https://api.cognitive.microsofttranslator.com/translate"

    def __init__(self, key: Optional[str] = None, region: Optional[str] = None, cap: int = MAX_PHRASES, post=None):
        super().__init__(cap, post)
        self.key = key if key is not None else (os.environ.get("AZURE_TRANSLATOR_KEY") or "").strip()
        self.region = (region if region is not None else (os.environ.get("AZURE_TRANSLATOR_REGION") or "")).strip()

    def _key(self) -> str:
        return self.key

    def _send(self, texts: list) -> list:
        import requests
        from src.net import retry_network
        headers = {"Ocp-Apim-Subscription-Key": self.key, "Content-Type": "application/json"}
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region
        r = retry_network(lambda: requests.post(self.URL, params={"api-version": "3.0", "from": "en", "to": "he", "textType": "html"}, json=[{"Text": t} for t in texts], headers=headers, timeout=60))
        if r.status_code >= 400:
            raise RuntimeError(f"Azure Translator HTTP {r.status_code}")        # the body can echo the request: only the code is reported
        return [x["translations"][0]["text"] for x in r.json()]


class GoogleTranslate(_Provider):
    """Google Cloud Translation v2; the key goes in a header and is never printed."""
    name = "google"

    def __init__(self, key: Optional[str] = None, cap: int = MAX_PHRASES, post=None):
        super().__init__(cap, post)
        self.key = key if key is not None else (os.environ.get("GOOGLE_TRANSLATE_API_KEY") or "")

    def _key(self) -> str:
        return self.key

    def _send(self, texts: list) -> list:
        import requests
        from src.net import retry_network
        r = retry_network(lambda: requests.post(ENDPOINT, json={"q": texts, "source": "en", "target": "he", "format": "html"}, headers={"X-goog-api-key": self.key}, timeout=60))
        if r.status_code >= 400:
            raise RuntimeError(f"Google Translate HTTP {r.status_code}")
        return [x["translatedText"] for x in r.json()["data"]["translations"]]


def make_translator(cap: int = MAX_PHRASES) -> _Provider:
    """The provider named by TRANSLATION_PROVIDER (default azure); Google stays as the alternative."""
    name = (os.environ.get("TRANSLATION_PROVIDER") or "azure").strip().lower()
    return GoogleTranslate(cap=cap) if name == "google" else AzureTranslate(cap=cap)


def wrap(text: str) -> str:
    return re.sub(r"(ZQ\d+Z)", lambda m: f'<span translate="no" class="notranslate">{m.group(1)}</span>', text)


def dictionary_markup(text: str, entries: dict) -> str:
    """Azure dynamic dictionary: each glossary placeholder becomes <mstrans:dictionary translation="HE">english</mstrans:dictionary>, so the translator keeps the Hebrew term inside its own grammar."""
    for ph, (matched, he) in entries.items():
        text = text.replace(ph, '<mstrans:dictionary translation="%s">%s</mstrans:dictionary>' % (he.replace('"', "&quot;"), matched))
    return text


def prepare(en: str, names: Optional[list], whole_sentence: bool, gloss: list, use_dictionary: bool = False) -> dict:
    """-> the text to send and what is needed to check and restore the answer. Names are protected by placeholders; glossary terms by placeholders (restored after the call) or, with ``use_dictionary``
    (Azure), by dictionary markup. A trailing word "Segment" of a segment name is not translated ("North America Segment" -> "North America")."""
    en_x = expand_abbreviations(en)
    if not whole_sentence:
        en_x = re.sub(r"^Segment\s+|\s+Segment$", "", en_x, flags=re.I) or en_x
    names = list(dict.fromkeys((names or []) + auto_names(en_x)))
    src = (PREFIX + en_x) if whole_sentence else en_x
    matched: dict = {}
    protected, mapping = protect(src, names, gloss, matched)
    gloss_used = [(e, h) for e, h in gloss if h in mapping.values() and re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(e), en_x, re.I)]
    if use_dictionary:
        entries = {}
        for ph, repl in list(mapping.items()):
            if repl in names:
                continue                                                    # a name: stays a placeholder
            entries[ph] = (matched[ph], repl)
            del mapping[ph]
        protected = dictionary_markup(protected, entries)
        return {"en": en, "en_x": en_x, "names": names, "mapping": mapping, "gloss_used": gloss_used, "send": wrap(protected), "whole": whole_sentence}
    return {"en": en, "en_x": en_x, "names": names, "mapping": mapping, "gloss_used": gloss_used, "send": wrap(protected), "whole": whole_sentence}


def finish(prep: dict, raw: str) -> dict:
    he, missing = restore(raw, prep["mapping"])
    reasons = [f"placeholder_lost ({m})" for m in missing]
    if prep["whole"]:
        if he.startswith("החברה "):
            he = he[len("החברה "):].strip()
        else:
            reasons.append("sentence_prefix_not_found")
    reasons += check_translation(prep["en_x"], he, [n for n in prep["names"] if n in prep["mapping"].values()], prep["gloss_used"])
    return {"he": he if not reasons else None, "reasons": reasons, "raw": he}


def translate_many(items: list, provider: _Provider, gloss: Optional[list] = None) -> list:
    """items [(english phrase, names to protect, whole_sentence)] -> [{"he", "reasons", "raw"}] in the same order; several phrases per request."""
    gloss = glossary_pairs() if gloss is None else gloss
    use_dict = bool(getattr(provider, "supports_dictionary", False))
    preps = [prepare(en, names, whole, gloss, use_dict) for en, names, whole in items]
    raws = provider.translate_batch([p["send"] for p in preps])
    return [finish(p, r) for p, r in zip(preps, raws)]


def translate_phrase(en: str, provider: _Provider, names: Optional[list] = None, whole_sentence: bool = False, gloss: Optional[list] = None) -> dict:
    """-> {"he": str or None, "reasons": [...]}. ``whole_sentence`` (core_activity): translated as "The company <phrase>" so that the verbs agree with a feminine noun, then "החברה" is removed."""
    return translate_many([(en, names, whole_sentence)], provider, gloss)[0]
