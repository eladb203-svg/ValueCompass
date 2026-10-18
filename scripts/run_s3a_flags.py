"""S3a: borderline-assignment flags over the bank (12), insurance (12) and managed-care (6) samples (cached data). Writes scripts/output_realestate_v2/s3a_other_profiles.md."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_insurance_test as ri_  # noqa: E402
import run_managed_care as mc  # noqa: E402
from run_bank_test import BANKS  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.bank_facts import build_bank_series, load_regulatory  # noqa: E402
from src.providers.insurance_facts import build_insurance_series  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.bank import bank_path  # noqa: E402
from src.scoring.insurance import INSURANCE_TEST  # noqa: E402
from src.scoring.profile_flags import borderline_flag  # noqa: E402

OUT = ROOT / "scripts" / "output_realestate_v2"


def pc(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    L = ["| Sample | Company | Test | Value | Threshold | Distance | Borderline |", "|---|---|---|---:|---:|---:|---|"]
    flagged = []
    try:
        reg_all = load_regulatory()
    except Exception:  # noqa: BLE001
        reg_all = {}
    for t in BANKS:
        raw = build_bank_series(sec, t, price_provider.get_splits(t))
        f = raw["f"]
        reg = reg_all.get(t, {})
        assets, equity, deposits, loans = f["assets"][-1], f["equity"][-1], f["deposits"][-1], f["loans"][-1]
        if loans is None and "loans_2025" in reg:
            loans = reg["loans_2025"]["value"] * 1e6
        liab = None if (assets is None or equity is None) else assets - equity
        lcr = reg.get("lcr_q4_average", {}).get("value")
        p = bank_path(raw["sic"], deposits, liab, loans, assets, "cet1_ratio_standardized" in reg or "cet1_ratio_advanced" in reg, isinstance(lcr, float))
        for k, th in (("deposits_to_liabilities", 0.5), ("loans_to_assets", 0.3)):
            b = k in p["borderline_tests"]
            L.append(f"| bank | {t} | {k} (path {p['path']}) | {pc(p[k])} | {pc(th)} | {'n/a' if p[k] is None else format((p[k] - th) * 100, '+.1f') + 'pp'} | {'**YES**' if b else '-'} |")
            if b:
                flagged.append(f"bank {t} ({k} {pc(p[k])} vs {pc(th)}, path {p['path']})")
    for t in ri_.COMPANIES:
        raw = build_insurance_series(sec, t, price_provider.get_splits(t))
        ii = type("II", (), {})()
        prof = ri_.profile_check(raw, ii)
        fl = borderline_flag({"insurance_liabilities_to_liabilities": (prof["ratio"], INSURANCE_TEST)})
        b = fl["borderline_assignment"]
        L.append(f"| insurance | {t} | insurance liabilities / total liabilities | {pc(prof['ratio'])} | {pc(INSURANCE_TEST)} | {'n/a' if prof['ratio'] is None else format((prof['ratio'] - INSURANCE_TEST) * 100, '+.1f') + 'pp'} | {'**YES**' if b else '-'} |")
        if b:
            flagged.append(f"insurance {t} ({pc(prof['ratio'])} vs {pc(INSURANCE_TEST)})")
    for t in mc.COMPANIES:
        raw = build_inputs(sec, t, "STANDARD", price_provider.get_splits(t))
        facts = sec.companyfacts(raw["cik"])
        inp = type("I", (), {})()
        inp.end = raw["ends"]
        prof = mc.profile_check(facts, inp)
        fl = borderline_flag({"insurance_liabilities_to_liabilities": (prof["ratio"], 0.5)})
        b = fl["borderline_assignment"]
        L.append(f"| managed care | {t} | insurance liabilities / total liabilities | {pc(prof['ratio'])} | 50.0% | {'n/a' if prof['ratio'] is None else format((prof['ratio'] - 0.5) * 100, '+.1f') + 'pp'} | {'**YES**' if b else '-'} |")
        if b:
            flagged.append(f"managed care {t} ({pc(prof['ratio'])} vs 50.0%)")
    L.append("\nFlagged (within 5pp of a threshold): " + ("; ".join(flagged) if flagged else "none") + ". The assignment itself is unchanged (the code follows the threshold); the flagged companies enter the admin review list.")
    (OUT / "s3a_other_profiles.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[-1:]))
    print("SEC requests:", sec.requests_made)


if __name__ == "__main__":
    main()
