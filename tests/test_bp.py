"""BP: the business profile (XBRL axes, BP-1 checks, closed vocabulary, phrase translation, template rendering, similar companies, idempotency). No network, no real database, no model."""
import json
import re
from types import SimpleNamespace

import pytest

from fakedb import FakeClient
from src.bp import bp1, render as R, xbrl_axes as X
from src.bp.similar import pick_similar, size_of
from src.bp.translate import GoogleTranslate, NoKey, auto_names, check_translation, protect, restore, translate_phrase
from src.bp.vocab import Vocab, region_of

VOCAB = Vocab.from_rows()


# ================================================================ XBRL axes
def ctx(cid, dims=(), start="2025-01-01", end="2025-12-31"):
    mem = "".join(f'<xbrldi:explicitMember dimension="{a}">{m}</xbrldi:explicitMember>' for a, m in dims)
    seg = f"<xbrli:segment>{mem}</xbrli:segment>" if mem else ""
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier>{seg}</xbrli:entity>'
            f"<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>")


def fact(cid, value, name="us-gaap:Revenues", scale=6):
    return f'<ix:nonFraction name="{name}" contextRef="{cid}" unitRef="usd" decimals="-6" scale="{scale}">{value:,}</ix:nonFraction>'


SEG = "us-gaap:StatementBusinessSegmentsAxis"
GEO = "srt:StatementGeographicalAxis"
PRD = "srt:ProductOrServiceAxis"


def sample_ixbrl():
    c = [ctx("t"), ctx("old", end="2024-12-31", start="2024-01-01"),
         ctx("a", [(SEG, "x:AlphaMember")]), ctx("b", [(SEG, "x:BetaMember")]), ctx("c", [(SEG, "x:GammaMember")]), ctx("par", [(SEG, "x:AlphaBetaGroupMember")]),
         ctx("corp", [(SEG, "x:CorporateAndOtherMember")]),
         ctx("us", [(GEO, "country:US")]), ctx("de", [(GEO, "country:DE")]), ctx("fr", [(GEO, "country:FR")]), ctx("jp", [(GEO, "country:JP")]), ctx("zz", [(GEO, "x:AtlantisMember")]),
         ctx("multi", [(SEG, "x:AlphaMember"), (GEO, "country:US")])]
    f = [fact("t", 1000), fact("old", 900), fact("a", 500), fact("b", 300), fact("c", 150), fact("par", 800), fact("corp", 50),
         fact("us", 600), fact("de", 100), fact("fr", 100), fact("jp", 40), fact("zz", 130), fact("multi", 111)]
    return "<html><body><ix:header><ix:resources>" + "".join(c) + "</ix:resources></ix:header>" + "".join(f) + "</body></html>"


LAB = """<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink"><link:labelLink>
<link:loc xlink:type="locator" xlink:href="x-20251231.xsd#x_AlphaMember" xlink:label="l1"/>
<link:label xlink:type="resource" xlink:label="r1" xlink:role="http://www.xbrl.org/2003/role/label" xml:lang="en-US">Alpha Cloud [Member]</link:label>
<link:labelArc xlink:type="arc" xlink:from="l1" xlink:to="r1"/>
<link:loc xlink:type="locator" xlink:href="x-20251231.xsd#x_BetaMember" xlink:label="l2"/>
<link:label xlink:type="resource" xlink:label="r2" xlink:role="http://www.xbrl.org/2003/role/terseLabel" xml:lang="en-US">Beta</link:label>
<link:labelArc xlink:type="arc" xlink:from="l2" xlink:to="r2"/></link:labelLink></link:linkbase>"""


def test_axes_are_read_from_the_latest_year_with_labels_shares_and_aggregates_removed():
    r = X.extract_axes(sample_ixbrl(), LAB)
    assert str(r["end"]) == "2025-12-31" and r["total_revenue"] == 1000e6 and r["labels_found"] == 2
    seg = r["axes"]["segments"]
    names = {i["name"]: i for i in seg["items"]}
    assert set(names) == {"Alpha Cloud", "Beta", "Gamma"}                                    # label linkbase; the camel-case name when there is no label
    assert names["Alpha Cloud"]["share"] == pytest.approx(0.5)
    reasons = dict(seg["dropped"])
    assert reasons["x:AlphaBetaGroupMember"].startswith("sum_of:") and reasons["x:CorporateAndOtherMember"] == "name_is_aggregate"   # a sum of others and a reconciling line are not items
    assert not r["axes"]["products_services"]["found"] and r["axes"]["products_services"]["flags"] == ["axis_not_in_filing"]       # a missing axis is reported
    assert all(i["member"] != "x:AlphaMember" or i["value"] == 500e6 for i in seg["items"])                                    # the two-dimension context is not used


def test_regions_are_mapped_summed_and_unknown_areas_go_to_other():
    reg = X.regions_field(X.extract_axes(sample_ixbrl(), LAB))
    by = {i["code"]: i for i in reg["items"]}
    assert by["us"]["share"] == pytest.approx(0.6) and by["europe"]["share"] == pytest.approx(0.2) and by["asia_pacific"]["share"] == pytest.approx(0.04)
    assert by["other"]["status"] == "other" and by["other"]["other_text"] == "Atlantis" and reg["status"] == "other"


def test_a_filing_without_revenue_facts_gives_no_axes():
    r = X.extract_axes("<html></html>")
    assert r["total_revenue"] is None and not any(a["found"] for a in r["axes"].values())


