"""Code stage K5a-2: availability probe - one realistic judgment prompt (KO, B3.1-Q1) per model, a few attempts with a timeout. Usage: python scripts/ai_probe.py MODEL [MODEL ...]"""
import sys, time, os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
os.environ["VC_AI_TIMEOUT_MS"] = os.environ.get("VC_AI_TIMEOUT_MS", "120000")
from src.ai import prompt as P
from src.ai.client import GeminiClient, RateLimiter
from src.ai.sections import find_filing, split_sections
tz = ZoneInfo("Asia/Jerusalem")
f = find_filing("KO", "2025-12-31"); s = split_sections(f.text)
sk = P.scoring_skills()["B3.1-Q1"]
text, _, _ = P.build_prompt(sk, {"company_name": "Coca-Cola", "ticker": "KO", "fiscal_year": "FY2025", "profile": "STANDARD", "accession": f.accession}, {"TXT-001": s["TXT-001"].text})
for m in sys.argv[1:]:
    c = GeminiClient(model=m, limiter=RateLimiter(rpm=30))
    os.environ["VC_AI_RETRIES"] = "1"
    for attempt in range(1, 4):
        t0 = time.time(); stamp = datetime.now(tz).strftime("%H:%M:%S")
        try:
            import src.ai.client as C
            C.MAX_RETRIES = 1
            r = c.generate(text)
            print(f"{m}: attempt {attempt} at {stamp} OK in {time.time() - t0:.1f}s, {r.prompt_tokens} tokens in, thoughts {r.thought_tokens}", flush=True)
            break
        except Exception as e:
            print(f"{m}: attempt {attempt} at {stamp} FAILED after {time.time() - t0:.0f}s: {str(e)[:110]}", flush=True)
            time.sleep(30)
