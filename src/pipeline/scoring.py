"""The score job (K6c, K6 spec 2.7): the engines run on the facts and extraction rows of the DATABASE, with the approved AI answers and AI extraction items of the database, and the result is
written to ``score_runs`` / ``score_details`` / ``valuations`` / ``company_score_summary``.

The engines are the ones the runners in ``scripts/`` drive (the golden harness uses the same ones): this module narrows a runner to one company, points its inputs classes at the database
(read only: the facts of K6b are not rewritten) and exports the approved AI answers / extraction items of the company to the two temporary files the engines read (``VC_AI_STORE``,
``VC_AI_EXT_STORE``). A company that a runner has no configuration for (a bank's required CET1, a REIT's asset type) is reported as ``needs_config``: it stays ``data_loaded``.
The result JSON is also kept in ``results_dir/<engine>/<ticker>.json`` (the same shape as the golden files): D1 / D2 and the peer groups read it.

Prices: the runners read the price history cache of ``src/providers/prices`` (the daily price refresh is K6d), so a run is priced at the last cached close.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "scripts" / "output_k6c" / "results"
GOLDEN_DIR = ROOT / "tests" / "golden" / "2026-10-20"
ENGINE_KEYS = ("general", "managed_care", "bank", "insurance", "realestate")


@dataclass
class ScoreOutcome:
    ticker: str
    status: str                       # scored | needs_config | not_scored | failed
    engine: Optional[str] = None
    result: Optional[dict] = None
    run_id: Optional[int] = None
    write: Optional[str] = None       # inserted | unchanged
    detail: str = ""
    ai_pending: int = 0
    notes: list = field(default_factory=list)


def _paths() -> None:
    for p in (str(ROOT / "scripts"), str(ROOT), str(GOLDEN_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


def seed_results(results_dir: Path = RESULTS_DIR) -> int:
    """The peer-group universe: the 54 golden results are copied once; a live score overwrites its company."""
    n = 0
    for p in GOLDEN_DIR.glob("*/*.json"):
        if p.name == "index.json":
            continue
        dst = results_dir / p.parent.name / p.name
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
            n += 1
    return n


def runner_engine(profile: str, ticker: str) -> str:
    _paths()
    import run_managed_care as rmc
    if profile in ("STANDARD", "TECH_ASSET_LIGHT"):
        return "managed_care" if ticker in rmc.COMPANIES else "general"
    return {"BANK": "bank", "INSURANCE": "insurance", "INCOME_REAL_ESTATE": "realestate"}[profile]


def configured(engine: str, ticker: str) -> bool:
    """Does the runner have the per-company configuration it needs?"""
    _paths()
    if engine == "bank":
        import run_bank_test as rbt
        return ticker in rbt.BANKS
    if engine == "insurance":
        import run_insurance_final as rif
        return ticker in rif.COMPANIES
    if engine == "realestate":
        import run_realestate_pricing_v7 as v7
        return ticker in v7.T
    return True


def patch_inputs_from_db(sink) -> None:
    """The runners' inputs classes read the database (read only)."""
    from src.etl.to_inputs import via_db
    _paths()
    import run_bank_test as rbt
    import run_insurance_test_v3 as r3
    import run_managed_care as rmc
    import run_realestate_v5 as v5
    import run_scoring_test as rst
    if getattr(rst.CompanyInputs, "_from_db", False):
        return
    for mod, name, eng in ((rst, "CompanyInputs", "general"), (rmc, "CompanyInputs", "general"), (rbt, "BankInputs", "bank"), (r3, "InsuranceInputs", "insurance"), (v5, "REInputs", "realestate")):
        wrapped = via_db(eng, getattr(mod, name), sink, None, write=False)
        wrapped._from_db = True
        setattr(mod, name, wrapped)


def run_runner(engine: str, ticker: str, raw_dir: Path) -> str:
    """Run one runner for one company; its JSON files land in raw_dir/<engine>/. -> the runner's log."""
    _paths()
    import make_golden as MG
    import run_bank_test as rbt
    import run_insurance_final as rif
    import run_managed_care as rmc
    import run_realestate_pricing_v7 as v7
    import run_scoring_test as rst
    saved = (rst.COMPANIES, rmc.COMPANIES, rbt.BANKS, rif.COMPANIES, v7.T)
    if hasattr(v7, "_k6c_orig_build_ri"):                       # the golden harness wraps build_ri on every run: start from the original, or the wrappers stack and write to old directories
        v7.build_ri = v7._k6c_orig_build_ri
    else:
        v7._k6c_orig_build_ri = v7.build_ri
    try:
        rst.COMPANIES = [(ticker, "K6c score job")]
        rmc.COMPANIES = [ticker] if engine == "managed_care" else []
        rbt.BANKS = {ticker: saved[2][ticker]} if engine == "bank" else {}
        rif.COMPANIES = [ticker] if engine == "insurance" else []
        v7.T = [ticker] if engine == "realestate" else []
        return MG.run_engine(engine, raw_dir)
    finally:
        rst.COMPANIES, rmc.COMPANIES, rbt.BANKS, rif.COMPANIES, v7.T = saved


def export_ai(ai_store, item_store, ticker: str, tmp: Path) -> dict:
    """Approved AI answers and AI extraction items of the company -> the two files the engines read. -> the environment to set."""
    env = {}
    rows = sorted(ai_store.rows(ticker), key=lambda r: (str(r.get("created_at")), r["question_id"]))
    if rows:
        (tmp / "assessments.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) for r in rows) + "\n", encoding="utf-8")
        env["VC_AI_STORE"] = str(tmp / "assessments.jsonl")
    n = item_store.export_jsonl(tmp / "items.jsonl", [ticker])
    if n:
        env["VC_AI_EXT_STORE"] = str(tmp / "items.jsonl")
    return env


def pending_ai(result: dict) -> int:
    return sum(1 for k in ("buffett_quality", "graham_quality") for c in (result.get(k) or {}).get("criteria", []) for i in c["items"] if i.get("state") == "ai_pending")


def score_company(ticker: str, profile: str, sink, ai_store, item_store, results_dir: Path = RESULTS_DIR, use_ai: bool = True) -> ScoreOutcome:
    """Run the engines for ``ticker`` on the database. The caller writes the result with ``ScoreRepository``."""
    engine = runner_engine(profile, ticker)
    if not configured(engine, ticker):
        return ScoreOutcome(ticker, "needs_config", engine, detail=f"the {engine} runner has no configuration for {ticker} (e.g. required CET1 / asset type): it stays data_loaded")
    patch_inputs_from_db(sink)
    tmp = Path(tempfile.mkdtemp(prefix=f"k6c_{ticker}_"))
    env_before = {k: os.environ.get(k) for k in ("VC_AI_STORE", "VC_AI_EXT_STORE", "VC_AI_EXT_UNAPPROVED")}
    try:
        for k in env_before:
            os.environ.pop(k, None)
        if use_ai:
            os.environ.update(export_ai(ai_store, item_store, ticker, tmp))
        log = run_runner(engine, ticker, tmp / "raw")
        _paths()
        import make_golden as MG
        res = MG.normalise(engine, tmp / "raw").get(ticker)
        if res is None:
            return ScoreOutcome(ticker, "failed", engine, detail=log[-600:])
        if res.get("state") not in (None, "scored") and not res.get("buffett_quality"):
            return ScoreOutcome(ticker, "not_scored", engine, result=res, detail=str(res.get("reason") or res.get("state")))
        out = results_dir / engine / f"{ticker}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return ScoreOutcome(ticker, "scored", engine, result=res, ai_pending=pending_ai(res))
    finally:
        for k, v in env_before.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
