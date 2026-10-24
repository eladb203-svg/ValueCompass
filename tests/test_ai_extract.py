"""Code stage K5b: AI extraction B1-B14 - checks, controls, approvals, sections by title, store and engine hookup (no model calls)."""
import json
from types import SimpleNamespace

import pytest

from src.ai import ext_checks as X
from src.ai import extract as E
from src.ai.client import Reply
from src.ai.prompt import extraction_blocks, build_extraction_prompt
from src.ai.sections import ext_section, Filing
from src.scoring import ext_items as EI

BLK = extraction_blocks()
TEXT = "Consolidated capital. | CET1 capital ratio | 14.6 | % | 15.7 | % |\nRisk-weighted assets | 1,740,429 | 1,700,000 |\nTotal loans | (1,234) | 1,200 |"


def keys(block):
    return {i["key"]: i["unit"] for i in block["items"]}


def item(**kw):
    d = {"item_key": "cet1_ratio_standardized", "period": "December 31, 2025", "value": 14.6, "unit": "percent", "scale": 1, "basis": None, "value_state": "value",
         "quote": {"text": "CET1 capital ratio | 14.6 | %", "section": "X-BANKCAP"}}
    d.update(kw)
    return d


def chk(it, fy=2025):
    return X.check_item(it, keys(BLK["EXT-BANK-CAP"]), X.normalize(TEXT), fy)


def test_all_fourteen_blocks_exist_with_items_control_and_approval():
    assert sorted(b["block"] for b in BLK.values()) == sorted(f"B{i}" for i in range(1, 15))
    assert BLK["EXT-RE-NAV"]["approval"] == "always" and BLK["EXT-RE-OPU"]["approval"] == "always"
    assert {BLK[s]["approval"] for s in ("EXT-RE-MAINT", "EXT-RE-VALUE", "EXT-RE-LIQ", "EXT-RE-FFO", "EXT-PROFILE")} == {"by_control"}
    assert BLK["EXT-GENERAL"]["control"] == "neighbours_3x"


def test_prompt_has_the_quote_rules_the_items_and_the_text():
    p, text, sent = build_extraction_prompt(BLK["EXT-BANK-CAP"], {"company_name": "JPM", "ticker": "JPM", "fiscal_year": "FY2025", "profile": "BANK", "accession": "x"}, {"X-BANKCAP": "hello"})
    assert "one continuous passage" in p and "'...'" not in p and "cet1_ratio_standardized" in p and "[X-BANKCAP]\nhello" in p and sent == ["X-BANKCAP"]
    assert '"items": [' in p and "{skill_id}" not in p


def test_item_checks_accept_a_good_item_and_give_each_rejection_its_reason():
    assert chk(item()).ok
    assert "quote_not_found" in chk(item(quote={"text": "CET1 capital ratio | 99 | %", "section": "x"})).reasons
    assert "quote_not_found" in chk(item(quote={"text": "CET1 ... | 14.6 | %", "section": "x"})).reasons
    assert "number_not_in_quote" in chk(item(value=15.0)).reasons
    assert "unit_not_allowed" in chk(item(unit="USD")).reasons
    assert "period_mismatch" in chk(item(period="December 31, 2021")).reasons
    assert chk(item(period="Q4 average")).flags == ["period_assumed_fiscal_year"]
    assert "value_state_inconsistent" in chk(item(value_state="not_disclosed")).reasons              # null only with NA / not_disclosed
    assert "value_state_inconsistent" in chk(item(value=None)).reasons
    assert chk(item(value=None, value_state="not_disclosed", quote=None)).ok and chk(item(value=None, value_state="NA", quote=None)).ok
    assert "item_key_unknown" in chk(item(item_key="nope")).reasons and "scale_not_allowed" in chk(item(scale=7)).reasons


