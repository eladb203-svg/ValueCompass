"""Share-scale guard audit over all 44 companies (14 v1.0 + 12 bank + 6 managed care + 12 insurance). Writes scripts/output_insurance_final/share_guard_audit.json.

Usage:  .venv/Scripts/python -X utf8 scripts/audit_share_guard.py
Builds each company's series through the ETL (SEC cache) and lists every share-count value the guard rescaled or set missing.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_insurance_test as ri  # noqa: E402
import run_scoring_test as rs  # noqa: E402
from run_bank_test import BANKS  # noqa: E402
from run_managed_care import COMPANIES as MC  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.bank_facts import build_bank_series  # noqa: E402
from src.providers.insurance_facts import build_insurance_series  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402

OUT = ROOT / "scripts" / "output_insurance_final"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    res = {}
    jobs = [("v1.0", t, lambda t=t, p=p: build_inputs(sec, t, p, price_provider.get_splits(t))) for t, p, _ in rs.COMPANIES]
    jobs += [("bank", t, lambda t=t: build_bank_series(sec, t, price_provider.get_splits(t))) for t in BANKS]
    jobs += [("managed_care", t, lambda t=t: build_inputs(sec, t, "STANDARD", price_provider.get_splits(t))) for t in MC]
    jobs += [("insurance", t, lambda t=t: build_insurance_series(sec, t, price_provider.get_splits(t))) for t in ri.COMPANIES]
    for grp, t, fn in jobs:
        try:
            raw = fn()
            ev = [p for p in raw["problems"] if p.startswith("share_scale_guard")]
            res[f"{grp}:{t}"] = {"group": grp, "ticker": t, "fired": bool(ev), "events": ev}
            print(f"{grp:13s} {t:5s} {'FIRED: ' + ev[0][:200] if ev else 'ok'}")
        except Exception as e:  # noqa: BLE001
            res[f"{grp}:{t}"] = {"group": grp, "ticker": t, "error": f"{type(e).__name__}: {e}"}
            print(f"{grp} {t}: ERROR {type(e).__name__}: {e}")
            traceback.print_exc()
    (OUT / "share_guard_audit.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
