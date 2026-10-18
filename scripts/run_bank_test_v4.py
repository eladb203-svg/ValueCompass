"""Confirmation run (spec 2026-10-13_10-10: V5 adjusted PPNR, V8, V11). Writes scripts/output_banks_v4/ only; earlier outputs are kept.

Cached filings and prices only; no DB; no AI calls; production thresholds unchanged (candidates are not used here).
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_bank_test as rbt  # noqa: E402
from run_bank_test_v3 import _buy, _ir, _pct, _ps, _rng, _v  # noqa: E402
from src.providers.bank_facts import load_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402

OUT = ROOT / "scripts" / "output_banks_v4"
V3 = ROOT / "scripts" / "output_banks_v3"
SPEC = "docs/scoring/ValueCompass_Bank_Rules_2026-10-13_10-10_EN.md"
EXPECT_VALUED = {"TFC", "KEY"}


def _bn(x):
    return "n/a" if x is None else f"{x / 1e9:.2f}"


def _gtxt(gp):
    return _v(gp.get("value")) if gp["state"] == "valued" else "cannot be valued"


def _v3(t):
    f = V3 / f"{t}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def build(rows, failures):
    L = [f"# ValueCompass BANK confirmation run (v4) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}` (supersedes 2026-10-12_22-35). Changes vs the v3 run: V5 adjusted PPNR (goodwill impairment + net realized securities loss), "
         "V8 implied-return lower bound just above 2.5% (\"below 2.5%\"), V11 FLG exemption evidence (total assets < $100bn), "
         "candidate thresholds removed from the production path. Cached data only (0 SEC requests); no DB; no AI calls; quality scores use production thresholds.\n"]
    if failures:
        L.append("**Failed banks:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------------------------------------------------------- expectations
    L.append("## 1. Expectation check\n")
    by = {bi.ticker: (res, bi, d, bq, bp, gq, gp) for res, bi, d, bq, bp, gq, gp in rows}
    old = {t: _v3(t) for t in by}
    diffs = []
    for t in EXPECT_VALUED:
        gp = by[t][6]
        L.append(f"- {t}: expected valued with flags -> **{'valued' if gp['state'] == 'valued' else 'CANNOT BE VALUED'}**"
                 f"{'' if gp['state'] == 'valued' else ': ' + gp['reason']}")
        if gp["state"] != "valued":
            diffs.append(f"{t} is still not valued")
    flg = by["FLG"][6]
    L.append(f"- FLG: expected still \"cannot be valued\" -> **{'cannot be valued' if flg['state'] != 'valued' else 'VALUED ' + _v(flg['value'])}**"
             f"{': ' + flg['reason'] if flg['state'] != 'valued' else ''}; Buffett: {by['FLG'][4]['state']} ({by['FLG'][4].get('reason', '')})")
    if flg["state"] == "valued":
        diffs.append("FLG is now valued")
    c = by["C"][6]
    c_old = (old["C"] or {}).get("graham_price", {})
    same = c_old and abs((c_old.get("value") or 0) - (c.get("value") or 0)) < 1e-4 and c["state"] == c_old.get("state")
    L.append(f"- C: expected unchanged -> {'unchanged' if same else '**CHANGED**'} (Graham value {_gtxt(c)}; v3 {_v((c_old or {}).get('value'))})")
    if not same:
        diffs.append("C changed")
    others = [t for t in by if t not in EXPECT_VALUED | {"FLG", "C"}]
    chg = [t for t in others if old[t] and (abs((old[t]["graham_price"].get("value") or 0) - (by[t][6].get("value") or 0)) > 1e-4
                                            or old[t]["graham_price"].get("state") != by[t][6]["state"])]
    L.append(f"- Other banks' Graham value/state: {'unchanged' if not chg else '**CHANGED: ' + ', '.join(chg) + '**'}")
    if chg:
        diffs.append("changed: " + ", ".join(chg))
    qchg = [t for t in by if old[t] and (abs(old[t]["buffett_quality"]["score"] - by[t][3].score) > 1e-4
                                         or abs(old[t]["graham_quality"]["score"] - by[t][5].score) > 1e-4)]
    L.append(f"- Quality scores vs v3: {'unchanged for all 12 banks' if not qchg else '**CHANGED: ' + ', '.join(qchg) + '**'}")
    if qchg:
        diffs.append("quality scores changed: " + ", ".join(qchg))
    L.append("\n**Differences from the expectation: " + ("none." if not diffs else "; ".join(diffs) + ".") + "**\n")
    # ---------------------------------------------------------------- loss years
    L.append("## 2. Loss years (diluted EPS < 0, 10-year window): classification, cause, adjusted PPNR vs provision\n")
    L.append("Adjusted PPNR = PPNR + goodwill impairment + net realized securities loss (a gain is not deducted). USD bn.\n")
    L.append("| Bank | Year | EPS | PPNR | + goodwill impairment | + securities loss | Adjusted PPNR | Provision | Pretax | Classification | Cause |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
    any_ly = False
    for t, (res, bi, d, bq, bp, gq, gp) in by.items():
        for ly in gp.get("loss_years") or []:
            any_ly = True
            L.append(f"| {t} | {ly['year']} | {ly['eps']:.2f} | {_bn(ly['ppnr'])} | {_bn(ly['goodwill_impairment'])} | {_bn(ly['securities_loss'])} | "
                     f"{_bn(ly['adjusted_ppnr'])} | {_bn(ly['provision'])} | {_bn(ly['pretax'])} | "
                     f"{'one-off (valued, flagged)' if ly['kind'] == 'one_off' else 'OPERATING -> cannot be valued'} | {ly['cause']} |")
    if not any_ly:
        L.append("| (none) | | | | | | | | | | |")
    L.append("\nBanks with no loss year in the window: " + ", ".join(t for t, v in by.items() if not (v[6].get('loss_years'))) + ".\n")
    # tags
    L.append("### XBRL tags found per bank-year (goodwill impairment / realized securities gain-loss; `-` = no tag filed for that year)\n")
    L.append("| Bank | Goodwill impairment tag (years found) | Realized securities gain/loss tag (years found) | Value in loss years |")
    L.append("|---|---|---|---|")
    for t, (res, bi, d, bq, bp, gq, gp) in by.items():
        cells = []
        for fld in ("goodwill_impairment", "securities_gain_loss"):
            lg = (bi.tag_log or {}).get(fld, {})
            tags = {}
            for fy in bi.fy[-10:]:
                tg = (lg.get(fy) or {}).get("tag")
                tags.setdefault(tg or "-", []).append(fy[2:])
            cells.append("; ".join(f"{k}: {','.join(v) if k != '-' else len(v) and str(len(v)) + ' yrs'}" for k, v in tags.items()))
        lv = "; ".join(f"{ly['year']}: gw {_bn(ly['goodwill_impairment'])}, sec {_bn(ly['securities_loss'])}" for ly in gp.get("loss_years") or []) or "-"
        L.append(f"| {t} | {cells[0]} | {cells[1]} | {lv} |")
    # ---------------------------------------------------------------- before / after
    L.append("\n## 3. Graham value and price score: before (v3) vs after (v4)\n")
    L.append("| Bank | Graham quality | Value before | Value after | Price score before | Price score after | State change |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for t, (res, bi, d, bq, bp, gq, gp) in by.items():
        o = (old[t] or {}).get("graham_price", {})
        ops = (o.get("price_score") or {}).get("points")
        ov = o.get("value")
        sc = "n/a" if (gp.get("price_score") or {}).get("points") is None else f"{gp['price_score']['points']:.1f}"
        chg_ = ("unchanged" if o.get("state") == gp["state"] else f"{o.get('state')} -> {gp['state']}")
        L.append(f"| {t} | {gq.score:.1f} | {_v(ov)}{'' if o.get('state') == 'valued' else ' (cannot be valued)'} | {_gtxt(gp)} | "
                 f"{'n/a' if ops is None else f'{ops:.1f}'} | {sc} | {chg_} |")
    # ---------------------------------------------------------------- full table
    L.append("\n## 4. Full 12-bank table\n")
    L.append("| Bank | Path | Buffett quality (range) | Graham quality (range) | Buffett v2 value (price) | Sensitivity range | Graham 10y value | "
             "Buffett price score | Graham price score | Implied return | Implied ROTCE | Buy price B / G | Flags |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t, (res, bi, d, bq, bp, gq, gp) in by.items():
        sr = bp.get("sensitivity_range")
        bval = _v(bp.get("fair_value")) if bp["state"] == "valued" else "cannot be valued"
        fl = []
        for ly in gp.get("loss_years") or []:
            fl.append(f"V5 {ly['year']} {ly['kind'].replace('_', '-')}: {ly['cause']}")
        if bp["state"] != "valued":
            fl.append("V6")
        if any(f.startswith("V7") for f in bp.get("flags", [])):
            fl.append("V7")
        lt = d["latest"]
        v9 = lt["v9"]
        if bi.ticker not in rbt_gsib():
            fl.append("V9 " + ("computed" if v9["stated"] is None else ("stated" if v9["computed"] is None else "computed=stated" if v9["match"] else "MISMATCH")))
        if lt["lcr"] == "NA":
            fl.append("V11 LCR n/a")
        elif lt.get("lcr_measure") == "quarter_end":
            fl.append("V10 LCR quarter-end")
        L.append(f"| {t} | {res['path']['path']} | {bq.score:.1f} ({_rng(bq)}) | {gq.score:.1f} ({_rng(gq)}) | {bval} ({bi.price_current:,.2f}) | "
                 f"{'n/a' if not sr else f'{sr[0]:,.1f} - {sr[1]:,.1f}'} | {_gtxt(gp)} | {_ps(bp)} | {_ps(gp)} | {_ir(bp.get('implied_return'))} | "
                 f"{_ir(bp.get('implied_rotce'))} | {_buy(bp)} / {_buy(gp)} | {'; '.join(fl) or '-'} |")
    L.append("\n### Detail of the new flag text\n")
    for t, (res, bi, d, bq, bp, gq, gp) in by.items():
        for f in gp["flags"]:
            if f.startswith("V5"):
                L.append(f"- {t}: {f}")
    L.append("\n## 5. V11 evidence and V8\n")
    reg = rbt_reg()
    r = reg.get("FLG", {}).get("lcr_q4_average", {})
    L.append(f"- FLG LCR: **{r.get('value')}** (not applicable). Evidence: total assets < $100bn (10-K). Quote: `{r.get('quote', '')[:140]}` "
             f"(verified: {r.get('verified')}). {r.get('note', '')}")
    ir = {t: v[4].get("implied_return") for t, v in by.items()}
    L.append(f"- Implied return (lower bound just above 2.5%, \"below 2.5%\" when the price implies less): "
             + ", ".join(f"{t} {_ir(v)}" for t, v in ir.items()) + ". No bank shows \"below 2.5%\" or \"no solution\".")
    L.append("\n## 6. Open issues\n")
    ip = ROOT / "scripts" / "bank_rule_issues_v4.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/bank_rule_issues_v4.md not written yet)")
    (OUT / "summary_banks_v4.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def rbt_gsib():
    return {"JPM", "BAC", "C", "WFC", "GS"}


_REG = {}


def rbt_reg():
    return _REG


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    rbt.OUT = OUT
    sec = SecClient()
    reg_all = load_regulatory()
    _REG.update(reg_all)
    rows, failures = [], []
    for t in rbt.BANKS:
        try:
            r = rbt.run_bank(sec, reg_all, t)
            if r is None:
                continue
            for name, m in (("buffett_quality", r[3]), ("graham_quality", r[5])):
                if m.range_error:
                    failures.append((t, f"{name} range check failed: {m.range_error}"))
            rows.append(r)
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if rows:
        build(rows, failures)
    print(f"SEC requests this run: {sec.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])