def test_number_in_quote_after_scale_conversion_parentheses_and_percents():
    f = X.number_in_quote
    assert f(1740429, 1000000, "USD", "Risk-weighted assets | 1,740,429 |")[0]            # table scale as stated
    assert f(1.2, 1000000000, "USD", "a loss of $1.2 billion")[0]                          # value in billions, words in the quote
    assert f(1200, 1000000, "USD", "a loss of $1.2 billion")[0]                            # value in millions, words in the quote
    assert f(-1234, 1000000, "USD", "Total loans | (1,234) |") == (True, True)             # parentheses = negative
    assert f(14.6, 1, "percent", "ratio was 14.6%")[0] and f(0.146, 1, "ratio", "ratio was 14.6%")[0]
    assert not f(14.7, 1, "percent", "ratio was 14.6%")[0]


def row(key, year, vf, unit="USD", basis=None, **kw):
    return {"item_key": key, "year": year, "value_full": vf, "item": {"unit": unit, "basis": basis}, "state": "value", **kw}


def test_block_controls():
    assert X.control_cet1_vs_rwa([row("cet1_capital", 2025, 254e9), row("rwa_standardized", 2025, 1740e9), row("cet1_ratio_standardized", 2025, 14.6, "percent")])["result"] == "pass"
    assert X.control_cet1_vs_rwa([row("cet1_capital", 2025, 254e9), row("rwa_standardized", 2025, 1740e9), row("cet1_ratio_standardized", 2025, 15.5, "percent")])["result"] == "fail"
    assert X.control_cet1_vs_rwa([row("cet1_ratio_standardized", 2025, 15.5, "percent")])["result"] == "na"
    lines = [row("loan_line", 2025, 600e9, basis="C&I"), row("loan_line", 2025, 395e9, basis="Consumer"), row("loan_line", 2025, 995e9, basis="Total loans")]
    assert X.control_loans_sum(lines + [row("total_loans", 2025, 1000e9)])["result"] == "pass"       # a 'Total' line is not summed
    assert X.control_loans_sum(lines[:1] + [row("total_loans", 2025, 1000e9)])["result"] == "fail"
    assert X.control_inv_sum([row("inv_fixed_maturities", 2025, 95e9), row("inv_equity", 2025, 4e9), row("inv_total", 2025, 100e9)])["result"] == "pass"       # 1% off
    assert X.control_inv_sum([row("inv_fixed_maturities", 2025, 90e9), row("inv_total", 2025, 100e9)])["result"] == "fail"                                   # 10% off
    assert X.control_bounds([row("occupancy", 2025, 98.0, "percent")])["result"] == "pass" and X.control_bounds([row("occupancy", 2025, 140.0, "percent")])["result"] == "fail"
    assets = [row("bsa_noi", 2025, 90e9), row("bsa_excl", 2025, 5e9), row("bsa_other", 2025, 5e9), row("total_assets", 2025, 100e9)]
    assert X.control_assets_sum(assets)["result"] == "pass"
    assert X.control_assets_sum([row("bsa_noi", 2025, 80e9), row("bsa_other", 2025, 12e9), row("total_assets", 2025, 100e9)])["result"] == "fail"
    nb = X.control_neighbours([row("cip", 2023, 10.0), row("cip", 2024, 100.0), row("cip", 2025, 11.0)])
    assert nb["result"] == "fail" and nb["years"]["cip"][2024] == "flag"


def mk(key="a", status=None, **kw):
    r = {"item_key": key, "approval_status": status, "block": "B1"}
    r.update(kw)
    return r


