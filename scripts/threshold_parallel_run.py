"""REFERENCE ONLY (section 6c parallel run, rejected 2026-10-13). Not part of the production path.

The candidate thresholds live here; production thresholds are ``src.scoring.bank.TH``.
"""
from contextlib import contextmanager

from src.scoring import bank as bk

TH_CANDIDATE = {
    "graham_buffer": [(0.0, 0), (4.0, 8)],
    "nonaccrual_buffett": [(0.004, 1), (0.02, 0)],
    "nonaccrual_graham": [(0.004, 3), (0.02, 0)],
    "acl_buffett": [(1.0, 0), (3.0, 1)],
    "acl_graham": [(1.0, 0), (3.0, 4)],
    "deposit_funding": [(0.60, 0), (0.90, 2)],
}


@contextmanager
def thresholds_override(cand: dict):
    saved = dict(bk.TH)
    bk.TH.update(cand)
    try:
        yield
    finally:
        bk.TH.clear()
        bk.TH.update(saved)
