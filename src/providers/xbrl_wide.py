"""Wide XBRL search for an item whose base tag leaves years missing (K6d-2 fixes, 2026-11-01). Runs inside the four providers, after the standard tag chain and before the formula fallbacks.

Three searches, in this order, each only for the years still missing; nothing is guessed (no model):
  (a) dimensions of the 10-K inline XBRL: a per-share item reported per class of stock (TSN: Class A and Class B dividends per share, no undimensioned value) takes the value of the TRADED class,
      the class whose trading symbol (``dei:TradingSymbol`` of the cover page) is the ticker; a share count reported per class is the sum of the classes (the company's total);
  (b) a company-extension element whose name is close to the standard one (word mapping, not a model): ``tsn:...DividendsPerShare...``;
  (c) the formulas the providers already have (dividends paid / shares, net interest ...) stay where they are, after this step.
Every value found is marked: ``DERIVED: ...`` (source_kind derived) for (a), ``ixbrl:custom_tag ...`` (source_kind ixbrl) for (b). Two candidates that disagree for a year leave the year missing and are returned as
a conflict, for the review list (``data_gap_review``).
"""
from __future__ import annotations

import re
from typing import Optional

from .sec_companyfacts import Fact
from .sec_filings import _get_raw
from .sec_ixbrl import _NF, _attr, parse_contexts, parse_numeric, tenk_filings

CLASS_AXIS = "StatementClassOfStockAxis"
_NN = re.compile(r"<ix:nonNumeric\b([^>]*)>(.*?)</ix:nonNumeric>", re.S | re.I)

# field -> (standard local names, unit kind, flow or instant, word pattern of a close company-extension element, how classes combine)
SPECS = {
    "dps": (["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"], "pershare", "flow", r"dividends?.*per.?share|per.?share.*dividends?", "traded"),
    "eps": (["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"], "pershare", "flow", r"^earnings?.?per.?share.*diluted", "traded"),
    "shares": (["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted"], "shares", "flow", r"^weighted.*diluted.*shares", "sum"),
    "shares_basic": (["WeightedAverageNumberOfSharesOutstandingBasic"], "shares", "flow", r"^weighted.*basic.*shares", "sum"),
    "shares_out": (["CommonStockSharesOutstanding"], "shares", "instant", r"^(common)?shares.?outstanding$", "sum"),
}


# a total reported only as a member of an axis: bank nonaccrual loans are the loans (before allowance) with the past-due member "Nonperforming" (EWBC); the standard nonaccrual tag has no undimensioned value
MEMBER_SPECS = {
    "nonaccrual": (["FinancingReceivableExcludingAccruedInterestNonaccrual", "FinancingReceivableRecordedInvestmentNonaccrualStatus",
                    "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss", "FinancingReceivableRecordedInvestment"],
                   "PastDueAxis", ("NonperformingFinancingReceivableMember", "NonaccrualMember", "FinancingReceivableRecordedInvestmentNonaccrualStatusMember", "FinancialAssetNonaccrualMember")),
}


def member_facts(raw: str, names: list, axis_suffix: str, members: tuple) -> dict:
    """{local name: {end: (value, full name, member)}} - instant facts whose ONLY dimension is the axis (name ends with ``axis_suffix``) at one of the members."""
    ctx = parse_contexts(raw)
    out: dict = {}
    for attrs, text in _NF.findall(raw):
        full = _attr(attrs, "name") or ""
        local = full.split(":")[-1]
        if local not in names or "usd" not in (_attr(attrs, "unitRef") or "").lower():
            continue
        c = ctx.get(_attr(attrs, "contextRef") or "")
        if not c or not c["instant"] or len(c["dims"]) != 1 or not c["dims"][0][0].endswith(axis_suffix) or c["dims"][0][1].split(":")[-1] not in members:
            continue
        v = parse_numeric(attrs, text)
        if v is not None:
            out.setdefault(local, {}).setdefault(c["end"], (v, full, c["dims"][0][1].split(":")[-1]))
    return out


def member_search(sec, cik: str, fld: str, needed_ends: list, max_filings: int = 6) -> dict:
    """{needed end: Fact} for a total reported as a member (MEMBER_SPECS), newest filing first; the tags are tried in the order of the spec."""
    names, axis, members = MEMBER_SPECS[fld]
    found: dict = {}
    missing = set(needed_ends)
    used = 0
    for k in tenk_filings(sec, cik):
        if not missing or used >= max_filings:
            break
        if all(abs((k["report_date"] - e).days) > 800 for e in missing):
            continue
        acc = k["accession"].replace("-", "")
        raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{k['primary']}", f"{acc}_{k['primary']}")
        used += 1
        mf = member_facts(raw, names, axis, members)
        for local in names:
            for end, (v, full, mem) in mf.get(local, {}).items():
                m = _near(missing, end)
                if m is not None and m not in found:
                    found[m] = Fact(val=v, end=end, filed=k["filed"], form="10-K", accn=k["accession"], tag=f"DERIVED: {full} at the member {mem} of {axis} (the total only exists as a member)")
        missing -= set(found)
    return found