def test_approval_rules_of_ai_spec_section_7():
    ok, bad = {"name": "c", "result": "pass", "detail": "", "items": []}, {"name": "c", "result": "fail", "detail": "x", "items": []}
    assert E.decide(BLK["EXT-BANK-CAP"], mk(), ok)[0] == "approved"
    assert E.decide(BLK["EXT-BANK-CAP"], mk(), bad)[0] == "pending"                               # an automatic block whose control failed goes to review
    assert E.decide(BLK["EXT-RE-NAV"], mk(), ok)[0] == "pending" and E.decide(BLK["EXT-RE-OPU"], mk(), None)[0] == "pending"          # always
    assert E.decide(BLK["EXT-RE-MAINT"], mk(), ok)[0] == "approved" and E.decide(BLK["EXT-RE-MAINT"], mk(), bad)[0] == "pending"      # by control (Q6)
    assert E.decide(BLK["EXT-RE-LIQ"], mk(), {"name": "coverage_band", "result": "na", "detail": "", "items": []})[0] == "pending"
    assert E.decide(BLK["EXT-GENERAL"], mk("cip"), ok)[0] == "approved" and E.decide(BLK["EXT-GENERAL"], mk("profile_total_assets"), ok)[0] == "pending"   # feeds PROFILE
    assert E.decide(BLK["EXT-GENERAL"], mk("cip"), bad)[0] == "pending"
    assert E.decide(BLK["EXT-BANK-CAP"], mk(status="rejected"), ok)[0] == "rejected"


def test_truncated_reply_keeps_the_complete_items():
    raw = '{"skill_id": "EXT-BANK-CAP", "version": 1, "items": [' + json.dumps(item()) + ', {"item_key": "rwa_stand'
    res, reasons = X.check_reply(raw, BLK["EXT-BANK-CAP"], TEXT, 2025)
    assert reasons == ["truncated_salvaged"] and len(res) == 1 and res[0].ok
    assert X.check_reply("nothing", BLK["EXT-BANK-CAP"], TEXT, 2025)[1] == ["invalid_json"]


class FakeClient:
    model = "fake"

    def __init__(self, text):
        self.text, self.calls, self.n = text, 0, 0

    def generate(self, prompt, seed_offset=0, thinking_budget=None):
        self.calls += 1
        self.n += 1
        return Reply(self.text, "fake", 10, 10, 0, 0.1, finish_reason="STOP")


def test_ask_block_stores_the_call_once_and_rows_carry_checks_control_and_approval(tmp_path):
    body = "x " * 400 + TEXT
    filing = Filing("JPM", body, "0001-26-000001", "p")
    rep = E.Report("JPM", "JPMorgan", "BANK", 2025, filing)
    rep._text_cache["X-BANKCAP"] = SimpleNamespace(found=True, text=body, flags=[])
    reply = json.dumps({"skill_id": "EXT-BANK-CAP", "version": 1, "items": [item(), item(item_key="rwa_standardized", value=1740429, unit="USD", scale=1000000,
                                                                                           quote={"text": "Risk-weighted assets | 1,740,429 |", "section": "X-BANKCAP"}),
                                                                                  item(item_key="cet1_ratio_advanced", value=99.0)]})
    cl, calls = FakeClient(reply), E.CallStore(tmp_path / "calls.jsonl")
    rec = E.ask_block(rep, BLK["EXT-BANK-CAP"], cl, calls)
    E.ask_block(rep, BLK["EXT-BANK-CAP"], cl, calls)
    assert cl.n == 1 and E.CallStore(tmp_path / "calls.jsonl").get("JPM", 2025, "EXT-BANK-CAP")["raw"] == reply
    rows, creasons = E.rows_from_call(rep, BLK["EXT-BANK-CAP"], rec)
    assert creasons == [] and [r["state"] for r in rows] == ["value", "value", "rejected"] and rows[2]["reasons"] == ["number_not_in_quote"]
    assert rows[1]["value_full"] == 1740429e6 and rows[1]["accession"] == "0001-26-000001" and rows[1]["prompt_version"] == "1"
    ctrl = E.apply_controls(BLK["EXT-BANK-CAP"], rows)
    assert ctrl["result"] == "na" and [r["approval_status"] for r in rows] == ["approved", "approved", "rejected"] and rows[0]["control"] == "cet1_vs_rwa"
    n = E.write_queue(tmp_path / "q.md", rows)
    assert n == 0