def test_drop_aggregates_total_name_and_nested_sums():
    kept, dropped = X.drop_aggregates({"x:TotalMember": 100.0, "x:A": 40.0, "x:B": 35.0, "x:C": 25.0, "x:ABC": 100.0001, "x:Parent": 75.0})
    assert set(kept) == {"x:A", "x:B", "x:C"} and {d[0] for d in dropped} == {"x:TotalMember", "x:ABC", "x:Parent"}


def test_region_map():
    assert region_of("Non-US") == "outside_us" and region_of("International") == "outside_us" and region_of("Rest of world") == "outside_us"
    assert region_of("United States") == "us" and region_of("EMEA") == "europe" and region_of("Greater China") == "asia_pacific" and region_of("Israel") == "israel"
    assert region_of("country:IL") == "israel" and region_of("Atlantis") == "other" and region_of("Americas") == "other"


# ================================================================ BP-1
ITEM1 = ("Acme Corp manufactures and sells industrial widgets to retailers and distributors. " * 3 + "The company earns its revenue from product sales and subscriptions. "
         + "Our products include the Zed brand and the Quark line. " + "Competition. We compete with Globex Corporation, Initech Inc. and many smaller firms in every market we serve.")
SECTIONS = [("TXT-001", ITEM1)]


def good_answer():
    return {"skill_id": "BP-1", "version": 1,
            "core_activity": {"value": "manufactures and sells industrial widgets", "quote": "Acme Corp manufactures and sells industrial widgets to retailers and distributors."},
            "customer_types": [{"code": "retailers", "other_text": None, "quote": "industrial widgets to retailers and distributors"}],
            "revenue_models": [{"code": "product_sales", "other_text": None, "quote": "earns its revenue from product sales and subscriptions"},
                               {"code": "subscriptions", "other_text": None, "quote": "earns its revenue from product sales and subscriptions"}],
            "competitors": [{"name": "Globex Corporation", "quote": "We compete with Globex Corporation, Initech Inc. and many smaller firms"},
                            {"name": "Initech", "quote": "We compete with Globex Corporation, Initech Inc. and many smaller firms"}],
            "competitor_types": []}


def v(ans, fields=bp1.ALWAYS):
    return bp1.validate(ans, VOCAB, SECTIONS, list(fields), "Acme")


def test_a_good_answer_passes_every_field_with_quotes():
    r = v(good_answer())
    assert all(x["status"] in ("ok", "not_found") for x in r.values())
    assert r["core_activity"]["items"][0]["section"] == "TXT-001" and [i["code"] for i in r["revenue_models"]["items"]] == ["product_sales", "subscriptions"]
    assert [i["name"] for i in r["competitors"]["items"]] == ["Globex Corporation", "Initech"] and r["competitor_types"]["status"] == "not_found"


@pytest.mark.parametrize("mutate,reason", [
    (lambda a: a["core_activity"].update(quote="Acme Corp invented the widget in 1950 and never looked back."), "quote_not_found"),
    (lambda a: a["core_activity"].update(value="manufactures and sells the world's leading industrial widgets"), "praise_words"),
    (lambda a: a["core_activity"].update(value="manufactures and sells 12 industrial widgets"), "contains_digits"),
    (lambda a: a["core_activity"].update(value="manufactures sells distributes designs markets repairs leases ships stores packs tests and widgets"), "over_12_words"),
    (lambda a: a["core_activity"].update(value="produces plutonium submarines for astronauts"), "content words"),
    (lambda a: a["core_activity"].update(value="develop and support industrial widgets", quote="Acme Corp manufactures and sells industrial widgets to retailers and distributors. We develop and support industrial widgets."), "third-person singular verb"),
    (lambda a: a["core_activity"].update(value="manufacturer of industrial widgets"), "third-person singular verb"),
    (lambda a: a["customer_types"][0].update(code="whales"), "code_not_in_list"),
    (lambda a: a["customer_types"][0].update(code="other"), "other_without_text"),
    (lambda a: a["revenue_models"][0].update(quote="we love widgets"), "quote_not_found"),
    (lambda a: a["competitors"][0].update(name="Hooli"), "name_not_in_quote"),
])
def test_each_check_fails_only_its_own_field(mutate, reason):
    a = good_answer()
    mutate(a)
    r = v(a)
    failed = {f: x for f, x in r.items() if x["status"] == "failed"}
    assert len(failed) == 1 and any(reason in s for x in failed.values() for s in x["reasons"])
    assert all(r[f]["status"] != "failed" for f in r if f not in failed)          # the other fields are kept


def test_a_failed_field_is_not_rendered_and_its_phrases_are_not_translated():
    from src.bp.pipeline import phrases_needed
    p = profile(segments={"status": "failed", "items": [item(name="Alpha", share=0.5), item(name="Beta", share=0.5)], "reasons": ["x"]},
                core_activity={"status": "failed", "items": [item(value="provides things")], "reasons": ["x"]})
    text, _ = R.render(inp(p), "en")
    assert "segments" not in text and "provides things" not in text and all(k != "segment" for _e, k, _w in phrases_needed(p)) and all(k != "core_activity" for _e, k, _w in phrases_needed(p))


def test_the_first_word_of_the_activity_phrase_must_be_a_third_person_verb():
    assert [bp1.third_person_verb(w) for w in ("provides", "operates", "is", "has", "own", "designer", "leasing", "business", "develop")] == [True, True, True, True, False, False, False, False, False]


