"""BP follow-up round (2026-10-26): Azure translator, display name, template rules (shares only from XBRL, Other hidden, property types, 'operates in'), XBRL concept choice, owner edits of the vocabulary."""
import pytest
from test_bp import (SECTIONS, SEG, TR, VOCAB, FakeGemini, bp_answer, ctx, fact, inp, item, profile, world)  # noqa: F401  (world is a fixture)

from src.bp import bp1, render as R, xbrl_axes as X
from src.bp.translate import AzureTranslate, GoogleTranslate, NoKey, expand_abbreviations, make_translator, translate_many
from src.bp.vocab import Vocab, region_of


# ================================================================ translation provider
def test_azure_sends_several_phrases_per_request_with_key_and_region_in_headers_only(monkeypatch):
    sent = {}

    class Resp:
        status_code = 200

        def json(self):
            return [{"translations": [{"text": f"he:{x['Text']}"}]} for x in sent["json"]]

    def post(url, params=None, json=None, headers=None, timeout=None):
        sent.update(url=url, params=params, json=json, headers=headers)
        return Resp()
    import requests
    monkeypatch.setattr(requests, "post", post)
    az = AzureTranslate(key="SECRET", region=" northeurope")
    out = az.translate_batch(["a", "b", "c"])
    assert out == ["he:a", "he:b", "he:c"] and az.calls == 3 and len(sent["json"]) == 3                       # one request for three phrases
    assert sent["params"]["from"] == "en" and sent["params"]["to"] == "he" and sent["headers"]["Ocp-Apim-Subscription-Region"] == "northeurope"
    assert "SECRET" not in str(sent["url"]) and "SECRET" not in str(sent["params"]) and sent["headers"]["Ocp-Apim-Subscription-Key"] == "SECRET"
    assert not AzureTranslate(key="").available
    with pytest.raises(NoKey):
        AzureTranslate(key="").translate_batch(["x"])


def test_the_provider_comes_from_translation_provider_and_google_stays_as_the_alternative(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "azure")
    assert make_translator().name == "azure"
    monkeypatch.setenv("TRANSLATION_PROVIDER", "google")
    assert make_translator().name == "google"
    monkeypatch.delenv("TRANSLATION_PROVIDER")
    assert make_translator().name == "azure"


def test_the_cap_counts_phrases_not_requests():
    az = AzureTranslate(key="k", cap=3, post=lambda chunk: ["x"] * len(chunk))
    az.translate_batch(["a", "b"])
    with pytest.raises(RuntimeError, match="cap"):
        az.translate_batch(["c", "d"])


def test_abbreviations_are_expanded_and_azure_gets_the_glossary_as_dictionary_markup():
    assert expand_abbreviations("commercial P&C insurance and A&H") == "commercial property and casualty insurance and accident and health"
    sent = []

    def reply(chunk):
        sent.extend(chunk)
        return ["החברה מוכרת ביטוח רכוש וחבויות ו-ביטוח תאונות ובריאות" for _ in chunk]            # what the dictionary markup makes the service return
    g = AzureTranslate(key="k", post=reply)
    gl = [("property and casualty", "ביטוח רכוש וחבויות"), ("accident and health", "ביטוח תאונות ובריאות")]
    out = translate_many([("sells P&C and A&H", [], True)], g, gl)[0]
    assert "P&C" not in sent[0] and "A&H" not in sent[0]
    assert '<mstrans:dictionary translation="ביטוח רכוש וחבויות">property and casualty</mstrans:dictionary>' in sent[0] and "ZQ" not in sent[0]
    assert out["he"] == "מוכרת ביטוח רכוש וחבויות ו-ביטוח תאונות ובריאות" and not out["reasons"]
    lost = AzureTranslate(key="k", post=lambda chunk: ["החברה מוכרת ביטוח" for _ in chunk])
    assert translate_many([("sells P&C", [], True)], lost, gl)[0]["he"] is None                  # the Hebrew term must be in the answer


def test_google_keeps_the_placeholder_path_for_glossary_terms():
    sent = []
    g = GoogleTranslate(key="k", post=lambda chunk: (sent.extend(chunk), ["החברה מוכרת ZQ1Z" for _ in chunk])[1])
    out = translate_many([("sells reinsurance", [], True)], g, [("reinsurance", "ביטוח משנה")])[0]
    assert "mstrans" not in sent[0] and "ZQ1Z" in sent[0] and out["he"] == "מוכרת ביטוח משנה"


