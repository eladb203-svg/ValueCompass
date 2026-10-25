"""K1 baseline harness (2026-10-20): runs the CURRENT runners unchanged and stores their per-company JSON.

Usage:  .venv/Scripts/python tests/golden/2026-10-20/make_golden.py [options] <raw_run_dir> [<golden_dir>]
Options:
  --as-of=YYYY-MM-DD   fix date.today() inside the runners (the baseline was made on 2026-10-20)
  --stub-yfinance      the EQR successor-price lookup (VMRK) finds no data, as in the baseline run (no network dependence); the router's provider industry
                       comes from scripts/provider_industry_2026-10-20.csv (K4b)
  --via-facts          code stage K2: every inputs object takes the detour provider output -> facts -> inputs (src/etl) before the engines run

* Each runner module is imported and its module-level OUT is redirected to <raw_run_dir>/<engine>/, then its own main() runs.
  Nothing under scripts/output*/ is written or changed. No DB, no AI. SEC / price data come from scripts/cache (request counts are printed).
* With <golden_dir>: the normalised JSON per company (date keys removed, keys sorted) and index.json (the digest) are written there.
* Not named test_*.py: pytest does not collect it.
"""
from __future__ import annotations

import datetime
import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

# engine -> (module, how to call main)
ENGINES = {
    "general": ("run_scoring_test", lambda m: m.main([])),
    "managed_care": ("run_managed_care", lambda m: m.main([])),
    "bank": ("run_bank_test_v4", lambda m: m.main([])),
    "insurance": ("run_insurance_final", lambda m: m.main()),
    "realestate": ("run_realestate_pricing_v7", lambda m: m.main()),
}
DROP_KEYS = {"as_of"}


def run_engine(engine: str, raw_dir: Path) -> str:
    modname, call = ENGINES[engine]
    mod = __import__(modname)
    out = raw_dir / engine
    out.mkdir(parents=True, exist_ok=True)
    mod.OUT = out
    if engine == "realestate":  # the v7 JSON carries no inputs: capture them from build_ri (harness-level wrapper, no source change)
        orig = mod.build_ri

        def capturing(sec, reg_all, t):
            ri, raw = orig(sec, reg_all, t)
            snap = {"fy": ri.fy, "end": ri.end, "f": ri.f, "reg": ri.reg, "tag_log": ri.tag_log, "price_current": ri.price_current,
                    "price_date": ri.price_date, "price_avg": ri.price_avg, "first_annual_report": ri.first_annual_report,
                    "asset_type": ri.asset_type, "noi_method": ri.noi_method, "flags": ri.flags, "data_problems": ri.data_problems}
            (out / f"{t}_inputs.json").write_text(json.dumps(snap, indent=1, sort_keys=True, default=str, ensure_ascii=False), encoding="utf-8")
            return ri, raw
        mod.build_ri = capturing
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            call(mod)
    except SystemExit as e:  # runners must not exit
        buf.write(f"\nSystemExit {e}\n")
    except Exception:  # noqa: BLE001
        buf.write("\n" + traceback.format_exc())
    (raw_dir / f"{engine}.log").write_text(buf.getvalue(), encoding="utf-8")
    return buf.getvalue()


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in DROP_KEYS}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


def companies(engine_dir: Path):
    for p in sorted(engine_dir.glob("*.json")):
        n = p.stem
        if n.endswith("_pricing") or n.endswith("_candidate_thresholds") or n.endswith("_inputs"):
            continue
        yield n, p


def normalise(engine: str, raw_dir: Path) -> dict:
    res = {}
    d = raw_dir / engine
    for t, p in companies(d):
        j = json.loads(p.read_text(encoding="utf-8"))
        pf = d / f"{t}_pricing.json"
        if pf.exists():  # insurance: pricing is a second file
            j["pricing_file"] = json.loads(pf.read_text(encoding="utf-8"))
        inf = d / f"{t}_inputs.json"
        if inf.exists():
            j["inputs"] = json.loads(inf.read_text(encoding="utf-8"))
        res[t] = strip(j)
    return res


def _pt(x):
    if isinstance(x, dict):
        return x.get("points") if x.get("points") is not None else x.get("state")
    return x


def digest(j: dict) -> dict:
    out = {"profile": j.get("profile"), "state": j.get("state")}
    pf = j.get("pricing_file") or {}
    for k in ("buffett", "graham"):
        q = j.get(f"{k}_quality") or {}
        p = j.get(f"{k}_price") or pf.get(f"{k}_price") or {}
        bp = p.get("buy_price") or {}
        out[k] = {
            "quality_score": q.get("score"), "quality_status": q.get("status"), "coverage": q.get("coverage"),
            "range": [q.get("range_min"), q.get("range_max")], "buy_price_allowed": q.get("buy_price_allowed"),
            "invalid_criteria": [c.get("id") for c in (q.get("invalid_criteria") or []) if isinstance(c, dict)] or q.get("invalid_criteria"),
            "value_state": p.get("state"), "value": p.get("fair_value") if p.get("fair_value") is not None else p.get("value"),
            "price_score": _pt(p.get("price_score")), "buy_price_state": bp.get("state"), "buy_price": bp.get("buy_price"),
            "criteria_items": {f"{c['id']}.{i['id']}": [i.get("state"), i.get("points")] for c in (q.get("criteria") or []) for i in c.get("items", [])},
            "price_flags": p.get("flags"),
        }
    out["flags"] = j.get("flags")
    out["n_data_problems"] = len(j.get("data_problems") or [])
    return out


