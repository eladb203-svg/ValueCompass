"""Final bank round (spec 2026-10-12_22-35: V5-V11, 6c). Writes scripts/output_banks_v3/ only; earlier outputs are kept.

Re-uses cached filings and prices (no SEC fetch unless something is new); no DB; no AI calls.
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
from run_scoring_test import jsonable, model_json  # noqa: E402
from src.providers.bank_facts import load_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring import bank as bk  # noqa: E402
from threshold_parallel_run import TH_CANDIDATE, thresholds_override  # noqa: E402

OUT = ROOT / "scripts" / "output_banks_v3"
SPEC = "docs/scoring/ValueCompass_Bank_Rules_2026-10-12_22-35_EN.md"
G_SIB = {"JPM", "BAC", "C", "WFC", "GS"}

# (model, criterion, sub-item, label) rows of the parallel threshold run (6c)
PAR_ITEMS = [("graham", "3.2", "1", "Graham capital buffer (8): full at 3pp -> 4pp"),
             ("graham", "3.2", "3", "Graham deposit funding (2): 50/80% -> 60/90%"),
             ("graham", "3.3", "2", "Graham nonaccrual rate (3): 0.5/3% -> 0.4/2%"),
             ("graham", "3.3", "3", "Graham ACL/nonaccrual (4): 75/200% -> 100/300%"),
             ("buffett", "3.6", "3", "Buffett nonaccrual rate (1): 0.5/3% -> 0.4/2%"),
             ("buffett", "3.6", "4", "Buffett ACL/nonaccrual (1): 75/150% -> 100/300%")]


def _item(model, cid, iid):
    return next(i for c in model.criteria if c.id == cid for i in c.items if i.id == iid)


def _pts(it):
    return "n/a" if it.state == "not_applicable" else (it.state.upper() if it.points is None else f"{it.points:.2f}")


def _v(x, nd=2):
    return "n/a" if x is None else (x if isinstance(x, str) else f"{x:,.{nd}f}")


def _pct(x, nd=1):
    return "n/a" if x is None or isinstance(x, str) else f"{x * 100:.{nd}f}%"


def _rng(m):
    return "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"


def _ps(p):
    p = p or {}
    ps = p.get("price_score") or {}
    if ps.get("state") == "not_shown":
        return "not shown (" + ps["reason"] + ")"
    return "n/a" if ps.get("points") is None else f"{ps['points']:.1f}"


def _ir(x):
    return _pct(x, 1) if isinstance(x, float) else (x or "n/a")


def _ranks(vals: dict):
    order = sorted(vals, key=lambda t: -vals[t])
    return {t: i + 1 for i, t in enumerate(order)}


def build_summary(rows, cand, reg_all, failures):
    L = [f"# ValueCompass BANK final round (v3) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}` (supersedes 21-05 and 22-30). Implements V5-V11 and the 6b/6c display and calibration items. "
         "Cached filings and prices only (0 SEC requests); no DB; no AI calls (AI items stay `ai_pending`); production thresholds unchanged. "
         "Earlier outputs (`output_banks/`, `output_banks_round1/`) are kept.\n"]
    if failures:
        L.append("**Failed banks:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------------------------------------------------------- per bank
    L.append("## 1. Per bank\n")
    L.append("| Bank | Path | Buffett quality (range) | Graham quality (range) | Buffett v2 value | Sensitivity range | Graham 10y value | "
             "Buffett price score | Graham price score | Implied return | Implied ROTCE | Buy price B / G |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        t = bi.ticker
        bval = _v(bp.get("fair_value")) if bp["state"] == "valued" else f"cannot be valued: {bp['reason']}"
        gval = _v(gp.get("value")) if gp["state"] == "valued" else f"cannot be valued: {gp['reason']}"
        sr = bp.get("sensitivity_range")
        L.append(f"| {t} | {res['path']['path']} | {bq.score:.1f} ({_rng(bq)}) | {gq.score:.1f} ({_rng(gq)}) | {bval} | "
                 f"{'n/a' if not sr else f'{sr[0]:,.1f} - {sr[1]:,.1f}'} | {gval} | {_ps(bp)} | {_ps(gp)} | {_ir(bp.get('implied_return'))} | "
                 f"{_ir(bp.get('implied_rotce'))} | {_buy(bp)} / {_buy(gp)} |")
    L.append("\nPrice for reference: " + ", ".join(f"{bi.ticker} {bi.price_current:,.2f}" for _, bi, *_ in rows) + ".\n")
    L.append("### Sensitivity detail (V7: erosion only when ROTCE_norm > 10%; +/-1pp recompute growth; scenario values <= 0 are not shown)\n")
    L.append("| Bank | ROTCE_norm | g1 | Base | Erosion | +1pp | -1pp |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for res, bi, d, bq, bp, gq, gp in rows:
        if bp["state"] != "valued":
            L.append(f"| {bi.ticker} | {_pct(bp.get('rotce_norm'))} | cannot be valued ({bp['reason']}) | | | | |")
            continue
        s = bp["sensitivity"]
        L.append(f"| {bi.ticker} | {_pct(bp['rotce_norm'])} | {_pct(bp['g1'])} | {_v(s['base'])} | {_v(s['erosion'])}"
                 f"{' (= base)' if abs(s['erosion'] - s['base']) < 1e-9 else ''} | {_v(s['rotce_plus_1pp'])} | {_v(s['rotce_minus_1pp'])} |")
    L.append("\n### Flags (V5 / V9 / V10 / V11 and display notes)\n")
    L.append("| Bank | V5 Graham loss years | V6 / V7 Buffett | V9 requirement | V10 LCR measurement | V11 / LCR treatment | 3.3.1 note |")
    L.append("|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        ly = gp.get("loss_years") or []
        v5 = "none" if not ly else "; ".join(f"{x['year']}: {x['kind']} (PPNR {_v((x['ppnr'] or 0) / 1e9, 1)}bn, prov {_v((x['provision'] or 0) / 1e9, 1)}bn)" for x in ly)
        if any(f.startswith("V5_price_score_hidden") for f in gp["flags"]):
            v5 += "; price score hidden (quality < 55)"
        v67 = [f.split(" (")[0] for f in bp.get("flags", []) if f.startswith(("V6", "V7"))]
        v9 = lt["v9"]
        v9s = ("as reported (G-SIB)" if bi.ticker in G_SIB else
               f"used {_v(v9['used'])}%; " + ("computed only" if v9["stated"] is None else
                                              ("stated only (no SCB row)" if v9["computed"] is None else
                                               ("computed = stated" if v9["match"] else "MISMATCH, stated used"))))
        if lt["lcr"] in ("NA", "MISSING"):
            v10 = "n/a (not applicable)" if lt["lcr"] == "NA" else "missing"
        else:
            v10 = f"{lt['lcr_measure']} {lt['lcr']}% as of {lt['lcr_date']}" + (" - FLAGGED quarter-end" if lt["lcr_measure"] == "quarter_end" else "")
        lcrt = "not applicable (regulatory category, V11)" if lt["lcr"] == "NA" else ("MISSING" if lt["lcr"] == "MISSING" else "scored")
        note = "window contains no credit crisis" if any("no credit crisis" in f for f in _item(gq, "3.3", "1").flags) else "-"
        L.append(f"| {bi.ticker} | {v5} | {', '.join(v67) or '-'} | {v9s} | {v10} | {lcrt} | {note} |")
    # ---------------------------------------------------------------- V9 table
    L.append("\n## 2. V9 check - required CET1: computed (4.5% + SCB + G-SIB surcharge + CCyB 0%) vs stated in the 10-K\n")
    L.append("| Bank | Type | SCB | G-SIB surcharge | CCyB | Computed | Stated in 10-K | Used | Result |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        v9 = lt["v9"]
        if bi.ticker in G_SIB:
            L.append(f"| {bi.ticker} | G-SIB | as reported | as reported | 0 | not computed | {_v(lt['required_std'])}"
                     f"{'' if lt['required_adv'] is None or lt['required_adv'] == lt['required_std'] else ' std / ' + _v(lt['required_adv']) + ' adv'} | "
                     f"{_v(lt['required_std'])} | extracted as reported (V9 does not apply) |")
            continue
        if v9["computed"] is None:
            L.append(f"| {bi.ticker} | non-G-SIB | no SCB (not subject) | 0 | 0 | - | {_v(v9['stated'])} (capital schedule with conservation buffer) | "
                     f"{_v(v9['used'])} | stated only; computation not applicable |")
            continue
        res_ = ("no total requirement stated in the 10-K (searched); computed value used" if v9["stated"] is None else
                ("match" if v9["match"] else "MISMATCH - stated used, logged"))
        L.append(f"| {bi.ticker} | non-G-SIB | {_v(v9['scb'])} | {_v(v9['gsib_surcharge'])} | 0 | {_v(v9['computed'])} | "
                 f"{'-' if v9['stated'] is None else _v(v9['stated'])} | {_v(v9['used'])} | {res_} |")
    # ---------------------------------------------------------------- parallel run
    L.append("\n## 3. Parallel threshold run (6c) - production thresholds are NOT changed\n")
    L.append("Candidates: Graham capital buffer full score at 4pp; nonaccrual 0.4% / 2.0% (both models); ACL/nonaccrual 100% / 300% (both models); "
             "deposit funding 60% / 90%. Unchanged: ROTCE, ROA, stress coverage, worst credit-loss year. Per sub-item points, old -> candidate.\n")
    hdr = " | ".join(x[3].split(":")[0] for x in PAR_ITEMS)
    L.append(f"| Bank | {hdr} |")
    L.append("|---|" + "---|" * len(PAR_ITEMS))
    for (res, bi, d, bq, bp, gq, gp), (bq2, gq2) in zip(rows, cand):
        cells = []
        for model, cid, iid, _ in PAR_ITEMS:
            a = _item(bq if model == "buffett" else gq, cid, iid)
            b = _item(bq2 if model == "buffett" else gq2, cid, iid)
            cells.append(f"{_pts(a)} -> {_pts(b)}" if _pts(a) != _pts(b) else f"{_pts(a)} (same)")
        L.append(f"| {bi.ticker} | " + " | ".join(cells) + " |")
    L.append("\nSub-items: " + "; ".join(f"{i + 1}) {x[3]}" for i, x in enumerate(PAR_ITEMS)) + ".\n")
    L.append("### Totals and ranks: (a) current thresholds vs (b) all candidates together\n")
    L.append("| Bank | Buffett (a) | Buffett (b) | Change | Rank a -> b | Graham (a) | Graham (b) | Change | Rank a -> b | Flag (> 3 points) |")
    L.append("|---|---:|---:|---:|---|---:|---:|---:|---|---|")
    ba = {bi.ticker: bq.score for (_, bi, _, bq, *_ ) in rows}
    bb = {bi.ticker: q[0].score for (_, bi, *_), q in zip(rows, cand)}
    ga = {bi.ticker: gq.score for (_, bi, _, _, _, gq, _) in rows}
    gb = {bi.ticker: q[1].score for (_, bi, *_), q in zip(rows, cand)}
    rba, rbb, rga, rgb = _ranks(ba), _ranks(bb), _ranks(ga), _ranks(gb)
    moved = []
    for _, bi, *_ in rows:
        t = bi.ticker
        db, dg = bb[t] - ba[t], gb[t] - ga[t]
        fl = []
        if abs(db) > 3:
            fl.append(f"Buffett {db:+.1f}")
        if abs(dg) > 3:
            fl.append(f"Graham {dg:+.1f}")
        if fl:
            moved.append(f"{t} ({', '.join(fl)})")
        L.append(f"| {t} | {ba[t]:.1f} | {bb[t]:.1f} | {db:+.1f} | {rba[t]} -> {rbb[t]}{' *' if rba[t] != rbb[t] else ''} | {ga[t]:.1f} | "
                 f"{gb[t]:.1f} | {dg:+.1f} | {rga[t]} -> {rgb[t]}{' *' if rga[t] != rgb[t] else ''} | {'**' + ', '.join(fl) + '**' if fl else '-'} |")
    L.append("\n`*` = rank changed. Banks whose total moves by more than 3 points: " + ("; ".join(moved) or "none") + ".\n")
    chg_b = [t for t in ba if rba[t] != rbb[t]]
    chg_g = [t for t in ga if rga[t] != rgb[t]]
    L.append(f"Rank changes - Buffett: {', '.join(chg_b) or 'none'}; Graham: {', '.join(chg_g) or 'none'}. "
             f"Mean absolute change: Buffett {sum(abs(bb[t] - ba[t]) for t in ba) / len(ba):.2f}, Graham {sum(abs(gb[t] - ga[t]) for t in ga) / len(ga):.2f} points. "
             f"Spread (max - min) a -> b: Buffett {max(ba.values()) - min(ba.values()):.1f} -> {max(bb.values()) - min(bb.values()):.1f}; "
             f"Graham {max(ga.values()) - min(ga.values()):.1f} -> {max(gb.values()) - min(gb.values()):.1f}.\n")
    # ---------------------------------------------------------------- open issues
    L.append("## 4. Open issues\n")
    L.append((ROOT / "scripts" / "bank_rule_issues_v3.md").read_text(encoding="utf-8") if (ROOT / "scripts" / "bank_rule_issues_v3.md").exists()
             else "(scripts/bank_rule_issues_v3.md not written yet)")
    L.append("\n### Data problems by bank\n")
    for res, *_ in rows:
        L.append(f"- **{res['ticker']}**: " + ("; ".join(res["data_problems"]) if res["data_problems"] else "none detected"))
    (OUT / "summary_banks_v3.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _buy(p):
    b = p.get("buy_price")
    if not b:
        return "-"
    if b.get("state") == "computed":
        return f"{b['buy_price']:.2f}"
    return b.get("state", "-")


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    rbt.OUT = OUT  # write per-bank JSON into the new folder; earlier outputs stay untouched
    sec = SecClient()
    reg_all = load_regulatory()
    rows, cand, failures = [], [], []
    for t in rbt.BANKS:
        try:
            r = rbt.run_bank(sec, reg_all, t)
            if r is None:
                print(f"{t}: not scored")
                continue
            res, bi, d, bq, bp, gq, gp = r
            with thresholds_override(TH_CANDIDATE):
                sc2 = bk.score_bank(bi)
            cand.append((sc2["buffett_quality"], sc2["graham_quality"]))
            for name, m in (("buffett_quality", bq), ("graham_quality", gq)):
                if m.range_error:
                    failures.append((t, f"{name} range check failed: {m.range_error}"))
            rows.append(r)
            (OUT / f"{t}_candidate_thresholds.json").write_text(json.dumps(jsonable({
                "buffett_quality": model_json(sc2["buffett_quality"]), "graham_quality": model_json(sc2["graham_quality"]),
                "thresholds": TH_CANDIDATE}), indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if rows:
        build_summary(rows, cand, reg_all, failures)
    print(f"SEC requests this run: {sec.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])