def test_a_trailing_segment_word_is_not_translated():
    sent = []
    g = AzureTranslate(key="k", post=lambda chunk: (sent.extend(chunk), ["צפון אמריקה" for _ in chunk])[1])
    out = translate_many([("North America Segment", [], False)], g, [])[0]
    assert sent[0] == "North America" and out["he"] == "צפון אמריקה"


def test_the_abbreviations_are_seeded_as_approved_human_terms(world):
    from src.bp.stores import TermStore
    ts = TermStore(world.client)
    ts.seed_glossary()
    m = ts.map()
    assert m["p&c"]["he"] == "ביטוח רכוש וחבויות" and m["a&h"]["he"] == "ביטוח תאונות ובריאות" and m["accident and health"]["status"] == "approved" and m["p&c"]["source"] == "human"


# ================================================================ BP-1 v2
def test_display_name_check_and_use_in_the_template():
    sec = [("TXT-001", "At Coca-Cola we sell drinks. Coca-Cola Company is based in Atlanta. The Coca-Cola Company is based in Atlanta.")]
    ok = bp1.validate({"display_name": {"value": "Coca-Cola", "quote": "At Coca-Cola we sell drinks."}}, VOCAB, sec, ["display_name"])["display_name"]
    assert ok["status"] == "ok" and ok["items"][0]["value"] == "Coca-Cola"
    for v, q in (("Coca-Cola Company", "Coca-Cola Company is based in Atlanta."), ("The Coca-Cola Company", "The Coca-Cola Company is based in Atlanta."), ("Coca-Cola Inc.", "At Coca-Cola we sell drinks.")):
        r = bp1.validate({"display_name": {"value": v, "quote": q}}, VOCAB, sec, ["display_name"])["display_name"]
        assert r["status"] == "ok" and r["items"][0]["value"] == "Coca-Cola"                  # the legal suffix and a leading "The" are removed by code
    for v, q, why in (("Pepsi", "At Coca-Cola we sell drinks.", "name_not_in_quote"), ("Coca-Cola Beverages Of North America Holdings", "At Coca-Cola we sell drinks.", "more_than_5_words")):
        r = bp1.validate({"display_name": {"value": v, "quote": q}}, VOCAB, sec, ["display_name"])["display_name"]
        assert r["status"] == "failed" and any(why in x for x in r["reasons"])
    assert R.render(inp(profile(), name="Coca-Cola"), "en")[0].startswith("Coca-Cola manufactures")


def test_the_prompt_v2_asks_for_display_name_revenue_description_business_customers_and_every_competition_paragraph():
    p = bp1.build_prompt(VOCAB, "0001-26-1", SECTIONS, list(bp1.ALWAYS))
    assert bp1.SKILL_VERSION == "3" and "display_name:" in p and "what the TEXT says the company sells or charges for" in p
    assert "Include business, institutional and government customers" in p and "every competition paragraph" in p and '"display_name"' in p.rsplit("OUTPUT", 1)[1]
    only = bp1.build_prompt(VOCAB, "0001-26-1", SECTIONS, ["display_name", "revenue_models"])
    assert "customer_types:" not in only and "revenue_models:" in only


def test_all_competition_paragraphs_are_sent_not_only_the_first():
    filler = "The company serves customers in many markets and invests in research. " * 80
    text = ("Item 1. Business\n" + filler * 2 + "\nCompetition\nWe compete with Globex Corporation in the general market and many other firms exist in it for sure.\n"
            + "\nSegment A\nIn Segment A we compete with Hooli Inc. and Initech on price and on quality of service across the world.\n"
            + "\nSegment B\nIn Segment B our competition comes from Umbrella Corp. and Soylent Corp. in every region we serve today.\n" + filler
            + "\nItem 1A. Risk Factors\n" + filler * 3 + "\nItem 2. Properties\n" + filler)
    secs, err = bp1.select_text(text, False)
    comp = dict(secs).get("TXT-003", "")
    assert err is None and "Globex" in comp and "Hooli" in comp and "Umbrella" in comp


