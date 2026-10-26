"""The NYSE / NASDAQ trading calendar (K6d-1): holidays, half days and the session times, in New York time (so the change between summer and winter time is always right, in New York and, through the
conversion, in Israel). No outside package: the rules are the exchange's published ones.

Holidays: New Year's Day, Martin Luther King Jr. Day, Presidents' Day, Good Friday, Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas. A holiday on a Saturday is
observed on the Friday before, on a Sunday on the Monday after (a New Year's Day on a Saturday is not observed). Half days (close 13:00): the day after Thanksgiving, 24 December, 3 July (when
4 July is a Tuesday - Friday). A one-off closure that no rule predicts goes in ``extra_closed`` of ``config/schedule.yaml``.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
OPEN, CLOSE, HALF_CLOSE = time(9, 30), time(16, 0), time(13, 0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th (1-based) given weekday (Mon=0) of a month; n=-1 is the last one."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
        return d
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def easter(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _observed(d: date) -> Optional[date]:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def holidays(year: int) -> dict:
    """{date: name} of the days the exchanges are closed in ``year`` (every observed date falls in the same year: a New Year's Day on a Saturday is not observed on 31 December)."""
    out = {}
    if date(year, 1, 1).weekday() != 5:                                       # Saturday: no observed day (the Friday before is a trading day)
        out[_observed(date(year, 1, 1))] = "New Year's Day"
    out[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    out[_nth_weekday(year, 2, 0, 3)] = "Presidents' Day"
    out[easter(year) - timedelta(days=2)] = "Good Friday"
    out[_nth_weekday(year, 5, 0, -1)] = "Memorial Day"
    if year >= 2022:
        out[_observed(date(year, 6, 19))] = "Juneteenth"
    out[_observed(date(year, 7, 4))] = "Independence Day"
    out[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    out[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving"
    out[_observed(date(year, 12, 25))] = "Christmas"
    return out


def half_days(year: int) -> set:
    out = {_nth_weekday(year, 11, 3, 4) + timedelta(days=1)}                  # the day after Thanksgiving
    dec24 = date(year, 12, 24)
    if dec24.weekday() < 5 and dec24 not in holidays(year):
        out.add(dec24)
    jul4 = date(year, 7, 4)
    if jul4.weekday() in (1, 2, 3, 4):
        out.add(date(year, 7, 3))
    return out


class Calendar:
    def __init__(self, extra_closed: Iterable = ()):
        self.extra_closed = {date.fromisoformat(str(x)) if not isinstance(x, date) else x for x in extra_closed}

    def is_trading_day(self, d: date) -> bool:
        if d.weekday() >= 5 or d in self.extra_closed:
            return False
        return d not in holidays(d.year)

    def is_half_day(self, d: date) -> bool:
        return self.is_trading_day(d) and d in half_days(d.year)

    def session(self, d: date) -> Optional[tuple]:
        """-> (open, close) as timezone-aware datetimes in New York, or None when the exchanges are closed."""
        if not self.is_trading_day(d):
            return None
        close = HALF_CLOSE if self.is_half_day(d) else CLOSE
        return datetime.combine(d, OPEN, NY), datetime.combine(d, close, NY)

    def prev_trading_day(self, d: date) -> date:
        """The last trading day strictly before ``d``."""
        d -= timedelta(days=1)
        while not self.is_trading_day(d):
            d -= timedelta(days=1)
        return d

    def next_trading_day(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.is_trading_day(d):
            d += timedelta(days=1)
        return d

    def trading_days(self, start: date, end: date) -> list:
        """Trading days from ``start`` to ``end``, both included."""
        out, d = [], start
        while d <= end:
            if self.is_trading_day(d):
                out.append(d)
            d += timedelta(days=1)
        return out

    def trading_days_between(self, a: date, b: date) -> int:
        """Trading days after ``a`` up to and including ``b`` (0 when b <= a)."""
        return len(self.trading_days(a + timedelta(days=1), b)) if b > a else 0

    def in_session(self, now: datetime) -> bool:
        s = self.session(now.astimezone(NY).date())
        return bool(s) and s[0] <= now < s[1]

    def last_close_at_or_before(self, now: datetime) -> Optional[datetime]:
        """The most recent session close at or before ``now`` (aware datetime in New York)."""
        d = now.astimezone(NY).date()
        for _ in range(12):
            s = self.session(d)
            if s and s[1] <= now:
                return s[1]
            d -= timedelta(days=1)
        return None


def utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)