def test_more_than_five_competitors_fail_that_field_only():
    names = ["Globex", "Initech", "Hooli", "Umbrella", "Soylent", "Vandelay"]
    text = "We compete with " + ", ".join(names) + " and others in every market."
    secs = [("TXT-001", text)]
    r = bp1.validate({"competitors": [{"name": n, "quote": text[:-1]} for n in names]}, VOCAB, secs, ["competitors"])
    assert r["competitors"]["status"] == "failed" and any("more_than_5" in x for x in r["competitors"]["reasons"]) and len(r["competitors"]["items"]) == 5


def test_other_keeps_the_original_words_and_is_flagged():
    a = good_answer()
    a["customer_types"] = [{"code": "other", "other_text": "widget hobbyists", "quote": "industrial widgets to retailers and distributors"}]
    r = v(a)["customer_types"]
    assert r["status"] == "other" and r["items"][0]["other_text"] == "widget hobbyists" and r["items"][0]["status"] == "other"


def test_competitors_and_types_are_never_both_and_types_are_checked():
    a = good_answer()
    a["competitor_types"] = [{"industry": "banks", "scope": "national", "quote": "many smaller firms in every market we serve"}]
    r = v(a)
    assert r["competitor_types"]["items"] == [] and "dropped" in r["competitor_types"]["note"]
    a["competitors"] = []
    r = v(a)
    assert r["competitor_types"]["items"][0]["industry"] == "banks" and r["competitor_types"]["items"][0]["scope"] == "national"
    a["competitor_types"][0]["scope"] = "galactic"
    assert v(a)["competitor_types"]["status"] == "failed"


def test_invalid_json_fails_every_field_and_deliberation_words_fail():
    assert all(x["status"] == "failed" for x in v(None).values())
    a = good_answer()
    a["customer_types"] = [{"code": "other", "other_text": "Wait, actually, hobbyists", "quote": "industrial widgets to retailers and distributors"}]
    assert v(a)["customer_types"]["status"] == "failed"


def test_fallback_fields_from_text_need_the_name_in_the_quote_and_a_share_the_quote_shows():
    a = {"segments": [{"name": "Widgets", "share_pct": 60, "quote": "Widgets segment generated 60% of revenue in the year"}, {"name": "Gizmos", "share_pct": 40, "quote": "Gizmos is the other one"}],
         "regions": [{"name": "Non-US", "share_pct": 38, "quote": "Non-US markets provided about 38% of revenue and so on"}]}
    secs = [("TXT-001", "Widgets segment generated 60% of revenue in the year. Gizmos is the other one. Non-US markets provided about 38% of revenue and so on.")]
    r = bp1.validate(a, VOCAB, secs, ["segments", "regions"])
    assert r["segments"]["status"] == "ok" and [i["share"] for i in r["segments"]["items"]] == [0.6, None]      # 40 is not in its quote: no share
    assert r["regions"]["items"][0]["code"] == "outside_us" and r["regions"]["items"][0]["share"] == 0.38


class FakeGemini:
    def __init__(self, *answers):
        self.answers, self.calls, self.model = list(answers), [], "fake-model"

    def generate(self, prompt, seed_offset=0, **kw):
        self.calls.append(prompt)
        a = self.answers.pop(0)
        return SimpleNamespace(text=a if isinstance(a, str) else json.dumps(a), model=self.model)


def test_one_call_when_everything_passes():
    g = FakeGemini(good_answer())
    out = bp1.run(g, VOCAB, "0001-26-1", SECTIONS, list(bp1.ALWAYS), "Acme")
    assert len(g.calls) == 1 and out["attempts"][0]["failed"] == {} and "customer_types: 1–3 codes from" in g.calls[0] and "banks" in g.calls[0]


def test_one_retry_with_the_exact_reason_a_fixed_field_replaces_the_failed_one_and_a_good_field_is_kept():
    bad = good_answer()
    bad["customer_types"][0]["code"] = "whales"
    bad["core_activity"]["value"] = "manufactures and sells industrial widgets"
    fixed = good_answer()
    fixed["core_activity"]["value"] = "WRONG would not be used"                     # a field that passed before is not replaced
    g = FakeGemini(bad, fixed)
    out = bp1.run(g, VOCAB, "0001-26-1", SECTIONS, list(bp1.ALWAYS), "Acme")
    assert len(g.calls) == 2 and "customer_types: code_not_in_list (whales)" in g.calls[1]
    f = out["fields"]
    assert f["customer_types"]["status"] == "ok" and f["core_activity"]["items"][0]["value"] == "manufactures and sells industrial widgets"


def test_a_field_that_fails_twice_is_failed_and_the_others_are_kept_and_there_is_no_third_call():
    bad = good_answer()
    bad["customer_types"][0]["code"] = "whales"
    g = FakeGemini(bad, bad)
    out = bp1.run(g, VOCAB, "0001-26-1", SECTIONS, list(bp1.ALWAYS), "Acme")
    assert len(g.calls) == 2 and out["fields"]["customer_types"]["status"] == "failed" and out["fields"]["revenue_models"]["status"] == "ok"


def long_filing():
    filler = "The company serves customers in many markets and invests in research. " * 80
    return ("Item 1. Business\n" + ITEM1.replace("Competition. ", "\nCompetition\n") + "\n" + filler + "\nThe Zed brand is our best known brand of widgets and our product lines are sold worldwide through partners. " * 3
            + "\nItem 1A. Risk Factors\n" + filler * 3 + "\nItem 1B. Unresolved Staff Comments\nNone.\nItem 2. Properties\n" + filler)


