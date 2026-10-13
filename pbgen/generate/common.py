"""Shared helpers for unit generators: run context, row factory, dates, weighted choices."""

from __future__ import annotations

import bisect
import calendar
import datetime as dt
import hashlib
import random
from dataclasses import dataclass, field
from functools import lru_cache

from faker import Faker

from pbgen import unitjson
from tools import schema_model as m

TZ = dt.timezone(dt.timedelta(hours=-5))
HISTORY_MONTHS = 12


def seed_int(*parts) -> int:
    return int(hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16], 16)


@dataclass
class RunContext:
    """Everything a unit generator needs besides the unit row itself."""
    schema: m.Schema
    run_id: int
    run_seed: int
    base_seed: int                      # RunSeed of run 1 (stable names for shared rows)
    as_of: dt.date                      # end of the 12-month window
    scale: float                        # cumulative target scale factor of this run
    employee_max: int = 0               # employees available to reference (all runs incl. this one)
    merchant_max: int = 0
    branch_count: int = 250
    months: list[tuple[dt.date, dt.date]] = field(default_factory=list)

    def __post_init__(self):
        if not self.months:
            self.months = window_months(self.as_of)

    @property
    def window_start(self) -> dt.date:
        return self.months[0][0]


def window_months(as_of: dt.date) -> list[tuple[dt.date, dt.date]]:
    """The 12 calendar months ending with as_of's month: [(first_day, last_day), ...] oldest first."""
    out = []
    y, mth = as_of.year, as_of.month
    for _ in range(HISTORY_MONTHS):
        out.append((dt.date(y, mth, 1), dt.date(y, mth, calendar.monthrange(y, mth)[1])))
        mth -= 1
        if mth == 0:
            y, mth = y - 1, 12
    return list(reversed(out))


def default_as_of(today: dt.date | None = None) -> dt.date:
    """Last day of the month before today."""
    today = today or dt.date.today()
    return today.replace(day=1) - dt.timedelta(days=1)


class Weighted:
    """Fast weighted choice over fixed items."""

    def __init__(self, items_weights):
        self.items = [i for i, _ in items_weights]
        acc, self.cum = 0.0, []
        for _, w in items_weights:
            acc += w
            self.cum.append(acc)
        self.total = acc

    def pick(self, rng: random.Random):
        return self.items[bisect.bisect_right(self.cum, rng.random() * self.total)]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:  # normal approximation, fine for counts
        return max(0, int(round(rng.gauss(lam, lam ** 0.5))))
    import math
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(1 for _ in range(n) if rng.random() < p)


def zipf_index(rng: random.Random, n: int, s: float = 1.1) -> int:
    """1..n, skewed toward small values."""
    if n <= 1:
        return 1
    return min(n, int(n ** (rng.random() ** s)) or 1)


def rand_datetime(rng: random.Random, day: dt.date, diurnal: bool = True) -> dt.datetime:
    if diurnal:
        hour = min(23, max(0, int(rng.gauss(14, 4))))
    else:
        hour = rng.randrange(24)
    return dt.datetime(day.year, day.month, day.day, hour, rng.randrange(60), rng.randrange(60),
                       rng.randrange(1000) * 1000, tzinfo=TZ)


def rand_day(rng: random.Random, first: dt.date, last: dt.date) -> dt.date:
    return first + dt.timedelta(days=rng.randrange((last - first).days + 1))


def cents(value: float) -> int:
    return int(round(value * 100))


def money(c: int) -> float:
    return round(c / 100, 2)


class RowFactory:
    """Builds complete, encoded rows: standard fields + the given values, checked against the schema."""

    def __init__(self, schema: m.Schema, rng: random.Random):
        self.rng = rng
        self.tables: dict[str, list[dict]] = {}
        self._fields = {t.name: [(f.name, f.type, f.decimals) for f in t.fields] for t in schema.tables}
        self._master = {t.name for t in schema.tables if t.cls == "M"}

    def add(self, table: str, row_id: int, created: dt.datetime, **values) -> dict:
        r = self.rng
        values[f"{table}Id"] = row_id
        values["RandomInt10"] = r.randint(1, 10)
        values["RandomInt100"] = r.randint(1, 100)
        values["RandomInt1000"] = r.randint(1, 1000)
        values["CreatedAt"] = created
        if table in self._master:
            values.setdefault("UpdatedAt", created)
        row = {}
        for name, ftype, dec in self._fields[table]:
            if name not in values:
                raise KeyError(f"{table}.{name} not generated")
            row[name] = unitjson.encode_value(ftype, values.pop(name), dec)
        if values:
            raise KeyError(f"{table}: unknown fields {sorted(values)}")
        self.tables.setdefault(table, []).append(row)
        return row

    def counts(self) -> dict[str, int]:
        return {t: len(rows) for t, rows in self.tables.items()}


_NAMES_LOCK = __import__("threading").Lock()


@lru_cache(maxsize=200_000)
def merchant_name(base_seed: int, merchant_id: int) -> str:
    """Deterministic merchant name for a merchant ID (used by merchant units and by debits)."""
    with _NAMES_LOCK:  # one shared, re-seeded Faker: serialise across threads
        return _merchant_name(base_seed, merchant_id)


def _merchant_name(base_seed: int, merchant_id: int) -> str:
    f = _name_faker()
    f.seed_instance(seed_int(base_seed, "merchant", merchant_id))
    words = f.random_int(1, 3)
    name = f.company() if words == 1 else f"{f.last_name()} {f.word().title()}" if words == 2 else \
        f"{f.word().title()} {f.word().title()} {f.company_suffix()}"
    return name[:80]


@lru_cache(maxsize=1)
def _name_faker() -> Faker:
    return Faker("en_US")


def _parse_map(text: str) -> dict[str, int]:
    """'Table=1;Other=5' -> {'Table': 1, 'Other': 5}"""
    return {k: int(v) for k, v in (e.split("=") for e in (text or "").split(";") if e)}


def format_map(values: dict[str, int]) -> str:
    return ";".join(f"{k}={v}" for k, v in values.items())


def bijective_number(value: int, digits: int, salt: int) -> int:
    """Unique pseudo-random number with the given digits for each value (affine bijection mod 10^digits)."""
    mod = 10 ** digits
    return (value * 7_654_321 + salt) % mod
