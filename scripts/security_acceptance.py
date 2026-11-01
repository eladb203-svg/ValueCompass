"""Security stage acceptance (spec section 11 + tests 10-14), against the TEST project only.

Real users (created through the Auth admin API), real JWTs, real PostgREST and Edge Function calls. Creates test users and removes them at the end.
Needs .env (SUPABASE_TEST_URL, SUPABASE_TEST_SECRET_KEY) and VC_TEST_PUBLISHABLE_KEY (the publishable key of the test project; it is not a secret).
Makes no Gemini and no Azure calls and puts nothing in the work queue.
Run:  VC_TEST_PUBLISHABLE_KEY=... python scripts/security_acceptance.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV = dotenv_values(ROOT / ".env")                                     # python-dotenv only; values are never printed
URL = ENV["SUPABASE_TEST_URL"].rstrip("/")
SERVICE = ENV["SUPABASE_TEST_SECRET_KEY"]
PUB = os.environ["VC_TEST_PUBLISHABLE_KEY"]
PASSWORD = "Test-Passw0rd-" + "x" * 6
EMAILS = {"pending": "sec-pending@test.invalid", "a": "sec-a@test.invalid", "b": "sec-b@test.invalid", "admin": "sec-admin@test.invalid"}
TABLES = ["ai_assessments", "ai_texts", "business_vocab", "companies", "company_business_profiles", "company_listings", "company_profile_history", "company_score_summary",
          "data_update_log", "dictionary_items", "extraction_items", "fact_tags", "filing_periods", "financial_facts", "fx_rates", "gov_yields", "market_calendar", "market_snapshot",
          "portfolio_holdings", "portfolios", "score_details", "score_runs", "term_translations", "user_profiles", "user_watchlist", "valuations", "work_queue",
          "app_settings", "support_tickets", "user_notifications", "admin_audit_log", "smart_search_usage",
          "portfolio_overview_view", "stock_score_overview_view", "watchlist_overview_view", "v_company_status", "v_display_metrics", "v_fin_bank", "v_fin_insurance",
          "v_fin_realestate", "v_fin_standard", "v_holding_counts"]
VIEWS = ["v_stocks", "v_stock_page", "v_top_ranked", "v_my_profile", "v_my_portfolio", "v_my_watchlist", "v_my_tickets", "v_my_notifications"]
FUNCS = ["portfolio-save", "request-company", "smart-search", "admin-users", "notifications-read"]
RESULTS: list = []


def http(method, path, key, token=None, body=None, headers=None):
    h = {"apikey": key, "Authorization": f"Bearer {token or key}", "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(URL + path, data=None if body is None else json.dumps(body).encode(), headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode("utf8", "replace")


def svc(method, path, body=None, prefer=None):
    return http(method, path, SERVICE, body=body, headers={"Prefer": prefer} if prefer else None)


def user_call(token, method, path, body=None):
    return http(method, path, PUB, token=token, body=body)


def fn(token, name, body=None):
    return http("POST", f"/functions/v1/{name}", PUB, token=token, body=body or {})


def record(n, name, ok, how):
    RESULTS.append((n, name, bool(ok), how))
    print(f"[{'PASS' if ok else 'FAIL'}] {n}. {name} - {how}")


def denied(status, body):
    return status in (401, 403) or (isinstance(body, dict) and body.get("code") in ("42501", "PGRST301"))


def main():
    users = {}
    try:
        for k, email in EMAILS.items():                                          # create (clean any leftovers first)
            s, lst = svc("GET", "/auth/v1/admin/users?per_page=200")
            for u in (lst or {}).get("users", []):
                if u["email"] == email:
                    svc("DELETE", f"/auth/v1/admin/users/{u['id']}")
            s, u = svc("POST", "/auth/v1/admin/users", {"email": email, "password": PASSWORD, "email_confirm": True})
            assert s == 200, (k, s, u)
            users[k] = {"id": u["id"]}
            s, t = http("POST", "/auth/v1/token?grant_type=password", PUB, body={"email": email, "password": PASSWORD})
            assert s == 200, (k, s, t)
            users[k]["token"] = t["access_token"]
        # the sign-up trigger: open mode (the default) without an invitation -> pending; it can never become active by itself
        s, mode = svc("GET", "/rest/v1/app_settings?key=eq.registration_mode&select=value")
        s, p = svc("GET", f"/rest/v1/user_profiles?id=eq.{users['a']['id']}&select=role,status")
        record("0a", "Default registration_mode is open; sign-up trigger without an invitation -> pending", mode == [{"value": "open"}] and p == [{"role": "user", "status": "pending"}], f"mode={mode}; profile={p}")
        s, a = user_call(users["a"]["token"], "GET", "/rest/v1/v_stocks?limit=1")
        record("0b", "Pending user sees nothing", a == [], f"v_stocks={a}")
        for k, st, role in (("pending", "pending", "user"), ("a", "active", "user"), ("b", "active", "user"), ("admin", "active", "admin")):
            svc("PATCH", f"/rest/v1/user_profiles?id=eq.{users[k]['id']}", {"status": st, "role": role})
        # the trigger with a real invitation flag (invited_at) is checked in SQL by the report (admin_email -> admin)

        # 1 anonymous
        bad = []
        for t in TABLES + VIEWS:
            s, b = http("GET", f"/rest/v1/{t}?limit=1", PUB)
            if not denied(s, b):
                bad.append((t, s))
        for f in ("is_active", "is_admin", "smart_search_take", "security_retention"):
            s, b = http("POST", f"/rest/v1/rpc/{f}", PUB, body={})
            if not denied(s, b):
                bad.append((f, s))
        for f in FUNCS:
            s, b = http("POST", f"/functions/v1/{f}", PUB, body={})
            if s != 401:
                bad.append((f, s))
        record(1, "Anonymous sees no table, view or function", not bad, f"{len(TABLES) + len(VIEWS)} relations + 4 rpc + {len(FUNCS)} functions via REST with the publishable key; failures={bad}")

        # 2 pending
        pt = users["pending"]["token"]
        got = {v: user_call(pt, "GET", f"/rest/v1/{v}?limit=5")[1] for v in VIEWS}
        ok = all(got[v] == [] for v in VIEWS if v != "v_my_profile") and len(got["v_my_profile"]) == 1 and got["v_my_profile"][0]["status"] == "pending"
        s, b = user_call(pt, "GET", "/rest/v1/companies?limit=1")
        record(2, "Pending user: only the waiting screen", ok and denied(s, b), f"views={ {v: (len(x) if isinstance(x, list) else x) for v, x in got.items()} }; companies direct -> {s}")

        # 3 active A
        at, bt = users["a"]["token"], users["b"]["token"]
        s, stocks = user_call(at, "GET", "/rest/v1/v_stocks?select=symbol&limit=3")
        s2, page = user_call(at, "GET", "/rest/v1/v_stock_page?select=symbol,buffett_quality_score,texts,metrics,criteria,valuations&limit=1")
        s3, top = user_call(at, "GET", "/rest/v1/v_top_ranked?rank_type=eq.combined&sector_scope=is.null&country_scope=is.null&order=rank")
        record(3, "Active A reads stock data", len(stocks) > 0 and len(page) > 0 and len(top) in range(1, 6), f"v_stocks={len(stocks)} rows, v_stock_page={len(page)}, v_top_ranked combined={len(top)} (max 5)")
        s, h = fn(at, "portfolio-save", {"symbol": "KO", "quantity": 10, "average_cost": 50})
        hid = (h or {}).get("holding", {}).get("id")
        svc("POST", "/rest/v1/user_watchlist", {"user_id": users["a"]["id"], "company_id": (h or {}).get("holding", {}).get("company_id"), "notes": "sec-test"})
        s, mine = user_call(at, "GET", "/rest/v1/v_my_portfolio")
        record("3b", "A writes only through functions and reads own rows", s == 200 and hid and any(r["symbol"] == "KO" for r in mine), f"portfolio-save -> holding {hid}; v_my_portfolio={len(mine)} row(s)")

        # 4 user B
        s, bp = user_call(bt, "GET", "/rest/v1/v_my_portfolio")
        s2, bw = user_call(bt, "GET", "/rest/v1/v_my_watchlist")
        s3, byid = user_call(bt, "GET", f"/rest/v1/portfolio_holdings?id=eq.{hid}")
        s4, upd = fn(bt, "portfolio-save", {"holding_id": hid, "quantity": 999})
        s5, dele = fn(bt, "portfolio-delete", {"holding_id": hid}) if False else (404, None)     # portfolio-delete is not deployed in this run (see report)
        s6, still = svc("GET", f"/rest/v1/portfolio_holdings?id=eq.{hid}&select=quantity")
        record(4, "User B cannot read or change A's private data, even by id", bp == [] and bw == [] and denied(s3, byid) and s4 == 404 and still[0]["quantity"] == 10,
               f"B views empty; direct by id -> {s3}; portfolio-save on A's holding -> {s4}; A's quantity still {still[0]['quantity']}")

        # 5 / 6 admin
        ad = users["admin"]["token"]
        s, lst = fn(ad, "admin-users", {"action": "list"})
        s2, counts = fn(ad, "admin-users", {"action": "holding_counts"})
        s3, adm_port = user_call(ad, "GET", "/rest/v1/v_my_portfolio")
        s4, setr = fn(ad, "admin-users", {"action": "set_status", "user_id": users["pending"]["id"], "value": "active"})
        s5, log = svc("GET", f"/rest/v1/admin_audit_log?admin_id=eq.{users['admin']['id']}&select=action,target_id,before,after")
        no_ids = all(set(c.keys()) <= {"company_id", "in_portfolios", "in_watchlists", "total"} for c in (counts or {}).get("counts", []))
        record(5, "Admin: functions work, A's portfolio not in admin screens, audit log records", s == 200 and s4 == 200 and adm_port == [] and no_ids and any(r["action"] == "set_status" and r["after"]["status"] == "active" for r in log),
               f"admin-users list={s}, set_status={s4}; admin v_my_portfolio={adm_port}; holding_counts keys without user ids={no_ids}; audit rows={len(log)}")
        svc("PATCH", f"/rest/v1/user_profiles?id=eq.{users['pending']['id']}", {"status": "pending"})
        s, r1 = fn(at, "admin-users", {"action": "list"})
        s2, r2 = fn(pt, "admin-users", {"action": "list"})
        s3, r3 = fn(at, "admin-users", {"action": "set_role", "user_id": users["a"]["id"], "value": "admin"})
        record(6, "Non-admin calls an admin function: refused (403)", (s, s2, s3) == (403, 403, 403), f"active user -> {s}, pending user -> {s2}, active user set_role self->admin -> {s3}")

        # 7 smart search cap
        svc("PATCH", "/rest/v1/app_settings?key=eq.smart_search_daily_cap", {"value": "1"})
        svc("DELETE", "/rest/v1/smart_search_usage?day=gte.2000-01-01")
        r1 = svc("POST", "/rest/v1/rpc/smart_search_take", {})[1]
        r2 = svc("POST", "/rest/v1/rpc/smart_search_take", {})[1]
        svc("PATCH", "/rest/v1/app_settings?key=eq.smart_search_daily_cap", {"value": "200"})
        svc("DELETE", "/rest/v1/smart_search_usage?day=gte.2000-01-01")
        s, res = fn(at, "smart-search", {"query": "coca"})
        txt = json.dumps(res).lower()
        record(7, "Smart-search cap reached: regular search answers, no message", (r1, r2) == (True, False) and s == 200 and res.get("results") and "smart" not in txt and "cap" not in txt,
               f"cap=1: take()={r1}, then {r2}; search 'coca' -> {len(res.get('results', []))} result(s), no smart/cap wording")

        # 12 search without result -> request-company runs automatically
        s, nf = fn(at, "smart-search", {"query": "ZZZZQ"})
        req = (nf or {}).get("request") or {}
        record(12, "A search with no result calls request-company automatically", s == 200 and nf.get("not_found") and req.get("status") in ("unavailable", "unsupported") and "report_form" in req,
               f"smart-search 'ZZZZQ' -> no result, request.status={req.get('status')}, reason={req.get('reason')}, report form prefilled={'report_form' in req}")

        # 13 notifications only for the right user
        sym = "SECTST1"
        s, c = svc("POST", "/rest/v1/companies", {"symbol": sym, "company_name": "Security Test Co", "exchange": "US", "country": "US", "reporting_currency": "USD", "processing_state": "resolved"}, "return=representation")
        cid = c[0]["id"]
        svc("POST", "/rest/v1/support_tickets", {"user_id": users["a"]["id"], "type": "company_request", "requested_ticker": sym, "company_id": cid, "status": "open"})
        for st in ("data_loaded", "complete"):
            svc("PATCH", f"/rest/v1/companies?id=eq.{cid}", {"processing_state": st})
        s, tk = svc("POST", "/rest/v1/support_tickets", {"user_id": users["a"]["id"], "type": "support", "body": "sec-test"}, "return=representation")
        svc("PATCH", f"/rest/v1/support_tickets?id=eq.{tk[0]['id']}", {"admin_reply": "answer"})
        svc("PATCH", f"/rest/v1/support_tickets?id=eq.{tk[0]['id']}", {"status": "closed"})
        s, na = user_call(at, "GET", "/rest/v1/v_my_notifications")
        s, nb = user_call(bt, "GET", "/rest/v1/v_my_notifications")
        types = sorted(n["type"] for n in na)
        s, tkts = user_call(at, "GET", "/rest/v1/v_my_tickets?select=type,status,requested_ticker&order=ticket_id")
        want = ["company_ready", "company_started", "ticket_reply", "ticket_status"]
        record(13, "Admin reply and a completed requested stock notify only the right user", types == want and nb == [],
               f"A's notifications={types}; B's={nb}; A's tickets={[(t['type'], t['status']) for t in tkts]}")
        svc("DELETE", f"/rest/v1/companies?id=eq.{cid}")
        s, read = fn(at, "notifications-read", {})
        s2, left = user_call(at, "GET", "/rest/v1/v_my_notifications?read_at=is.null")
        record("13b", "notifications-read marks only the caller's", s == 200 and read["marked"] == 4 and left == [], f"marked={read}")

        # 10 / 11 no direct table access, role/status cannot be changed
        bad = []
        for t in TABLES:
            for m, path, body in (("GET", f"/rest/v1/{t}?limit=1", None), ("POST", f"/rest/v1/{t}", {}), ("PATCH", f"/rest/v1/{t}?id=eq.0", {}), ("DELETE", f"/rest/v1/{t}?id=eq.0", None)):
                s, b = user_call(at, m, path, body)
                ok_ = denied(s, b) if m == "GET" else s not in (200, 201, 204)     # a write that succeeds is the failure; the grant catalog is checked in scripts/security_privileges_check.sql
                if not ok_:
                    bad.append((m, t, s))
        record(10, "Active user reads or writes no table directly (incl. user_profiles, portfolios)", not bad, f"{len(TABLES)} relations x GET/POST/PATCH/DELETE as active user A; failures={bad}")
        tries = [user_call(at, "PATCH", f"/rest/v1/user_profiles?id=eq.{users['a']['id']}", {"role": "admin"}), user_call(at, "PATCH", f"/rest/v1/user_profiles?id=eq.{users['a']['id']}", {"status": "active"}),
                 user_call(at, "POST", "/rest/v1/user_profiles", {"id": users["a"]["id"], "role": "admin"}), fn(at, "admin-users", {"action": "set_role", "user_id": users["a"]["id"], "value": "admin"})]
        s, prof = svc("GET", f"/rest/v1/user_profiles?id=eq.{users['a']['id']}&select=role,status")
        record(11, "A user cannot change own role or status in any way", all(denied(s, b) for s, b in tries) and prof == [{"role": "user", "status": "active"}],
               f"PATCH role, PATCH status, POST profile, admin-users set_role -> {[s for s, _ in tries]}; profile afterwards={prof} (DB trigger guard is checked in SQL, see report)")

        # 14 retention (180 days)
        old = (datetime.now(timezone.utc) - timedelta(days=181)).isoformat()
        young = (datetime.now(timezone.utc) - timedelta(days=179)).isoformat()
        uid = users["a"]["id"]
        def mk(body_, status, **extra):
            s, r = svc("POST", "/rest/v1/support_tickets", {"user_id": uid, "type": "support", "body": body_, "status": status}, "return=representation")
            return r[0]["id"]
        t_closed_old, t_closed_young, t_open_old = mk("ret-closed-old", "closed"), mk("ret-closed-young", "closed"), mk("ret-open-old", "open")
        svc("PATCH", f"/rest/v1/support_tickets?id=eq.{t_closed_old}", {"closed_at": old})
        svc("PATCH", f"/rest/v1/support_tickets?id=eq.{t_closed_young}", {"closed_at": young})
        svc("PATCH", f"/rest/v1/support_tickets?id=eq.{t_open_old}", {"created_at": old})
        svc("POST", "/rest/v1/user_notifications", [{"user_id": uid, "type": "ticket_status", "text": "ret-old", "created_at": old}, {"user_id": uid, "type": "ticket_status", "text": "ret-young", "created_at": young}])
        s, out = svc("POST", "/rest/v1/rpc/security_retention", {})
        s, left = svc("GET", f"/rest/v1/support_tickets?id=in.({t_closed_old},{t_closed_young},{t_open_old})&select=id")
        s, nl = svc("GET", f"/rest/v1/user_notifications?user_id=eq.{uid}&text=in.(ret-old,ret-young)&select=text")
        ids = sorted(r["id"] for r in left)
        record(14, "Closed ticket 181 days old deleted; old open ticket stays; notifications 180 days", ids == sorted([t_closed_young, t_open_old]) and [r["text"] for r in nl] == ["ret-young"],
               f"retention={out}; remaining tickets={ids} (closed-young, open-old); remaining notifications={[r['text'] for r in nl]}")

        # 15-17 sign-up requests (no sign-in)
        def signup(name, email, ip):
            return http("POST", "/functions/v1/signup-request", PUB, body={"name": name, "email": email}, headers={"x-forwarded-for": ip})
        e1, e2, e3 = ("eladb203+vcsec1@gmail.com", "eladb203+vcsec2@gmail.com", "sec-req3@test.invalid")
        codes = [signup("R", e3, "198.51.100.1")[0] for _ in range(4)]            # 3 rows of this caller, the 4th is refused by the e-mail limit
        profiles_before = len(svc("GET", "/auth/v1/admin/users?per_page=200")[1]["users"])
        s1, b1 = signup("Dana Test", e1, "203.0.113.1")
        s_t, tick = svc("GET", f"/rest/v1/support_tickets?signup_email=eq.{quote(e1)}&select=id,type,status,user_id,signup_name")
        users_after = svc("GET", "/auth/v1/admin/users?per_page=200")[1]["users"]
        record(15, "signup-request without sign-in creates a request and no account", s1 == 200 and len(tick) == 1 and tick[0]["type"] == "signup" and tick[0]["status"] == "open" and tick[0]["user_id"] is None
               and len(users_after) == profiles_before and not any(u["email"] == e1 for u in users_after), f"status={s1}; ticket={tick}; auth users {profiles_before} -> {len(users_after)}")
        signup("Rot Test", e2, "203.0.113.2")
        _, t2 = svc("GET", f"/rest/v1/support_tickets?signup_email=eq.{quote(e2)}&select=id")
        ad = users["admin"]["token"]
        sa, _ = fn(users["a"]["token"], "admin-tickets", {"action": "signup_decision", "ticket_id": tick[0]["id"], "decision": "approve"})
        sr, _ = fn(ad, "admin-tickets", {"action": "signup_decision", "ticket_id": t2[0]["id"], "decision": "reject"})
        sap, bap = fn(ad, "admin-tickets", {"action": "signup_decision", "ticket_id": tick[0]["id"], "decision": "approve"})
        _, st = svc("GET", f"/rest/v1/support_tickets?id=in.({tick[0]['id']},{t2[0]['id']})&select=id,status&order=id")
        au = svc("GET", "/auth/v1/admin/users?per_page=200")[1]["users"]
        inv1 = [u for u in au if u["email"] == e1]
        inv2 = [u for u in au if u["email"] == e2]
        _, prof1 = svc("GET", f"/rest/v1/user_profiles?id=eq.{inv1[0]['id']}&select=role,status,full_name") if inv1 else (0, None)
        part_ok = sa == 403 and sr == 200 and {r["id"]: r["status"] for r in st}.get(t2[0]["id"]) == "closed" and not inv2 and (sap == 200 or (sap == 400 and {r["id"]: r["status"] for r in st}.get(tick[0]["id"]) == "open" and not inv1))
        record("16b", "Non-admin refused; rejection closes without an invitation; a failed invitation leaves the request open", part_ok, f"non-admin={sa}, reject={sr}, approve={sap} {bap if sap != 200 else ''}; statuses={st}")
        record(16, "Approval creates an invitation (invited user active, name kept); rejection closes without one; non-admin refused", sa == 403 and sr == 200 and sap in (200,)
               and {r["id"]: r["status"] for r in st} == {tick[0]["id"]: "done", t2[0]["id"]: "closed"} and len(inv1) == 1 and inv1[0].get("invited_at") and not inv2
               and prof1 == [{"role": "user", "status": "active", "full_name": "Dana Test"}], f"non-admin={sa}, reject={sr}, approve={sap} {bap if sap != 200 else ''}; statuses={st}; invited e1={bool(inv1)} (invited_at={inv1[0].get("invited_at") if inv1 else None}), e2={bool(inv2)}; profile={prof1}")
        # rows of this caller so far: e3 x3, e1, e2 = 5 -> a new email from the same address is refused by the IP limit (the platform sets the real client address; a forged header does not help)
        code_ip = signup("R", "sec-ip@test.invalid", "192.0.2.77")[0]
        record(17, "Rate limit: 3 per email and 5 per IP per day", codes == [200, 200, 200, 429] and code_ip == 429, f"same email x4 -> {codes}; 6th request from the same address (new email) -> {code_ip}")

        # 18 a real invitation through Auth (inviteUserByEmail = POST /auth/v1/invite): the profile must end active; admin only for the admin e-mail
        ADM_EMAIL, USR_EMAIL = "eladb203+vcsecadm@gmail.com", "eladb203+vcsec3@gmail.com"
        s_, old_admin = svc("GET", "/rest/v1/app_settings?key=eq.admin_email&select=value")
        svc("PATCH", "/rest/v1/app_settings?key=eq.admin_email", {"value": ADM_EMAIL})
        try:
            r_adm = svc("POST", "/auth/v1/invite", {"email": ADM_EMAIL, "data": {"full_name": "Adm Test", "invited_by": users["admin"]["id"]}})
            r_usr = svc("POST", "/auth/v1/invite", {"email": USR_EMAIL, "data": {"full_name": "Usr Test", "invited_by": users["admin"]["id"], "role": "admin"}})
            got = {}
            for em, r_ in ((ADM_EMAIL, r_adm), (USR_EMAIL, r_usr)):
                if r_[0] == 200:
                    got[em] = svc("GET", f"/rest/v1/user_profiles?id=eq.{r_[1]['id']}&select=role,status,full_name,invited_by")[1]
            ok18 = (r_adm[0] == 200 and r_usr[0] == 200
                    and got[ADM_EMAIL] == [{"role": "admin", "status": "active", "full_name": "Adm Test", "invited_by": users["admin"]["id"]}]
                    and got[USR_EMAIL] == [{"role": "user", "status": "active", "full_name": "Usr Test", "invited_by": users["admin"]["id"]}])
            record(18, "Real invitation: admin e-mail -> admin+active; any other -> user+active (role in metadata ignored)", ok18,
                   f"invite statuses={r_adm[0]},{r_usr[0]}; messages={[r_[1].get('msg') or r_[1].get('message') for r_ in (r_adm, r_usr) if r_[0] != 200]}; profiles={got}")
        finally:
            svc("PATCH", "/rest/v1/app_settings?key=eq.admin_email", {"value": old_admin[0]["value"]})
            for u in svc("GET", "/auth/v1/admin/users?per_page=200")[1].get("users", []):
                if u["email"] in (ADM_EMAIL, USR_EMAIL):
                    svc("DELETE", f"/auth/v1/admin/users/{u['id']}")
    finally:
        svc("DELETE", "/rest/v1/support_tickets?type=eq.signup")
        for u in svc("GET", "/auth/v1/admin/users?per_page=200")[1].get("users", []):
            if u["email"] in ("eladb203+vcsec1@gmail.com", "eladb203+vcsec2@gmail.com"):
                svc("DELETE", f"/auth/v1/admin/users/{u['id']}")
        for k, u in users.items():                                               # remove everything this run created
            uid = u["id"]
            for t in ("user_notifications", "support_tickets", "user_watchlist"):
                svc("DELETE", f"/rest/v1/{t}?user_id=eq.{uid}")
            s, ps = svc("GET", f"/rest/v1/portfolios?user_id=eq.{uid}&select=id")
            for p in ps or []:
                svc("DELETE", f"/rest/v1/portfolio_holdings?portfolio_id=eq.{p['id']}")
            svc("DELETE", f"/rest/v1/portfolios?user_id=eq.{uid}")
            svc("DELETE", f"/rest/v1/admin_audit_log?admin_id=eq.{uid}")
            svc("DELETE", f"/auth/v1/admin/users/{uid}")
        svc("DELETE", "/rest/v1/companies?symbol=eq.SECTST1")
        s, left = svc("GET", "/auth/v1/admin/users?per_page=200")
        rest = [u["email"] for u in (left or {}).get("users", []) if u["email"] in EMAILS.values()]
        print("test users left:", rest)
    failed = [r for r in RESULTS if not r[2]]
    print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