def test_text_selection_opening_competition_and_products_only_without_a_product_axis():
    secs, err = bp1.select_text(long_filing(), need_products=True)
    ids = [s for s, _ in secs]
    assert err is None and ids[0] == "TXT-001" and len(secs[0][1]) <= bp1.OPENING_CHARS
    secs2, _ = bp1.select_text(long_filing(), need_products=False)
    assert "TXT-PRD" not in [s for s, _ in secs2]
    assert bp1.select_text("no items here at all", True)[1] == "business_section_not_found"


def test_the_prompt_lists_the_closed_codes_and_asks_for_fallback_fields_only_when_needed():
    p = bp1.build_prompt(VOCAB, "0001-26-1", SECTIONS, bp1.fields_wanted(True, False, False))
    assert "retailers" in p and "product_sales" in p and "banks" in p and "private_companies" in p and "national" in p
    assert "products_services:" in p and "regions:" in p and "segments:" not in p.split("TEXT (filing")[0].split("FIELDS")[1].replace("segments / ", "")


# ================================================================ translation
def test_protection_replaces_names_and_glossary_terms_and_restores_them():
    t, m = protect("sells Coca-Cola concentrates and syrups", ["Coca-Cola"], [("concentrates", "תרכיזים"), ("syrups", "סירופים")])
    assert "Coca" not in t and "concentrates" not in t and len(m) == 3
    he, missing = restore(t.replace("sells", "מוכרת"), m)
    assert "Coca-Cola" in he and "תרכיזים" in he and "סירופים" in he and not missing


def test_auto_names_finds_acronyms_and_internal_capitals():
    assert set(auto_names("sells iPhone devices and AWS cloud services in EMEA")) >= {"iPhone", "AWS", "EMEA"}


def test_translation_checks_foreign_script_names_and_length():
    assert check_translation("sells beverages", "מוכרת משקאות", [], []) == []
    assert "foreign_script" in check_translation("sells beverages", "מוכרת משקאות 饮料", [], [])
    assert any(r.startswith("name_lost") for r in check_translation("sells Coca-Cola drinks", "מוכרת משקאות", ["Coca-Cola"], []))
    assert any(r.startswith("length_out_of_range") for r in check_translation("sells beverages and snacks around the world every day", "מוכרת", [], []))
    assert "no_hebrew" in check_translation("sells beverages", "sells beverages", [], [])


def fake_post(reply):
    seen = []

    def post(body):
        seen.append(body)
        return reply(body["q"]) if callable(reply) else reply
    post.seen = seen
    return post


def test_translate_phrase_sends_placeholders_never_the_names_and_strips_the_company_prefix():
    post = fake_post(lambda q: q.replace("The company", "החברה").replace("sells", "מוכרת").replace("beverage concentrates", "תרכיזי משקאות"))
    g = GoogleTranslate(key="k", post=post)
    out = translate_phrase("sells Fanta beverage concentrates", g, ["Fanta"], whole_sentence=True, gloss=[("concentrates", "תרכיזים")])
    assert out["he"] and out["he"].startswith("מוכרת") and "Fanta" in out["he"] and not out["reasons"]
    assert "Fanta" not in post.seen[0]["q"] and "ZQ" in post.seen[0]["q"] and post.seen[0]["q"].startswith("The company")
    assert g.calls == 1


def test_a_lost_placeholder_or_foreign_script_rejects_the_translation():
    g = GoogleTranslate(key="k", post=fake_post("החברה מוכרת בגדים"))
    out = translate_phrase("sells Fanta drinks", g, ["Fanta"], whole_sentence=True, gloss=[])
    assert out["he"] is None and any("placeholder_lost" in r or "name_lost" in r for r in out["reasons"])
    g = GoogleTranslate(key="k", post=fake_post("החברה מוכרת 饮料"))
    assert "foreign_script" in translate_phrase("sells drinks", g, [], True, gloss=[])["reasons"]


def test_no_key_means_no_call_and_the_cap_is_enforced():
    with pytest.raises(NoKey):
        GoogleTranslate(key="").translate("x")
    assert not GoogleTranslate(key="").available
    g = GoogleTranslate(key="k", cap=2, post=fake_post("שלום"))
    g.translate("a")
    g.translate("b")
    with pytest.raises(RuntimeError, match="cap"):
        g.translate("c")


# ================================================================ rendering
def item(**k):
    return {"source": "ai", "status": "ok", **k}


def profile(**over):
    p = {"core_activity": {"status": "ok", "items": [item(value="manufactures and sells beverage concentrates", quote="q")]},
         "segments": {"status": "ok", "items": [item(name="Alpha", share=0.5), item(name="Beta", share=0.3), item(name="Gamma", share=0.1), item(name="Delta", share=0.05)]},
         "products_services": {"status": "ok", "items": [item(name="Soft drinks", kind="product_line", share=0.6), item(name="Juices", kind="product_line", share=0.25), item(name="Fanta", kind="brand", share=None)]},
         "customer_types": {"status": "ok", "items": [item(code="retailers"), item(code="consumers")]},
         "revenue_models": {"status": "ok", "items": [item(code="product_sales"), item(code="licensing")]},
         "regions": {"status": "ok", "items": [item(code="outside_us", share=0.6), item(code="us", share=0.4)]},
         "competitors": {"status": "ok", "items": [item(name="Globex"), item(name="Initech")]},
         "competitor_types": {"status": "not_found", "items": []}}
    p.update(over)
    return p


HE = {"manufactures and sells beverage concentrates": "מייצרת ומוכרת תרכיזי משקאות", "soft drinks": "משקאות קלים", "juices": "מיצים", "alpha": "אלפא", "beta": "בטא", "gamma": "גמא"}
TR = {k: {"he": v, "status": "approved"} for k, v in HE.items()}


