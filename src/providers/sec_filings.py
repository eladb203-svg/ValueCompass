"""SEC filing text provider: fetch a 10-K (and its Exhibit 13 annual report, if any) and convert it to plain text.

Used by the bank test round to extract regulatory items that are not in XBRL. Respects the same fair-access limits as
SecClient (identifying User-Agent, <= 10 requests/s) and caches under scripts/cache/filings.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from .sec_companyfacts import ROOT, SecClient

FILINGS = ROOT / "scripts" / "cache" / "filings"


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6", "section"}
    SKIP = {"script", "style", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(raw: str) -> str:
    raw = re.sub(r"<ix:header>.*?</ix:header>", " ", raw, flags=re.S | re.I)  # hidden XBRL context block
    p = _Text()
    p.feed(raw)
    t = html.unescape("".join(p.out)).replace("\xa0", " ")
    t = t.translate({0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2212: "-"})  # unify dash variants
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"( \| )+", " | ", t)  # collapse empty cells
    t = re.sub(r" \|\s*\n", "\n", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t


def _get_raw(sec: SecClient, url: str, cache_name: str) -> str:
    path = FILINGS / cache_name
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    import time
    import requests
    wait = 0.15 - (time.monotonic() - sec._last)
    if wait > 0:
        time.sleep(wait)
    r = requests.get(url, headers=sec._headers, timeout=180)
    sec._last = time.monotonic()
    sec.requests_made += 1
    r.raise_for_status()
    FILINGS.mkdir(parents=True, exist_ok=True)
    path.write_text(r.text, encoding="utf-8")
    return r.text


def latest_10k(sec: SecClient, cik: str) -> Optional[dict]:
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    rec = sub["filings"]["recent"]
    for form, filed, acc, doc, rdate in zip(rec["form"], rec["filingDate"], rec["accessionNumber"],
                                             rec["primaryDocument"], rec["reportDate"]):
        if form == "10-K":
            return {"filed": filed, "accession": acc, "primary": doc, "report_date": rdate}
    return None


def filing_documents(sec: SecClient, cik: str, k: dict) -> list:
    """Main document plus any Exhibit 13 (annual report) file names of the filing."""
    acc = k["accession"].replace("-", "")
    idx = sec.get_json(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json",
                       f"idx_{acc}.json")
    names = [i["name"] for i in idx["directory"]["item"]]
    docs = [k["primary"]]
    for n in names:
        if re.search(r"ex[-_]?13", n, re.I) and n.lower().endswith((".htm", ".html")) and n not in docs:
            docs.append(n)
    return docs


def fetch_filing_text(sec: SecClient, ticker: str, cik: str, extra_docs: tuple = ()) -> dict:
    """Download the latest 10-K (+ EX-13) and store the plain text; returns metadata incl. the text file path."""
    k = latest_10k(sec, cik)
    if not k:
        raise RuntimeError(f"no 10-K found for {ticker}")
    docs = filing_documents(sec, cik, k) + [d for d in extra_docs]
    acc = k["accession"].replace("-", "")
    texts = []
    for d in docs:
        raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{d}", f"{acc}_{d}")
        texts.append(f"\n===== DOCUMENT: {d} =====\n" + html_to_text(raw))
    out = FILINGS / f"{ticker}_10K_text.txt"
    out.write_text("\n".join(texts), encoding="utf-8")
    return {**k, "documents": docs, "text_path": str(out), "chars": sum(len(t) for t in texts),
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{docs[0]}"}


def load_text(ticker: str) -> str:
    return (FILINGS / f"{ticker}_10K_text.txt").read_text(encoding="utf-8")


def save_meta(meta: dict) -> None:
    (FILINGS / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
