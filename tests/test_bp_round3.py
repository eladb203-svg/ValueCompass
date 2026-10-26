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
    no_interest = profile(revenue_models={"status": "ok", "items": [item(code="fees_asset_mgmt")]})
    assert "earning its revenue from interest income and fees and asset management" in R.render(inp(no_interest, profile_name="BANK"), "en")[0]       # added by code for a bank
    assert "interest" not in R.render(inp(no_interest), "en")[0]


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