def inp(prof=None, **k):
    base = dict(name="Acme", profile=prof or profile(), vocab=VOCAB, revenue=47.9e9, fiscal_year=2025, moat_level=2, moat_source="brand", translations=TR)
    base.update(k)
    return R.RenderInput(**base)


def test_english_full_text_follows_the_template_sentence_by_sentence():
    text, info = R.render(inp(), "en")
    p1, p2 = text.split("\n\n")
    assert p1.startswith("Acme manufactures and sells beverage concentrates. Its main product lines are Soft drinks (60% of revenue) and Juices (25%); its brands include Fanta.")
    assert "It sells mainly to retailers and consumers, earning its revenue from product sales and licensing and royalties." in p1
    assert "It reports 4 segments, the largest being Alpha (50%), Beta (30%) and Gamma (10%); 60% of revenue comes from outside the United States and 40% from the United States." in p1
    assert p1.endswith("Revenue in FY2025: $47.9 billion.")
    assert p2 == "Its main competitors include Globex and Initech. A clear competitive advantage: brand." and info["missing"] == []


def test_hebrew_full_text_uses_vocab_labels_prefixes_and_conjunctions():
    text, info = R.render(inp(), "he")
    p1, p2 = text.split("\n\n")
    assert p1.startswith("חברת Acme מייצרת ומוכרת תרכיזי משקאות. קווי המוצרים העיקריים: משקאות קלים (60% מההכנסות) ומיצים (25%); בין המותגים: Fanta.")
    assert "לקוחותיה הם בעיקר קמעונאים וצרכנים, והכנסותיה ממכירת מוצרים ומרישוי ותמלוגים." in p1
    assert "היא מדווחת על 4 מגזרים, הגדולים שבהם אלפא (50%), בטא (30%) וגמא (10%); 60% מההכנסות מחוץ לארה\"ב ו-40% מארצות הברית." in p1
    assert p1.endswith("הכנסות ב-FY2025: 47.9 מיליארד $.")
    assert p2 == "בין המתחרים העיקריים: Globex ו-Initech. יתרון תחרותי ברור: מותג."
    assert info["unreviewed"] == [] and "manufactures and sells beverage concentrates" in info["used"]


def test_hebrew_sentence_without_a_translation_is_left_out_and_listed_and_preview_shows_it():
    tr = {k: v for k, v in TR.items() if k not in ("soft drinks", "alpha")}
    text, info = R.render(inp(translations=tr), "he")
    assert "קווי המוצרים" not in text and "מגזרים" not in text and set(info["missing"]) == {"Soft drinks", "Alpha"}
    pv, _ = R.render(inp(translations=tr), "he", preview=True)
    assert "[ממתין: Soft drinks]" in pv
    text_en, info_en = R.render(inp(translations={}), "en")
    assert info_en["missing"] == [] and "Soft drinks" in text_en                       # English never waits


def test_unreviewed_phrases_are_listed_for_the_reviewed_flag():
    tr = {**TR, "juices": {"he": "מיצים", "status": "unreviewed"}}
    _t, info = R.render(inp(translations=tr), "he")
    assert info["unreviewed"] == ["Juices"]


def test_no_products_no_regions_no_segments_no_customers_sentences_are_dropped():
    p = profile(products_services={"status": "not_found", "items": []}, regions={"status": "not_found", "items": []}, segments={"status": "ok", "items": [item(name="Only", share=1.0)]},
                customer_types={"status": "not_found", "items": []}, revenue_models={"status": "ok", "items": [item(code="other", other_text="x")]})
    text, _ = R.render(inp(p), "en")
    assert text.split("\n\n")[0] == "Acme manufactures and sells beverage concentrates. Revenue in FY2025: $47.9 billion."     # one segment is no sentence; 'other' is not rendered
    assert "product lines" not in text and "segments" not in text


def test_regions_alone_make_their_own_sentence_and_the_rest_is_named():
    p = profile(segments={"status": "not_found", "items": []}, regions={"status": "ok", "items": [item(code="us", share=0.5), item(code="europe", share=0.3), item(code="asia_pacific", share=0.15), item(code="mea", share=0.05)]})
    en, _ = R.render(inp(p), "en")
    he, _ = R.render(inp(p), "he")
    assert "50% of revenue comes from the United States and 30% from Europe, and 20% from other regions." in en
    assert "50% מההכנסות מארצות הברית ו-30% מאירופה, ו-20% מאזורים אחרים." in he


def test_competition_cases_types_nothing_and_similar_companies():
    types = profile(competitors={"status": "not_found", "items": []}, competitor_types={"status": "ok", "items": [
        item(industry="banks", scope="national"), item(industry="insurance_carriers", scope="national"), item(industry="private_companies", scope=None), item(industry="other", scope=None)]})
    en, _ = R.render(inp(types, similar=["Alpha Co", "Beta Co"]), "en")
    he, _ = R.render(inp(types, similar=["Alpha Co", "Beta Co"]), "he")
    assert en.split("\n\n")[1] == "It competes with national banks, national insurance carriers and private companies. Similar companies in ValueCompass: Alpha Co, Beta Co. A clear competitive advantage: brand."
    assert he.split("\n\n")[1] == "מתחרה בבנקים ארציים, בחברות ביטוח ארציות ובחברות פרטיות. חברות דומות ב-ValueCompass: Alpha Co, Beta Co. יתרון תחרותי ברור: מותג."
    nothing = profile(competitors={"status": "not_found", "items": []})
    en, _ = R.render(inp(nothing, similar=[]), "en")
    assert en.split("\n\n")[1] == "The report does not describe its competitors. A clear competitive advantage: brand."
    assert R.render(inp(nothing), "he")[0].split("\n\n")[1].startswith("הדוח לא מפרט את מתחריה.")