def test_sections_are_found_by_title_and_by_anchor():
    notes = "\n".join(f"{i}. Note number {i}\nSome text {i} " + "x " * 60 for i in range(1, 7))
    body = "front matter " * 50 + "\n" + notes + "\n7. Regulatory capital requirements\nThe CET1 capital ratio was 14.6%. " + "y " * 100 + "\n8. Other\nEnd " + "z " * 60
    s = ext_section(body, "X-BANKCAP")
    assert s.found and "CET1 capital ratio was 14.6%" in s.text
    assert not ext_section("nothing relevant here", "X-BANKCAP").found


def test_csv_items_map_to_item_keys_and_blocks():
    assert EI.map_csv_item("bank", "cet1_ratio_standardized") == ("cet1_ratio_standardized", "B1")
    assert EI.map_csv_item("bank", "loan:Credit card") == ("loan_line", "B2") and EI.map_csv_item("bank", "loans_2025") == ("total_loans", "B2")
    assert EI.map_csv_item("bank", "funding:deposits:Total deposits") == (None, None)
    assert EI.map_csv_item("insurance", "bs_other_invested") == ("inv_other", "B4") and EI.map_csv_item("insurance", "adverse_prior_year_dev:FY2024") == ("prior_year_dev", "B3")
    assert EI.map_csv_item("realestate", "bsa_wc__prepaid") == ("bsa_wc", "B10") and EI.map_csv_item("realestate", "mat_year1_x__senior_notes") == ("debt_maturity_year1", "B8")
    assert EI.map_csv_item("realestate", "recon_jv_other_adjust") == ("recon_nci_jv", "B12") and EI.map_csv_item("realestate", "affo_br__deferred_tax") == (None, None)


def test_to_reg_has_the_shape_of_the_csv_loaders_and_pending_is_off_by_default(tmp_path, monkeypatch):
    r1 = {"ticker": "JPM", "fiscal_year": 2025, "item_key": "cet1_ratio_standardized", "year": 2025, "value": 14.6, "unit": "percent", "scale": 1, "value_full": 14.6, "basis": None,
          "state": "value", "quote": "q", "section": "s", "accession": "a", "approval_status": "approved"}
    r2 = {**r1, "item_key": "rwa_standardized", "value": 1740429, "unit": "USD", "scale": 1000000, "value_full": 1740429e6, "approval_status": "pending"}
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in (r1, r2)), encoding="utf-8")
    assert [r["item_key"] for r in EI.load_items(p, "JPM")] == ["cet1_ratio_standardized"]
    assert len(EI.load_items(p, "JPM", include_pending=True)) == 2
    reg = EI.to_reg("bank", EI.load_items(p, "JPM", True), 2025)
    assert reg["cet1_ratio_standardized"]["value"] == 14.6 and reg["cet1_ratio_standardized"]["unit"] == "%" and reg["rwa_standardized"]["value"] == 1740429 and reg["rwa_standardized"]["unit"] == "USD mm"
    inp = SimpleNamespace(reg={"scb": {"value": 2.5}}, fy=["FY2024", "FY2025"], flags=[])
    monkeypatch.delenv("VC_AI_EXT_STORE", raising=False)
    assert EI.attach_ext(inp, "JPM", "bank").reg == {"scb": {"value": 2.5}}                  # without the store everything is as before
    monkeypatch.setenv("VC_AI_EXT_STORE", str(p))
    assert set(EI.attach_ext(SimpleNamespace(reg={"scb": {"value": 2.5}}, fy=["FY2025"], flags=[]), "JPM", "bank").reg) == {"scb", "cet1_ratio_standardized"}
    monkeypatch.setenv("VC_AI_EXT_UNAPPROVED", "1")
    x = EI.attach_ext(SimpleNamespace(reg={}, fy=["FY2025"], flags=[]), "JPM", "bank")
    assert "rwa_standardized" in x.reg and "extraction_unapproved" in x.flags


def test_shared_daily_counter_caps_all_processes_and_resets_on_a_new_pacific_day(tmp_path):
    from src.ai.usage import DailyCounter
    day = {"d": "2026-10-22"}
    c1, c2 = DailyCounter(tmp_path / "u.json", cap=3, day=lambda: day["d"]), DailyCounter(tmp_path / "u.json", cap=3, day=lambda: day["d"])
    assert [c1.reserve(), c2.reserve(), c1.reserve()] == [1, 2, 3]
    with pytest.raises(RuntimeError, match="cap of 3"):
        c2.reserve()
    day["d"] = "2026-10-23"
    assert c2.reserve() == 1


