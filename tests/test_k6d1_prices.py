"""K6d-1: the price jobs - hot stocks, the batch parse, the price score recomputed in place (no new run), one run per company with the "what changed" line, stale prices (E1). Fake database."""
import json
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from fakedb import FakeClient
from src.pipeline import dq
from src.pipeline.prices import apply_snapshot, parse_batch
from src.pipeline.reprice import PriceUpdater, parse_anchors, reprice_block, reprice_result, vs_buy
from src.repositories.score_repository import ScoreRepository, core_fingerprint
from src.sched.hot import hot_stocks, is_hot
from src.sched.jobs import JobRunner
from src.sched.schedule import DEFAULT_PATH, Config
from src.scoring import buffett as B
from src.scoring import graham as G
from src.scoring.interpolate import describe, interpolate

GOLDEN = Path(__file__).resolve().parent / "golden" / "2026-10-20"
NOW = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def golden(engine, ticker):
    return json.loads((GOLDEN / engine / f"{ticker}.json").read_text(encoding="utf-8"))


def company(client, symbol):
    client.table("companies").insert({"symbol": symbol, "company_name": symbol, "exchange": "US", "country": "US", "reporting_currency": "USD", "processing_state": "complete", "cik": f"{1000 + len(client.tables.get('companies', [])):010d}"}).execute()
    return client.tables["companies"][-1]["id"]


# ---------------------------------------------------------------- hot stocks
def test_is_hot_needs_a_price_and_a_buy_price_within_110_percent():
    assert is_hot(10.9, [10.0, None]) and is_hot(10.0, [None, 9.5]) and not is_hot(11.1, [10.0, 9.0]) and is_hot(11.1, [10.0, 12.0])
    assert not is_hot(None, [10.0]) and not is_hot(5.0, [None, None]) and not is_hot(5.0, [0, -1])


def test_hot_stocks_are_followed_by_a_user_and_near_a_buy_price():
    c = FakeClient()
    ids = {s: company(c, s) for s in ("KO", "MSFT", "INTC", "JPM")}
    prices = {"KO": 28.0, "MSFT": 500.0, "INTC": 20.0, "JPM": 10.0}
    buys = {"KO": (26.43, 11.57), "MSFT": (300.0, 200.0), "INTC": (None, None), "JPM": (9.5, None)}
    for s, p in prices.items():
        c.table("market_snapshot").insert({"company_id": ids[s], "current_price": p}).execute()
        c.table("company_score_summary").insert({"company_id": ids[s], "buffett_buy_price": buys[s][0], "graham_buy_price": buys[s][1]}).execute()
    c.table("portfolio_holdings").insert({"portfolio_id": 1, "company_id": ids["KO"], "quantity": 1}).execute()
    c.table("user_watchlist").insert({"user_id": "u", "company_id": ids["MSFT"]}).execute()
    c.table("user_watchlist").insert({"user_id": "u", "company_id": ids["INTC"]}).execute()
    c.table("user_watchlist").insert({"user_id": "v", "company_id": ids["JPM"]}).execute()
    # KO 28 <= 1.1 x 26.43; MSFT far above both; INTC has no buy price; JPM 10 <= 1.1 x 9.5 = 10.45 and followed
    assert [h["symbol"] for h in hot_stocks(c)] == ["KO", "JPM"]
    c.tables["portfolio_holdings"].clear()
    c.tables["user_watchlist"].clear()
    assert hot_stocks(c) == []                                                                 # nobody follows anything: no hot stock


def test_no_hot_stock_sends_no_request_and_a_closed_exchange_is_skipped():
    c = FakeClient()
    calls = []
    cfg = Config.load(DEFAULT_PATH)
    open_now = datetime(2026, 10, 26, 18, 0, tzinfo=timezone(timedelta(hours=2)))
    jr = JobRunner(c, cfg, now=lambda: open_now.astimezone(timezone.utc), fetch_batch=lambda t, intraday=False: calls.append(t) or {})
    out = jr.run("intraday_prices")
    assert out.status == "no_change" and out.detail["hot"] == 0 and calls == []
    closed = datetime(2026, 10, 24, 18, 0, tzinfo=timezone(timedelta(hours=2)))
    jr2 = JobRunner(c, cfg, now=lambda: closed.astimezone(timezone.utc), fetch_batch=lambda t, intraday=False: calls.append(t) or {})
    n = len(c.tables.get("data_update_log", []))
    assert jr2.run("intraday_prices").skipped and calls == [] and len(c.tables.get("data_update_log", [])) == n       # nothing logged for a skipped slot