@pytest.mark.parametrize("level,src,en,he", [
    (2, "brand", "A clear competitive advantage: brand.", "יתרון תחרותי ברור: מותג."),
    (1, "scale", "A competitive advantage that is not proven: scale.", "יתרון תחרותי לא מוכח: יתרון לגודל."),
    (0, None, "No identifiable competitive advantage.", "אין יתרון תחרותי מזוהה."),
    (None, None, None, None),
    (2, None, None, None)])
def test_moat_three_levels(level, src, en, he):
    for lang, want in (("en", en), ("he", he)):
        text = R.render(inp(moat_level=level, moat_source=src), lang)[0]
        assert (want in text) if want else ("advantage" not in text and "יתרון" not in text)


def test_names_and_money_are_formatted_by_code():
    assert R.money_en(331.8e9) == "$331.8 billion" and R.money_he(267e6) == "267 מיליון $" and R.pct(0.381) == "38%" and R.pct(0.042) == "4.2%"
    assert R.join_en(["a"]) == "a" and R.join_en(["a", "b", "c"]) == "a, b and c"
    assert R.join_he(["אלפא", "בטא", "גמא"]) == "אלפא, בטא וגמא" and R.join_he(["אלפא", "Beta"]) == "אלפא ו-Beta"


def test_rendering_twice_gives_the_same_text():
    assert R.render(inp(), "he") == R.render(inp(), "he") and R.render(inp(), "en") == R.render(inp(), "en")


# ================================================================ similar companies
def rec(t, profile="STANDARD", ind="Software", rev=None):
    return {"ticker": t, "profile": profile, "industry": ind, "metrics": {"revenue": rev}}


def test_three_closest_in_size_same_profile_and_industry_banks_by_assets():
    target = rec("T", rev=100)
    recs = [target, rec("A", rev=90), rec("B", rev=200), rec("C", rev=1000), rec("D", rev=105), rec("E", ind="Hardware", rev=100), rec("F", profile="BANK", rev=100), rec("G")]
    sizes = {r["ticker"]: size_of(r, None) for r in recs}
    assert [r["ticker"] for r in pick_similar(target, recs, sizes)] == ["D", "A", "B"]
    assert [r["ticker"] for r in pick_similar(target, recs[:2], sizes)] == ["A"]                         # fewer than 3: what exists
    assert pick_similar(target, [target], sizes) == []
    bank = rec("BK", "BANK", "Banks", rev=5)
    assert size_of(bank, {"financials": {"assets": {"FY2024": 1.0, "FY2025": 900.0}}}) == 900.0 and size_of(bank, None) == 5.0
    ins = rec("IN", "INSURANCE", "Insurance carriers", rev=7)
    assert size_of(ins, {"financials": {"assets": {"FY2025": 70.0}}}) == 70.0 and size_of(rec("X", rev=3), {"financials": {"assets": {"FY2025": 70.0}}}) == 3.0


def test_same_market_comes_first():
    target = rec("T", rev=100)
    recs = [target, rec("A", rev=101), rec("B", rev=500)]
    assert [r["ticker"] for r in pick_similar(target, recs, {"T": 100, "A": 101, "B": 500}, markets={"A": "IL"}, n=2)] == ["B", "A"]


# ================================================================ the builder: storage, idempotency, superseding
class Ai:
    def rows(self, ticker=None):
        return [{"ticker": "ACM", "fiscal_year": 2025, "question_id": "B3.2-Q5", "state": "answered", "answer": 2, "evidence": {"extra": {"moat_source": "brand"}}}]


def general_json(t, name, rev):
    return {"ticker": t, "name": name, "profile": "STANDARD", "fiscal_years": {"FY2025": "2025-12-31"}, "financials": {"revenue": {"FY2025": rev}, "net_income": {}, "eps": {}, "equity": {}},
            "derived": {}, "buffett_quality": {}, "graham_quality": {}, "profile_router": {"classification": {"industry": "Software"}}}


@pytest.fixture
def world(tmp_path):
    from src.ai.db_stores import DbTextStore
    from src.bp.pipeline import BackgroundBuilder
    client = FakeClient()
    client.table("companies").insert({"symbol": "ACM", "exchange": "US", "company_name": "ACME CORP", "cik": "0000000001", "country": "US"}).execute()
    for t, n, r in (("ACM", "ACME CORP", 100.0), ("P1", "PEER ONE INC", 90.0), ("P2", "PEER TWO INC", 250.0), ("P3", "PEER THREE CO", 105.0), ("P4", "PEER FOUR CO", 1e6)):
        d = tmp_path / "res" / "general"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{t}.json").write_text(json.dumps(general_json(t, n, r)), encoding="utf-8")
    doc = tmp_path / "000000000126000001_acm-20251231.htm"
    doc.write_text(sample_ixbrl(), encoding="utf-8")
    filing = SimpleNamespace(ticker="ACM", text=long_filing(), accession="0000000001-26-000001", path=str(doc), report_date="20251231")

    def build(translator=None, gem=None):
        texts = DbTextStore(client)
        return BackgroundBuilder(client, Ai(), texts, gemini=gem, translator=translator or GoogleTranslate(key=""), results_dir=tmp_path / "res", sec=None,
                                 find_filing=lambda t, end=None: filing, vocab=VOCAB), texts
    return SimpleNamespace(client=client, build=build, filing=filing)