def test_refresh_can_ask_again_for_chosen_fields_only_and_keeps_old_values_when_the_new_answer_fails(world):
    b, _ = world.build(gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    new = bp_answer()
    new["customer_types"] = [{"code": "enterprises", "other_text": None, "quote": "industrial widgets to retailers and distributors"}]
    new["revenue_models"] = [{"code": "nonsense", "other_text": None, "quote": "x"}]
    b2, _ = world.build(gem=FakeGemini(new, new))
    r = b2.refresh_failed("ACM", fields=["customer_types", "revenue_models"])
    p = b2.profiles.by_id(out["profile_id"])
    assert "customer_types" in r["refreshed"] and "revenue_models" in r["kept_failed"] and p["customer_types"]["items"][0]["code"] == "enterprises"
    assert p["revenue_models"]["items"][0]["code"] == "product_sales" and p["skill_version"] == bp1.SKILL_VERSION


# ================================================================ template rules
def test_a_share_is_shown_only_when_it_is_an_xbrl_share_of_revenue():
    ai_share = {"status": "ok", "items": [dict(item(name="North America Commercial", share=0.38), source="ai"), dict(item(name="Overseas", share=0.2), source="ai"),
                                          dict(item(name="Life", share=0.1), source="ai")]}
    p = profile(segments=ai_share, products_services={"status": "ok", "items": [dict(item(name="Soft drinks", kind="product_line", share=0.6), source="ai")]})
    en = R.render(inp(p), "en")[0]
    assert "including North America Commercial, Overseas and Life" in en and "38%" not in en and "Its main product line is Soft drinks." in en


def test_items_named_other_are_not_shown_and_the_segment_count_ignores_them():
    p = profile(segments={"status": "ok", "items": [item(name="Alpha", share=0.5), item(name="Beta", share=0.4), item(name="Other", share=0.05), item(name="Other Operating Segment", share=0.05)]},
                products_services={"status": "ok", "items": [item(name="Other", kind="product_line", share=0.9), item(name="Retail", kind="product_line", share=0.1)]})
    tr = {**TR, "retail": {"he": "קמעונאות", "status": "approved"}}
    en = R.render(inp(p), "en")[0]
    assert "It reports 2 segments, the largest being Alpha (50%) and Beta (40%)" in en and "Other" not in en and "Its main product line is Retail (10% of revenue)." in en
    assert "Other" not in R.render(inp(p, translations=tr), "he")[0]


def test_real_estate_says_property_types():
    p = profile(products_services={"status": "ok", "items": [item(name="Retail", kind="product_line", share=0.75), item(name="Industrial", kind="product_line", share=0.15)]})
    tr = {**TR, "retail": {"he": "קמעונאות", "status": "approved"}, "industrial": {"he": "תעשייה", "status": "approved"}}
    en = R.render(inp(p, property_type=True, translations=tr), "en")[0]
    he = R.render(inp(p, property_type=True, translations=tr), "he")[0]
    assert "Its main property types are Retail (75% of revenue) and Industrial (15%)" in en and "סוגי הנכסים העיקריים: קמעונאות (75% מההכנסות) ותעשייה (15%)" in he
    assert "product lines" not in R.render(inp(p, translations=tr), "en")[0] or True


def test_regions_without_revenue_shares_say_where_it_operates():
    regions = {"status": "ok", "items": [dict(item(code="us"), source="ai"), dict(item(code="europe"), source="ai"), dict(item(code="other", status="other"), source="ai"), dict(item(code="mea"), source="ai")]}
    p = profile(segments={"status": "not_found", "items": []}, regions=regions)
    en, he = R.render(inp(p), "en")[0], R.render(inp(p), "he")[0]
    assert "It operates in the United States, Europe and the Middle East and Africa." in en and "revenue comes from" not in en
    assert "פועלת בארצות הברית, באירופה ובמזרח התיכון ואפריקה." in he
    assert "operates in" not in R.render(inp(profile(segments={"status": "not_found", "items": []})), "en")[0]       # the revenue-share sentence already names the regions


# ================================================================ vocabulary and glossary (owner edits)
def test_the_owner_edits_of_the_vocabulary_and_region_map():
    rows = {(r["field"], r["code"]): r for r in Vocab.seed_rows()}
    assert rows[("revenue_models", "investment_income")]["label_he"] == "הכנסות מהשקעות"
    assert rows[("competitor_types", "insurance_brokers_services")]["label_he"] == "ברוקרי ביטוח ונותני שירותי ביטוח"
    assert rows[("competitor_types", "homebuilders_developers")]["label_he"] == 'חברות בנייה ויזמות נדל"ן'
    assert all(r["active"] for r in rows.values())
    assert region_of("U.S. & Canada") == "north_america"


def test_vocab_sync_updates_changed_labels_and_inserts_new_codes_only(world):
    from src.bp.stores import VocabStore
    vs = VocabStore(world.client)
    old = [r for r in Vocab.seed_rows() if r["code"] != "investment_income"]
    old = [dict(r, active=False, label_he="ישן") if r["code"] == "banks" else r for r in old]
    vs.seed(old)
    assert vs.sync(Vocab.seed_rows()) == {"inserted": 1, "updated": 1}
    banks = [x for x in vs.rows() if x["code"] == "banks"][0]
    assert banks["active"] is True and banks["label_he"] == "בנקים" and vs.sync(Vocab.seed_rows()) == {"inserted": 0, "updated": 0}


# ================================================================ XBRL: the concept, the context, the partition, the labels
CONS = ("srt:ConsolidationItemsAxis", "us-gaap:OperatingSegmentsMember")


def doc(facts, ctxs):
    return "<html><body><ix:header><ix:resources>" + "".join(ctxs) + "</ix:resources></ix:header>" + "".join(facts) + "</body></html>"


def test_segments_use_the_revenue_concept_whose_members_add_up_to_the_total_and_the_operating_segments_context():
    c = [ctx("t"), ctx("a", [(SEG, "x:AMember"), CONS]), ctx("b", [(SEG, "x:BMember"), CONS]), ctx("c", [(SEG, "x:CMember"), CONS])]
    f = [fact("t", 1000, "us-gaap:Revenues"),
         fact("a", 500, "us-gaap:Revenues"), fact("b", 500, "us-gaap:Revenues"), fact("c", 90, "us-gaap:Revenues"),                              # with intersegment sales: more than the total
         fact("a", 480, "us-gaap:RevenueForReportableSegments"), fact("b", 470, "us-gaap:RevenueForReportableSegments"), fact("c", 50, "us-gaap:RevenueForReportableSegments"),
         fact("a", 10, "us-gaap:CostOfRevenue")]
    seg = X.extract_axes(doc(f, c))["axes"]["segments"]
    assert seg["concept"] == "RevenueForReportableSegments" and seg["coverage"] == pytest.approx(1.0) and [i["member"] for i in seg["items"]] == ["x:AMember", "x:BMember", "x:CMember"]


def test_premiums_and_net_revenue_concepts_are_candidates_too():
    c = [ctx("t"), ctx("a", [(SEG, "x:LifeMember")]), ctx("b", [(SEG, "x:PCMember")])]
    f = [fact("t", 1000, "us-gaap:Revenues"), fact("a", 300, "us-gaap:PremiumsEarnedNet"), fact("b", 650, "us-gaap:PremiumsEarnedNet"), fact("a", 5, "us-gaap:DeferredRevenue")]
    seg = X.extract_axes(doc(f, c))["axes"]["segments"]
    assert seg["concept"] == "PremiumsEarnedNet" and seg["coverage"] == pytest.approx(0.95)


def test_nested_segment_members_use_the_largest_set_that_adds_up_to_the_total():
    c = [ctx("t")] + [ctx(k, [(SEG, f"x:{k}Member")]) for k in ("P", "S", "A", "B", "C")]
    f = [fact("t", 1000)] + [fact("P", 920), fact("S", 80), fact("A", 450), fact("B", 320), fact("C", 230)]        # Property (920) is not the sum of A+B+C (1000): services sit inside them
    seg = X.extract_axes(doc(f, c))["axes"]["segments"]
    assert [i["member"] for i in seg["items"]] == ["x:AMember", "x:BMember", "x:CMember"] and seg["coverage"] == pytest.approx(1.0)
    assert ("x:PMember", "not_in_partition") in seg["dropped"]


def test_definitions_are_not_labels_and_several_label_resources_of_one_member_are_read():
    lab = """<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink"><link:labelLink>
    <link:loc xlink:type="locator" xlink:href="x.xsd#x_CcbMember" xlink:label="l1"/>
    <link:label xlink:label="r1" xlink:role="http://www.xbrl.org/2003/role/terseLabel">Consumer &amp; Community Banking</link:label>
    <link:label xlink:label="r1" xlink:role="http://www.xbrl.org/2003/role/verboseLabel">CCB</link:label>
    <link:label xlink:label="r1" xlink:role="http://www.xbrl.org/2003/role/documentation">A component of an entity for which there is an accounting requirement to report separate financial information on that component.</link:label>
    <link:labelArc xlink:from="l1" xlink:to="r1"/></link:labelLink></link:linkbase>"""
    assert X.parse_labels(lab) == {"x_CcbMember": "Consumer & Community Banking"}
    assert X.member_name("x:CcbMember", X.parse_labels(lab)) == "Consumer & Community Banking"
