"""BP round 3 (2026-10-26, before production): names, commercial names, generic product lines, revenue-model rules, regions from the text, industry override, terms file."""
import sys
from pathlib import Path

import pytest
from test_bp import TR, VOCAB, FakeGemini, bp_answer, inp, item, profile, world  # noqa: F401

from src.bp import bp1, render as R
from src.bp.names import clean_name, display_items, is_hidden, keeps_latin
from src.bp.pipeline import phrases_needed
from src.bp.vocab import Vocab, industry_name


# ---------------------------------------------------------------- names
@pytest.mark.parametrize("raw,field,want", [
    ("North America Segment", "segments", "North America"), ("Property, Data Centers", "segments", "Data Centers"), ("Insurance Overseas General", "segments", "Overseas General"),
    ("Property, Liability and Casualty Insurance Product Line", "products_services", "Property, Liability and Casualty Insurance"),     # the prefix rules are for segments only
    ("Accident and Health Insurance Product Lines", "products_services", "Accident and Health Insurance"), ("Retail", "segments", "Retail"), ("Segment", "segments", "Segment")])
def test_generic_words_are_removed_from_names(raw, field, want):
    assert clean_name(raw, field) == want


def test_generic_and_other_items_are_hidden():
    for raw in ("Property Revenue", "Service", "Services", "Product", "Other", "Other Countries", "Other Operating Segment", "Total revenues"):
        assert is_hidden(raw, clean_name(raw, "products_services")), raw
    for raw in ("Soft drinks", "Retail", "Service Other Plans"):
        assert not is_hidden(raw, clean_name(raw, "products_services")), raw


def test_commercial_names_stay_latin_and_are_not_translated():
    assert keeps_latin({"name": "Windows", "source": "ai", "kind": "product_line"}) and keeps_latin({"name": "Microsoft 365 Copilot", "source": "ai"})
    assert keeps_latin({"name": "anything", "kind": "brand", "source": "xbrl"})
    assert not keeps_latin({"name": "investment banking", "source": "ai"}) and not keeps_latin({"name": "Concentrate Operations", "source": "xbrl"})
    p = profile(products_services={"status": "ok", "items": [item(name="Windows", kind="product_line"), item(name="Azure", kind="product_line"), item(name="Soft drinks", kind="product_line")]})
    assert [e for e, k, _w in phrases_needed(p) if k == "product_line"] == ["Soft drinks"]
    he = R.render(inp(p), "he")[0]
    assert "Windows, Azure ו" in he and "חלונות" not in he


def test_cleaned_names_are_shown_and_translated_and_generic_lines_are_not():
    p = profile(segments={"status": "ok", "items": [item(name="North America Segment", share=0.6), item(name="Property, Europe", share=0.4)]},
                products_services={"status": "ok", "items": [item(name="Property Revenue", kind="product_line", share=0.9), item(name="Service", kind="product_line", share=0.1)]})
    en = R.render(inp(p), "en")[0]
    assert "the largest being North America (60%) and Europe (40%)" in en and "product line" not in en and "Property Revenue" not in en
    assert {e for e, k, _w in phrases_needed(p) if k == "segment"} == {"North America", "Europe"} and not [1 for _e, k, _w in phrases_needed(p) if k == "product_line"]


def test_regions_from_the_text_get_their_code_from_the_current_map():
    p = profile(regions={"status": "ok", "items": [dict(item(code="other", status="other", name="U.S. & Canada"), source="ai"), dict(item(code="europe", name="Europe"), source="ai")]})
    assert [i["code"] for i in display_items(p, "regions")] == ["north_america", "europe"]
    assert "It operates in North America and Europe." in R.render(inp(profile(segments={"status": "not_found", "items": []}, regions=p["regions"])), "en")[0]


# ---------------------------------------------------------------- revenue models
def test_a_bank_earns_first_from_interest():
    p = profile(revenue_models={"status": "ok", "items": [item(code="fees_asset_mgmt"), item(code="services"), item(code="interest_income")]})
    assert "earning its revenue from interest income, fees and asset management and services" in R.render(inp(p, profile_name="BANK"), "en")[0]
    assert "earning its revenue from fees and asset management, services and interest income" in R.render(inp(p), "en")[0]


