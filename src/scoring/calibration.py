"""Calibration parameters (config/calibration.yaml), all off by default (K6d-2, 2026-11-03). ``flag(name)`` reads the file once; the environment variable VC_CAL_<NAME> (1 / 0) overrides it, for the
measurement scripts (a runner may run in a child process, which inherits the environment). ``override`` is the same for tests."""
from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parents[2] / "config" / "calibration.yaml"
_FORCED: dict = {}


@lru_cache(maxsize=1)
def _file() -> dict:
    try:
        return yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}


def value(name: str, default=None):
    if name in _FORCED:
        return _FORCED[name]
    env = os.environ.get("VC_CAL_" + name.upper())
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes") if isinstance(_file().get(name, default), bool) else float(env)
    return _file().get(name, default)


def flag(name: str) -> bool:
    return bool(value(name, False))


@contextmanager
def override(**kw):
    old = dict(_FORCED)
    _FORCED.update(kw)
    try:
        yield
    finally:
        _FORCED.clear()
        _FORCED.update(old)