def bp_answer():
    a = good_answer()
    a["core_activity"] = {"value": "manufactures and sells industrial widgets", "quote": "Acme Corp manufactures and sells industrial widgets to retailers and distributors."}
    a["segments"] = []
    return a


def test_no_key_english_is_approved_hebrew_waits_and_the_second_run_changes_nothing(world):
    b, texts = world.build(gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    assert out["he_state"] == "awaiting_translation" and out["translation"]["pending"] >= 1 and b.log["translation_skipped_no_key"] >= 1
    en, he = texts.get("ACM", 2025, "background", "bp", "", "en"), texts.get("ACM", 2025, "background", "bp", "", "he")
    assert en["approval_status"] == "approved" and en["template_version"] == "1" and en["profile_id"] == out["profile_id"] and en["text"].startswith("Acme manufactures and sells industrial widgets.")
    assert he["approval_status"] == "pending_review" and he["state"] == "awaiting_translation" and he["human_reviewed"] is False
    again, _ = world.build(gem=FakeGemini())                                     # a model with no answers: BP-1 must not be asked again
    out2 = again.run("ACM")
    assert out2["texts_changed"] == 0 and again.log["profiles_reused"] == 1 and again.log["profiles_built"] == 0


def test_axes_become_source_xbrl_and_bp1_fills_the_missing_ones_with_source_ai(world):
    b, _ = world.build(gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    p = b.profiles.by_id(out["profile_id"])
    assert p["segments"]["source"] == "xbrl" and p["segments"]["items"][0]["tag"].startswith("us-gaap:StatementBusinessSegmentsAxis")
    assert p["regions"]["source"] == "xbrl" and p["products_services"]["status"] == "not_found" and p["products_services"]["source"] == "ai"
    assert p["core_activity"]["items"][0]["source"] == "ai" and p["axes_found"]["axes"]["segments"]["found"] and not p["axes_found"]["axes"]["products_services"]["found"]


def test_translations_make_hebrew_approved_and_human_reviewed_only_when_all_phrases_are_approved(world):
    post = fake_post(lambda q: "החברה מייצרת ומוכרת ווידג'טים תעשייתיים" if q.startswith("The company") else "משקאות")
    b, texts = world.build(translator=GoogleTranslate(key="k", post=post), gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    assert out["translation"]["needed"] == len(b.log["translated"]) + out["translation"]["already"] and b.translator.calls == len(b.log["translated"]) + len(b.log["translation_failed"])
    he = texts.get("ACM", 2025, "background", "bp", "", "he")
    rows = b.terms.rows()
    if he["approval_status"] == "approved":
        assert he["human_reviewed"] is False and all(r["status"] == "unreviewed" and r["source"] == "google" for r in rows)
        for r in rows:
            b.terms.approve(r["id"])
        b.render_only("ACM")
        assert texts.get("ACM", 2025, "background", "bp", "", "he")["human_reviewed"] is True
    calls = b.translator.calls
    b.run("ACM")
    assert b.translator.calls == calls                                            # a phrase that has a translation is not translated again


def test_old_d1_t1_texts_are_marked_superseded_not_deleted_and_not_touched_twice(world):
    c = world.client
    cid = c.table("companies").select("*").execute().data[0]["id"]
    for lang, st in (("en", "approved"), ("he", "approved"), ("he", "failed")):
        c.table("ai_texts").insert({"company_id": cid, "fiscal_year": 2025, "kind": "background", "language": lang, "text": "old", "prompt_version": "4" if st == "approved" else "5", "run_label": "",
                                    "approval_status": st, "edited_by": "ai", "human_reviewed": False}).execute()
    b, _ = world.build(gem=FakeGemini(bp_answer()))
    out = b.run("ACM")
    assert out["superseded"] == 3
    old = [r for r in c.table("ai_texts").select("*").execute().data if r.get("template_version") is None]
    assert len(old) == 3 and {r["approval_status"] for r in old} == {"superseded"}
    assert b.run("ACM")["superseded"] == 0


def test_similar_companies_appear_only_when_no_competitor_is_named_and_come_from_the_pool(world):
    a = bp_answer()
    a["competitors"], a["competitor_types"] = [], []
    b, texts = world.build(gem=FakeGemini(a))
    b.run("ACM")
    en = texts.get("ACM", 2025, "background", "bp", "", "en")["text"]
    assert "The report does not describe its competitors. Similar companies in ValueCompass: Peer Three, Peer One, Peer Two." in en


def test_the_model_budget_is_required_only_for_a_new_profile(world):
    from src.ai.content import BudgetExceeded
    b, _ = world.build(gem=None)
    with pytest.raises(BudgetExceeded):
        b.run("ACM")


def test_vocab_and_glossary_seed_is_idempotent_and_never_overwrites_the_owners_edits(world):
    from src.bp.stores import TermStore, VocabStore
    vs, ts = VocabStore(world.client), TermStore(world.client)
    first = vs.seed(Vocab.seed_rows())
    assert first["inserted"] == len(Vocab.seed_rows()) and vs.seed(Vocab.seed_rows())["inserted"] == 0
    industry = [r for r in vs.rows() if r["field"] == "competitor_types" and r["code"] == "banks"][0]
    assert industry["active"] is False and industry["label_he"] == "בנקים"                  # a proposal until approved
    assert all(r["active"] for r in vs.rows() if r["field"] != "competitor_types")
    g = ts.seed_glossary()
    assert g["inserted"] >= 15 and ts.seed_glossary()["inserted"] == 0
    assert all(r["status"] == "approved" and r["source"] == "human" for r in ts.rows())
    t = ts.rows()[0]
    ts.edit(t["id"], "תיקון")
    ts.seed_glossary()
    assert ts.get_by_id(t["id"])["he"] == "תיקון"


def test_vocab_rows_cover_every_closed_list_of_the_skills_document():
    f = {}
    for r in Vocab.seed_rows():
        f.setdefault(r["field"], []).append(r["code"])
    assert len(f["customer_types"]) == 10 and len(f["revenue_models"]) == 12 and len(f["regions"]) == 9
    assert {"local", "regional", "national", "international", "private_companies", "private_label", "startups", "government_entities", "other"} <= set(f["competitor_types"])
    assert len([c for c in f["competitor_types"] if c not in {"local", "regional", "national", "international", "private_companies", "private_label", "startups", "government_entities", "other"}]) == 22


def test_refresh_asks_once_with_the_reasons_replaces_only_failed_fields_and_does_nothing_when_all_pass(world):
    bad = bp_answer()
    bad["core_activity"]["value"] = "develop and support industrial widgets"
    b, _ = world.build(gem=FakeGemini(bad, bad))
    out = b.run("ACM")
    p = b.profiles.by_id(out["profile_id"])
    assert p["core_activity"]["status"] == "failed" and p["customer_types"]["items"][0]["code"] == "retailers"
    good = bp_answer()
    good["customer_types"] = [{"code": "consumers", "other_text": None, "quote": "industrial widgets to retailers and distributors"}]
    g = FakeGemini(good)
    b2, _ = world.build(gem=g)
    r = b2.refresh_failed("ACM")
    p = b2.profiles.by_id(out["profile_id"])
    assert r["refreshed"] == ["core_activity"] and len(g.calls) == 1 and "core_activity" in g.calls[0].split("NOTE:")[1]
    assert p["core_activity"]["status"] == "ok" and p["customer_types"]["items"][0]["code"] == "retailers"          # a field that had passed is not replaced
    g2 = FakeGemini()
    b3, _ = world.build(gem=g2)
    assert b3.refresh_failed("ACM") == {"refreshed": [], "kept_failed": [], "attempts": 0} and g2.calls == []


def test_word_families_count_as_the_same_word_but_unrelated_words_do_not():
    assert bp1.same_word("design", "designer") and bp1.same_word("manufactur", "manufacturer") and bp1.same_word("manag", "management") and bp1.same_word("acquir", "acquisition")
    assert not bp1.same_word("car", "carry")
    assert not bp1.same_word("power", "powder") and not bp1.same_word("sell", "service")
    a = good_answer()
    a["core_activity"] = {"value": "designs and manufactures widgets", "quote": "We are a global designer and manufacturer of widgets and sell them."}
    secs = [("TXT-001", "We are a global designer and manufacturer of widgets and sell them.")]
    assert bp1.validate(a, VOCAB, secs, ["core_activity"])["core_activity"]["status"] == "ok"


def test_recheck_adopts_a_stored_raw_answer_that_passes_the_current_checks_without_a_model_call(world):
    bad = bp_answer()
    bad["core_activity"]["value"] = "develop and support industrial widgets"
    b, _ = world.build(gem=FakeGemini(bad, bad))
    out = b.run("ACM")
    p = b.profiles.by_id(out["profile_id"])
    assert p["core_activity"]["status"] == "failed"
    af = p["axes_found"]
    af["attempts"][0]["raw"] = json.dumps(bp_answer())                      # an earlier raw answer that the current checks accept
    b.profiles.put({**p, "axes_found": af})
    g = FakeGemini()
    b2, _ = world.build(gem=g)
    r = b2.recheck_stored("ACM")
    assert r == {"adopted": ["core_activity"], "still_failed": []} and g.calls == []
    assert b2.profiles.by_id(out["profile_id"])["core_activity"]["status"] == "ok"


def test_segments_say_largest_only_when_every_shown_segment_has_a_share_and_are_sorted_by_it():
    p = profile(segments={"status": "ok", "items": [item(name="Small", share=0.1), item(name="Big", share=0.6), item(name="Mid", share=0.3)]})
    assert "the largest being Big (60%), Mid (30%) and Small (10%)" in R.render(inp(p), "en")[0]
    p = profile(segments={"status": "ok", "items": [item(name="A", share=0.4), item(name="B", share=None), item(name="C", share=None)]})
    en, he = R.render(inp(p), "en")[0], R.render(inp(p), "he")[0]
    assert "It reports 3 segments, including A (40%), B and C" in en and "largest" not in en
    assert "ביניהם" in he or "[ממתין" in he or "מגזרים" not in he


def test_names_end_with_one_period_and_company_names_are_cleaned():
    from src.bp.pipeline import pretty_name
    p = profile(competitors={"status": "ok", "items": [item(name="Globex"), item(name="Cellnex Telecom, S.A.")]})
    assert "Globex and Cellnex Telecom, S.A." in R.render(inp(p), "en")[0] and "S.A.." not in R.render(inp(p), "en")[0]
    assert pretty_name("BANK OF AMERICA CORP /DE/") == "Bank of America" and pretty_name("WELLS FARGO & COMPANY/MN") == "Wells Fargo" and pretty_name("PROGRESSIVE CORP/OH/") == "Progressive"


def test_member_names_are_readable():
    assert X.member_fallback_name("msft:ProductivityAndBusinessProcessesMember") == "Productivity and Business Processes"
    assert X.member_name("x:RetailMember", {"x_RetailMember": "Product and Service, Retail [Member]".replace(" [Member]", "")}) == "Retail"
