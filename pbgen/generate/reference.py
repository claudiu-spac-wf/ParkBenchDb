"""REFERENCE unit: every fixed table plus the initial BenchmarkTableInfo rows (run 1 only)."""

from __future__ import annotations

import datetime as dt
import random

from pbgen.generate import refdata
from pbgen.generate.common import TZ, RowFactory, RunContext, rand_datetime, seed_int, zipf_index
from pbgen.generate.fakerpool import UnitFakers, sized_text
from tools import schema_model as m

# InterestRateHistory.ChangedByEmployeeId must reference an employee created in run 1 (research R7).
IRH_EMPLOYEE_MAX = 60


def generate_reference_unit(unit: dict, ctx: RunContext) -> dict[str, list[dict]]:
    seed = int(unit["UnitSeed"], 16)
    rng = random.Random(seed)
    rows = RowFactory(ctx.schema, random.Random(seed + 1))
    fk = UnitFakers(seed).en
    base = dt.datetime(ctx.window_start.year - 1, 1, 1, 8, 0, tzinfo=TZ)

    for i, (code, name, num, minor, sym) in enumerate(refdata.CURRENCIES, 1):
        rows.add("Currency", i, base, CurrencyCode=code, CurrencyName=name[:40], NumericCode=num, MinorUnits=minor,
                 CurrencySymbol=sym[:5], IsActive=rng.random() < 0.95 or code == "USD")

    for i, (code, name, cur, prefix) in enumerate(refdata.COUNTRIES, 1):
        rows.add("Country", i, base, CountryCode=code, CountryName=name[:60], DefaultCurrencyCode=cur,
                 PhonePrefix=prefix or f"+{rng.randint(20, 999)}")

    # 39 non-USD currencies x 365 days ending at the as-of date; a random walk from a seed rate
    rid = 0
    first_day = ctx.as_of - dt.timedelta(days=364)
    for code, *_ in refdata.CURRENCIES[1:]:
        rate = rng.uniform(0.0005, 4.0)
        for d in range(365):
            rate *= 1 + rng.uniform(-0.005, 0.005)
            rid += 1
            day = first_day + dt.timedelta(days=d)
            rows.add("ExchangeRate", rid, dt.datetime(day.year, day.month, day.day, 17, 0, tzinfo=TZ),
                     RateDate=day, FromCurrencyCode=code, ToCurrencyCode="USD", Rate=round(rate, 8),
                     RateSource=rng.choice(["ECB", "FED", "INTERNAL"]))

    for i in range(1, 251):
        country = "US" if rng.random() < 0.9 else rng.choice(["CA", "MX", "GB", "DE", "FR", "ES"])
        city = fk.city()
        opened = dt.date(rng.randint(1950, 2024), rng.randint(1, 12), rng.randint(1, 28))
        rows.add("Branch", i, base, BranchCode=f"B{i:05d}", BranchName=f"{city} {rng.choice(['Main St', 'Downtown', 'Central', 'North', 'Plaza'])}"[:60],
                 AddressLine1=fk.street_address()[:60], City=city[:40], StateProvince=fk.state()[:30],
                 PostalCode=fk.postcode()[:10], CountryCode=country, Phone=fk.phone_number()[:20],
                 OpenDate=opened, IsActive=rng.random() < 0.96)

    for i, (code, name, cat, term, rate, minbal, fee, od) in enumerate(refdata.ACCOUNT_TYPES, 1):
        rows.add("AccountType", i, base, AccountTypeCode=code, AccountTypeName=name, Category=cat,
                 Description=fk.sentence(nb_words=14)[:200], TermsText=sized_text(fk, rng, 900, 1200),
                 MinimumBalance=minbal, MonthlyFee=fee, OverdraftAllowed=od, TermMonths=term,
                 CurrentInterestRate=rate, IsActive=True)

    rid = 0
    for t, (_code, _n, _c, _term, rate, *_rest) in enumerate(refdata.ACCOUNT_TYPES, 1):
        for mth in range(120):  # monthly for 10 years ending at the as-of month
            y, mo = divmod((ctx.as_of.year * 12 + ctx.as_of.month - 1) - (119 - mth), 12)
            rid += 1
            eff = dt.date(y, mo + 1, 1)
            r = rate if mth == 119 else max(0.0, round(rate + rng.uniform(-1.5, 1.5), 4))
            rows.add("InterestRateHistory", rid, dt.datetime(y, mo + 1, 1, 9, 0, tzinfo=TZ), AccountTypeId=t,
                     EffectiveDate=eff, InterestRate=round(r, 4),
                     ChangedByEmployeeId=zipf_index(rng, IRH_EMPLOYEE_MAX))

    for i, (code, desc, direction, channel, fee) in enumerate(refdata.TRANSACTION_TYPES, 1):
        rows.add("TransactionType", i, base, TransactionTypeCode=code, Description=desc[:60], Direction=direction,
                 Channel=channel, IsFee=fee)

    mid = 0
    for group, lo, hi, n in refdata.MCC_GROUPS:
        codes = sorted(random.Random(seed_int(seed, group)).sample(range(lo, hi + 1), n))
        for code in codes:
            mid += 1
            rows.add("MerchantCategory", mid, base, MccCode=f"{code:04d}",
                     Description=f"{group} - {fk.catch_phrase()}"[:80], CategoryGroup=group)

    # BenchmarkTableInfo: one row per benchmark table, counts filled in by the watermark
    loaded = dt.datetime.combine(ctx.as_of + dt.timedelta(days=1), dt.time(0, 0), TZ)  # deterministic; the agent sets LoadedAt when it advances the watermark
    for i, t in enumerate(sorted(ctx.schema.tables, key=lambda x: x.name.lower()), 1):
        rows.add("BenchmarkTableInfo", i, loaded, TableName=t.name, TableRowCount=0, MaxId=0,
                 ScaleFactor=round(ctx.scale, 2), VolumeTier=m.volume_tier(t.rows), RecordSizeTier=m.size_tier(t),
                 AsOfDate=ctx.as_of, LoadedAt=loaded)
    return rows.tables
