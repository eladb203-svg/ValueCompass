"""K6b: SEC source (rate limit, cache), RESOLVE, AUDIT, SRC hierarchy, DQ checks. No network, no database (SEC answers are made up)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from fakedb import FakeClient
from src.etl.db_io import PLACEHOLDER_ACCESSION
from src.etl.facts import Fact, FactSet
from src.pipeline import audit as A
from src.pipeline import collect as C
from src.pipeline import dq as D
from src.pipeline import resolve as R
from src.pipeline.prices import refresh_snapshot
from src.pipeline.sec_source import PipelineSec, RateLimiter
from src.repositories.company_repository import CompanyRepository


# ---------------------------------------------------------------- SEC source
class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_rate_limit_never_exceeds_ten_requests_in_any_second():
    clk = Clock()
    lim = RateLimiter(clock=clk.now, sleep=clk.sleep)
    stamps = []
    for _ in range(60):
        lim.wait()
        stamps.append(clk.t)
        clk.t += 0.001                                           # the request itself
    for i, s in enumerate(stamps):
        assert sum(1 for x in stamps if s <= x < s + 1.0) <= 10
    assert all(b - a >= 0.12 - 1e-9 for a, b in zip(stamps, stamps[1:]))


def test_cache_dir_freshness_and_files_saved(tmp_path):
    calls = []
    clk = Clock()
    now = [1_000_000.0]

    def fetch(url):
        calls.append(url)
        return json.dumps({"url": url})
    sec = PipelineSec(tmp_path, fetch=fetch, limiter=RateLimiter(clock=clk.now, sleep=clk.sleep), now=lambda: now[0])
    sec.get_json("https://data.sec.gov/submissions/CIK1.json", "sub_1.json")
    sec.get_json("https://data.sec.gov/submissions/CIK1.json", "sub_1.json")
    assert len(calls) == 1 and (tmp_path / "sub_1.json").exists() and sec.requests_made == 1       # saved, and read from the cache the second time
    now[0] += 21 * 3600                                                                          # older than 20 hours: a mutable document is downloaded again
    import os
    os.utime(tmp_path / "sub_1.json", (1_000_000.0, 1_000_000.0))
    sec.get_json("https://data.sec.gov/submissions/CIK1.json", "sub_1.json")
    assert len(calls) == 2
    sec.get_json("https://www.sec.gov/Archives/x/index.json", "index_x.json")
    now[0] += 99 * 3600
    os.utime(tmp_path / "index_x.json", (1_000_000.0, 1_000_000.0))
    sec.get_json("https://www.sec.gov/Archives/x/index.json", "index_x.json")                   # a filing index never changes: no new download
    assert len(calls) == 3 and [d[0] for d in sec.downloads] == ["sub_1.json", "sub_1.json", "index_x.json"]


def test_infinite_max_age_never_downloads_what_is_cached_and_transform_overlays(tmp_path):
    (tmp_path / "sub_1.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    sec = PipelineSec(tmp_path, fetch=lambda u: (_ for _ in ()).throw(AssertionError("no download expected")), max_age_hours=float("inf"),
                      transform=lambda name, d: {**d, "b": 2}, limiter=RateLimiter(sleep=lambda s: None))
    assert sec.get_json("u", "sub_1.json") == {"a": 1, "b": 2} and sec.requests_made == 0


# ---------------------------------------------------------------- RESOLVE
def sub(forms, sic="2080", tickers=("ACM",), name="Acme Corp", exchanges=("NYSE",)):
    n = len(forms)
    return {"cik": "1", "name": name, "sic": sic, "sicDescription": "x", "fiscalYearEnd": "1231", "tickers": list(tickers), "exchanges": list(exchanges), "formerNames": [{"name": "Old Acme"}],
            "filings": {"recent": {"form": [f for f, *_ in forms], "accessionNumber": [a for _, a, *_ in forms], "filingDate": [d for _, _, d, _ in forms], "reportDate": [r for *_, r in forms],
                                   "primaryDocument": ["d.htm"] * n}, "files": []}}


def fake_sec(subs, tickers=None):
    class S:
        requests_made = 0

        def cik_for(self, t):
            if t not in (tickers or {"ACM": "0000000001"}):
                raise KeyError(t)
            return (tickers or {"ACM": "0000000001"})[t], "ACME CORP"

        def get_json(self, url, name, refresh=False):
            return subs
    return S()


K10 = [("10-K", f"0000000001-{y % 100}-00000{y % 10}", f"{y + 1}-02-20", f"{y}-12-31") for y in range(2016, 2026)]


def test_resolve_a_normal_filer_lists_annual_reports_and_listings():
    r = R.resolve(fake_sec(sub(K10)), "acm")
    assert r.supported and r.cik == "0000000001" and r.name == "Acme Corp" and r.former_names == ["Old Acme"] and r.sic == "2080" and r.fiscal_year_end == "1231"
    assert [f.fiscal_year for f in r.annual][:2] == [2025, 2024] and r.e2_ok and r.listings == [{"symbol": "ACM", "exchange": "NYSE", "mic": "XNYS", "is_primary": True}]


@pytest.mark.parametrize("forms,sic,why", [
    ([("20-F", "a-1", "2026-03-01", "2025-12-31")], "3674", "20-F"),
    ([("40-F", "a-2", "2026-03-01", "2025-12-31")], "1000", "40-F"),
    (K10, "6770", "SPAC"),
    (K10, "6189", "asset-backed"),
    ([("8-K", "a-3", "2026-03-01", None), ("10-Q", "a-4", "2026-03-01", "2026-03-31")], "2080", "no annual report"),
])
def test_unsupported_issuers_get_a_reason(forms, sic, why):
    r = R.resolve(fake_sec(sub(forms, sic=sic)), "ACM")
    assert not r.supported and why in r.unsupported_reason


def test_a_company_that_switched_to_10k_from_20f_is_supported_but_the_reverse_is_not():
    switched = K10 + [("20-F", "old-1", "2012-03-01", "2011-12-31")]
    assert R.resolve(fake_sec(sub(switched)), "ACM").supported
    reverse = K10[:3] + [("20-F", "new-1", "2026-03-01", "2025-12-31")]
    assert "20-F" in R.resolve(fake_sec(sub(reverse)), "ACM").unsupported_reason


def test_unknown_ticker_and_the_listed_entity_check_e2():
    with pytest.raises(R.ResolveError) as e:
        R.resolve(fake_sec(sub(K10)), "ZZZZ")
    assert e.value.kind == "not_found"
    merged = R.resolve(fake_sec(sub(K10, tickers=("NEWCO",)), tickers={"OLD": "0000000001"}), "OLD")          # the old ticker no longer belongs to the filing entity
    assert not merged.e2_ok and "E2" in merged.warnings[0]


def test_persist_creates_one_company_per_cik_and_updates_listings_not_the_company():
    c = FakeClient()
    repo = CompanyRepository(c)
    r = R.resolve(fake_sec(sub(K10, tickers=("ACM", "ACM-B"), exchanges=("NYSE", "NYSE"))), "ACM")
    row = R.persist(r, repo, c, state="resolved")
    assert row["cik"] == "0000000001" and row["processing_state"] == "resolved" and len(c.tables["companies"]) == 1 and len(c.tables["company_listings"]) == 2
    assert {x["symbol"]: x["is_primary"] for x in c.tables["company_listings"]} == {"ACM": True, "ACM-B": False}
    w = c.writes
    R.persist(r, repo, c, state="resolved")
    assert c.writes == w                                                                                    # idempotent
    r2 = R.resolve(fake_sec(sub(K10, tickers=("ACMN",), exchanges=("Nasdaq",), name="Acme Renamed")), "ACMN") if False else None
    row2 = repo.get_by_cik("0000000001")
    repo.set_processing_state(row2["id"], "data_loaded")
    R.persist(r, repo, c, state="resolved")                                                                 # a later resolve never moves the state backwards
    assert repo.get_by_cik("0000000001")["processing_state"] == "data_loaded"


def test_persist_stores_an_unsupported_company_with_its_reason():
    c = FakeClient()
    r = R.resolve(fake_sec(sub([("20-F", "a-1", "2026-03-01", "2025-12-31")], sic="3674")), "ACM")
    row = R.persist(r, CompanyRepository(c), c, state="resolved")
    assert row["processing_state"] == "unsupported" and "20-F" in row["unsupported_reason"]


# ---------------------------------------------------------------- AUDIT
def test_audit_statuses_present_missing_superseded_not_available():
    r = R.resolve(fake_sec(sub(K10)), "ACM")
    eff = {f.fiscal_year: f.accession for f in r.annual}
    db = [{"fiscal_year": 2025, "accession": eff[2025]}, {"fiscal_year": 2024, "accession": PLACEHOLDER_ACCESSION}, {"fiscal_year": 2023, "accession": "0000000001-OLD"}]
    plans = {p.fiscal_year: p for p in A.plan(r, db)}
    assert [p.fiscal_year for p in A.plan(r, db)] == list(range(2016, 2026))
    assert plans[2025].status == "present" and plans[2024].status == "superseded" and "placeholder" in plans[2024].reason
    assert plans[2023].status == "superseded" and "newer filing" in plans[2023].reason and plans[2022].status == "missing"
    assert A.years_to_load(list(plans.values())) == [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    short = R.resolve(fake_sec(sub(K10[-4:])), "ACM")
    assert {p.fiscal_year: p.status for p in A.plan(short, [])} == {**{y: "not_available" for y in range(2016, 2022)}, **{y: "missing" for y in range(2022, 2026)}}


def test_amendment_supersedes_only_when_its_data_is_in_companyfacts():
    forms = K10 + [("10-K/A", "0000000001-26-000099", "2026-06-01", "2025-12-31")]
    r = R.resolve(fake_sec(sub(forms)), "ACM")
    orig = next(f.accession for f in r.annual if f.fiscal_year == 2025 and f.form == "10-K")
    db = [{"fiscal_year": 2025, "accession": orig}]
    part3_only = {p.fiscal_year: p for p in A.plan(r, db, xbrl_accessions=set())}[2025]
    assert part3_only.status == "present"
    with_data = {p.fiscal_year: p for p in A.plan(r, db, xbrl_accessions={"0000000001-26-000099"})}[2025]
    assert with_data.status == "superseded" and with_data.accession == "0000000001-26-000099" and with_data.form == "10-K/A"
    assert "UNSUPPORTED" in A.render(R.resolve(fake_sec(sub(K10, sic="6770")), "ACM"), [])


# ---------------------------------------------------------------- SRC hierarchy
def quarter_entries(tag_val, start, n=4, days=91):
    out, s = [], start
    for i in range(n):
        e = s + timedelta(days=days)
        out.append({"start": s.isoformat(), "end": e.isoformat(), "val": tag_val, "form": "10-Q", "fp": f"Q{i + 1}", "filed": "2025-05-01", "accn": f"q{i}"})
        s = e + timedelta(days=1)
    return out


def test_quarter_sum_needs_four_consecutive_quarters_that_fill_the_year():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": quarter_entries(100.0, date(2024, 1, 1))}}}}}
    assert C.quarter_sum(facts, ["Revenues"], "USD", date(2023, 12, 31), date(2024, 12, 31)) == (400.0, "Revenues")
    three = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": quarter_entries(100.0, date(2024, 1, 1), n=3)}}}}}
    assert C.quarter_sum(three, ["Revenues"], "USD", date(2023, 12, 31), date(2024, 12, 31)) is None
    assert C.quarter_sum(facts, ["Revenues"], "USD", date(2022, 12, 31), date(2023, 12, 31)) is None


def test_quarterly_sum_fills_only_a_missing_annual_value_and_is_labelled():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": quarter_entries(100.0, date(2024, 1, 1))}}}}}
    fs = FactSet("ACM", "Acme", "general", [(2024, "FY2024", date(2024, 12, 30))], series_fields=["revenue", "net_income"])
    rep = C.SourceReport()
    C.fill_quarterly_sums(fs, facts, rep)
    f = next(x for x in fs.facts if x.item_key == "revenue")
    assert (f.value, f.source_kind, f.tag, f.flags) == (400.0, "quarterly_sum", "Revenues", ("quarterly_sum",)) and rep.filled == [("quarterly_sum", 2024, "revenue")]
    before = list(fs.facts)
    C.fill_quarterly_sums(fs, facts, C.SourceReport())                         # the annual value now exists: nothing is added
    assert fs.facts == before


def test_extraction_fills_only_approved_single_mapped_missing_facts():
    fs = FactSet("JPM", "JPM", "bank", [(2025, "FY2025", date(2025, 12, 31))], series_fields=[])
    rows = [{"id": 7, "item_key": "loans_2025", "period": "", "value": 1.5e12, "value_state": "value", "approval_status": "approved"},
            {"id": 8, "item_key": "loans_2025", "period": "", "value": 9, "value_state": "value", "approval_status": "pending"},
            {"id": 9, "item_key": "cet1_ratio_standardized", "period": "", "value": 14.6, "value_state": "value", "approval_status": "approved"},
            {"id": 10, "item_key": "loans_2025", "period": "", "value": None, "value_state": "MISSING", "approval_status": "approved"}]
    rep = C.select_sources(fs, {}, rows, dictionary_keys={"loans_extracted"})
    got = [(f.item_key, f.value, f.source_kind, f.extraction_ref, f.flags) for f in fs.facts]
    assert got == [("loans_extracted", 1.5e12, "extraction", "7", ("from_extraction",))] and rep.by_kind == {"extraction": 1}
    assert rep.not_in_dictionary == ["cet1_ratio_standardized"]                  # mapped to a key that is not a dictionary item: stays in extraction_items only
    assert any("FR Y-9C" in s for s in rep.skipped)                              # step 4 is reported as not built
    rep2 = C.select_sources(fs, {}, rows, dictionary_keys={"loans_extracted"})                                          # the fact exists now: not added twice
    assert len(fs.facts) == 1 and rep2.filled == []


# ---------------------------------------------------------------- DQ
def F(year, key, value, **kw):
    return Fact("ACM", year, key, value, kw.pop("status", "found"), kw.pop("source_kind", "xbrl"), **kw)


def test_share_scale_rescales_powers_of_ten_and_holds_unexplained_jumps():
    shares = [F(2020 + i, "shares_diluted_weighted", v) for i, v in enumerate([1.0e9, 1.0e9, 1.0e12, 1.01e9, 5.0e11])]
    res = []
    out = D.check_share_scale(shares, res)
    by = {f.fiscal_year: f for f in out}
    assert by[2022].value == pytest.approx(1.0e9) and "share_scale_rescaled" in by[2022].flags
    assert 2024 not in by                                                        # 500x: no power-of-ten explanation -> held (missing)
    assert [(r.outcome, r.fiscal_year) for r in res] == [("rescaled", 2022), ("held", 2024)]
    assert all(f.value > 0 for f in out)


def test_currency_balance_identity_signs_and_year_coverage():
    res = []
    assert D.check_currency([F(2024, "revenue", 5.0), F(2024, "shares_period_end", 3.0)], "EUR", res)[0].item_key == "shares_period_end" and res[0].outcome == "held"
    ok = [F(2024, "total_assets", 100.0), F(2024, "total_liabilities", 60.0), F(2024, "equity", 40.5)]
    assert all(not f.flags for f in D.check_balance_identity(ok, []))                                   # 0.5% apart: fine
    bad = [F(2024, "total_assets", 100.0), F(2024, "total_liabilities", 60.0), F(2024, "equity", 30.0), F(2024, "revenue", 1.0)]
    r2 = []
    out = D.check_balance_identity(bad, r2)
    assert [f.item_key for f in out if "balance_identity" in f.flags] == ["total_assets", "total_liabilities", "equity"] and r2[0].outcome == "flagged"
    neg = D.check_signs([F(2024, "revenue", -1.0), F(2024, "net_income", -5.0)], [])
    assert "negative_value" in neg[0].flags and not neg[1].flags                                           # expenses and losses as reported
    r3 = []
    D.check_year_coverage([F(2024, "revenue", 1.0), F(2023, "revenue", 1.0)] + [F(y, "net_income", 1.0) for y in range(2020, 2025)], r3)
    assert {r.item_key for r in r3} == {"revenue", "cfo", "equity", "total_assets"}
    r4 = []
    D.check_year_coverage([F(2024, "net_income", 1.0)], r4, "bank")                                       # a bank is checked on its own items (no revenue / cfo)
    assert {r.item_key for r in r4} == {"net_income", "equity", "total_assets", "loans", "deposits"}


def test_restatement_flags_a_changed_value_and_keeps_the_flag_when_unchanged():
    prev = {(2024, "revenue"): {"value": 100.0, "flags": ()}, (2023, "revenue"): {"value": 90.0, "flags": ("restated",)}, (2022, "revenue"): {"value": 80.0, "flags": ()}}
    res = []
    out = D.check_restatement([F(2024, "revenue", 101.0), F(2023, "revenue", 90.0), F(2022, "revenue", 80.0), F(2021, "revenue", 70.0)], prev, res)
    assert ["restated" in f.flags for f in out] == [True, True, False, False] and [(r.fiscal_year) for r in res] == [2024]
    assert "stored 100" in res[0].detail and out[0].value == 101.0                                         # the latest filing wins


def test_run_checks_returns_facts_and_results_and_prepares_reconciliations():
    facts, res = D.run_checks([F(2024, "revenue", 5.0), F(2024, "net_income", 1.0)], {}, "USD")
    assert len(facts) == 2 and all(isinstance(r, D.DqResult) for r in res)
    assert D.reconciliation_inputs(facts)["FFO"][2024] == {"net_income": 1.0, "da": None}


def test_price_freshness_and_snapshot_row():
    now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    assert D.price_freshness(now - timedelta(days=1), now)[0] is False and D.price_freshness(now - timedelta(days=9), now)[0] is True and D.price_freshness(None, now)[0] is True
    c = FakeClient()
    ok = refresh_snapshot(c, 1, "ACM", lambda t: {"price": 12.5, "previous_close": 12.0, "market_date": date(2026, 10, 23)}, now)
    assert ok["status"] == "updated" and ok["is_stale"] is False and c.tables["market_snapshot"][0]["current_price"] == 12.5
    refresh_snapshot(c, 1, "ACM", lambda t: {"price": 13.0, "previous_close": 12.5, "market_date": date(2026, 10, 23)}, now)
    assert len(c.tables["market_snapshot"]) == 1 and c.tables["market_snapshot"][0]["current_price"] == 13.0         # updated in place, one row per stock
    assert refresh_snapshot(c, 1, "ACM", lambda t: None, now)["status"] == "no_price" and c.tables["market_snapshot"][0]["is_stale"] is False and c.tables["market_snapshot"][0]["current_price"] == 13.0       # a failed request leaves the price as it is; the date decides if it is stale


def test_filing_documents_go_through_the_same_client_and_reuse_the_old_cache_read_only(tmp_path, monkeypatch):
    from src.pipeline import sec_source
    from src.providers import sec_filings
    old = tmp_path / "old_filings"
    old.mkdir()
    (old / "acc_cached.htm").write_text("<html>old</html>", encoding="utf-8")
    monkeypatch.setattr(sec_source, "FILINGS_CACHE", old)
    calls = []
    sec = PipelineSec(tmp_path / "live", fetch=lambda u: calls.append(u) or "<html>new</html>", limiter=RateLimiter(sleep=lambda s: None))
    assert sec_filings._get_raw(sec, "https://www.sec.gov/x/cached.htm", "acc_cached.htm") == "<html>old</html>" and calls == []
    assert sec_filings._get_raw(sec, "https://www.sec.gov/x/new.htm", "acc_new.htm") == "<html>new</html>" and len(calls) == 1 and (old / "acc_new.htm").exists()      # a new file in the shared cache
    sec_filings._get_raw(sec, "https://www.sec.gov/x/new.htm", "acc_new.htm")
    assert len(calls) == 1 and sec.requests_made == 1 and (old / "acc_cached.htm").read_text(encoding="utf-8") == "<html>old</html>"          # the old file is untouched


def test_balance_identity_counts_noncontrolling_interests_without_changing_the_equity_fact():
    facts = [F(2025, "total_assets", 272_327.0), F(2025, "total_liabilities", 192_548.0), F(2025, "equity", 73_757.0)]
    res = []
    flagged = D.check_balance_identity(facts, res)                                                  # CB 2025 without the noncontrolling interest: 2.2% apart
    assert res and all("balance_identity" in f.flags for f in flagged)
    res2 = []
    out = D.check_balance_identity(facts, res2, {2025: 6_022.0})                                    # + MinorityInterest: balanced
    assert res2 == [] and all(not f.flags for f in out) and [f.value for f in out] == [272_327.0, 192_548.0, 73_757.0]       # the equity fact is the parent's, unchanged
    res3 = []
    D.check_balance_identity(facts, res3, {2025: 500.0})                                            # a noncontrolling interest that does not explain the gap still flags
    assert res3


def test_noncontrolling_by_year_reads_the_minority_tag_then_the_difference_of_the_two_equity_tags():
    def inst(vals):
        return {"units": {"USD": [{"end": e, "val": v, "form": "10-K", "fp": "FY", "filed": "2026-02-01", "accn": "a"} for e, v in vals.items()]}}
    cf = {"facts": {"us-gaap": {"MinorityInterest": inst({"2025-12-31": 6_022.0}),
                                "StockholdersEquity": inst({"2025-12-31": 73_757.0, "2024-12-31": 64_021.0}),
                                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": inst({"2025-12-31": 79_779.0, "2024-12-31": 68_394.0})}}}
    periods = [(2024, "FY2024", date(2024, 12, 31)), (2025, "FY2025", date(2025, 12, 31)), (2023, "FY2023", date(2023, 12, 31))]
    assert D.noncontrolling_by_year(cf, periods) == {2025: 6_022.0, 2024: 4_373.0}                  # 2023: neither tag -> none


def test_resolve_adopts_a_legacy_company_without_cik_instead_of_creating_a_second_one():
    c = FakeClient()
    c.table("companies").insert({"symbol": "ACM", "company_name": "Acme Corporation", "exchange": "NASDAQ", "country": "US", "reporting_currency": "USD", "sector": "Technology"}).execute()
    c.table("company_listings").insert({"company_id": 1, "symbol": "ACM", "exchange": "NASDAQ", "is_primary": True, "is_active": True, "trading_currency": "USD", "data_source": "FMP"}).execute()
    repo = CompanyRepository(c)
    r = R.resolve(fake_sec(sub(K10, exchanges=("Nasdaq",))), "ACM")
    row = R.persist(r, repo, c, state="resolved")
    assert len(c.tables["companies"]) == 1 and row["id"] == 1 and row["cik"] == "0000000001" and row["exchange"] == "US" and row["sector"] == "Technology"      # updated in place, nothing lost
    assert len(c.tables["company_listings"]) == 1 and c.tables["company_listings"][0]["exchange"] == "NASDAQ"                                                     # same listing, the stored spelling stays
    w = c.writes
    R.persist(r, repo, c, state="resolved")
    assert c.writes == w and len(c.tables["company_listings"]) == 1                                                                                              # and it is idempotent


def test_resolve_does_not_adopt_a_company_of_another_cik_and_stops_on_an_ambiguous_legacy():
    c = FakeClient()
    c.table("companies").insert({"symbol": "ACM", "company_name": "Other", "exchange": "NYSE", "country": "US", "reporting_currency": "USD", "cik": "0000000999"}).execute()
    row = R.persist(R.resolve(fake_sec(sub(K10)), "ACM"), CompanyRepository(c), c, state="resolved")
    assert len(c.tables["companies"]) == 2 and row["cik"] == "0000000001" and c.tables["companies"][0]["cik"] == "0000000999"      # a different CIK is a different company
    d = FakeClient()
    for ex in ("NASDAQ", "NYSE"):
        d.table("companies").insert({"symbol": "ACM", "company_name": "Acme", "exchange": ex, "country": "US", "reporting_currency": "USD"}).execute()
    with pytest.raises(ValueError, match="have no CIK"):
        R.persist(R.resolve(fake_sec(sub(K10)), "ACM"), CompanyRepository(d), d, state="resolved")
    assert len(d.tables["companies"]) == 2