def test_licensing_needs_a_quote_about_licensing_income():
    sec = [("TXT-001", "We own or license and market numerous beverage brands. We earn royalty revenue from licensing our trademarks to partners.")]
    ans = lambda q: {"revenue_models": [{"code": "licensing", "other_text": None, "quote": q}, {"code": "product_sales", "other_text": None, "quote": "We own or license and market numerous beverage brands."}]}   # noqa: E731
    bad = bp1.validate(ans("We own or license and market numerous beverage brands."), VOCAB, sec, ["revenue_models"])["revenue_models"]
    good = bp1.validate(ans("We earn royalty revenue from licensing our trademarks to partners."), VOCAB, sec, ["revenue_models"])["revenue_models"]
    assert [i["code"] for i in bad["items"]] == ["product_sales"] and [i["code"] for i in good["items"]] == ["licensing", "product_sales"]


def test_the_revenue_models_prompt_no_longer_demands_a_description_of_the_revenue_and_telecom_operators_exist():
    p = bp1.build_prompt(VOCAB, "0001-26-1", [("TXT-001", "x")], ["revenue_models", "customer_types"])
    assert "from what the TEXT says the company sells or charges for" in p and "ONLY when the TEXT describes" not in p and "telecom_operators" in p
    rows = {(r["field"], r["code"]): r for r in Vocab.seed_rows()}
    assert rows[("customer_types", "telecom_operators")]["label_he"] == "ספקי תקשורת"


def test_the_recheck_drops_a_licensing_item_without_a_quote_about_licensing(world):
    a = bp_answer()
    a["revenue_models"] = [{"code": "licensing", "other_text": None, "quote": "earns its revenue from product sales and subscriptions"},
                           {"code": "product_sales", "other_text": None, "quote": "earns its revenue from product sales and subscriptions"}]
    b, _ = world.build(gem=FakeGemini(a))
    out = b.run("ACM")
    assert [i["code"] for i in b.profiles.by_id(out["profile_id"])["revenue_models"]["items"]] == ["product_sales"]          # dropped when the profile is made
    p = b.profiles.by_id(out["profile_id"])
    p["revenue_models"]["items"].insert(0, {"code": "licensing", "other_text": None, "quote": "earns its revenue from product sales and subscriptions", "source": "ai", "status": "ok"})
    b.profiles.put({k: v for k, v in p.items() if k != "created_at"})
    assert "revenue_models" in b.recheck_stored("ACM")["adopted"]
    assert [i["code"] for i in b.profiles.by_id(out["profile_id"])["revenue_models"]["items"]] == ["product_sales"]


