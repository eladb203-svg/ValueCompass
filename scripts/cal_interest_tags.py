"""Owner decision 2026-11-05 (item 3): the REIT leverage inputs (interest expense, D&A, debt, cash) of MAC, BDN, HPP as the provider finds them now. Reads cached SEC facts; no model, no DB write.
Usage: python scripts/cal_interest_tags.py [TICKER ...]"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
from src.providers.realestate_facts import build_realestate_series
from src.providers.sec_companyfacts import SecClient
sec = SecClient()
for t in (sys.argv[1:] or ["MAC", "BDN", "HPP"]):
    try:
        raw = build_realestate_series(sec, t, [])
    except Exception as e:  # noqa: BLE001
        print(t, "FAILED", type(e).__name__, str(e)[:160]); continue
    f = raw["f"]
    print("==", t, raw["labels"][-3:])
    for k in ("interest_expense", "da_total", "re_depreciation", "gains_sale", "debt_total", "cash", "net_income"):
        if k in f: print(f"   {k:17} last3={f[k][-3:]}  tag={ (raw['tag_log'].get(k, {}).get(raw['labels'][-1]) or {}).get('tag') }")
