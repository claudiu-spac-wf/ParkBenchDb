"""Seeded Faker instances per unit, and small per-unit value pools for high-volume text fields."""

from __future__ import annotations

import threading

from faker import Faker

LOCALES = {"en": "en_US", "es": "es_MX"}


_LOCAL = threading.local()   # creating a Faker is slow (provider discovery); reuse per thread


def _faker_for(locale: str) -> Faker:
    cache = getattr(_LOCAL, "fakers", None)
    if cache is None:
        cache = _LOCAL.fakers = {}
    f = cache.get(locale)
    if f is None:
        f = cache[locale] = Faker(locale)
    return f


class UnitFakers:
    """One seeded Faker per locale for a unit; draws are deterministic for the unit seed.

    The process-wide instances are re-seeded when a unit first uses them, so a unit's values
    depend only on its seed, never on which units the process generated before.
    """

    _OFFSETS = {"en_US": 0, "es_MX": 7919}

    def __init__(self, seed: int):
        self._by_locale: dict[str, Faker] = {}
        self.seed = seed

    def get(self, lang: str = "en") -> Faker:
        loc = LOCALES.get(lang, "en_US")
        f = self._by_locale.get(loc)
        if f is None:
            f = _faker_for(loc)
            f.seed_instance(self.seed + self._OFFSETS[loc])
            self._by_locale[loc] = f
        return f

    @property
    def en(self) -> Faker:
        return self.get("en")


def pool(faker: Faker, method: str, n: int = 256, **kw) -> list:
    fn = getattr(faker, method)
    return [fn(**kw) for _ in range(n)]


def fit_bytes(text: str, max_bytes: int) -> str:
    """Trims text so its UTF-8 encoding fits in max_bytes (LOB-SIZE limits are in bytes)."""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[:max_bytes].decode("utf-8", errors="ignore").rstrip()


def sized_text(faker: Faker, rng, min_len: int, max_len: int) -> str:
    """Text between min_len and max_len characters, built from Faker sentences."""
    target = rng.randint(min_len, max_len)
    parts, length = [], 0
    while length < target:
        s = faker.sentence(nb_words=rng.randint(6, 14))
        parts.append(s)
        length += len(s) + 1
    text = " ".join(parts)
    return text[:target].rstrip()