def _unit_ok(unit: str, kind: str) -> bool:
    u = unit.lower()
    return ("share" in u and "usd" in u) if kind == "pershare" else (u == "shares" or (u.endswith("shares") and "usd" not in u))


def traded_member(raw: str, ticker: str, members=()) -> Optional[str]:
    """The class-of-stock member of the class that trades under the ticker: (1) the ``dei:TradingSymbol`` fact of the cover page that is the ticker and carries the class axis, else (2) the title of the
    registered security on the cover page ("Class A Common Stock") when the symbol of the cover page is the ticker, matched to the member named ``...ClassA...``; None when neither says it."""
    ctx = parse_contexts(raw)
    symbol_here = False
    for attrs, body in _NN.findall(raw):
        if (_attr(attrs, "name") or "").lower() != "dei:tradingsymbol":
            continue
        if re.sub(r"<[^>]+>", "", body).strip().upper() != ticker.upper():
            continue
        symbol_here = True
        c = ctx.get(_attr(attrs, "contextRef") or "")
        for axis, member in (c or {}).get("dims", []):
            if axis.split(":")[-1] == CLASS_AXIS:
                return member
    if symbol_here:
        for attrs, body in _NN.findall(raw):
            if (_attr(attrs, "name") or "").lower() != "dei:security12btitle":
                continue
            m = re.search(r"class\s+([A-Z])", re.sub(r"<[^>]+>", " ", body), re.I)
            if m:
                hits = [x for x in members if re.search(r"[Cc]lass" + m.group(1).upper() + r"(?![a-z])", x.split(":")[-1])]
                if len(hits) == 1:
                    return hits[0]
    return None


def class_facts(raw: str, local_names: list, unit_kind: str, kind: str) -> dict:
    """{local name: {end: {member: (value, full name)}}} - annual facts whose only dimension is the class of stock."""
    ctx = parse_contexts(raw)
    out: dict = {}
    for attrs, text in _NF.findall(raw):
        full = _attr(attrs, "name") or ""
        local = full.split(":")[-1]
        if local not in local_names:
            continue
        if not _unit_ok(_attr(attrs, "unitRef") or "", unit_kind):
            continue
        c = ctx.get(_attr(attrs, "contextRef") or "")
        if not c or (kind == "instant") != c["instant"] or len(c["dims"]) != 1 or c["dims"][0][0].split(":")[-1] != CLASS_AXIS:
            continue
        if kind == "flow" and not 340 <= (c["end"] - c["start"]).days <= 380:
            continue
        v = parse_numeric(attrs, text)
        if v is not None:
            out.setdefault(local, {}).setdefault(c["end"], {}).setdefault(c["dims"][0][1], (v, full))
    return out


def plain_facts(raw: str, pattern: str, unit_kind: str, kind: str) -> dict:
    """{full name: {end: value}} of company-extension elements (not us-gaap / dei / srt) whose local name matches ``pattern`` and that have no dimension."""
    ctx = parse_contexts(raw)
    out: dict = {}
    for attrs, text in _NF.findall(raw):
        full = _attr(attrs, "name") or ""
        prefix, _, local = full.partition(":")
        if prefix.lower() in ("us-gaap", "dei", "srt", "ifrs-full") or not re.search(pattern, local, re.I):
            continue
        if not _unit_ok(_attr(attrs, "unitRef") or "", unit_kind):
            continue
        c = ctx.get(_attr(attrs, "contextRef") or "")
        if not c or c["dims"] or (kind == "instant") != c["instant"]:
            continue
        if kind == "flow" and not 340 <= (c["end"] - c["start"]).days <= 380:
            continue
        v = parse_numeric(attrs, text)
        if v is not None:
            out.setdefault(full, {}).setdefault(c["end"], v)
    return out


def _near(missing, end, tol=10):
    return next((m for m in missing if abs((m - end).days) <= tol), None)


