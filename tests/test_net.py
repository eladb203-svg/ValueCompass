"""Network resilience (src/net.py): a gradual wait (30, 60, 120, 120 s; five attempts) on connection errors - default in the DB client and in the SEC clients. No network, no real waiting."""
import httpx
import pytest
import requests

from src import net


class Boom(Exception):
    pass


def flaky(failures, exc, result="ok"):
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if state["calls"] <= failures:
            raise exc
        return result
    return fn, state


def test_waits_are_30_60_120_120_and_the_call_succeeds_when_the_network_returns():
    waits = []
    fn, st = flaky(3, httpx.ConnectError("[Errno 11001] getaddrinfo failed"))
    assert net.retry_network(fn, sleep=waits.append) == "ok" and waits == [30, 60, 120] and st["calls"] == 4


def test_after_five_failed_attempts_the_last_error_is_raised_unchanged():
    waits = []
    err = httpx.ConnectError("[WinError 10065] unreachable host")
    fn, st = flaky(99, err)
    with pytest.raises(httpx.ConnectError) as e:
        net.retry_network(fn, sleep=waits.append)
    assert e.value is err and st["calls"] == 5 and waits == [30, 60, 120, 120]


@pytest.mark.parametrize("exc", [httpx.ConnectError("x"), httpx.ConnectTimeout("x"), requests.exceptions.ConnectionError("x"), requests.exceptions.ConnectTimeout("x"), __import__("socket").gaierror(11001, "getaddrinfo failed")])
def test_which_errors_count_as_network_errors(exc):
    assert net.is_network_error(exc)


@pytest.mark.parametrize("exc", [Boom("x"), ValueError("x"), httpx.ReadTimeout("x"), requests.exceptions.HTTPError("503")])
def test_other_errors_are_raised_at_once_without_waiting(exc):
    waits = []
    fn, st = flaky(1, exc)
    with pytest.raises(type(exc)):
        net.retry_network(fn, sleep=waits.append)
    assert waits == [] and st["calls"] == 1                    # a read timeout may mean the server got the request: never repeated


def test_the_db_transport_retries_a_failed_connection_for_a_write_too_and_the_server_answers_once():
    sent, waits = [], []

    def handler(request):
        sent.append(request.method)
        return httpx.Response(201, json=[{"id": 1}])
    inner_calls = {"n": 0}
    mock = httpx.MockTransport(handler)

    class Inner(httpx.BaseTransport):
        def handle_request(self, request):
            inner_calls["n"] += 1
            if inner_calls["n"] <= 2:
                raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
            return mock.handle_request(request)
    client = httpx.Client(transport=net.RetryTransport(Inner(), sleep=waits.append))
    r = client.post("https://example.test/rest/v1/t", json={"a": 1})
    assert r.status_code == 201 and sent == ["POST"] and waits == [30, 60]


def test_the_supabase_client_is_built_with_the_retrying_transport(monkeypatch):
    from src import db
    monkeypatch.setattr(db.config, "SUPABASE_TEST_URL", "https://wbhxjcegoobkbnjnuise.supabase.co")
    monkeypatch.setattr(db.config, "SUPABASE_TEST_SECRET_KEY", "sb_secret_dummy")
    monkeypatch.setenv("VC_DB_TARGET", "test")
    captured = {}
    monkeypatch.setattr(db, "create_client", lambda url, key, options=None: captured.update(url=url, options=options) or "client")
    assert db.get_supabase_client() == "client"
    assert isinstance(captured["options"].httpx_client._transport, net.RetryTransport)


def test_the_sec_clients_wait_and_retry_a_connection_error(monkeypatch, tmp_path):
    from src.pipeline.sec_source import PipelineSec, RateLimiter
    waits, calls = [], {"n": 0}
    monkeypatch.setattr(net.time, "sleep", waits.append)

    class Resp:
        text = '{"ok": 1}'

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": 1}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise requests.exceptions.ConnectionError("getaddrinfo failed")
        return Resp()
    monkeypatch.setattr(requests, "get", fake_get)
    sec = PipelineSec(tmp_path, user_agent="t t@example.com", limiter=RateLimiter(sleep=lambda s: None))
    assert sec.get_json("https://data.sec.gov/x.json", "x.json") == {"ok": 1} and calls["n"] == 3 and waits == [30, 60]
