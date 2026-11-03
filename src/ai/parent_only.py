"""Statements of the parent company alone are never a source (K6d-2 fixes, decided 2026-11-02).

A 10-K of a holding company carries, after the consolidated statements, "Schedule II - Condensed Financial Information of Registrant (Parent Company Only)": a balance sheet, an income statement and a
cash-flow statement of the holding company alone. Its totals look like the consolidated ones and differ from them (equity-method investments, no policyholder liabilities ...). A figure read from there is a wrong
figure that enters the score. ``parent_spans`` finds those pages in the text of a report; ``remove`` takes them out before sections are searched; ``in_parent`` says whether a quote lies inside one.
"""
from __future__ import annotations

import re
from typing import Optional

# the heading of the schedule itself (not a reference to it: "See Schedule II included under Item 8")
HEADING = re.compile(r"SCHEDULE\s+II\b[^.]{0,60}?CONDENSED\s+FINANCIAL\s+INFORMATION|CONDENSED\s+FINANCIAL\s+INFORMATION\s+OF\s+(?:THE\s+)?REGISTRANT|PARENT\s+COMPANY\s+ONLY\s+(?:CONDENSED\s+)?(?:BALANCE|STATEMENTS?|FINANCIAL)|"
                     r"(?<![a-z])Condensed\s+Financial\s+Information\s+of\s+(?:the\s+)?(?:Registrant|Parent)\b|Schedule\s+I\s+[-–—]\s+Condensed\s+Financial\s+Information", re.S)
END = re.compile(r"SCHEDULE\s+(?:III|IV|V)\b|Schedule\s+(?:III|IV|V)\s+[-–—]|\bSIGNATURES\b|EXHIBIT\s+INDEX", re.S)
MAX_SPAN = 30000                                              # the schedule is a few pages; the span never runs past this


def parent_spans(text: str) -> list:
    """[(start, end)] of the parent-company-only pages of a report text."""
    spans = []
    for m in HEADING.finditer(text or ""):
        if spans and m.start() < spans[-1][1]:
            continue
        # a reference ("See Schedule II ...", "included under Item 8") is not the schedule: the schedule is followed by a table within a short distance
        head = text[m.start():m.start() + 700]
        if not re.search(r"(?:balance sheets?|statements? of (?:income|cash flows|operations)|ASSETS|parent company)", head, re.I) or re.search(r"see\s+Schedule", text[max(0, m.start() - 12):m.start() + 12], re.I):
            continue
        e = END.search(text, m.end())
        end = min(e.start() if e else len(text), m.start() + MAX_SPAN)
        spans.append((m.start(), end))
    return spans


def remove(text: str) -> str:
    """The text without the parent-company-only pages."""
    spans = parent_spans(text)
    if not spans:
        return text
    out, pos = [], 0
    for a, b in spans:
        out.append(text[pos:a])
        pos = b
    out.append(text[pos:])
    return "".join(out)


def in_parent(text: str, quote: str, spans: Optional[list] = None) -> bool:
    """True when the quote occurs ONLY inside a parent-company-only span (the same words in the consolidated statements make it a consolidated quote)."""
    spans = parent_spans(text) if spans is None else spans
    if not spans or not quote:
        return False
    hits = [m.start() for m in re.finditer(re.escape(quote), text)]
    return bool(hits) and all(any(a <= h < b for a, b in spans) for h in hits)
