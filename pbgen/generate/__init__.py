"""Unit generators. generate_unit() dispatches on LoaderUnit.UnitKind."""

from __future__ import annotations

from pbgen.generate.common import RunContext


def generate_unit(unit: dict, ctx: RunContext) -> dict[str, list[dict]]:
    kind = unit["UnitKind"]
    if kind == "REFERENCE":
        from pbgen.generate.reference import generate_reference_unit
        return generate_reference_unit(unit, ctx)
    if kind == "EMPLOYEE":
        from pbgen.generate.shared import generate_employee_unit
        return generate_employee_unit(unit, ctx)
    if kind == "MERCHANT":
        from pbgen.generate.shared import generate_merchant_unit
        return generate_merchant_unit(unit, ctx)
    if kind == "CUSTOMER":
        from pbgen.generate.customer import generate_customer_unit
        return generate_customer_unit(unit, ctx)
    raise ValueError(f"unknown unit kind {kind!r}")
