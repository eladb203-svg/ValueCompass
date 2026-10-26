"""The schedule (K6 spec 3.1): ``config/schedule.yaml`` -> the times every job is due, computed in code (so New York's and Israel's clock changes, holidays and half days are always right).

``slots(job, day)``  the due times of a job on one Israel calendar day
``next_due`` / ``last_due``  the first due time after a moment / the last one at or before it
``SlotTrigger``  an APScheduler trigger that fires at those times
Any job may have ``interval_minutes: N`` in the file: it then runs every N minutes all day (for a short live test).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml
from apscheduler.triggers.base import BaseTrigger

from .nyse import NY, Calendar

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "schedule.yaml"
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
JOB_NAMES = ("close_prices", "intraday_prices", "new_reports", "ai_queue", "audit", "yields", "fx", "cleanup")
NO_CATCH_UP = ("intraday_prices",)
SEARCH_DAYS = 45                                        # a monthly job is found within this many days


def _hm(text: str) -> time:
    h, m = str(text).split(":")
    return time(int(h), int(m))


class Config:
    def __init__(self, raw: dict, path: Optional[Path] = None):
        self.raw, self.path = raw, path
        self.tz = ZoneInfo(raw.get("timezone") or "Asia/Jerusalem")
        self.jobs = {n: dict(raw.get("jobs", {}).get(n) or {}) for n in JOB_NAMES}
        self.calendar = Calendar(raw.get("extra_closed") or [])
        self.ignore_market_hours = bool(raw.get("ignore_market_hours"))
        self.admin_email = raw.get("ADMIN_EMAIL")
        self.catch_up_order = list(raw.get("catch_up_order") or [])

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = Path(path) if path else DEFAULT_PATH
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, path)

    def enabled(self, job: str) -> bool:
        return bool(self.jobs[job].get("enabled", True)) and bool(self.jobs[job])

    def get(self, job: str, key: str, default=None):
        return self.jobs[job].get(key, default)

    # ------------------------------------------------------------ the due times
    def _at(self, d: date, t: time) -> datetime:
        return datetime.combine(d, t, self.tz)

    def slots(self, job: str, d: date) -> list:
        """Due times (aware, Israel time) of ``job`` on the Israel calendar day ``d``, in order."""
        j = self.jobs[job]
        if not self.enabled(job):
            return []
        step = j.get("interval_minutes")
        if step:
            return [self._at(d, time(0, 0)) + timedelta(minutes=k) for k in range(0, 24 * 60, int(step))]
        if job == "close_prices":
            out = []
            for nd in (d - timedelta(days=1), d, d + timedelta(days=1)):
                s = self.calendar.session(nd)
                if s:
                    t = (s[1] + timedelta(minutes=int(j.get("minutes_after_close", 30)))).astimezone(self.tz)
                    if t.date() == d:
                        out.append(t)
            return sorted(out)
        if job == "intraday_prices":
            n = max(30, min(60, int(j.get("every_minutes", 30))))
            lo, hi = _hm(j.get("from", "10:00")), _hm(j.get("to", "23:00"))
            out, k = [], 0
            while k < 24 * 60:
                t = self._at(d, time(0, 0)) + timedelta(minutes=k)
                if lo <= t.time() <= hi and (self.ignore_market_hours or self.calendar.in_session(t)):
                    out.append(t)
                k += n
            return out
        if job == "ai_queue":
            n = int(j.get("every_minutes", 30))
            start = _hm(j.get("from", "10:00"))
            out, k = [], start.hour * 60 + start.minute
            while k < 24 * 60:
                out.append(self._at(d, time(0, 0)) + timedelta(minutes=k))
                k += n
            return out
        if job in ("new_reports", "fx"):
            return [self._at(d, _hm(j.get("at", "06:00")))]
        if job in ("audit", "cleanup"):
            return [self._at(d, _hm(j.get("at", "03:00")))] if d.weekday() == WEEKDAYS[str(j.get("weekday", "sun")).lower()[:3]] else []
        if job == "yields":
            return [self._at(d, _hm(j.get("at", "07:00")))] if d.day == min(int(j.get("day", 3)), 28) else []
        raise KeyError(job)

    def next_due(self, job: str, after: datetime) -> Optional[datetime]:
        """The first due time strictly after ``after``."""
        after = after.astimezone(self.tz)
        d = after.date()
        for _ in range(SEARCH_DAYS):
            for t in self.slots(job, d):
                if t > after:
                    return t
            d += timedelta(days=1)
        return None

    def last_due(self, job: str, now: datetime) -> Optional[datetime]:
        """The last due time at or before ``now``."""
        now = now.astimezone(self.tz)
        d = now.date()
        for _ in range(SEARCH_DAYS):
            ok = [t for t in self.slots(job, d) if t <= now]
            if ok:
                return ok[-1]
            d -= timedelta(days=1)
        return None

    def intraday_open(self, now: datetime) -> bool:
        """May the intraday job work now? (the exchange is open and it is inside the window; a test may ignore the market)"""
        t = now.astimezone(self.tz).time()
        lo, hi = _hm(self.get("intraday_prices", "from", "10:00")), _hm(self.get("intraday_prices", "to", "23:00"))
        return lo <= t <= hi and (self.ignore_market_hours or self.calendar.in_session(now))

    def ny_today(self, now: datetime) -> date:
        return now.astimezone(NY).date()


class SlotTrigger(BaseTrigger):
    """An APScheduler trigger (APScheduler 3: ``get_next_fire_time(previous_fire_time, now)``)."""

    def __init__(self, cfg: Config, job: str):
        self.cfg, self.job = cfg, job

    def get_next_fire_time(self, previous_fire_time, now):
        base = max(x for x in (previous_fire_time, now) if x is not None) if previous_fire_time else now
        return self.cfg.next_due(self.job, base)

    def __str__(self) -> str:
        return f"slots[{self.job}]"
