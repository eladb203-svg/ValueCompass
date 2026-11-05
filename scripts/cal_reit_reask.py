"""Calibration (owner decision 2026-11-04, item 4): ask the four REIT questions again with the REIT-only reworded level definitions (B3.2-Q4, B3.2-Q5, B3.7-Q5, B3.8-Q6) for every REIT of the test
database (INCOME_REAL_ESTATE, weak reference set first). The wording lives in the profile note of the profile INCOME_REAL_ESTATE only (other profiles get the same prompt as before). The answers go to
scripts/state/cal_reit_reask.jsonl - NOT to the database and NOT to the approval flow; the production skill file is not touched until the owner's criteria are met.
Usage: python scripts/cal_reit_reask.py [MAX_ATTEMPTS=150]"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

import vc  # noqa: E402
from src.ai import assess  # noqa: E402
from src.ai.facts import discontinued_facts, facts_for  # noqa: E402
from src.ai.prompt import scoring_skills  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from src.pipeline import scoring as S  # noqa: E402

REPLACES = "For this profile the levels are the following; they REPLACE the scale above. "
QUOTE = " The quote must be the sentence of the report that shows the fact (a number or a multi-year trend), not a sentence that only describes the business, and not the statement that disclosure controls are effective."
NEW = {
    "B3.2-Q4": REPLACES + "2 = the report shows at least one durability fact over several years (occupancy held through the cycle, same-property NOI growth, positive rent spreads on renewals, long weighted-average lease term, tenant retention); being the largest or among the largest is NOT by itself level 2. "
                          "1 = the position is plausible (size, location) but the report shows no multi-year durability fact, or the signals are mixed (occupancy or same-property NOI slipping, short leases, rents rising only with the market). "
                          "0 = occupancy, rents or same-property NOI are falling, or the report states weakening demand for the properties. A temporarily rising property market is not a stable competitive position." + QUOTE,
    "B3.2-Q5": REPLACES + "2 = a location or irreplaceable-asset advantage (scarce sites, high barriers to entry, long leases to strong tenants) that is MEASURED in the report (occupancy, rent premium or retention over several years). "
                          "1 = a plausible advantage is stated (location, scale) without such a measured result. 0 = no identifiable advantage, or occupancy / rents / same-property NOI are deteriorating. A rising market and size alone do not count." + QUOTE,
    "B3.7-Q5": REPLACES + "2 = clear reporting: FFO / AFFO / NOI measures are reconciled to GAAP and are not the only headline of the management discussion, the strategy is consistent, no restatements or governance disputes. "
                          "1 = heavy reliance on adjusted measures (FFO, AFFO, core FFO, adjusted EBITDA) as the headline, or frequent strategy changes, or equity issued below net asset value, or disposal proceeds used to fund the dividend. "
                          "0 = restatements, governance problems, aggressive accounting. The sentence that disclosure controls are effective is not evidence for level 2." + QUOTE,
    "B3.8-Q6": REPLACES + "2 = growth shown by same-property NOI or rent growth over several years, not dependent on acquisitions, on development financed by new equity or debt, or on revaluation. "
                          "1 = growth partly depends on acquisitions or on externally financed development, or on a rising market. 0 = growth only from acquisitions, debt or revaluation, or same-property NOI is falling." + QUOTE,
}
QS = list(NEW)
WEAK = ["PK", "BDN", "DHC", "HPP", "MAC"]
MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 150
runner = vc.make_runner(MAX)
S._paths()
base = scoring_skills()
sk = {}
for q in QS:
    s = copy.deepcopy(base[q])
    s["profile_notes"] = {**(s.get("profile_notes") or {}), "INCOME_REAL_ESTATE": NEW[q]}
    s["version"] = f"{s['version']}-reit"                      # the experiment's own version: it never matches a stored production row
    sk[q] = s
store = AssessmentStore(ROOT / "scripts" / "state" / "cal_reit_reask.jsonl")
rows = runner.client.table("company_score_summary").select("company_id,profile").eq("profile", "INCOME_REAL_ESTATE").execute().data
sym = {r["id"]: r["symbol"] for r in runner.client.table("companies").select("id,symbol").eq("exchange", "US").execute().data}
reits = sorted({sym[r["company_id"]] for r in rows} | set(WEAK), key=lambda t: (t not in WEAK, WEAK.index(t) if t in WEAK else 0, t))
print("REITs:", len(reits), reits, flush=True)
import run_ai_k5a2 as K5A2  # noqa: E402
for t in reits:
    co = dict(runner.companies.get_by_symbol(t, "US"))
    co["profile"] = "INCOME_REAL_ESTATE"
    try:
        res = runner.load_result(t)
        K5 = runner._meta_context(co, res)
        K5A2.golden = K5.golden
        m = K5.meta(t)
        filing = find_filing(t, str(m["end"][-1])[:10])
        a = assess.Company(t, m["name"], "INCOME_REAL_ESTATE", int(m["fy"][-1][2:]), filing)
        fd = K5A2.facts_data(t, m)
        note = a.sections().get("NOTE-ACQ")
        fd["discontinued"] = discontinued_facts(getattr(note, "text", note) or "", max_year=2000 + int(m["fy"][-1][2:]))
        a.code_facts = {q: facts_for(q, fd) for q in QS if facts_for(q, fd)}
    except Exception as e:   # noqa: BLE001
        print(f"== {t} SETUP FAILED {type(e).__name__}: {str(e)[:150]}", flush=True)
        continue
    for q in QS:
        if runner.gemini.attempts >= MAX:
            print("attempt cap reached", flush=True)
            break
        if store.get(t, a.fiscal_year, q, assess.prompt_version_of(sk[q], "3.1")):          # resume: already asked in an earlier run of the experiment
            continue
        try:
            r = assess.ask(a, sk[q], runner.gemini, store, assess.Stats(), force=True, variant="3.1")
        except Exception as e:   # noqa: BLE001
            print(f"== {t} {q} FAILED {type(e).__name__}: {str(e)[:150]}", flush=True)
            continue
        ev = r.get("evidence") or {}
        print(f"== {t} {q} answer={r.get('answer')} state={r.get('state')} check_ok={ev.get('check_ok')} reasons={ev.get('reasons')}", flush=True)
print("model request attempts:", runner.gemini.attempts, flush=True)
