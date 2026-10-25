"""A small in-memory stand-in for the supabase-py client (the subset the K6a repositories use): table(name).select/eq/in_/order/range/limit/insert/upsert/update/execute."""
from __future__ import annotations

import copy

AUTO_ID = {"companies": "id", "fact_tags": "id", "extraction_items": "id", "company_listings": "id", "data_update_log": "id"}
UNIQUE = {"companies": [("symbol", "exchange"), ("cik",)], "fact_tags": [("tag",)], "extraction_items": [("company_id", "item_key", "period", "document_ref")],
          "financial_facts": [("company_id", "fiscal_year", "item_id")], "filing_periods": [("company_id", "fiscal_year")], "company_listings": [("symbol", "exchange")],
          "company_profile_history": [("company_id", "fiscal_year")], "market_snapshot": [("company_id",)]}


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, name):
        self.db, self.name, self.rows = db, name, db.tables.setdefault(name, [])
        self._eq, self._order, self._range, self._limit, self._op, self._payload, self._conflict = [], None, None, None, "select", None, None

    def select(self, cols="*"):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def range(self, a, b):
        self._range = (a, b)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op, self._payload, self._conflict = "upsert", payload, on_conflict
        return self

    def update(self, fields):
        self._op, self._payload = "update", fields
        return self

    def _match(self, r):
        return all(r.get(c) == v for c, v in self._eq)

    def _next_id(self, col):
        return max([r.get(col, 0) for r in self.rows] + [0]) + 1

    def _put(self, row, conflict_cols):
        row = copy.deepcopy(row)
        if self.name in AUTO_ID and AUTO_ID[self.name] not in row:
            row[AUTO_ID[self.name]] = None
        for cols in UNIQUE.get(self.name, []):
            if conflict_cols and tuple(conflict_cols) != tuple(cols):
                continue
            for r in self.rows:
                if all(r.get(c) == row.get(c) for c in cols):
                    if conflict_cols:
                        keep = r.get(AUTO_ID.get(self.name))
                        r.update(row)
                        if keep is not None:
                            r[AUTO_ID[self.name]] = keep
                        return r
                    raise ValueError(f"duplicate key in {self.name}: {cols}")
        if self.name in AUTO_ID and row.get(AUTO_ID[self.name]) is None:
            row[AUTO_ID[self.name]] = self._next_id(AUTO_ID[self.name])
        self.rows.append(row)
        return row

    def execute(self):
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            return Result([copy.deepcopy(self._put(r, None)) for r in items])
        if self._op == "upsert":
            cols = [c.strip() for c in self._conflict.split(",")] if self._conflict else None
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            return Result([copy.deepcopy(self._put(r, cols)) for r in items])
        if self._op == "update":
            hit = [r for r in self.rows if self._match(r)]
            for r in hit:
                r.update(self._payload)
            return Result(copy.deepcopy(hit))
        out = [copy.deepcopy(r) for r in self.rows if self._match(r)]
        if self._order:
            out.sort(key=lambda r: (r.get(self._order[0]) is None, r.get(self._order[0])), reverse=self._order[1])
        if self._range:
            out = out[self._range[0]:self._range[1] + 1]
        if self._limit:
            out = out[:self._limit]
        return Result(out)


class FakeClient:
    def __init__(self, dictionary_keys=()):
        self.tables = {"dictionary_items": [{"id": i + 1, "item_key": k} for i, k in enumerate(dictionary_keys)]}
        self.writes = 0

    def table(self, name):
        q = Query(self, name)
        orig = q.execute

        def counted():
            if q._op in ("insert", "upsert", "update"):
                self.writes += len(q._payload) if isinstance(q._payload, list) else 1
            return orig()
        q.execute = counted
        return q
