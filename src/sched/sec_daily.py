"""New annual reports and amendments from ONE request per trading day: the SEC daily form index (K6 spec 3.1).

``https://www.sec.gov/Archives/edgar/daily-index/<year>/QTR<n>/form.<yyyymmdd>.idx`` lists every filing of the day. The 10-K, 10-K/A and 10-KT lines whose CIK is one of ours are the news; a company
is queued with ``new_report`` (an original report) or ``amendment`` (a 10-K/A), priority 3 (K6 spec 2.8).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

ANNUAL = ("10-K", "10-K/A", "10-KT", "10-KT/A")
LINE = re.compile(r"^(?P<form>\S.*?)\s{2,}(?P<name>.*?)\s+(?P<cik>\d+)\s+(?P<date>\d{8})\s+(?P<file>edgar/\S+)\s*$")


def index_url(d: date) -> str:
    return f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{(d.month - 1) // 3 + 1}/form.{d:%Y%m%d}.idx"


def fetch_index(sec, d: date) -> Optional[str]:
    """The text of the day's form index, or None when the SEC has no such file (a day that is not published yet, or no filings). Cached on disk (a day's index never changes)."""
    name = f"idx_{d:%Y%m%d}.idx"
    path = sec.cache_dir / name
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        text = sec._download(index_url(d))
    except Exception as e:   # noqa: BLE001 - a 404 is "not there", anything else is a real failure
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 404 or isinstance(e, FileNotFoundError):
            return None
        raise
    path.write_text(text, encoding="utf-8")
    return text


def parse_form_index(text: str, forms: tuple = ANNUAL) -> list:
    """The filings of the given forms in a form index -> [{"form", "company", "cik" (int), "filed", "accession"}]. The columns of the real file are not fixed-width (a long form type pushes
    the others), so a line is read from its end: ``<form> <name> <cik> <yyyymmdd> edgar/data/<cik>/<accession>.txt``."""
    out = []
    for ln in text.splitlines():
        m = LINE.match(ln)
        if not m or m["form"] not in forms:
            continue
        acc = re.search(r"(\d{10}-\d{2}-\d{6})", m["file"])
        if not acc:
            continue
        out.append({"form": m["form"], "company": m["name"].strip(), "cik": int(m["cik"]), "filed": m["date"], "accession": acc.group(1)})
    return out


def ours(filings: list, companies: list) -> list:
    """The filings whose CIK belongs to one of our companies (rows of ``companies`` with a ``cik``) -> [(filing, company)]."""
    by_cik = {int(c["cik"]): c for c in companies if c.get("cik") and str(c["cik"]).isdigit()}
    return [(f, by_cik[f["cik"]]) for f in filings if f["cik"] in by_cik]


def job_of(form: str) -> str:
    return "amendment" if form.endswith("/A") else "new_report"