# ---------------------------------------------------------------- batch parse
def frame(two_levels=True):
    idx = pd.to_datetime(["2026-10-22 15:55", "2026-10-23 15:55", "2026-10-23 15:59"])
    if two_levels:
        cols = pd.MultiIndex.from_product([["KO", "MSFT"], ["Close", "Volume"]])
        return pd.DataFrame([[60.0, 1, 400.0, 1], [61.0, 1, 401.0, 1], [62.5, 1, None, 1]], index=idx, columns=cols)
    return pd.DataFrame({"Close": [60.0, 61.0, 62.5]}, index=idx)


def test_parse_batch_takes_the_last_close_and_the_last_close_of_an_earlier_day():
    out = parse_batch(frame(), ["KO", "MSFT", "ZZZ"])
    assert out["KO"] == {"price": 62.5, "previous_close": 60.0, "market_date": date(2026, 10, 23)}          # the last bar of 23 Oct, and the last bar of 22 Oct
    assert out["MSFT"]["price"] == 401.0 and out["MSFT"]["previous_close"] == 400.0 and "ZZZ" not in out                                   # the missing last bar is skipped; an unknown ticker is left out
    assert parse_batch(frame(False), ["KO"])["KO"]["price"] == 62.5 and parse_batch(pd.DataFrame(), ["KO"]) == {}
    swapped = frame().swaplevel(axis=1)
    assert parse_batch(swapped, ["KO"])["KO"]["price"] == 62.5                                  # price type on top, ticker below


# ---------------------------------------------------------------- the price score in place
def test_the_anchors_the_run_stored_are_the_engines_anchors():
    assert parse_anchors(describe(B.PRICE_ANCHORS)) == B.PRICE_ANCHORS and parse_anchors(describe(G.CLASSIC_PRICE)) == G.CLASSIC_PRICE
    g = golden("general", "KO")
    assert parse_anchors(g["buffett_price"]["price_score"]["anchors"]) == B.PRICE_ANCHORS


def test_reprice_block_gives_the_engines_own_score_for_the_new_price():
    g = golden("general", "KO")
    b = reprice_block("buffett", g["buffett_price"], 28.0)
    fv = g["buffett_price"]["fair_value"]
    disc = (fv - 28.0) / fv
    assert b["price_score"]["points"] == pytest.approx(interpolate(disc, B.PRICE_ANCHORS)) and b["price_score"]["discount"] == pytest.approx(disc)
    assert b["price_current"] == 28.0 and b["fair_value"] == fv and b["buy_price"] == g["buffett_price"]["buy_price"]      # value and buy price do not move
    assert b["price_vs_buy"]["price_position"] == "near_buy_price" and b["price_vs_buy"]["distance"] == pytest.approx(28.0 / 26.431748 - 1)
    assert g["buffett_price"]["price_current"] == 88.050003                                     # the input is not changed
    assert reprice_block("graham", g["graham_price"], 28.0)["price_score"]["points"] == 0.0     # far above the Graham value
    low = reprice_block("buffett", g["buffett_price"], 26.0)
    assert low["price_vs_buy"]["price_position"] == "at_or_below_buy_price" and reprice_block("buffett", g["buffett_price"], 80.0)["price_vs_buy"]["price_position"] == "above_buy_price"


def test_a_stale_price_gives_no_price_score_and_a_missing_price_changes_nothing():
    g = golden("general", "KO")
    assert reprice_block("buffett", g["buffett_price"], 30.0, stale=True)["price_score"] == {"state": "stale", "points": None, "reason": "the price date is before the last trading day (E1)"}
    assert reprice_block("buffett", g["buffett_price"], None) is g["buffett_price"]
    assert reprice_result(g, None) is g
    assert vs_buy(30.0, {"state": "not_suitable"})["price_position"] == "no_buy_price"


def test_a_value_that_cannot_be_priced_stays_as_the_engine_left_it():
    blk = {"state": "cannot_be_valued", "fair_value": None, "price_score": {"state": "score", "points": 0.0}, "buy_price": None}
    assert reprice_block("buffett", blk, 30.0) is blk


