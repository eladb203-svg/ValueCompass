"""D2 (results analysis) written by CODE, without AI (decision 2026-10-24): the sentence frames of the skills document (3.3) are filled directly in Hebrew from the D2 inputs - glossary names,
strength words, the range with "משוער", "הנמוך ביותר", the method name, numbers formatted by code, the score-change line. The result goes through the same ``check_analysis`` checks as an
AI text, so a template or input mistake cannot reach the screen."""
from __future__ import annotations

import json
from typing import Optional

from . import content as C


def _score_part(blk: dict) -> str:
    return blk["score_display"] + (f" ({blk['label_he']})" if blk.get("label_he") else "")


def render_d2(inputs: dict) -> dict:
    """-> the D2 answer dict {skill_id, version, quality_he, value_he, criteria_cited, change_he} (the same shape as the model's answer)."""
    cfg = C.content_cfg()
    results, peers, ch = inputs["results"], inputs["peers"], inputs.get("changes")
    g = cfg["glossary"]
    bn, gn = g["models"]["buffett"], g["models"]["graham"]
    b, gr = results["models"][bn], results["models"][gn]
    names_b = ", ".join(b["strongest_he"]) if isinstance(b["strongest_he"], list) else "אין"
    names_g = ", ".join(gr["strongest_he"]) if isinstance(gr["strongest_he"], list) else "אין"
    if names_b != "אין" and names_g != "אין":
        strong_sentence = f"לפי באפט: {names_b}; לפי גרהם: {names_g}"
    else:
        strong_sentence = names_b if names_g == "אין" and names_b != "אין" else (names_g if names_b == "אין" and names_g != "אין" else "אין")
    low_b, low_g = b["lowest_he"], gr["lowest_he"]
    q = (f"ציון האיכות לפי באפט: {_score_part(b)}; לפי גרהם: {_score_part(gr)}. הקריטריונים החזקים: {strong_sentence}. "
         f"הנמוך ביותר: {low_b['name_he']} ({low_b['strength_he']}) לפי באפט, {low_g['name_he']} ({low_g['strength_he']}) לפי גרהם.")
    if peers["group"]["compare"]:
        q += f" ביחס ל-{peers['group']['n']} עמיתים ({peers['group']['definition']}): {peers['quality'][bn]['position_he']} לפי באפט, {peers['quality'][gn]['position_he']} לפי גרהם."

    def value_part(blk: dict, with_mos: bool) -> str:
        head = f"{blk['value_text']} ({blk['method_he']})" if blk["value_text"] else "לא זמין"
        if blk["buy_price_text"] is not None:
            tail = f"מחיר הקנייה: {blk['buy_price_text']}" + (f", במרווח ביטחון נדרש של {blk['required_mos_text']}" if with_mos and blk["required_mos_text"] else "")
        else:
            tail = blk["state_he"] or g["states"]["cannot_price"]
        return f"{head}; {tail}"
    v = f"השווי לפי באפט: {value_part(b, True)}. לפי גרהם: {value_part(gr, False)}."
    cited = []
    for blk in (b, gr):
        for c in blk["criteria"]:
            if c["name_he"] in q or any(c["name_he"] == n for n in (blk["strongest_he"] if isinstance(blk["strongest_he"], list) else [])):
                if c["id"] not in cited:
                    cited.append(c["id"])
    out = {"skill_id": cfg["d2"]["skill_id"], "version": cfg["d2"]["version"], "quality_he": q, "value_he": v, "criteria_cited": cited}
    if ch:
        first = ch["changes"][0] if ch["changes"] else None
        out["change_he"] = (f"לעומת הריצה הקודמת ({ch['previous_run']}): {first['name_he']} {first['direction_he']} מ-{first['from']:.1f} ל-{first['to']:.1f} — {ch['reason_he']}." if first else None)
    return out


def generate_analysis_template(ticker: str, fiscal_year: int, inputs: dict, store: C.TextStore, force: bool = False) -> dict:
    """D2 once per scoring run, without a model call. The row has the same shape as the AI rows (``model`` = "code-template")."""
    version = f"t{C.content_cfg()['d2']['version']}"
    run_id = inputs["results"]["run_id"]
    if inputs.get("ai_pending"):
        return {"ticker": ticker, "fiscal_year": fiscal_year, "kind": "analysis", "state": "skipped_ai_pending", "run_id": run_id, "text": None,
                "checks": {"ok": False, "reasons": [f"{inputs['ai_pending']} AI questions are still pending"], "attempts": []}}
    ex = None if force else store.get(ticker, fiscal_year, "analysis", version, run_id)
    if ex is not None and ex.get("state") == "stored":
        return ex
    ans = render_d2(inputs)
    res = C.check_analysis(json.dumps(ans, ensure_ascii=False), inputs)
    text = (ans["quality_he"] + "\n\n" + ans["value_he"]) if res.ok else None
    return store.put({"ticker": ticker, "fiscal_year": fiscal_year, "kind": "analysis", "language": "he", "text": text, "quality_he": ans["quality_he"] if res.ok else None,
                      "value_he": ans["value_he"] if res.ok else None, "change_he": ans.get("change_he") if res.ok else None, "criteria_cited": ans["criteria_cited"], "model": "code-template",
                      "prompt_version": version, "run_id": run_id, "state": res.state, "quotes": [], "generator": "template",
                      "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": []}, "rendered": ans})