class _Meta(type):
    def __instancecheck__(cls, o):
        return isinstance(o, datetime.date)


def fixed_date(iso: str):
    y, m, d = (int(x) for x in iso.split("-"))

    class FD(datetime.date, metaclass=_Meta):
        @classmethod
        def today(cls):
            return datetime.date(y, m, d)
    return FD


def patch_date(iso: str):
    fd = fixed_date(iso)
    for name in ("run_scoring_test", "run_managed_care", "run_bank_test", "run_insurance_test", "run_realestate_v5", "run_realestate_pricing_v7"):
        __import__(name).date = fd


def patch_yfinance():
    import pandas as pd
    import types

    class _T:
        def __init__(self, *a, **k):
            pass

        def history(self, *a, **k):
            return pd.DataFrame({"Close": []})
    sys.modules["yfinance"] = types.SimpleNamespace(Ticker=_T)
    from src.providers import industry_provider  # the provider industry (router tier 2) comes from a fixed file, not the network
    industry_provider.use_fixed(ROOT / "scripts" / "provider_industry_2026-10-20.csv")


def patch_via_facts():
    from src.etl.to_inputs import via_facts
    import run_bank_test as rbt
    import run_insurance_test_v3 as r3
    import run_managed_care as rmc
    import run_realestate_v5 as v5
    import run_scoring_test as rst
    rst.CompanyInputs = via_facts("general", rst.CompanyInputs)
    rmc.CompanyInputs = via_facts("general", rmc.CompanyInputs)
    rbt.BankInputs = via_facts("bank", rbt.BankInputs)
    r3.InsuranceInputs = via_facts("insurance", r3.InsuranceInputs)
    v5.REInputs = via_facts("realestate", v5.REInputs)


DB_REPORT: list = []


def patch_via_db():
    """K6a: provider output -> facts -> database (target valuecompass-test; VC_DB_TARGET) -> facts -> inputs. The write statistics and the cache-vs-db differences go to DB_REPORT."""
    from src.etl.db_io import FactSetDb
    from src.etl.to_inputs import via_db
    import run_bank_test as rbt
    import run_insurance_test_v3 as r3
    import run_managed_care as rmc
    import run_realestate_v5 as v5
    import run_scoring_test as rst
    sink = FactSetDb()
    rst.CompanyInputs = via_db("general", rst.CompanyInputs, sink, DB_REPORT)
    rmc.CompanyInputs = via_db("general", rmc.CompanyInputs, sink, DB_REPORT)
    rbt.BankInputs = via_db("bank", rbt.BankInputs, sink, DB_REPORT)
    r3.InsuranceInputs = via_db("insurance", r3.InsuranceInputs, sink, DB_REPORT)
    v5.REInputs = via_db("realestate", v5.REInputs, sink, DB_REPORT)


def main(argv):
    db_report = None
    opts = [a for a in argv if a.startswith("--")]
    argv = [a for a in argv if not a.startswith("--")]
    for o in opts:
        if o.startswith("--as-of="):
            patch_date(o.split("=", 1)[1])
        elif o == "--stub-yfinance":
            patch_yfinance()
        elif o == "--via-facts":
            patch_via_facts()
        elif o == "--via-db":
            patch_via_db()
        elif o.startswith("--db-report="):
            db_report = o.split("=", 1)[1]
        else:
            raise SystemExit(f"unknown option {o}")
    raw_dir = Path(argv[0]).resolve()
    golden = Path(argv[1]).resolve() if len(argv) > 1 else None
    raw_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for eng in ENGINES:
        log = run_engine(eng, raw_dir)
        summary[eng] = [ln for ln in log.splitlines() if "SEC requests" in ln or "FAILED" in ln or "Traceback" in ln]
        print(eng, summary[eng] or "ok")
    if db_report:
        Path(db_report).write_text(json.dumps(DB_REPORT, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        print("db report:", len(DB_REPORT), "inputs objects")
    if golden:
        idx = {}
        for eng in ENGINES:
            norm = normalise(eng, raw_dir)
            (golden / eng).mkdir(parents=True, exist_ok=True)
            for t, j in norm.items():
                (golden / eng / f"{t}.json").write_text(json.dumps(j, indent=1, sort_keys=True, ensure_ascii=False, default=str), encoding="utf-8")
            idx[eng] = {t: digest(j) for t, j in norm.items()}
        (golden / "index.json").write_text(json.dumps(idx, indent=1, sort_keys=True, ensure_ascii=False, default=str), encoding="utf-8")
        print("golden written:", {e: len(v) for e, v in idx.items()})


if __name__ == "__main__":
    main(sys.argv[1:])