def test_a_price_update_changes_the_price_part_in_place_and_never_creates_a_run():
    c = FakeClient()
    cid = company(c, "KO")
    s = ScoreRepository(c)
    g = golden("general", "KO")
    run_id, _ = s.write_result(cid, g)
    summ0 = dict(c.tables["company_score_summary"][0])
    snap = apply_snapshot(c, cid, {"price": 28.0, "previous_close": 27.5, "market_date": date(2026, 10, 26)}, NOW)
    r = PriceUpdater(c, now=lambda: NOW).update_company(cid, 28.0, date(2026, 10, 26), snap["snapshot_at"], snap["is_stale"])
    assert r["status"] == "updated" and len(c.tables["score_runs"]) == 1 and c.tables["score_runs"][0]["id"] == run_id
    vals = {v["model"]: v for v in c.tables["valuations"]}
    fv = g["buffett_price"]["fair_value"]
    assert vals["buffett"]["price_score"] == pytest.approx(round(interpolate((fv - 28.0) / fv, B.PRICE_ANCHORS), 2)) and vals["buffett"]["price_state"] == "scored"
    assert vals["buffett"]["details"]["price_vs_buy"]["price_position"] == "near_buy_price" and vals["graham"]["price_score"] == 0.0
    summ = c.tables["company_score_summary"][0]
    assert summ["buffett_price_score"] == vals["buffett"]["price_score"] and summ["buffett_quality_score"] == summ0["buffett_quality_score"] and summ["latest_run_id"] == run_id
    assert c.tables["score_runs"][0]["price"] == 28.0 and str(c.tables["score_runs"][0]["price_date"]) == "2026-10-26"
    assert c.tables["market_snapshot"][0]["current_price"] == 28.0 and c.tables["market_snapshot"][0]["is_stale"] is False
    n = len(c.tables["score_details"])
    assert PriceUpdater(c, now=lambda: NOW).update_company(cid, 28.0, date(2026, 10, 26), snap["snapshot_at"], False)["status"] == "unchanged"       # the same price twice changes nothing
    assert len(c.tables["score_details"]) == n


def test_a_stale_price_withdraws_the_price_score_and_a_new_price_brings_it_back():
    c = FakeClient()
    cid = company(c, "KO")
    ScoreRepository(c).write_result(cid, golden("general", "KO"))
    u = PriceUpdater(c, now=lambda: NOW)
    u.update_company(cid, 30.0, date(2026, 10, 20), None, stale=True)
    assert {v["price_state"] for v in c.tables["valuations"]} == {"stale"} and all(v["price_score"] is None for v in c.tables["valuations"])
    assert c.tables["company_score_summary"][0]["buffett_price_score"] is None
    u.update_company(cid, 30.0, date(2026, 10, 26), None, stale=False)
    assert {v["price_state"] for v in c.tables["valuations"]} == {"scored"} and c.tables["company_score_summary"][0]["buffett_price_score"] is not None


def test_a_company_without_a_run_is_left_alone():
    c = FakeClient()
    cid = company(c, "KO")
    assert PriceUpdater(c).update_company(cid, 30.0, date(2026, 10, 26)) == {"status": "no_run", "valuations": 0}


# ---------------------------------------------------------------- one run, the same result at another price
def test_the_same_quality_and_value_at_another_price_is_the_same_run():
    c = FakeClient()
    cid = company(c, "KO")
    s = ScoreRepository(c)
    g = golden("general", "KO")
    run_id, st = s.write_result(cid, g)
    assert st == "inserted" and core_fingerprint(g) == core_fingerprint(reprice_result(g, 40.0, "2026-10-26"))
    assert s.write_result(cid, reprice_result(g, 40.0, "2026-10-26")) == (run_id, "unchanged")
    assert len(c.tables["score_runs"]) == 1


def test_the_core_fingerprint_changes_with_quality_and_value_not_with_the_price():
    g = golden("general", "KO")
    q = json.loads(json.dumps(g))
    q["buffett_quality"]["score"] += 1
    v = json.loads(json.dumps(g))
    v["graham_price"]["value"] += 1
    assert core_fingerprint(q) != core_fingerprint(g) and core_fingerprint(v) != core_fingerprint(g)
    for engine, t in (("bank", "JPM"), ("insurance", "CB"), ("realestate", "O"), ("managed_care", "UNH")):
        r = golden(engine, t)
        assert core_fingerprint(reprice_result(r, 123.45, "2026-10-26")) == core_fingerprint(r), engine


