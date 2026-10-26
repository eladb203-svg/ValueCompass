"""Builders shared by the runner commands (``scripts/vc.py``) and the scheduler: the pipeline (RESOLVE ... WRITE) and the queue runner. The database is the one ``VC_DB_TARGET`` names."""
from __future__ import annotations

from src.db import get_supabase_client
from src.pipeline.runner import Pipeline
from src.pipeline.sec_source import PipelineSec


def make_pipeline(dry_run: bool = False, offline: bool = False, client=None) -> Pipeline:
    sec = PipelineSec(max_age_hours=float("inf") if offline else 20.0)
    return Pipeline(sec, client=client, dry_run=dry_run)


def make_runner(budget: int = 0, rpm: int = 12, rpd: int = 450, client=None):
    """The queue runner. ``budget`` = most model request attempts of this run (0: data tasks only); ``rpd`` is the shared daily cap of the one Google project."""
    from src.pipeline.queue_runner import QueueRunner
    client = client or get_supabase_client()
    gemini = None
    if budget > 0:
        from src.ai.client import GeminiClient, RateLimiter
        gemini = GeminiClient(limiter=RateLimiter(rpm=rpm, rpd=rpd))
    return QueueRunner(client, gemini=gemini, budget=budget, pipeline_factory=lambda: make_pipeline(False, client=client))
