"""File store for AI answers (until code stage K6): ``scripts/ai_store/assessments.jsonl``, one JSON object per line, same structure as ``ai_assessments``.

Unique key (ticker, fiscal_year, question_id, prompt_version): an existing answer is never asked again. Repeat runs (stability) go to ``assessments_repeat.jsonl``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
STORE_DIR = ROOT / "scripts" / "ai_store"


class AssessmentStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else STORE_DIR / "assessments.jsonl"
        self._rows: dict = {}
        if self.path.exists():
            for ln in self.path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    self._rows[self.key(r)] = r

    @staticmethod
    def key(r: dict) -> tuple:
        return (r["ticker"], int(r["fiscal_year"]), r["question_id"], str(r["prompt_version"]))

    def get(self, ticker: str, fiscal_year: int, question_id: str, prompt_version) -> Optional[dict]:
        return self._rows.get((ticker, int(fiscal_year), question_id, str(prompt_version)))

    def put(self, row: dict) -> dict:
        row = {**row, "created_at": row.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._rows[self.key(row)] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def rows(self) -> list:
        return list(self._rows.values())

    def answers_for(self, ticker: str, fiscal_year: int) -> dict:
        """skill id -> the dict the engines read (``inp.ai_answers``)."""
        out = {}
        for (t, fy, q, v), r in self._rows.items():
            if t == ticker and fy == int(fiscal_year):
                out[q] = {"state": r["state"], "answer": r["answer"], "version": int(v) if str(v).isdigit() else v, "flags": r.get("evidence", {}).get("flags", [])}
        return out