def test_a_new_run_keeps_the_change_line_and_deletes_the_previous_run():
    c = FakeClient()
    cid = company(c, "KO")
    s = ScoreRepository(c)
    g = golden("general", "KO")
    for q in ("buffett_quality", "graham_quality"):                                             # a complete previous run: no AI item waits
        g[q]["pending_criteria"] = []
        for crit in g[q]["criteria"]:
            for it in crit["items"]:
                if it["state"] == "ai_pending":
                    it["state"], it["points"] = "score", it["max_pts"]
    first, _ = s.write_result(cid, g)
    c.tables["score_runs"][0]["run_at"] = "2026-10-20T10:00:00+00:00"
    nxt = json.loads(json.dumps(g))
    crit = nxt["buffett_quality"]["criteria"][0]
    crit["observed_points"] = max(0.0, (crit.get("observed_points") or 0) - 4.0)
    crit["range_min"] = crit["range_max"] = crit["observed_points"]
    nxt["buffett_quality"]["score"] = g["buffett_quality"]["score"] - 4.0
    nxt["buffett_quality"]["range_min"] = nxt["buffett_quality"]["range_max"] = nxt["buffett_quality"]["score"]
    second, st = s.write_result(cid, nxt)
    assert st == "inserted" and [r["id"] for r in c.tables["score_runs"]] == [second] and second != first
    ch = c.tables["score_runs"][0]["changes"]
    assert ch["previous_run"] == "2026-10-20" and ch["changes"] and ch["changes"][0]["direction_he"] and ch["reason_he"]
    assert "changes_error" not in c.tables["score_runs"][0]["flags"]
    assert {d["run_id"] for d in c.tables["score_details"]} == {second} and {v["run_id"] for v in c.tables["valuations"]} == {second}
    assert c.tables["company_score_summary"][0]["latest_run_id"] == second


def test_a_previous_run_that_waited_for_ai_passes_its_own_change_line_on():
    c = FakeClient()
    cid = company(c, "KO")
    s = ScoreRepository(c)
    g = golden("general", "KO")                                                                 # the golden still has AI items pending
    s.write_result(cid, g)
    c.tables["score_runs"][0]["changes"] = {"previous_run": "2026-09-01", "reason_he": "x", "changes": []}
    nxt = json.loads(json.dumps(g))
    nxt["buffett_quality"]["score"] += 2
    s.write_result(cid, nxt)
    assert c.tables["score_runs"][0]["changes"] == {"previous_run": "2026-09-01", "reason_he": "x", "changes": []}


# ---------------------------------------------------------------- the score job prices the run at the stored price
def test_priced_result_uses_the_stored_snapshot_and_rewrites_the_result_file(tmp_path):
    from src.pipeline.queue_runner import QueueRunner
    c = FakeClient()
    cid = company(c, "KO")
    c.table("market_snapshot").insert({"company_id": cid, "current_price": 28.0, "market_date": "2026-10-26", "is_stale": False}).execute()
    qr = QueueRunner(c, results_dir=tmp_path)
    g = golden("general", "KO")
    (tmp_path / "general").mkdir()
    out = types.SimpleNamespace(result=g, engine="general")
    res = qr.priced_result(cid, "KO", out)
    assert res["buffett_price"]["price_current"] == 28.0 and res["price"]["current"] == 28.0
    assert json.loads((tmp_path / "general" / "KO.json").read_text(encoding="utf-8"))["buffett_price"]["price_current"] == 28.0
    c.tables["market_snapshot"][0]["is_stale"] = True
    assert qr.priced_result(cid, "KO", out)["buffett_price"]["price_score"]["state"] == "stale"
    c.tables["market_snapshot"].clear()
    assert qr.priced_result(cid, "KO", out) is g                                                # no stored price: the engine's own price stays


# ---------------------------------------------------------------- E1
def test_a_price_is_stale_when_its_date_is_before_the_last_trading_day():
    """E1 (2026-10-28): the last trading day = the most recent day whose session has closed (New York time)."""
    fri = datetime(2026, 10, 23, 21, 0, tzinfo=timezone.utc)                                              # the close of Friday 23 Oct
    assert dq.price_freshness(fri, datetime(2026, 10, 26, 12, tzinfo=timezone.utc))[0] is False         # Monday morning (before the open): Friday is the last trading day
    assert dq.price_freshness(fri, datetime(2026, 10, 26, 18, tzinfo=timezone.utc))[0] is False         # Monday during the session: still fresh
    assert dq.price_freshness(fri, datetime(2026, 10, 26, 20, 30, tzinfo=timezone.utc))[0] is True      # Monday after the close: Monday is the last trading day, Friday's price is old
    mon = datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc)
    assert dq.price_freshness(mon, datetime(2026, 10, 27, 14, tzinfo=timezone.utc))[0] is False         # Tuesday during the session
    thanks = datetime(2026, 11, 25, 21, 0, tzinfo=timezone.utc)                                          # Wednesday before Thanksgiving
    assert dq.price_freshness(thanks, datetime(2026, 11, 26, 20, tzinfo=timezone.utc))[0] is False       # Thursday is a holiday: Wednesday stays the last trading day
    assert dq.price_freshness(thanks, datetime(2026, 11, 27, 19, tzinfo=timezone.utc))[0] is True        # Friday (half day, closed 18:00 UTC): the price of Wednesday is old
    assert dq.price_freshness(None)[0] is True
