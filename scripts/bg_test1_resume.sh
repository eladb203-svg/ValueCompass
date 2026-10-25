#!/bin/sh
# Background test 1 - runs ONLY what is missing (a finished version of a company is never asked again), then builds the blind page.
# Model: gemini-3.5-flash for every version (one model, so the comparison is fair). Cap: 50 request attempts for the whole test minus what was already used
# (scripts/output_bg_test/ledger.json: 21 so far -> 29 left); enforced in code. Retries per call: 3. Run it after the quota reset (10:00 Israel time).
cd "$(dirname "$0")/.." || exit 1
VC_AI_RETRIES=3 PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_bg_test1.py --model gemini-3.5-flash --total-cap 50 && \
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/run_bg_test1.py --blind