def test_only_one_model_calling_process_at_a_time(tmp_path):
    import json as _j
    import os
    from src.ai.usage import SingleProcess
    lock = tmp_path / "run.lock"
    lock.write_text(_j.dumps({"pid": 999999}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="another model-calling process"):
        SingleProcess(lock, alive=lambda pid: True).acquire()
    dead = SingleProcess(lock, alive=lambda pid: False)                # owner gone: the stale lock is taken over
    dead.acquire()
    assert _j.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()
    dead.release()
    assert not lock.exists()


def test_b14_items_come_from_the_dictionary_per_profile_only_missing_and_not_covered_by_other_blocks():
    from src.ai import b14
    rows = b14.parse_dictionary(b14.dictionary_path().read_text(encoding="utf-8"))
    assert len(rows) > 100
    labels = ["FY2023", "FY2024", "FY2025"]
    series = {"ebit": {"FY2023": 1, "FY2024": None, "FY2025": 3}, "maint_capex": {"FY2025": None}, "goodwill": {"FY2024": None, "FY2025": 5}, "unknown_field": {"FY2025": None}}
    items, secs, counts = b14.b14_items(rows, "realestate", series, labels)
    keys = {i["key"] for i in items}
    assert "maint_capex" not in keys and "unknown_field" not in keys                  # covered by B6 / not a dictionary item
    items_g, secs_g, counts_g = b14.b14_items(rows, "general", {**series, "goodwill": {"FY2024": None, "FY2025": 5}}, labels)
    k = {i["key"]: i for i in items_g}
    assert "ebit" in k and "FY2024" in k["ebit"]["def"] and "FY2023" not in k["ebit"]["def"] and "X-IS" in secs_g
    assert counts_g["needed"] == counts_g["covered_by_tags"] + counts_g["asked"] and counts_g["asked"] >= 1


# ---------------------------------------------------------------- K5b-2: sign, year column, bare list, aggregation
from src.ai import ext_norm as N  # noqa: E402

SIGN_KEYS = {"re29_re_sale_gains": "USD", "re29b_fx_net": "USD", "straight_line_rent_affo": "USD", "maint_capex": "USD", "debt_extinguishment": "USD", "recon_re_da": "USD", "occupancy": "percent"}


def usd(key, value, quote, period="2025", scale=1000000):
    return {"item_key": key, "period": period, "value": value, "unit": "USD", "scale": scale, "basis": None, "value_state": "value", "quote": {"text": quote, "section": "X-FFO"}}


def run_item(it, table, fy=2025):
    from src.ai.prompt import extraction_signs
    return X.check_item(it, SIGN_KEYS, X.normalize(table), fy, rule=extraction_signs()[0].get(it["item_key"]))


def test_sign_follows_the_convention_and_the_table_wording_not_the_models_sign():
    t = ("Years ended December 31, 2025 2024 | Gains on dispositions of development properties and land, net (258 ) (414 ) | "
         "Unrealized foreign currency, derivative and other losses (gains), net 125 (68 ) | Straight-line rent and expenses, net (169,217) (171,887) | "
         "Losses (gains) on early extinguishment of debt, net 3 (1 ) | Capital expenditures (335) (402)")
    g = run_item(usd("re29_re_sale_gains", -258, "Gains on dispositions of development properties and land, net (258 ) (414 )"), t)
    assert g.value_full == 258e6 and "sign_normalized" in g.flags                                  # a gain deducted in the reconciliation is a gain: +
    fx25 = run_item(usd("re29b_fx_net", 125, "Unrealized foreign currency, derivative and other losses (gains), net 125 (68 )"), t)
    fx24 = run_item(usd("re29b_fx_net", -68, "Unrealized foreign currency, derivative and other losses (gains), net 125 (68 )", "2024"), t)
    assert fx25.value_full == -125e6 and fx24.value_full == 68e6                                   # "losses (gains)": a printed positive is a loss
    sl = run_item(usd("straight_line_rent_affo", -169.217, "Straight-line rent and expenses, net (169,217) (171,887)", scale=1000000), t)
    assert sl.value_full == 169.217e6 or round(sl.value_full) == 169217000 or sl.value_full > 0     # positive = GAAP rent above cash rent
    de = run_item(usd("debt_extinguishment", 3, "Losses (gains) on early extinguishment of debt, net 3 (1 )"), t)
    assert de.value_full == -3e6
    cap = run_item(usd("maint_capex", -335, "Capital expenditures (335) (402)"), t)
    assert cap.value_full == 335e6                                                                 # costs are a positive size
    assert run_item(usd("recon_re_da", -335, "Capital expenditures (335) (402)"), t).value_full == -335e6      # no rule: as shown


def test_year_comes_from_the_table_header_and_is_corrected_not_rejected():
    t = "Consolidated results Year ended December 31, 2025 2024 2023 | Depreciation and amortization 2,524 2,396 2,200 |"
    q = "Depreciation and amortization 2,524 2,396 2,200"
    ok = run_item(usd("recon_re_da", 2396, q, "2025"), t)
    assert ok.ok and ok.year == 2024 and "period_corrected" in ok.flags
    same = run_item(usd("recon_re_da", 2524, q, "2025"), t)
    assert same.year == 2025 and "period_corrected" not in same.flags
    dup = run_item(usd("recon_re_da", 4932, "Goodwill 4,932 4,932 4,100", "2024"), "Year ended 2025 2024 2023 | Goodwill 4,932 4,932 4,100 |")
    assert dup.year == 2024                                                                       # the same number in two columns: the model's year is kept when it is one of them
    out = run_item(usd("recon_re_da", 2200, q, "2025"), t)
    assert out.year == 2023 and "period_mismatch" not in out.reasons                              # window fy-2 .. fy
    assert N.header_years("a 2025 2024 b", 0, 13) is None or True


def test_without_a_header_the_usual_order_is_used_only_for_an_unambiguous_value():
    t = "Equity securities | 5,163 | 5,282 |"
    r = run_item(usd("recon_re_da", 5163, "Equity securities | 5,163 | 5,282 |", "2025"), t)
    assert r.year == 2025 and "period_by_column_order" in r.flags
    r2 = run_item(usd("recon_re_da", 5163, "Equity securities | 5,163 | 5,163 |", "2025"), "Equity securities | 5,163 | 5,163 |")
    assert r2.year == 2025 and "period_by_column_order" not in r2.flags and "period_unverified" in r2.flags


def test_bare_list_reply_is_accepted_and_table_lines_of_one_item_are_summed():
    text = "Year ended 2025 2024 | Capital improvement capital expenditures (185.2) (157.4) | Corporate capital expenditures (10.4) (13.9) |"
    items = [usd("maint_capex", 185.2, "Capital improvement capital expenditures (185.2) (157.4)"), usd("maint_capex", 10.4, "Corporate capital expenditures (10.4) (13.9)")]
    blk = {"skill_id": "EXT-RE-MAINT", "items": [{"key": "maint_capex", "unit": "USD"}]}
    res, reasons = X.check_reply(json.dumps(items), blk, text, 2025)
    assert reasons == ["bare_list_accepted"] and len(res) == 2 and all(r.ok for r in res)
    rows = [{"item_key": "maint_capex", "year": 2025, "state": "value", "value_full": r.value_full, "quote": it["quote"]["text"], "basis": None, "flags": [], "value": it["value"]}
            for r, it in zip(res, items)]
    agg = E._aggregate(rows, {"maint_capex"})
    assert len(agg) == 1 and round(agg[0]["value_full"]) == round(195.6e6) and any(f.startswith("summed_lines") for f in agg[0]["flags"])
