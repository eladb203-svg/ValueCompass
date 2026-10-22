"""Split a 10-K into the sections the AI receives (AI spec section 3).

Text sections: TXT-001 Business (Item 1), TXT-002 Risk factors (Item 1A), TXT-003 Competition (subsection of Item 1), TXT-004 MD&A + controls (Item 7 + Item 9A),
TXT-005 Segments and customers (segment / concentration note). Note sections (code stage K5a-2): NOTE-ACQ acquisitions, business combinations and goodwill (A8),
NOTE-UNUSUAL restructuring, impairments, other income / expense, gains and losses (A13), NOTE-LOANS loan portfolio and credit quality (A14).

Pure over text, plus ``find_filing`` which reads the local filings cache (scripts/cache/filings). The cached text of a filing may hold several documents
(``===== DOCUMENT: name =====`` markers: the 10-K and, for banks that incorporate Items by reference, the Exhibit 13 annual report). Each document is split by the Item headings
and, as a fallback, by topic headings (10-Ks organised by topic with a cross-reference index); the best candidate per section wins; a section that came from another document is
flagged ``source_exhibit:<name>``. A section that is not found is ``section_not_found``; a section longer than its cap is trimmed and flagged ``trimmed``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
FILINGS = ROOT / "scripts" / "cache" / "filings"

SECTION_IDS = ("TXT-001", "TXT-002", "TXT-003", "TXT-004", "TXT-005")
NOTE_IDS = ("NOTE-ACQ", "NOTE-UNUSUAL", "NOTE-LOANS")
ALL_IDS = SECTION_IDS + NOTE_IDS
MAX_CHARS = {"TXT-001": 150_000, "TXT-002": 120_000, "TXT-003": 30_000, "TXT-004": 200_000, "TXT-005": 30_000, "NOTE-ACQ": 60_000, "NOTE-UNUSUAL": 60_000, "NOTE-LOANS": 60_000}
NOTE_CAP = 30_000          # per note
MIN_CHARS = 1_500          # a heading span shorter than this is a table-of-contents line or a cross-reference stub
STUB_BELOW = {"TXT-001": 5_000, "TXT-002": 8_000, "TXT-004": 10_000}   # an Item candidate shorter than this is treated as a stub (reference / index line)

_ITEM = r"^[\s|]*item\s*{num}\s*[\.\:\-–—]?\s*(?:\|\s*)?{title}"
HEADINGS = {   # key -> regex (multiline, case-insensitive) for the heading line of each Item
    "1": _ITEM.format(num="1", title=r"business"),
    "1A": _ITEM.format(num="1A", title=r"risk\s+factors"),
    "1B": _ITEM.format(num="1B", title=r"unresolved"),
    "1C": _ITEM.format(num="1C", title=r"cyber"),
    "2": _ITEM.format(num="2", title=r"propert"),
    "3": _ITEM.format(num="3", title=r"legal"),
    "7": _ITEM.format(num="7", title=r"management.s\s+discussion"),
    "7A": _ITEM.format(num="7A", title=r"quantitative"),
    "8": _ITEM.format(num="8", title=r"(?:consolidated\s+)?financial\s+statements"),
    "9": _ITEM.format(num="9", title=r"changes\s+in\s+and"),
    "9A": _ITEM.format(num="9A", title=r"controls"),
    "9B": _ITEM.format(num="9B", title=r"other\s+information"),
    "10": _ITEM.format(num="10", title=r"directors"),
}
_DOC_MARK = re.compile(r"^===== DOCUMENT: (.+?) =====\s*$", re.M)


@dataclass
class Section:
    id: str
    text: Optional[str]
    chars: int = 0                 # length of the text kept
    full_chars: int = 0            # length before trimming
    flags: list = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.text is not None


# ---------------------------------------------------------------- Item-based candidates
def _positions(text: str, key: str) -> list:
    return [m.start() for m in re.finditer(HEADINGS[key], text, flags=re.I | re.M)]


def _span(text: str, key: str) -> Optional[tuple]:
    """Longest span from a heading of Item ``key`` to the next heading of any other Item (table-of-contents lines give short spans)."""
    ends = sorted(p for k in HEADINGS if k != key for p in _positions(text, k))
    best = None
    for s in _positions(text, key):
        nxt = next((e for e in ends if e > s + 10), len(text))
        if best is None or nxt - s > best[1] - best[0]:
            best = (s, nxt)
    return best if best and best[1] - best[0] >= MIN_CHARS else None


_SUB = re.compile(r"^[\s|]*(?:competition|competitive\s+(?:position|landscape|environment|conditions?))\b[^\n]{0,60}$", re.I | re.M)
_NEXT_HEAD = re.compile(r"^[\s|]*(?:[A-Z][A-Za-z&,\-’' ]{2,70})$", re.M)


def _competition(item1: str) -> Optional[str]:
    """The 'Competition' subsection of Item 1: from its heading to the next short title-like line (at most 8,000 characters)."""
    for m in _SUB.finditer(item1):
        start = m.start()
        nxt = next((h.start() for h in _NEXT_HEAD.finditer(item1, m.end() + 400) if len(h.group(0).strip()) < 70), len(item1))
        seg = item1[start:min(nxt, start + 8000)]
        if len(seg) >= 300:
            return seg
    return None


# ---------------------------------------------------------------- topic-based candidates (10-Ks organised by topic)
def _standalone(words: str) -> "re.Pattern":
    return re.compile(r"^[ \t|]*(?:%s)[ \t|:]*$" % words, re.I | re.M)


_TOPIC_END = _standalone(r"risk\s+factors|management.s\s+discussion\s+and\s+analysis[^|\n]{0,60}|unresolved\s+staff\s+comments|cybersecurity|properties|legal\s+proceedings|"
                         r"quantitative\s+and\s+qualitative[^|\n]{0,60}|financial\s+statements\s+and\s+supplementary\s+data|notes\s+to\s+consolidated\s+financial\s+statements|controls\s+and\s+procedures")
_TOPIC_START = {"business": _standalone(r"overview|business|business\s+overview|our\s+business"), "risk": _standalone(r"risk\s+factors"),
                "mdna": _standalone(r"management.s\s+discussion\s+and\s+analysis[^|\n]{0,60}")}


def _same_topic(text: str, pos: int, which: str) -> bool:
    end = text.find("\n", pos)
    line = text[pos:end if end >= 0 else len(text)].lower()
    return (which == "risk" and "risk factors" in line) or (which == "mdna" and "management" in line)


def _topic_span(text: str, which: str) -> Optional[str]:
    """Longest span from a stand-alone topic heading to the next stand-alone heading of another topic (running page headers of the same topic are skipped)."""
    ends = [m.start() for m in _TOPIC_END.finditer(text)]
    best = None
    for m in _TOPIC_START[which].finditer(text):
        cand = [e for e in ends if e > m.end() + 200 and not _same_topic(text, e, which)]
        nxt = cand[0] if cand else len(text)
        if best is None or nxt - m.start() > best[1] - best[0]:
            best = (m.start(), nxt)
    return text[best[0]:best[1]] if best and best[1] - best[0] >= MIN_CHARS else None


# ---------------------------------------------------------------- notes to the financial statements
_NOTE_HEAD = re.compile(r"^[ \t]*(?:note\s*)?\(?(\d{1,2})\)?[ \t]*[\.\):\-–—][ \t]*([A-Z][^\n]{2,110}?)[ \t]*$", re.I | re.M)
_NOTE_HEAD_ALONE = re.compile(r"^[ \t]*note[ \t]*(\d{1,2})[ \t]*[\.\):\-–—]?[ \t]*\n+[ \t]*([A-Z][^\n]{2,110}?)[ \t]*$", re.I | re.M)


def _note_heads(body: str) -> list:
    """Numbered note headings -> [(pos, number, title)]. Table-cell bars and the replacement character (a lost dash) are read as separators; offsets are unchanged."""
    b = body.replace("|", " ").replace("�", "-")
    out = [(m.start(), int(m.group(1)), m.group(2).strip()) for m in _NOTE_HEAD.finditer(b)]
    out += [(m.start(), int(m.group(1)), m.group(2).strip()) for m in _NOTE_HEAD_ALONE.finditer(b)]
    return sorted(out)
NOTE_KEYS = {
    "NOTE-ACQ": re.compile(r"acquisition|business\s+combination|goodwill|divestiture|dispositions?\b|mergers?\b", re.I),
    "NOTE-UNUSUAL": re.compile(r"restructuring|impairment|other\s+(?:income|expense|operating|charges)|special\s+|unusual|nonrecurring|non-recurring|\bgains?\b|\blosses\b|discontinued|"
                               r"supplemental\s+(?:financial|balance)|litigation|legal\s+(?:proceedings|matters)|settlements?", re.I),
    "NOTE-LOANS": re.compile(r"^loans?\b|\bloans\b.*(?:allowance|credit|portfolio)|allowance\s+for\s+(?:credit|loan)|credit\s+quality|financing\s+receivables", re.I),
}
SEGMENT_KEYS = re.compile(r"segment|geographic|major\s+customers?|concentrations?\s+of|significant\s+customers?", re.I)


def _note_chain(body: str) -> list:
    """The notes of the financial statements: the longest chain of numbered headings 1, 2, 3, ... in order -> [(pos, number, title)]."""
    heads = _note_heads(body)
    best: list = []
    for i, h in enumerate(heads):
        if h[1] != 1:
            continue
        chain, pos, want = [h], h[0], 2
        for g in heads[i + 1:]:
            if g[1] == want and g[0] > pos:
                chain.append(g)
                pos, want = g[0], want + 1
        if len(chain) >= 5 and (not best or chain[-1][0] - chain[0][0] > best[-1][0] - best[0][0]):    # the real notes span far more text than a table-of-contents list
            best = chain
    return best


def _note_texts(body: str, chain: list, key: "re.Pattern", cap_each: int = NOTE_CAP) -> list:
    out = []
    for k, (pos, num, title) in enumerate(chain):
        if key.search(title):
            end = chain[k + 1][0] if k + 1 < len(chain) else min(len(body), pos + cap_each)
            out.append((title, body[pos:min(end, pos + cap_each)]))
    return out


_SEG_HEAD = re.compile(r"^[\s|]*(?:note\s*)?\d{0,2}[\.\):\- ]*\s*(?:segments?(?:\s+(?:information|reporting|and\s+geographic[^\n]{0,40}))?|reportable\s+segments|business\s+segments|"
                       r"segment\s+and\s+geographic[^\n]{0,40})\s*$", re.I | re.M)
_NOTE_START = re.compile(r"^[\s|]*(?:note\s*\d{1,2}\b|\d{1,2}[\.\)]\s+[A-Z][A-Za-z ,&\-]{3,60}$)", re.I | re.M)


def _segments(text: str) -> Optional[str]:
    """Heading-based fallback for the segment note: a short heading line containing 'segment' up to the next note heading (at most 25,000 characters)."""
    best = None
    for m in _SEG_HEAD.finditer(text):
        nxt = next((n.start() for n in _NOTE_START.finditer(text, m.end() + 600)), len(text))
        seg = text[m.start():min(nxt, m.start() + 25_000)]
        if len(seg) >= 800 and (best is None or len(seg) > len(best)):
            best = seg
    return best


def _cap(sid: str, text: Optional[str]) -> Section:
    if text is None or not text.strip():
        return Section(sid, None, 0, 0, ["section_not_found"])
    text = text.strip()
    full = len(text)
    flags = []
    if full > MAX_CHARS[sid]:
        text = text[:MAX_CHARS[sid]]
        flags.append("trimmed")
    return Section(sid, text, len(text), full, flags)


# ---------------------------------------------------------------- one document
def _document_candidates(body: str) -> dict:
    """sid -> [(text, method)] for one document (method: item | topic | note); '_9A' holds the Item 9A span."""
    out: dict = {k: [] for k in ALL_IDS}
    i1, i1a, i7, i9a = (_span(body, k) for k in ("1", "1A", "7", "9A"))
    if i1:
        out["TXT-001"].append((body[i1[0]:i1[1]], "item"))
    if i1a:
        out["TXT-002"].append((body[i1a[0]:i1a[1]], "item"))
    if i7:
        out["TXT-004"].append((body[i7[0]:i7[1]], "item"))
    out["_9A"] = [(body[i9a[0]:i9a[1]], "item")] if i9a else []
    for sid, which in (("TXT-001", "business"), ("TXT-002", "risk"), ("TXT-004", "mdna")):
        t = _topic_span(body, which)
        if t:
            out[sid].append((t, "topic"))
    sg = _segments(body)
    if sg:
        out["TXT-005"].append((sg, "note"))
    chain = _note_chain(body)
    if chain:
        seg = _note_texts(body, chain, SEGMENT_KEYS)
        if seg:
            out["TXT-005"].append(("\n\n".join(t for _, t in seg), "note"))
        for nid, key in NOTE_KEYS.items():
            nt = _note_texts(body, chain, key)
            if nt:
                out[nid].append(("\n\n".join(t for _, t in nt), "note"))
    return out


def _documents(text: str) -> list:
    marks = list(_DOC_MARK.finditer(text))
    if not marks:
        return [("main", text)]
    return [(m.group(1), text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))]) for i, m in enumerate(marks)]


def _primary_name(names: list) -> str:
    plain = [n for n in names if not re.search(r"_d\d|ex[-_]?\d|exhibit", n, re.I)]
    return (plain or names)[0]


def split_sections(text: str) -> dict:
    """text (one 10-K, possibly several documents) -> {section id: Section} for TXT-001..005 and NOTE-ACQ / NOTE-UNUSUAL / NOTE-LOANS."""
    docs = _documents(text)
    prim = _primary_name([n for n, _ in docs])
    cands: dict = {k: [] for k in ALL_IDS}
    nine_a: list = []
    for name, body in docs:
        c = _document_candidates(body)
        for sid in ALL_IDS:
            cands[sid] += [(t, method, name) for t, method in c[sid]]
        nine_a += [(t, m, name) for t, m in c["_9A"]]

    def best(sid):
        cs = cands[sid]
        if not cs:
            return None
        floor = STUB_BELOW.get(sid, 0)
        good = [x for x in cs if x[1] in ("item", "note") and len(x[0].strip()) >= floor]    # Item / note based and not a stub: preferred, primary document first
        if good:
            return sorted(good, key=lambda x: (x[2] != prim and x[1] == "item", -len(x[0])))[0]
        return sorted(cs, key=lambda x: -len(x[0]))[0]

    out: dict = {}
    for sid in ("TXT-001", "TXT-002", "TXT-005", "NOTE-ACQ", "NOTE-UNUSUAL", "NOTE-LOANS"):
        b = best(sid)
        sec = _cap(sid, b[0] if b else None)
        if b and sec.found:
            if b[1] == "topic":
                sec.flags.append("topic_fallback")
            if b[2] != prim:
                sec.flags.append(f"source_exhibit:{b[2]}")
        out[sid] = sec
    t1 = out["TXT-001"].text
    out["TXT-003"] = _cap("TXT-003", _competition(t1) if t1 else None)
    if out["TXT-003"].found:
        out["TXT-003"].flags += [f for f in out["TXT-001"].flags if f.startswith(("source_exhibit", "topic_fallback"))]
    b7 = best("TXT-004")
    b9 = sorted(nine_a, key=lambda x: (x[2] != prim, -len(x[0])))[0] if nine_a else None
    parts = [x for x in (b7, b9) if x]
    t4 = _cap("TXT-004", "\n\n".join(p[0].strip() for p in parts) if parts else None)
    if t4.found:
        if b7 is None:
            t4.flags.append("item7_not_found")
        else:
            if b7[1] == "topic":
                t4.flags.append("topic_fallback")
            if b7[2] != prim:
                t4.flags.append(f"source_exhibit:{b7[2]}")
            if len(b7[0].strip()) < STUB_BELOW["TXT-004"]:
                t4.flags.append("item7_short")
        if b9 is None:
            t4.flags.append("item9a_not_found")
    out["TXT-004"] = t4
    return {k: out[k] for k in ALL_IDS}


# ---------------------------------------------------------------- filings cache
@dataclass
class Filing:
    ticker: str
    text: str
    accession: str
    path: str
    report_date: str = ""


def _accession(prefix: str) -> str:
    return f"{prefix[:10]}-{prefix[10:12]}-{prefix[12:18]}" if len(prefix) >= 18 else prefix


def find_filing(ticker: str, end_date: Optional[str] = None, directory: Path = FILINGS) -> Optional[Filing]:
    """A 10-K of ``ticker`` in the cache: the html (preferred; the accession is in the file name) or ``<TICKER>_10K_text.txt`` (accession from meta.json).
    With ``end_date`` (YYYY-MM-DD, the engines' latest fiscal year end) the filing whose period end is within 20 days of it; otherwise the latest."""
    from datetime import date as _d
    t = ticker.upper()

    def dist(stamp: str) -> int:
        try:
            return abs((_d(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8])) - _d.fromisoformat(end_date)).days)
        except ValueError:                       # a file name that only looks like a date
            return 10 ** 6
    htmls = sorted((p for p in directory.glob(f"*_{t.lower()}-*.htm") if re.match(r"\d{8}", p.stem.split("-")[-1]) and not re.search(r"_d\d+$", p.stem)),
                   key=lambda p: p.stem.split("-")[-1][:8])
    if end_date:
        htmls = [p for p in htmls if dist(p.stem.split("-")[-1][:8]) <= 20]
    if htmls:
        from ..providers.sec_filings import html_to_text
        p = htmls[-1]
        text = f"===== DOCUMENT: {p.name} =====\n" + html_to_text(p.read_text(encoding="utf-8", errors="ignore"))
        for q in sorted(directory.glob(p.stem + "_d*.htm")):         # companion documents of the same filing (Exhibit 13 annual report etc.)
            text += f"\n===== DOCUMENT: {q.name} =====\n" + html_to_text(q.read_text(encoding="utf-8", errors="ignore"))
        txt0 = directory / f"{t}_10K_text.txt"
        if not (txt0.exists() and _accession(p.name.split("_")[0]) == (json.loads((directory / "meta.json").read_text(encoding="utf-8")).get(t, {}).get("accession", "")
                                                                         if (directory / "meta.json").exists() else "")
                and text.count("===== DOCUMENT") == 1 and txt0.read_text(encoding="utf-8", errors="ignore").count("===== DOCUMENT") > 1):
            return Filing(t, text, _accession(p.name.split("_")[0]), str(p), p.stem.split("-")[-1])
    txt = directory / f"{t}_10K_text.txt"
    if txt.exists():
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8")) if (directory / "meta.json").exists() else {}
        m = meta.get(t, {})
        rd = (m.get("report_date") or "").replace("-", "")
        if end_date and rd and dist(rd) > 20:
            return None
        return Filing(t, txt.read_text(encoding="utf-8", errors="ignore"), m.get("accession", ""), str(txt), m.get("report_date", ""))
    return None


def section_report(ticker: str, end_date: Optional[str] = None) -> dict:
    f = find_filing(ticker, end_date)
    if f is None:
        return {"ticker": ticker, "filing": None, "sections": {}}
    secs = split_sections(f.text)
    return {"ticker": ticker, "filing": {"accession": f.accession, "report_date": f.report_date, "path": f.path, "chars": len(f.text)},
            "sections": {k: {"found": s.found, "chars": s.chars, "full_chars": s.full_chars, "flags": s.flags} for k, s in secs.items()}}
