"""Background test 1 (English): five ways to write the D1 background for the 7 development-set companies, compared blind. Files only: no write to Supabase (test is read for the existing texts).

    .venv/Scripts/python scripts/run_bg_test1.py --dry-run                       builds every input and prompt (no model call) and prints the input lengths
    .venv/Scripts/python scripts/run_bg_test1.py --model gemini-3.5-flash --total-cap 50   runs only what is missing of V2-V5 (V1 is the stored text); the cap of this run = 50 minus the attempts the
                                                                                      test already used (scripts/output_bg_test/ledger.json); --cap N sets it directly. One model for all versions.
    .venv/Scripts/python scripts/run_bg_test1.py --blind                          writes scripts/output_bg_test/blind_en.html and key.json from runs.jsonl
Outside sources (Yahoo Finance, Wikipedia) are used for this test only and are not stored in a database.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import assess, bg_test as B, checks, content as C  # noqa: E402
from src.ai.db_stores import DbTextStore  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.db import get_supabase_client  # noqa: E402
from src.net import retry_network  # noqa: E402

OUT = ROOT / "scripts" / "output_bg_test"
DEV = ["KO", "MSFT", "JPM", "CB", "O", "AMT", "INTC"]
WIKI = {"KO": "Coca-Cola", "MSFT": "Microsoft", "JPM": "JPMorgan Chase", "CB": "Chubb Limited", "O": "Realty Income", "AMT": "American Tower", "INTC": "Intel"}
BLIND_SEED = 20261025


def context(runner, t: str) -> dict:
    """Facts, the report sections (raw) and the filing of one company, from the local results and the filings cache."""
    from src.scoring import peer_source as PS
    co = runner.companies.get_by_symbol(t, "US")
    res = runner.load_result(t)
    K5 = runner._meta_context(co, res)
    import run_ai_k5c as K5C
    rec = next(r for r in PS.load_records(runner.results_dir) if r["ticker"] == t)
    facts, _moat, _missing = K5C.d1_inputs(rec, runner.ai_store)
    m = K5.meta(t)
    filing = find_filing(t, str(m["end"][-1])[:10])
    a = assess.Company(t, m["name"], m["profile"], int(rec["fiscal_year"][2:]), filing)
    secs = {k: v.text for k, v in a.sections().items() if k in ("TXT-001", "TXT-003", "TXT-005") and v.found}
    return {"facts": facts, "sections": secs, "accession": filing.accession, "fiscal_year": a.fiscal_year}


def outside_sources(t: str, cache: dict) -> dict:
    """Yahoo description and the opening of the English Wikipedia article (cached in sources.json; not a database)."""
    if t in cache:
        return cache[t]
    out = {"yahoo": None, "wikipedia": None}
    try:
        import yfinance as yf
        out["yahoo"] = (yf.Ticker(t).info or {}).get("longBusinessSummary") or None
    except Exception as e:   # noqa: BLE001
        out["yahoo_error"] = f"{type(e).__name__}: {e}"[:200]
    try:
        import requests
        from src.providers.sec_companyfacts import _read_user_agent
        r = retry_network(lambda: requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1, "titles": WIKI[t], "format": "json"},
                                               headers={"User-Agent": _read_user_agent() or "ValueCompass research test"}, timeout=30))
        r.raise_for_status()
        page = next(iter(r.json()["query"]["pages"].values()))
        out["wikipedia"] = (page.get("extract") or "").strip() or None
    except Exception as e:   # noqa: BLE001
        out["wikipedia_error"] = f"{type(e).__name__}: {e}"[:200]
    cache[t] = out
    return out


def v1_row(texts, t: str, ctx: dict) -> dict:
    """V1 = the stored English text (latest fiscal year, highest prompt version), measured with the same checks (no model call)."""
    rows = [r for r in texts.rows(t) if r["kind"] == "background" and r["language"] == "en" and r.get("text")]
    if not rows:
        return {"ticker": t, "version": "V1", "state": "no_source", "text": None, "attempts": [], "input_chars": 0}
    r = max(rows, key=lambda x: (x["fiscal_year"], str(x["prompt_version"])))
    trimmed, _ = C.trim_d1_sections(ctx["facts"], ctx["accession"], ctx["sections"])
    _p, text_sent, sent = C.build_d1_prompt(ctx["facts"], ctx["accession"], trimmed)
    raw = r.get("raw_answer") or json.dumps({"skill_id": "BG-1", "version": 5, "text_en": r["text"], "competitors": r.get("competitors", []), "competitor_types": r.get("competitor_types", []), "quotes": r.get("quotes", [])})
    res = B.check_version(raw, ctx["facts"], text_sent, sent, ctx["fiscal_year"])
    return {"ticker": t, "version": "V1", "model": r.get("model"), "prompt_version": str(r["prompt_version"]), "input_chars": len(text_sent), "attempts": [{"ok": res.ok, "reasons": res.reasons, "measured": True}],
            "state": "stored" if res.ok else "failed", "text": r["text"], "words": C.count_words(r["text"]), "competitors": r.get("competitors", []), "competitor_types": r.get("competitor_types", [])}


def generate(client, version: str, t: str, ctx: dict, outside: dict, chapter: dict) -> dict:
    src = {"V4": outside.get("yahoo"), "V5": outside.get("wikipedia")}.get(version)
    inp = B.blocks_for(version, ctx["sections"], chapter, src)
    row = {"ticker": t, "version": version, "model": getattr(client, "model", ""), "input_chars": inp["input_chars"], "chapter": {k: chapter[k] for k in ("method", "length", "heading")},
           "attempts": [], "text": None}
    if inp["no_source"]:
        return {**row, "state": "no_source"}
    note, last = "", None
    for attempt in (1, 2):
        prompt, text_sent, sent = B.build_prompt(version, ctx["facts"], ctx["accession"], inp["blocks"], inp["description"], note)
        row["prompt_chars"] = len(prompt)
        rep = client.generate(prompt, seed_offset=attempt - 1)
        res = B.check_version(rep.text, ctx["facts"], text_sent, sent, ctx["fiscal_year"])
        text = (res.parsed or {}).get("text_en") if isinstance(res.parsed, dict) else None
        row["attempts"].append({"ok": res.ok, "reasons": res.reasons})
        if isinstance(text, str):
            row.update({"text": text, "words": C.count_words(text), "competitors": res.extra.get("competitors", []), "competitor_types": res.extra.get("competitor_types", []), "quotes": res.quotes})
        last = res
        if res.ok:
            break
        note = B.retry_note(res.reasons, ctx["facts"])
    return {**row, "state": "stored" if last.ok else "failed"}


def load_runs(path: Path) -> dict:
    return {(r["ticker"], r["version"]): r for r in (json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())} if path.exists() else {}


def append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def blind(runs: dict) -> None:
    rng = random.Random(BLIND_SEED)
    key, html_blocks = {}, []
    for t in DEV:
        avail = [v for v in B.VERSIONS if runs.get((t, v), {}).get("text")]
        order = avail[:]
        rng.shuffle(order)
        letters = "ABCDE"[:len(order)]
        key[t] = {letters[i]: {"version": v, "state": runs[(t, v)]["state"], "model": runs[(t, v)].get("model")} for i, v in enumerate(order)}
        cards = []
        for i, v in enumerate(order):
            r = runs[(t, v)]
            bad = r["state"] != "stored"
            why = "; ".join(r["attempts"][-1]["reasons"][:4]) if bad and r.get("attempts") else ""
            cards.append(f'<div class="card{" bad" if bad else ""}"><div class="hd"><label><input type="radio" name="{t}" value="{letters[i]}"> <b>{letters[i]}</b></label>'
                         f'<span class="meta">{r["words"]} words' + (f' · <span class="warn">failed the checks: {why}</span>' if bad else "") + f'</span></div><p dir="ltr">{r["text"]}</p></div>')
        html_blocks.append(f'<section><h2>{t}</h2>{"".join(cards)}<input class="note" type="text" id="note_{t}" placeholder="הערה (לא חובה)"></section>')
    page = ("<!doctype html><html lang=\"he\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>מבחן רקע - אנגלית</title><style>"
            ":root{--bg:#fff;--fg:#1d1d1f;--mut:#6b6b70;--line:#d9d9de;--card:#f6f6f8;--bad:#fff4f2;--badline:#e8b4a8;--acc:#0a5cff}"
            "@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececf0;--mut:#9a9aa3;--line:#37373d;--card:#222226;--bad:#2c1f1c;--badline:#6b3b30;--acc:#6aa0ff}}"
            "body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,Segoe UI,Arial,sans-serif}main{max-width:860px;margin:0 auto;padding:16px}"
            "h1{font-size:1.3rem}h2{font-size:1.1rem;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}"
            ".card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0}.card.bad{background:var(--bad);border-color:var(--badline)}"
            ".hd{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.meta{color:var(--mut);font-size:.85rem}.warn{color:#c0392b}"
            "p{margin:8px 0 2px;text-align:left}.note{width:100%;box-sizing:border-box;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}"
            "button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:1rem;cursor:pointer;margin:18px 0}textarea{width:100%;min-height:150px;box-sizing:border-box}"
            "</style></head><body><main><h1>מבחן רקע (אנגלית) - בחירה עיוורת</h1><p style=\"text-align:right;color:var(--mut)\">לכל חברה, בחר את הנוסח הטוב ביותר. האותיות מעורבבות לכל חברה. לא נשמר דבר ולא נשלח דבר.</p>"
            + "".join(html_blocks) + "<button type=\"button\" id=\"copy\">העתק בחירות</button><textarea id=\"out\" readonly placeholder=\"הבחירות יופיעו כאן\"></textarea></main>"
            "<script>const T=" + json.dumps(DEV) + ";document.getElementById('copy').onclick=function(){let lines=[];T.forEach(t=>{const r=document.querySelector('input[name='+t+']:checked');"
            "const n=document.getElementById('note_'+t).value.trim();lines.push(t+': '+(r?r.value:'-')+(n?' \\u2014 '+n:''));});const s=lines.join('\\n');const o=document.getElementById('out');o.value=s;"
            "if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s).catch(()=>{o.select();document.execCommand('copy');});}else{o.select();document.execCommand('copy');}};</script></body></html>")
    (OUT / "blind_en.html").write_text(page, encoding="utf-8")
    (OUT / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")


def main(argv) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    arg = lambda name, default=None: argv[argv.index(name) + 1] if name in argv else default  # noqa: E731
    runs_path, src_path = OUT / "runs.jsonl", OUT / "sources.json"
    runs = load_runs(runs_path)
    if "--blind" in argv:
        blind(runs)
        print("written: scripts/output_bg_test/blind_en.html and key.json (the key is not shown)")
        return 0
    from src.pipeline.queue_runner import CappedGemini, QueueRunner
    runner = QueueRunner(get_supabase_client("test"))                      # reads only
    texts = DbTextStore(get_supabase_client("test"))
    cache = json.loads(src_path.read_text(encoding="utf-8")) if src_path.exists() else {}
    dry = "--dry-run" in argv
    client = None
    ledger_path = OUT / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"attempts": 0, "log": []}
    if not dry:
        from src.ai.client import GeminiClient, RateLimiter
        cap = int(arg("--cap")) if arg("--cap") else int(arg("--total-cap", "50")) - ledger["attempts"]
        if cap <= 0:
            print(f"the test already used {ledger['attempts']} request attempts: nothing left under the cap")
            return 0
        inner = GeminiClient(model=arg("--model", "gemini-3.5-flash"), limiter=RateLimiter(rpm=10, rpd=450))
        client = CappedGemini(inner, cap)
        print(f"model {inner.model}; cap of this run {cap} request attempts (used so far by the test: {ledger['attempts']})", flush=True)
    from src.ai.content import BudgetExceeded
    stopped = False
    try:
        return _run(DEV, runner, texts, cache, dry, client, runs, runs_path, src_path, stopped, ledger, ledger_path)
    finally:
        pass


def _run(DEV, runner, texts, cache, dry, client, runs, runs_path, src_path, stopped, ledger, ledger_path) -> int:
    from src.ai.content import BudgetExceeded
    try:
        return _loop(DEV, runner, texts, cache, dry, client, runs, runs_path, src_path, stopped)
    finally:
        if client:                                               # the attempts of this run are added to the ledger even when it ends with an error
            ledger["attempts"] += client.attempts
            ledger["log"].append({"model": client.model, "attempts": client.attempts, "cap": client.cap})
            ledger_path.write_text(json.dumps(ledger, indent=1), encoding="utf-8")


def _loop(DEV, runner, texts, cache, dry, client, runs, runs_path, src_path, stopped) -> int:
    from src.ai.content import BudgetExceeded
    for t in DEV:
        ctx = context(runner, t)
        out = outside_sources(t, cache)
        src_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
        chapter = B.competition_chapter(ctx["sections"].get("TXT-001", ""))
        if ("V1" not in [v for (tt, v) in runs if tt == t]) and (t, "V1") not in runs:
            runs[(t, "V1")] = v1_row(texts, t, ctx)
            append(runs_path, runs[(t, "V1")])
        lens = {}
        for v in ("V2", "V3", "V4", "V5"):
            src = {"V4": out.get("yahoo"), "V5": out.get("wikipedia")}.get(v)
            inp = B.blocks_for(v, ctx["sections"], chapter, src)
            lens[v] = "no source" if inp["no_source"] else inp["input_chars"]
            if dry or (t, v) in runs or stopped:
                continue
            try:
                runs[(t, v)] = generate(client, v, t, ctx, out, chapter)
            except (BudgetExceeded, RuntimeError) as e:
                stopped = True
                runs[(t, v)] = {"ticker": t, "version": v, "state": "not_run", "text": None, "attempts": [], "note": str(e)[:160], "input_chars": inp["input_chars"]}
                print(f"  STOPPED at {t} {v}: {str(e)[:120]}")
            append(runs_path, runs[(t, v)])
        print(f"{t:<5} chapter: {chapter['method']:<10} {chapter['length']:>5} chars | yahoo {'yes' if out.get('yahoo') else 'NO'} | wikipedia {'yes' if out.get('wikipedia') else 'NO'} | input chars {lens}"
              + ("" if dry else " | " + ", ".join(f"{v}:{runs[(t, v)]['state']}" for v in ("V2", "V3", "V4", "V5") if (t, v) in runs)), flush=True)
    if client:
        print("request attempts of this run:", client.attempts, "of cap", client.cap)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
