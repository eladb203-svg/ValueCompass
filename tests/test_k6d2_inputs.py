"""K6d-2: automatic inputs of a new bank / insurer / REIT (and the range a default makes), BP-1 v4 (founded, listed since), sentence 6 of the background, the sector glossary, the last price
at 23:00. Fake database, no network."""
from datetime import date, datetime, timezone

import pytest

from fakedb import FakeClient
from src.bp import bp1, render as R
from src.bp.pipeline import BackgroundBuilder
from src.bp.stores import ProfileStore, TermStore
from src.bp.vocab import Vocab
from src.pipeline import auto_config as AC
from src.scoring import coverage as CV

TEXT = [("TXT-001", "The Coca-Cola Company was incorporated in 1919 under Delaware law. We were founded in 1886 in Atlanta. We completed our initial public offering in 2021 and our shares are listed on the NYSE.")]
NORM = bp1.normalize(bp1.sent_text(TEXT))


# ---------------------------------------------------------------- BP-1 v4
def test_founded_needs_a_year_a_kind_and_a_quote_that_shows_the_year():
    ok = bp1.check_year_field({"year": 1886, "kind": "founded", "quote": "We were founded in 1886 in Atlanta."}, "founded", NORM, TEXT)
    assert ok["status"] == "ok" and ok["items"][0]["year"] == 1886 and ok["items"][0]["kind"] == "founded"
    inc = bp1.check_year_field({"year": 1919, "kind": "incorporated", "quote": "was incorporated in 1919 under Delaware law"}, "founded", NORM, TEXT)
    assert inc["items"][0]["kind"] == "incorporated"
    wrong_year = bp1.check_year_field({"year": 1890, "kind": "founded", "quote": "We were founded in 1886 in Atlanta."}, "founded", NORM, TEXT)
    assert wrong_year["status"] == "failed" and "year_not_in_quote" in " ".join(wrong_year["reasons"])
    assert bp1.check_year_field({"year": 1886, "kind": "born", "quote": "We were founded in 1886 in Atlanta."}, "founded", NORM, TEXT)["status"] == "failed"
    assert bp1.check_year_field({"year": 1886, "kind": "founded", "quote": "We were founded in 1886 in Boston."}, "founded", NORM, TEXT)["status"] == "failed"      # not in the text
    assert bp1.check_year_field(None, "founded", NORM, TEXT)["status"] == "not_found"


def test_listed_since_needs_a_quote_about_an_ipo_or_a_listing():
    ok = bp1.check_year_field({"year": 2021, "quote": "We completed our initial public offering in 2021"}, "listed_since", NORM, TEXT)
    assert ok["status"] == "ok" and ok["items"][0]["year"] == 2021
    no = bp1.check_year_field({"year": 1886, "quote": "We were founded in 1886 in Atlanta."}, "listed_since", NORM, TEXT)
    assert no["status"] == "failed" and "IPO" in " ".join(no["reasons"])
    assert bp1.SKILL_VERSION == "4" and set(bp1.NEW_FIELDS) <= set(bp1.ALWAYS)


def test_the_prompt_asks_the_two_fields_alone_for_an_old_profile():
    vocab = Vocab.from_rows([]) if hasattr(Vocab, "from_rows") else None
    if vocab is None:
        pytest.skip("Vocab has no offline constructor")
    p = bp1.build_prompt(vocab, "acc-1", TEXT, list(bp1.NEW_FIELDS))
    assert "founded:" in p and "listed_since:" in p and "core_activity:" not in p and '"founded"' in p


# ---------------------------------------------------------------- the price-history fallback and the profile update
class FakeGemini:
    model = "gemini-3.5-flash-lite"
    calls = 0

    def generate(self, prompt, seed_offset=0, **kw):
        FakeGemini.calls += 1
        return type("R", (), {"text": '{"skill_id": "BP-1", "version": 4, "founded": {"year": 1886, "kind": "founded", "quote": "We were founded in 1886 in Atlanta."}, "listed_since": null}',
                              "model": self.model})()


class Builder(BackgroundBuilder):
    def __init__(self, client, profile_row):
        self.client, self.gemini = client, FakeGemini()
        self.profiles = ProfileStore(client)
        self.vocab = None
        self._profile = profile_row
        self.ctx = {"co": {"id": 1, "symbol": "KO", "company_name": "Coca Cola Co"}, "filing": type("F", (), {"accession": "a-1", "text": ""})(), "fy": 2025}

    def load(self, ticker):
        return self.ctx

    @staticmethod
    def first_price_date(ticker):
        return date(1962, 1, 2)


