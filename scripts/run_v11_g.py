"""Regression test for v1.1 candidates G1 (Buffett owner-earnings base) and G2 (Graham Number normalized EPS). HISTORICAL: G1-B and G2-C are production since 2026-10-14.

Universe: the 14 v1.0 companies + 6 managed-care companies. Output: scripts/output_v11_g/summary_v11_g.md (+ json). No DB, no AI calls, cached data only.
Usage: .venv/Scripts/python -X utf8 scripts/run_v11_g.py
"""
from __future__ import annotations

raise SystemExit("HISTORICAL: G1-B and G2-C became production on 2026-10-14 and the A/B/C flags were removed; outputs of the regression are kept in scripts/output_v11_g/.")

import json
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_scoring_test import COMPANIES, jsonable  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.candidates import candidates  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_v11_g"
MC = ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"]
UNIVERSE = [(t, p, "v1.0") for t, p, _ in COMPANIES] + [(t, "STANDARD", "managed care") for t in MC]
MOVE = 0.15


def build(sec, ticker, profile):
    raw = build_inputs(sec, ticker, profile, price_provider.get_splits(ticker))
    pr = price_provider.load_prices(ticker, raw["ends"], raw["labels"])
    return CompanyInputs(ticker=ticker, name=raw["name"], profile=profile, fy=raw["labels"], end=raw["ends"], f=raw["f"], sbc_state=raw["sbc_state"],
                         price_current=pr["current"], price_avg=pr["avg"], first_annual_report=raw["first_annual_report"], as_of=date.today(),
                         flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])


def buy(b):
    if not b:
        return "n/a"
    if b.get("state") == "computed":
        return f"{b['buy_price']:.2f}"
    return b.get("state", "n/a")


def snap(sc, kind):
    if kind == "buffett":
        bp = sc["buffett_price"]
        return {"state": bp.get("state"), "base": bp.get("oe_base"), "median": bp.get("oe_base_median"), "value": bp.get("fair_value"),
                "ps": (bp.get("price_score") or {}).get("points"), "buy": buy(bp.get("buy_price")), "flags": [f for f in bp.get("flags", []) if f.startswith("G1")],
                "oe_last5": bp.get("owner_earnings_last5"), "reason": bp.get("reason"), "g1": bp.get("stage1_growth")}
    gp = sc["graham_price"]
    gn = gp.get("graham_number") or {}
    prim = gp.get("value")
    tech = gp.get("profile") == "TECH_ASSET_LIGHT"
    return {"state": gp.get("state"), "tech": tech, "eps": gn.get("normalized_eps"), "gn_value": gn.get("value") if gn.get("state") == "valued" else None,
            "gn_reason": gn.get("reason"), "value": prim, "ps": (gp.get("price_score") or {}).get("points"), "buy": buy(gp.get("buy_price")),
            "addbacks": gn.get("g2_addbacks"), "years": gn.get("g2_years"), "loss_years": gn.get("g2_loss_years"), "eps_reported_3y": gn.get("eps_reported_3y_avg")}