def search(sec, cik: str, ticker: str, fld: str, needed_ends: list, max_filings: int = 6) -> tuple:
    """-> ({needed end: Fact}, [conflict dicts]) for one field. Reads the 10-K inline XBRL newest first until every needed year is covered."""
    names, unit_kind, kind, pattern, how = SPECS[fld]
    found: dict = {}
    conflicts: list = []
    missing = set(needed_ends)
    used = 0
    for k in tenk_filings(sec, cik):
        if not missing or used >= max_filings:
            break
        if all(abs((k["report_date"] - e).days) > 800 for e in missing):
            continue
        acc = k["accession"].replace("-", "")
        raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{k['primary']}", f"{acc}_{k['primary']}")
        used += 1
        cf = class_facts(raw, names, unit_kind, kind)
        all_members = sorted({m for byend in cf.values() for ms in byend.values() for m in ms})
        traded = traded_member(raw, ticker, all_members)
        for local in names:                                                  # (a) the classes, in the priority order of the standard chain
            for end, members in cf.get(local, {}).items():
                m = _near(missing, end)
                if m is None or m in found:
                    continue
                if how == "traded":
                    pick = traded if traded in members else None
                    if pick is None:
                        conflicts.append({"field": fld, "end": str(end), "reason": f"{local} is reported per class ({', '.join(sorted(x.split(':')[-1] for x in members))}) and the traded class of {ticker} is not identified"})
                        continue
                    v, full = members[pick]
                    tag = f"DERIVED: {full} of the traded class {pick.split(':')[-1]} (the only values are per class of stock; class={pick.split(':')[-1]})"
                else:
                    v, full = sum(x[0] for x in members.values()), next(iter(members.values()))[1]
                    tag = f"DERIVED: sum of {len(members)} classes of stock: {full} ({', '.join(sorted(x.split(':')[-1] for x in members))})"
                found[m] = Fact(val=v, end=end, filed=k["filed"], form="10-K", accn=k["accession"], tag=tag)
        left = missing - set(found)
        if left:                                                             # (b) a close company element
            cands = plain_facts(raw, pattern, unit_kind, kind)
            for end in {e for vals in cands.values() for e in vals}:
                m = _near(left, end)
                if m is None or m in found:
                    continue
                vals = {n: v[end] for n, v in cands.items() if end in v}
                if len({round(x, 6) for x in vals.values()}) > 1:
                    conflicts.append({"field": fld, "end": str(end), "reason": "two company elements with close names disagree: " + "; ".join(f"{n}={x}" for n, x in sorted(vals.items()))})
                    continue
                n, x = next(iter(vals.items()))
                found[m] = Fact(val=x, end=end, filed=k["filed"], form="10-K", accn=k["accession"], tag=f"ixbrl:custom_tag {n} (a company element with a name close to {names[0]})")
        missing -= set(found)
    from datetime import date
    keep, seen = [], set()
    for c in conflicts:                                                      # a conflict counts only for a year that stays missing, once per field and year
        y = date.fromisoformat(c["end"])
        if _near(set(found), y) is None and (c["field"], c["end"]) not in seen:
            seen.add((c["field"], c["end"]))
            keep.append(c)
    return found, keep


def fill(sec, cik: str, ticker: str, f: dict, log: dict, labels: list, ends: list, problems: list, split_factor=None, fields=("dps", "eps", "shares", "shares_basic", "shares_out")) -> list:
    """Fill the years still missing of the fields; mutates ``f``, ``log``, ``problems``. -> conflicts (for ``data_gap_review``). A failure of the search is reported in ``problems`` and changes nothing."""
    conflicts: list = []
    for fld in [x for x in MEMBER_SPECS if x in f]:
        miss = [e for e, v in zip(ends, f[fld]) if v is None]
        if not miss:
            continue
        try:
            got = member_search(sec, cik, fld, miss)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{fld}: wide XBRL member search failed ({type(exc).__name__}: {exc})")
            continue
        done = []
        for i, (end, lab) in enumerate(zip(ends, labels)):
            fact = got.get(end)
            if fact is not None and f[fld][i] is None:
                f[fld][i] = fact.val
                log.setdefault(fld, {})[lab] = {"tag": fact.tag, "value": fact.val, "filed": str(fact.filed), "form": fact.form}
                done.append(lab)
        if done:
            problems.append(f"{fld}: wide XBRL search (member of an axis) filled {', '.join(done)}")
    for fld in fields:
        if fld not in f or fld not in SPECS:
            continue
        miss = [e for e, v in zip(ends, f[fld]) if v is None]
        if not miss:
            continue
        try:
            got, conf = search(sec, cik, ticker, fld, miss)
        except Exception as exc:  # noqa: BLE001 - the search is an addition; a failure is a note, never a stop
            problems.append(f"{fld}: wide XBRL search failed ({type(exc).__name__}: {exc})")
            continue
        conflicts += conf
        done = []
        for i, (end, lab) in enumerate(zip(ends, labels)):
            fact = got.get(end)
            if fact is None or f[fld][i] is not None:
                continue
            v = fact.val
            fac = 1.0
            if split_factor is not None:
                fac = split_factor(fact.filed)
                v = v / fac if SPECS[fld][1] == "pershare" else v * fac
            f[fld][i] = v
            log.setdefault(fld, {})[lab] = {"tag": fact.tag, "value": v, "filed": str(fact.filed), "form": fact.form, **({"split_adjust_factor": fac} if fac != 1.0 else {})}
            done.append(lab)
        if done:
            problems.append(f"{fld}: wide XBRL search filled {', '.join(done)} ({got[next(e for e in ends if e in got)].tag[:90]})")
    return conflicts