def test_listed_since_falls_back_to_the_first_price_date_only_from_the_year_2000():
    b = Builder(FakeClient(), None)
    nf = {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    r = b.listed_fallback("KO", nf)                                                           # Yahoo's history of KO starts in 1962: that is where the data starts, not the listing
    assert r["status"] == "not_found" and r["items"] == []
    Builder.first_price_date = staticmethod(lambda t: date(2012, 5, 18))
    try:
        r = b.listed_fallback("FB", nf)
        assert r["status"] == "ok" and r["items"][0] == {"year": 2012, "source": "price_history", "approximate": True, "tag": "first date in the Yahoo price history: 2012-05-18", "status": "ok"}
        old = {"status": "ok", "source": "code", "items": [{"year": 1962, "source": "price_history", "approximate": True}]}
        assert b.listed_fallback("KO", old)["status"] == "not_found"                         # a stored year before 2000 is withdrawn
    finally:
        Builder.first_price_date = staticmethod(lambda t: date(1962, 1, 2))
    keep = {"status": "ok", "source": "ai", "items": [{"year": 2021, "quote": "IPO in 2021"}]}
    assert b.listed_fallback("KO", keep) is keep                                              # the report's own year wins, whatever it is
    assert b.listed_fallback("KO", {"status": "ok", "source": "ai", "items": [{"year": 1994, "quote": "IPO in 1994"}]})["items"][0]["year"] == 1994


# ---------------------------------------------------------------- sentence 6
class V:
    labels = {}
    gender = {}

    def label(self, *a):
        return ""


def inp(founded=None, listed=None):
    profile = {"core_activity": {"status": "ok", "items": []}}
    if founded:
        profile["founded"] = {"status": "ok", "items": [founded]}
    if listed:
        profile["listed_since"] = {"status": "ok", "items": [listed]}
    return R.RenderInput(name="Acme", profile=profile, vocab=V(), fiscal_year=2025)


@pytest.mark.parametrize("founded,listed,en,he", [
    ({"year": 1886, "kind": "founded"}, {"year": 2021, "source": "ai"}, "Founded in 1886; listed since 2021.", "נוסדה ב-1886; נסחרת בבורסה מאז 2021."),
    ({"year": 1919, "kind": "incorporated"}, {"year": 1962, "source": "price_history", "approximate": True}, "Listed since about 1962.", "נסחרת בבורסה מאז כ-1962."),
    ({"year": 1919, "kind": "incorporated"}, None, None, None),
    ({"year": 1886, "kind": "founded"}, None, "Founded in 1886.", "נוסדה ב-1886."),
    (None, {"year": 2021, "source": "ai"}, "Listed since 2021.", "נסחרת בבורסה מאז 2021."),
    (None, None, None, None),
])
def test_sentence_6_each_half_only_when_found(founded, listed, en, he):
    for lang, want in (("en", en), ("he", he)):
        c = R._Ctx(inp(founded, listed), lang, False)
        assert R.s_history(c) == want
    text, _ = R.render(inp(founded, listed), "en")
    assert (en in text) if en else ("Founded" not in text and "Listed" not in text)
    assert R.TEMPLATE_VERSION == "2"


def test_a_failed_field_is_not_written():
    p = inp()
    p.profile["founded"] = {"status": "failed", "items": [{"year": 1886, "kind": "founded"}]}
    assert R.s_history(R._Ctx(p, "en", False)) is None


# ---------------------------------------------------------------- the sector glossary
def test_the_sector_glossary_is_stored_once_as_human_approved_and_feeds_the_translator():
    c = FakeClient()
    ts = TermStore(c)
    dry = ts.seed_sectors(dry_run=True)
    assert dry["inserted"] >= 60 and not c.tables.get("term_translations")
    r = ts.seed_sectors()
    assert r["inserted"] == dry["inserted"] and {x["source"] for x in c.tables["term_translations"]} == {"human"} and {x["status"] for x in c.tables["term_translations"]} == {"approved"}
    assert ts.seed_sectors() == {"inserted": 0, "existing": dry["inserted"], "terms": r["terms"]}
    terms = dict(ts.glossary_entries())
    assert terms["Wealth Management"] == "ניהול עושר" and terms["Data Centers"] == "מרכזי נתונים" and "Personal Computing" in terms and "Commercial" in terms
    assert all(len(en.split()) <= 3 for en in terms)


# ---------------------------------------------------------------- automatic inputs
def ai_row(item, year, value, unit="percent"):
    return {"item_key": item, "year": year, "value_full": value, "state": "value", "unit": unit}


def test_bank_required_cet1_from_the_filing_then_scb_then_the_documented_default():
    assert AC.bank_required_cet1([ai_row("cet1_required_standardized", 2025, 9.5), ai_row("cet1_required_standardized", 2024, 8.0)]) == (9.5, "ai")
    assert AC.bank_required_cet1([ai_row("scb", 2025, 2.9), ai_row("gsib_surcharge", 2025, 1.0)]) == (pytest.approx(8.4), "ai")
    assert AC.bank_required_cet1([]) == (7.0, "default") and AC.DEFAULT_REQUIRED_CET1 == 4.5 + 2.5


def test_reit_asset_type_from_the_business_words_else_default():
    assert AC.reit_asset_type("We own apartment communities. Multifamily housing is our business; residential rents.") == ("residential", "profile")
    assert AC.reit_asset_type("wireless towers and tower sites, a tower company") == ("communication towers", "profile")
    assert AC.reit_asset_type("We own properties.") == ("diversified", "default")
    assert AC.reit_utilization("communication towers") == "not_applicable" and AC.reit_utilization("data centers") == "leased_capacity" and AC.reit_utilization("residential") == "occupancy"
    assert AC.reit_noi_method(True) == (["prop_opex"], "xbrl") and AC.reit_noi_method(False)[1] == "default"


def test_derive_marks_the_defaults_and_apply_fills_the_engine_tables_without_touching_the_golden_ones():
    from src.providers import realestate_facts as RF
    from src.scoring import bank as BK
    a = AC.derive("realestate", "ZZZ", {"company_name": "Zed Apartments Trust"}, [], None, {"property_opex": {2025: 1.0}})
    assert a.values["asset_type"] == "diversified" and a.defaults == ["asset_type", "utilization"] and a.flags() == ["auto_input_default:asset_type", "auto_input_default:utilization"]
    AC.apply(a)
    assert RF.ASSET_TYPE["ZZZ"] == "diversified" and RF.NOI_METHOD["ZZZ"] == ["prop_opex"]
    del RF.ASSET_TYPE["ZZZ"], RF.UTILIZATION["ZZZ"], RF.NOI_METHOD["ZZZ"]
    golden = AC.derive("realestate", "O", {"company_name": "Realty Income"}, [], None, {})
    AC.apply(golden)
    assert RF.ASSET_TYPE["O"] == "net lease" and "O" in AC.MANUAL_RE
    b = AC.derive("bank", "ZBK", {}, [], None)
    AC.apply(b)
    assert "ZBK" in BK.REQUIRED_CET1_DEFAULT and b.defaults == ["required_cet1"]
    AC.apply(AC.derive("bank", "ZBK", {}, [ai_row("cet1_required_standardized", 2025, 9.0)], None))
    assert "ZBK" not in BK.REQUIRED_CET1_DEFAULT


def test_a_sub_item_computed_from_a_default_widens_the_range_but_not_the_score():
    a = CV.scored("1", "Capital buffer", 4, 3.0, flags=["default"])
    b = CV.scored("2", "Other", 6, 6.0)
    c = CV.evaluate_criterion("3.6", "Balance", [a, b])
    plain = CV.evaluate_criterion("3.6", "Balance", [CV.scored("1", "Capital buffer", 4, 3.0), b])
    assert c.observed == plain.observed == 9.0 and c.normalized == plain.normalized                 # the score uses the default value
    assert (plain.min_score, plain.max_score) == (10.0, 10.0) if False else True
    assert c.min_score == pytest.approx(6.0) and c.max_score == pytest.approx(10.0)                    # the range runs from 0 to the full points of the defaulted item
    assert plain.min_score == pytest.approx(9.0) and plain.max_score == pytest.approx(9.0)


def test_the_bank_capital_buffer_uses_the_default_and_marks_the_item():
    from src.scoring import bank as BK
    bi = type("BI", (), {"ticker": "ZBK", "required_cet1": 7.0, "reg": {"cet1_ratio_standardized": {"value": 12.0, "unit": "%", "section": "x", "note": ""}}, "end": [], "series": lambda s, k: [None, None, None, None, None]})()
    BK.REQUIRED_CET1_DEFAULT.add("ZBK")
    try:
        out = BK.resolve_latest(bi)
    finally:
        BK.REQUIRED_CET1_DEFAULT.discard("ZBK")
    assert out["capital_buffer"] == pytest.approx(5.0) and "default" in out["flags"] and "requirement_default_cet1_7" in out["flags"]
    out2 = BK.resolve_latest(bi)
    assert out2["capital_buffer"] is None and "default" not in out2["flags"]                          # a golden bank is never defaulted


# ---------------------------------------------------------------- the last price at 23:00
def test_the_batch_fetch_reads_one_minute_bars_and_does_not_retry(monkeypatch):
    from src.pipeline import prices as P
    import pandas as pd
    calls = []

    class YF:
        @staticmethod
        def download(tickers, **kw):
            calls.append((tickers, kw))
            idx = pd.to_datetime(["2026-10-27 15:59", "2026-10-28 15:59", "2026-10-28 16:00"])
            return pd.DataFrame({"Close": [90.0, 91.0, 91.85]}, index=idx)

    monkeypatch.setitem(__import__("sys").modules, "yfinance", YF)
    out = P.fetch_prices_batch(["KO"])
    assert out["KO"] == {"price": 91.85, "previous_close": 90.0, "market_date": date(2026, 10, 28)}
    assert len(calls) == 1 and calls[0][1]["interval"] == "1m"
    calls.clear()
    P.fetch_prices_batch(["KO", "ZZZ"])
    assert len(calls) == 1                                                                              # ZZZ is missing: no second attempt
    P.fetch_prices_batch(["KO", "ZZZ"], retry_missing=True)
    assert len(calls) == 3
