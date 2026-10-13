"""EMPLOYEE and MERCHANT units: the shared rows every customer unit may reference."""

from __future__ import annotations

import datetime as dt
import random

from pbgen.generate import lob
from pbgen.generate.common import TZ, RowFactory, RunContext, _parse_map, merchant_name, zipf_index
from pbgen.generate.fakerpool import UnitFakers

JOBS = ["Teller", "Personal Banker", "Loan Officer", "Branch Manager", "Analyst", "Relationship Manager",
        "Customer Service Representative", "Mortgage Advisor", "Operations Specialist", "Compliance Officer"]


def generate_employee_unit(unit: dict, ctx: RunContext) -> dict[str, list[dict]]:
    seed = int(unit["UnitSeed"], 16)
    rng = random.Random(seed)
    rows = RowFactory(ctx.schema, random.Random(seed + 1))
    fk = UnitFakers(seed).en
    first = _parse_map(unit["FirstIds"])["Employee"]
    count = _parse_map(unit["RowCounts"])["Employee"]
    for eid in range(first, first + count):
        hire = ctx.as_of - dt.timedelta(days=rng.randint(30, 30 * 365))
        created = dt.datetime(hire.year, hire.month, hire.day, 9, 0, tzinfo=TZ)
        # the first 250 employees of the database manage branch 1..250 (exactly one manager per branch)
        is_mgr = eid <= ctx.branch_count
        branch = eid if is_mgr else (1 if rng.random() < 0.15 else rng.randint(1, ctx.branch_count))
        first_name, last_name = fk.first_name(), fk.last_name()
        photo = lob.jpeg_like(rng, 8192, 24576, 49152) if rng.random() < 0.8 else None
        rows.add("Employee", eid, created, EmployeeNumber=f"E{eid:07d}", BranchId=branch,
                 FirstName=first_name[:30], LastName=last_name[:40],
                 JobTitle="Branch Manager" if is_mgr else rng.choice(JOBS),
                 Email=f"{first_name}.{last_name}{eid}@parkbench.example".lower()[:80], HireDate=hire,
                 TerminationDate=(hire + dt.timedelta(days=rng.randint(100, 3000))) if rng.random() < 0.08 else None,
                 IsBranchManager=is_mgr, Salary=round(rng.uniform(35000, 250000), 2), Photo=photo)
    return rows.tables


def generate_merchant_unit(unit: dict, ctx: RunContext) -> dict[str, list[dict]]:
    seed = int(unit["UnitSeed"], 16)
    rng = random.Random(seed)
    rows = RowFactory(ctx.schema, random.Random(seed + 1))
    fk = UnitFakers(seed).en
    first = _parse_map(unit["FirstIds"])["Merchant"]
    count = _parse_map(unit["RowCounts"])["Merchant"]
    for mid in range(first, first + count):
        country = "US" if rng.random() < 0.85 else rng.choice(["CA", "MX", "GB", "DE", "FR", "ES", "JP", "AU"])
        lat, lng, city, _cc, _tz = fk.local_latlng(country_code="US") if country == "US" else \
            (str(fk.latitude()), str(fk.longitude()), fk.city(), country, "")
        rows.add("Merchant", mid, dt.datetime.combine(ctx.window_start, dt.time(8), TZ),
                 MerchantNumber=f"M{mid:014d}", MerchantName=merchant_name(ctx.base_seed, mid),
                 MerchantCategoryId=zipf_index(rng, 600), City=city[:40], StateProvince=fk.state()[:30],
                 PostalCode=fk.postcode()[:10], CountryCode=country, Latitude=round(float(lat), 6),
                 Longitude=round(float(lng), 6), IsOnline=rng.random() < 0.25,
                 RiskScore=max(0, min(100, int(rng.gauss(20, 12)))))
    return rows.tables
