"""Code stage K5a: attach stored AI answers to an engine inputs object. A no-op unless the environment variable VC_AI_STORE names an assessments .jsonl file,
so every normal / golden run is unchanged."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.ai.store import AssessmentStore  # noqa: E402
from src.scoring.ext_items import attach_ext  # noqa: E402


def attach_ai(inp, ticker):
    path = os.environ.get("VC_AI_STORE")
    if path:
        inp.ai_answers = AssessmentStore(Path(path)).answers_for(ticker, int(inp.fy[-1][2:]))
    kind = {"BankInputs": "bank", "InsuranceInputs": "insurance", "REInputs": "realestate"}.get(type(inp).__name__)
    if kind:
        attach_ext(inp, ticker, kind)       # no-op unless VC_AI_EXT_STORE is set (code stage K5b)
    return inp