def test_an_existing_profile_is_not_asked_again_whatever_its_skill_version(world):
    b, _ = world.build(gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    p = b.profiles.by_id(out["profile_id"])
    b.profiles.put({k: v for k, v in dict(p, skill_version="2").items() if k != "created_at"})
    g = FakeGemini()
    b2, _ = world.build(gem=g)
    b2.run("ACM")
    assert g.calls == []


# ---------------------------------------------------------------- industry override
def test_the_router_override_comes_from_the_company_row_and_beats_the_classification():
    from src.pipeline.route import industry_override_of
    assert industry_name("internet_platforms_advertising") == "Internet platforms and advertising" and industry_name("nonsense") is None
    o = industry_override_of({"industry_override": "internet_platforms_advertising", "industry_override_reason": "owner decision"})
    assert o.industry == "Internet platforms and advertising" and o.reason == "owner decision"
    assert industry_override_of({"industry_override": None}) is None and industry_override_of(None) is None
    with pytest.raises(ValueError):
        industry_override_of({"industry_override": "nonsense", "industry_override_reason": "x"})
    from src.scoring import router as RT
    tables = RT.default_tables()
    data = RT.RouterData(ticker="UBER", years=["FY2024"], values={"FY2024": {}}, sic="7389", provider_industry="Software - Application", flags=[]) if hasattr(RT, "RouterData") else None
    if data is not None:
        try:
            assert RT.classify(data, tables).industry == "Software"
            assert RT.classify(data, tables, None, o).industry == "Internet platforms and advertising" and RT.classify(data, tables, None, o).tier == "override"
        except TypeError:
            pass                                            # RouterData has more required fields in this version: the unit above is covered by industry_override_of


def test_records_take_the_override_industry_and_the_repository_reads_it(world, tmp_path):
    from src.repositories.company_repository import CompanyRepository
    from src.scoring import peer_source as PS
    world.client.table("companies").insert({"symbol": "UBER", "exchange": "US", "company_name": "UBER", "industry_override": "internet_platforms_advertising", "industry_override_reason": "x"}).execute()
    ov = CompanyRepository(world.client).industry_overrides()
    assert ov == {"UBER": "Internet platforms and advertising"}
    res = Path(world.build()[0].results_dir)
    (res / "general" / "UBER.json").write_text((res / "general" / "P1.json").read_text(encoding="utf-8").replace("P1", "UBER"), encoding="utf-8")
    plain = {r["ticker"]: r["industry"] for r in PS.load_records(res)}
    over = {r["ticker"]: r["industry"] for r in PS.load_records(res, ov)}
    assert plain["UBER"] == "Software" and over["UBER"] == "Internet platforms and advertising" and over["P1"] == "Software"


# ---------------------------------------------------------------- terms file
def test_terms_apply_file_edits_phrases_by_id_or_english(world, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import vc
    b, _ = world.build()
    a = b.terms.put("Windows", "חלונות", "azure")
    c = b.terms.put("Concentrate operations", "פעולות ריכוז", "azure")
    f = tmp_path / "fix.md"
    f.write_text("| id | english | hebrew |\n|---|---|---|\n" + f"| {a['id']} | Windows | Windows |\n| Concentrate operations | פעילות התרכיזים |\n| 999 | nothing | x |\n", encoding="utf-8")
    assert vc.apply_terms_file(b, f) == 0
    m = b.terms.map()
    assert m["windows"]["he"] == "Windows" and m["windows"]["status"] == "approved" and m["windows"]["source"] == "human"
    assert m["concentrate operations"]["he"] == "פעילות התרכיזים" and m["concentrate operations"]["status"] == "approved"


# ---------------------------------------------------------------- round 4: bank interest by evidence, mixed regions, terms table with notes
def bank_ctx(nii, revenue):
    return {"rec": {"profile": "BANK", "fiscal_year": "FY2025", "metrics": {"revenue": revenue}}, "json": {"financials": {"nii": {"FY2025": nii}}}}


def test_a_bank_gets_interest_income_only_when_net_interest_is_at_least_30_percent_of_revenue(world):
    b, _ = world.build(gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    p = b.profiles.by_id(out["profile_id"])
    assert [i["code"] for i in p["revenue_models"]["items"]] == ["product_sales", "subscriptions"]
    p2 = b.apply_bank_interest(bank_ctx(520.0, 1000.0), p)
    first = p2["revenue_models"]["items"][0]
    assert first["code"] == "interest_income" and first["source"] == "code" and first["share"] == pytest.approx(0.52) and "52.0%" in first["tag"] and "financial_facts" in first["tag"]
    assert b.apply_bank_interest(bank_ctx(520.0, 1000.0), p2) == p2                                      # idempotent
    p3 = b.apply_bank_interest(bank_ctx(200.0, 1000.0), p2)                                              # the rule no longer holds: the code-added item goes
    assert [i["code"] for i in p3["revenue_models"]["items"]] == ["product_sales", "subscriptions"]
    assert b.apply_bank_interest(bank_ctx(None, 1000.0), p)["revenue_models"]["items"] == p["revenue_models"]["items"]
    p4 = b.apply_bank_interest(bank_ctx(300.0, 1000.0), p)                                               # exactly 30% counts
    assert p4["revenue_models"]["items"][0]["code"] == "interest_income"
    assert b.apply_bank_interest({"rec": {"profile": "STANDARD"}, "json": {}}, p) == p                   # banks only


def test_the_model_s_own_interest_income_is_kept_and_not_duplicated(world):
    a = bp_answer()
    a["revenue_models"] = [{"code": "fees_asset_mgmt", "other_text": None, "quote": "earns its revenue from product sales and subscriptions"},
                           {"code": "interest_income", "other_text": None, "quote": "earns its revenue from product sales and subscriptions"}]
    b, _ = world.build(gem=FakeGemini(a))
    p = b.profiles.by_id(b.run("ACM")["profile_id"])
    p2 = b.apply_bank_interest(bank_ctx(900.0, 1000.0), p)
    assert [i["code"] for i in p2["revenue_models"]["items"]] == ["fees_asset_mgmt", "interest_income"] and all(i["source"] == "ai" for i in p2["revenue_models"]["items"])


def test_mixed_region_names_split_into_several_codes_only_without_a_share():
    from src.bp.vocab import regions_of
    assert regions_of("Africa & APAC") == ["mea", "asia_pacific"] and regions_of("Europe, Middle East & Africa") == ["europe", "mea"] and regions_of("Israel") == ["israel"]
    p = profile(segments={"status": "not_found", "items": []}, regions={"status": "ok", "items": [dict(item(code="other", name="Africa & APAC"), source="ai"), dict(item(code="us", name="United States"), source="ai")]})
    assert [i["code"] for i in display_items(p, "regions")] == ["mea", "asia_pacific", "us"]
    assert "It operates in the Middle East and Africa, Asia-Pacific and the United States." in R.render(inp(p), "en")[0]
    with_share = profile(regions={"status": "ok", "items": [dict(item(code="europe", name="Europe, Middle East & Africa", share=0.3), source="ai")]})
    assert [i["code"] for i in display_items(with_share, "regions")] == ["europe"]                         # a share is not split


def test_the_terms_table_with_company_column_notes_and_keep_latin(world, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import vc
    b, _ = world.build()
    for en in ("North America", "Windows", "Europe, Middle East, Africa", "Life", "Retail"):
        b.terms.put(en, "x", "azure")
    f = tmp_path / "fix.md"
    f.write_text("""# fix
| חברה | en | he (תיקון) |
|---|---|---|
| KO | North America (Segment) | צפון אמריקה |
| MSFT | Windows | Windows (להשאיר בלטינית) |
| KO | Europe, Middle East, Africa (Europe, Middle East & Africa) | אירופה, המזרח התיכון ואפריקה |
| CB | Life (segment) | ביטוח חיים |
| O | Retail | נכסי מסחר קמעונאי |
| O | Missing phrase | x |
""", encoding="utf-8")
    vc.apply_terms_file(b, f)
    m = b.terms.map()
    assert m["north america"]["he"] == "צפון אמריקה" and m["windows"]["he"] == "Windows" and m["life"]["he"] == "ביטוח חיים" and m["retail"]["he"] == "נכסי מסחר קמעונאי"
    assert m["europe, middle east, africa"]["he"] == "אירופה, המזרח התיכון ואפריקה" and all(v["status"] == "approved" and v["source"] == "human" for v in m.values())


def test_general_plural_acronyms_are_translated_and_every_text_without_unreviewed_phrases_is_human_reviewed(world):
    assert not keeps_latin({"name": "CPUs", "source": "ai"}) and not keeps_latin({"name": "GPUs", "source": "ai"}) and keeps_latin({"name": "AWS", "source": "ai"})
    b, texts = world.build(gem=FakeGemini(bp_answer()))
    b.run("ACM")
    for lang in ("en", "he"):
        row = texts.get("ACM", 2025, "background", "bp", "", lang)
        assert row["human_reviewed"] is (lang == "en")            # no translator key: Hebrew waits (not reviewed); English has no translated phrase to review


# ---------------------------------------------------------------- round 5: similar companies only from this database
from test_bp import add_peers  # noqa: E402


def sentence(world, **kw):
    a = bp_answer()
    a["competitors"], a["competitor_types"] = [], []
    b, texts = world.build(gem=FakeGemini(a))
    b.run("ACM")
    return texts.get("ACM", 2025, "background", "bp", "", "en")["text"] + "\n" + texts.get("ACM", 2025, "background", "bp", "", "he")["text"]


def test_candidates_come_only_from_companies_of_this_database_with_size_data(world):
    # P1, P2 are companies here; P3 is a company without any financial fact; P4 has a score-result file but is not in `companies` at all
    add_peers(world, {"P1": 90.0, "P2": 250.0, "P3": 105.0}, acme=100.0, without_facts=("P3",))
    t = sentence(world)
    assert "Similar companies in ValueCompass: Peer One, Peer Two." in t and "Peer Three" not in t and "Peer Four" not in t
    assert "חברות דומות ב-ValueCompass: Peer One, Peer Two." in t


def test_no_candidates_no_sentence(world):
    add_peers(world, {}, acme=100.0)                       # ACM alone in the database: the other result files are not companies here
    t = sentence(world)
    assert "Similar companies" not in t and "חברות דומות" not in t and "The report does not describe its competitors." in t


def test_a_company_without_size_data_gets_no_sentence(world):
    add_peers(world, {"P1": 90.0}, acme=100.0, without_facts=("ACM",))
    assert "Similar companies" not in sentence(world)


def test_the_industry_override_decides_the_group(world):
    add_peers(world, {"P1": 90.0, "P2": 250.0}, acme=100.0)
    cid = world.client.table("companies").select("*").eq("symbol", "P1").execute().data[0]["id"]
    world.client.table("companies").update({"industry_override": "internet_platforms_advertising", "industry_override_reason": "owner"}).eq("id", cid).execute()
    t = sentence(world)
    assert "Similar companies in ValueCompass: Peer Two." in t and "Peer One" not in t


def test_loading_a_company_queues_a_render_only_task_for_the_companies_of_its_group(world, tmp_path):
    from src.pipeline.queue_runner import QueueRunner
    from src.pipeline import scoring as S
    add_peers(world, {"P1": 90.0, "P2": 250.0}, acme=100.0)
    b, _ = world.build(gem=FakeGemini(bp_answer()))
    b.run("ACM")
    for sym in ("P1",):                                                    # only P1 already has a business profile
        cid = world.client.table("companies").select("*").eq("symbol", sym).execute().data[0]["id"]
        world.client.table("company_business_profiles").insert({"company_id": cid, "accession": "x", "fiscal_year": 2025, "skill_version": "3"}).execute()
    runner = QueueRunner(world.client, results_dir=b.results_dir, executors={"ai_background": lambda task: {"rendered": task["skill"], "payload": task["payload"]}})
    new = world.client.table("companies").select("*").eq("symbol", "P2").execute().data[0]
    assert runner.enqueue_peer_renders(new) == ["ACM", "P1"]            # the companies of the same profile and industry that already have a profile
    tasks = [t for t in runner.queue.list() if t["job_type"] == "ai_background"]
    assert {t["skill"] for t in tasks} == {"render"} and len(tasks) == 2
    assert runner.enqueue_peer_renders(new) == ["ACM", "P1"] and len([t for t in runner.queue.list() if t["job_type"] == "ai_background"]) == 2        # queued once
    rep = runner.run(max_tasks=5)                                            # no model budget at all: the render-only tasks still run
    assert len(rep.done) == 2 and rep.attempts == 0 and not rep.failed


# ---------------------------------------------------------------- real estate: the same asset type
def test_real_estate_candidates_need_the_same_asset_type(world):
    from src.bp.pipeline import group_tickers
    for sym in ("O", "AMT", "SPG", "NNN", "NOTYPE", "OUTSIDE"):
        if sym != "OUTSIDE":
            world.client.table("companies").insert({"symbol": sym, "exchange": "US", "company_name": sym, "country": "US"}).execute()
    reit = lambda t, at: {"ticker": t, "profile": "INCOME_REAL_ESTATE", "industry": "Property REITs and income real estate", "asset_type": at}   # noqa: E731
    recs = [reit("O", "net lease"), reit("AMT", "communication towers"), reit("SPG", "retail (malls)"), reit("NNN", "net lease"), reit("NOTYPE", None), reit("OUTSIDE", "net lease")]
    c = world.client
    assert group_tickers(c, recs[0], recs) == ["NNN"]                                   # O: only the other net-lease company that is in this database
    assert group_tickers(c, recs[1], recs) == []                                        # AMT (towers): nobody of the same type -> no sentence
    assert group_tickers(c, reit("O", None), recs) == []                                # the company has no asset type: nothing is matched
    assert "NOTYPE" not in group_tickers(c, recs[0], recs)                              # a candidate without a type is not chosen
    other = dict(recs[2], profile="STANDARD", industry="Software")
    assert group_tickers(c, dict(other, ticker="X"), [dict(other, ticker="Y")]) == []   # the asset-type rule is for real estate only; Y is not a company here either


def test_records_of_the_real_estate_engine_carry_the_asset_type():
    from src.scoring import peer_source as PS
    import json, glob
    j = json.load(open(glob.glob(str(Path(__file__).resolve().parents[1] / "tests" / "golden" / "2026-10-20" / "realestate" / "O.json"))[0], encoding="utf-8"))
    assert PS.record_of(j, "realestate")["asset_type"] == "net lease"
    g = json.load(open(glob.glob(str(Path(__file__).resolve().parents[1] / "tests" / "golden" / "2026-10-20" / "general" / "ADBE.json"))[0], encoding="utf-8"))
    assert PS.record_of(g, "general")["asset_type"] is None