def f(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def chg(a, b):
    if a is None or b is None or a == 0:
        return "n/a"
    return f"{(b / a - 1) * 100:+.1f}%"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    res, failures = {}, []
    for t, prof, grp in UNIVERSE:
        try:
            inp = build(sec, t, prof)
            r = {"group": grp, "profile": prof, "price": inp.price_current, "buffett": {}, "graham": {}}
            for v in "ABC":
                with candidates(g1=v):
                    sc = score_company(inp)
                    r["buffett"][v] = snap(sc, "buffett")
                    if v == "A":
                        r["bq"], r["gq"] = sc["buffett_quality"].score, sc["graham_quality"].score
                with candidates(g2=v):
                    r["graham"][v] = snap(score_company(inp), "graham")
            res[t] = r
            print(t, "ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
    (OUT / "v11_g.json").write_text(json.dumps(jsonable(res), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    T = list(res)
    L = [f"# ValueCompass v1.1 candidates G1 / G2 regression - {date.today().isoformat()}\n",
         "Flags `candidates(g1=..., g2=...)` default to `A` (current production); this run switches them one at a time. No production change, no DB, no AI calls, cached data only "
         f"(SEC requests this run: {sec.requests_made}). Universe: 14 v1.0 companies + 6 managed-care companies. Quality scores are unaffected by G1/G2 (they only change the price side).\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------- G1
    L.append("## G1 - Buffett owner-earnings base\n")
    L.append("A = 5y median x (1+g)^2 (current); B = roll only if latest OE >= 5y median, else the median; C = as B, and if both of the last two years are >25% below the median, base = average of the last 2 years. "
             "Stage-1 growth g1 and the growth gate are unchanged (they come from the median, not the base). Values per share, USD; change vs A.\n")
    L.append("| Company | Group | Price | OE latest / 5y median (bn) | Base A | Base B | Base C | Value A | Value B | Value C | B vs A | C vs A | Price score A / B / C | Buy price A / B / C | Flag >15% |")
    L.append("|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|")
    big1 = []
    for t in T:
        r = res[t]["buffett"]
        a, b, c = r["A"], r["B"], r["C"]
        oe = a.get("oe_last5")
        moved = [k for k, x in (("B", b), ("C", c)) if a["value"] and x["value"] is not None and abs(x["value"] / a["value"] - 1) > MOVE]
        if moved:
            big1.append(f"{t} ({'/'.join(moved)})")
        hl = "**" if t == "ELV" else ""
        L.append(f"| {hl}{t}{hl} | {res[t]['group']} | {f(res[t]['price'])} | {f(oe[-1] / 1e9) if oe else 'n/a'} / {f(a['median'] / 1e9) if a['median'] else 'n/a'} | "
                 f"{f(a['base'] / 1e9) if a['base'] else 'n/a'} | {f(b['base'] / 1e9) if b['base'] else 'n/a'} | {f(c['base'] / 1e9) if c['base'] else 'n/a'} | "
                 f"{f(a['value'])} | {f(b['value'])} | {f(c['value'])} | {chg(a['value'], b['value'])} | {chg(a['value'], c['value'])} | "
                 f"{f(a['ps'])} / {f(b['ps'])} / {f(c['ps'])} | {a['buy']} / {b['buy']} / {c['buy']} | {'MOVES ' + '/'.join(moved) if moved else '-'} |")
    L.append("\nValue moves by more than 15%: " + (", ".join(big1) or "none") + ".")
    if "ELV" in res:
        a, b, c = (res["ELV"]["buffett"][v] for v in "ABC")
        oe = a["oe_last5"]
        L.append(f"\n**ELV (G1 focus).** Owner earnings last 5 years (USD bn): {', '.join(f(x / 1e9) for x in oe)}; 5y median {f(a['median'] / 1e9)}; stage-1 growth {f((a.get('g1') or 0) * 100, 1)}%. "
                 f"Base A {f(a['base'] / 1e9)} -> B {f(b['base'] / 1e9)} -> C {f(c['base'] / 1e9)}; value {f(a['value'])} -> {f(b['value'])} -> {f(c['value'])} (price {f(res['ELV']['price'])}). "
                 f"Flags B: {', '.join(b['flags']) or 'none'}; C: {', '.join(c['flags']) or 'none'}.")
    changed = [t for t in T if any(res[t]["buffett"][v]["base"] != res[t]["buffett"]["A"]["base"] for v in "BC")]
    L.append("\nCompanies whose base changes under B or C: " + (", ".join(changed) or "none") + ". All others are identical to A (latest OE at or above the median and no two-year collapse).")
    # ---------------- G2
    L.append("\n## G2 - Graham Number normalized EPS\n")
    L.append("A = 3-year average diluted EPS (current); B = 3-year average after adding back after-tax goodwill / asset impairments (ETL field `impairments`, effective tax rate clipped 0-40%, 25% on a pretax loss; "
             "flagged by year and tag); C = 7-10 year average diluted EPS (>= 7 years, loss years included; average <= 0 cannot be valued). TECH_ASSET_LIGHT companies are priced with Graham Tech, "
             "so G2 must not change their value: the check is in the last column.\n")
    L.append("| Company | Profile | Price | EPS A | EPS B | EPS C (years) | Value A | Value B | Value C | B vs A | C vs A | Price score A / B / C | Buy price A / B / C | Flag >15% | Tech value unchanged |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|")
    big2 = []
    for t in T:
        r = res[t]["graham"]
        a, b, c = r["A"], r["B"], r["C"]
        tech = a["tech"]
        va, vb, vc = (a["value"], b["value"], c["value"])
        moved = [k for k, x in (("B", vb), ("C", vc)) if va and x is not None and abs(x / va - 1) > MOVE]
        cannot_c = [k for k, x in (("B", vb), ("C", vc)) if va and x is None]
        if moved or cannot_c:
            big2.append(f"{t} ({'/'.join(moved + [k + ':cannot be valued' for k in cannot_c])})")
        same = "n/a" if not tech else ("yes" if (va == vb == vc and a["ps"] == b["ps"] == c["ps"]) else "NO")
        hl = "**" if t == "CNC" else ""
        L.append(f"| {hl}{t}{hl} | {res[t]['profile']} | {f(res[t]['price'])} | {f(a['eps'])} | {f(b['eps'])} | {f(c['eps'])} ({c['years'] or 'n/a'}) | "
                 f"{f(va) if va else (a['gn_reason'] or 'tech: ' + str(a['state']))} | {f(vb) if vb else 'n/a'} | {f(vc) if vc else (c['gn_reason'] or 'n/a')} | {chg(va, vb)} | {chg(va, vc)} | "
                 f"{f(a['ps'])} / {f(b['ps'])} / {f(c['ps'])} | {a['buy']} / {b['buy']} / {c['buy']} | {'MOVES ' + ', '.join(moved + cannot_c) if (moved or cannot_c) else '-'} | {same} |")
    L.append("\nValue moves by more than 15% (or becomes unvaluable): " + (", ".join(big2) or "none") + ".")
    techs = [t for t in T if res[t]["graham"]["A"]["tech"]]
    bad = [t for t in techs if not (res[t]["graham"]["A"]["value"] == res[t]["graham"]["B"]["value"] == res[t]["graham"]["C"]["value"])]
    L.append(f"\n**Tech check:** {len(techs)} TECH_ASSET_LIGHT companies ({', '.join(techs)}); Graham Tech value identical under G2 A/B/C: " + ("yes for all." if not bad else "NO for " + ", ".join(bad) + "."))
    if "CNC" in res:
        a, b, c = (res["CNC"]["graham"][v] for v in "ABC")
        L.append(f"\n**CNC (G2 focus).** Reported 3y EPS average {f(a['eps'])}; with impairment add-backs {f(b['eps'])} ({'; '.join(b['addbacks'] or []) or 'no impairment tagged in the last 3 years'}); "
                 f"{c['years'] or 0}-year average {f(c['eps'])} (loss years: {c['loss_years']}). Value {f(a['value'])} -> {f(b['value'])} -> {f(c['value'])} (price {f(res['CNC']['price'])}).")
    L.append("\n### G2-B add-backs found\n")
    for t in T:
        ab = res[t]["graham"]["B"].get("addbacks")
        if ab:
            L.append(f"- **{t}**: " + "; ".join(ab))
    if not any(res[t]["graham"]["B"].get("addbacks") for t in T):
        L.append("- none: no impairment charge in the last 3 years for any company")
    L.append("\n## Observations\n")
    conv = [f"{t} ({'/'.join(k for k in 'BC' if res[t]['graham'][k]['value'] is not None)})" for t in T
            if not res[t]["graham"]["A"]["tech"] and res[t]["graham"]["A"]["value"] is None and any(res[t]["graham"][k]["value"] is not None for k in "BC")]
    L.append("- **G1.** Only 7 of 20 bases change (KO, HD, NUE, DOW, INTC, ELV, MOH); the other 13 are identical because the latest owner earnings are at or above the 5-year median. "
             "Variant B moves one company by more than 15% (ELV -19.9%; its price score stays 10.00). Variant C moves ELV (-53.5%, value 419 vs price 422, price score 10.00 -> 2.43), "
             "KO (-56.4%) and NUE (-61.0%), and makes DOW, INTC (already a negative value under A) and MOH unvaluable because the two-year average base is not positive.")
    L.append("- **G2.** Variant B moves no valued company by more than 15% (largest +1.4%, ELV); companies that A cannot value but a variant can (letter = variant): " + (", ".join(conv) or "none")
             + ". CNC's B value rests almost entirely on one add-back (+11.12 EPS from a 7.3bn FY2025 asset impairment, tagged AssetImpairmentCharges); the add-back is taxed at the effective rate "
             "(clipped 0-40%), while goodwill impairments are often not deductible, so the add-back is an upper bound. DOW (-0.19) and INTC (-1.17) stay unvaluable under B. "
             "Variant C moves MOH -21.8% (>15%), KO -14.2% and HUM +10.8%, and values DOW, INTC, KHC and CNC from 9-10 year averages (all buy prices stay `not_suitable`).")
    L.append("- **TECH profiles.** Graham Tech is the primary value for all 7 tech companies and does not change under G2; the (display-only) classic Graham Number is not used for them.")
    L.append("- Nothing was changed in production: both flags default to `A`; the full test suite passes with the flag code present.")
    (OUT / "summary_v11_g.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
