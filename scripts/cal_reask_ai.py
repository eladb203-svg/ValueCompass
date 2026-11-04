"""Calibration experiment (AI answers stored as "insufficient evidence"): ask again, with a sharpened instruction for the REASON the code rejected the answer, only the answers listed below (at most 20 calls). The new
answers go to a separate file (scripts/state/cal_ai_experiment.jsonl), NOT to the database and NOT to the approval flow. Prints the answer before and after.
Usage: python scripts/cal_reask_ai.py"""
import json
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

NOTES = {
    "no_quote": "A quote is required for every answer. If no customer, product or license is disclosed above 10% of revenue, set largest_exposure.type to none and quote ONE sentence of the TEXT that supports it "
                "(the sentence that describes the customer base or says that no customer reached 10%). Do not leave the quote empty.",
    "one_sentence": "The one_sentence field must be a single sentence of at most 25 words.",
    "quote_from_facts": "Every quote must be copied from the TEXT of the annual report, never from the FACTS block. The FACTS may be mentioned only in facts_check.",
    "quote_not_found": "Copy each quote character for character as ONE continuous passage of the TEXT, without shortening or joining passages.",
    "insufficient": "Choose the level that fits best on the FACTS and the TEXT together. Answer insufficient evidence only when neither the FACTS nor the TEXT supports any of the levels.",
}
ITEMS = [("UBER", "G3.1-Q3", "no_quote"), ("EWBC", "G3.1-Q3", "no_quote"), ("LNC", "G3.1-Q3", "no_quote"), ("SUI", "G3.1-Q3", "no_quote"), ("WY", "G3.1-Q3", "no_quote"), ("ANET", "G3.1-Q3", "no_quote"),
         ("NKE", "B3.1-Q5", "one_sentence"), ("ZION", "B3.1-Q5", "one_sentence"), ("WY", "B3.1-Q5", "one_sentence"),
         ("INTC", "B3.7-Q3", "quote_from_facts"), ("INTC", "B3.8-Q6", "quote_from_facts"), ("RF", "B3.7-Q3", "quote_from_facts"),
         ("HRL", "B3.7-Q3", "no_quote"), ("ANET", "G3.8-Q3", "no_quote"),
         ("AFG", "B3.8-Q6", "quote_not_found"), ("ORI", "B3.1-Q1", "quote_not_found"), ("ADSK", "B3.1-Q2", "quote_not_found"), ("MKL", "B3.1-Q4", "quote_not_found"),
         ("VICI", "B3.7-Q3", "insufficient"), ("ANET", "B3.1-Q3", "insufficient")]
assert len(ITEMS) <= 20
runner = vc.make_runner(24)
from src.pipeline import scoring as S  # noqa: E402
S._paths()
sk = scoring_skills()
store = AssessmentStore(ROOT / "scripts" / "state" / "cal_ai_experiment.jsonl")
by = {}
for t, q, kind in ITEMS:
    by.setdefault(t, []).append((q, kind))
for t, qs in by.items():
    co = runner.companies.get_by_symbol(t, "US")
    co = dict(co)
    if not co.get("profile"):                      # the companies of the first stages keep the profile in the score summary only
        co["profile"] = runner.client.table("company_score_summary").select("profile").eq("company_id", co["id"]).execute().data[0]["profile"]
    res = runner.load_result(t)
    K5 = runner._meta_context(co, res)
    import run_ai_k5a2 as K5A2
    K5A2.golden = K5.golden
    m = K5.meta(t)
    filing = find_filing(t, str(m["end"][-1])[:10])
    a = assess.Company(t, m["name"], m["profile"], int(m["fy"][-1][2:]), filing)
    fd = K5A2.facts_data(t, m)
    note = a.sections().get("NOTE-ACQ")
    fd["discontinued"] = discontinued_facts(getattr(note, "text", note) or "", max_year=2000 + int(m["fy"][-1][2:]))
    a.code_facts = {s: facts_for(s, fd) for s, _k in qs if facts_for(s, fd)}
    for q, kind in qs:
        before = runner.ai_store.get(t, a.fiscal_year, q, assess.prompt_version_of(sk[q], "3.1")) or {}
        bev = before.get("evidence") or {}
        after = assess.ask(a, sk[q], runner.gemini, store, assess.Stats(), force=True, variant="3.1", extra_note=NOTES[kind])
        aev = after.get("evidence") or {}
        quote = ((aev.get("quotes") or [{}])[0] or {}).get("text") if aev.get("quotes") else None
        print(f"== {t} {q} [{kind}]\n   before: state={before.get('state')} reasons={bev.get('reasons')}\n   after : answer={after.get('answer')} state={after.get('state')} reasons={aev.get('reasons')} check_ok={aev.get('check_ok')}\n"
              f"   reasoning: {str(aev.get('reasoning'))[:260]}\n   quote: {str(quote)[:200]}", flush=True)
print("model request attempts:", runner.gemini.attempts)
