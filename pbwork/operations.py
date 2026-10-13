"""Deterministic, allowlisted workload request construction."""

from __future__ import annotations

from .seeds import operation_rng
from .seeds import operation_seed


def point_descriptor(run_seed: int, version: int, ordinal: int, operation, counts: dict[str, int]) -> dict:
    """Choose a primary key without depending on worker assignment or process state."""
    if operation.handler != "point_lookup" or not operation.table:
        raise ValueError("point_descriptor requires a point lookup")
    count = int(counts.get(operation.table, 0))
    if count < 1:
        raise ValueError(f"{operation.table} has no rows available for point reads")
    rng = operation_rng(run_seed, version, ordinal, operation.id)
    key = rng.randint(1, count)
    retry_keys = [rng.randint(1, count) for _ in range(3)]
    return {"ordinal": ordinal, "operation_id": operation.id, "handler": "point_lookup",
            "table": operation.table, "key_id": key, "retry_keys": retry_keys,
            "selection": operation.selection, "transaction": operation.transaction}


def read_descriptor(run_seed: int, version: int, ordinal: int, operation, counts: dict[str, int], parameters: dict | None = None) -> dict:
    """Build a bounded descriptor for one of the six read handler families."""
    params = parameters or {}
    handler = operation.handler
    if handler == "point_lookup":
        return point_descriptor(run_seed, version, ordinal, operation, counts)
    if handler not in {"indexed_selective", "range_scan", "table_scan", "relationship_navigation", "lob_fetch"}:
        raise ValueError(f"unsupported read handler: {handler}")
    table = operation.table or operation.selection.get("parent")
    if not table:
        raise ValueError("read operation has no driving table")
    count = int(counts.get(table, 0))
    if count < 1:
        raise ValueError(f"{table} has no rows available for reads")
    rng = operation_rng(run_seed, version, ordinal, operation.id)
    descriptor = {"ordinal": ordinal, "operation_id": operation.id, "handler": handler,
                  "table": table, "tables": list(operation.tables),
                  "selection": operation.selection, "transaction": operation.transaction}
    if handler == "indexed_selective":
        field = operation.selection.get("field")
        ranges = {"RandomInt10": 10, "RandomInt100": 100, "RandomInt1000": 1000}
        if field not in ranges:
            raise ValueError("selective read requires an indexed RandomInt field")
        descriptor.update(field=field, predicate_value=rng.randint(1, ranges[field]),
                          limit=min(int(operation.selection.get("limit", 1000)), 10000))
    elif handler == "range_scan":
        width = int(params.get("rangeWidth", operation.selection.get("width", 100)))
        if not 1 <= width <= 10000:
            raise ValueError("range width must be 1..10000")
        descriptor.update(range_start=rng.randint(1, count), limit=width)
    elif handler == "table_scan":
        limit = int(params.get("scanLimit", operation.selection.get("limit", 1000)))
        if not 1 <= limit <= 10000:
            raise ValueError("scan limit must be 1..10000")
        descriptor.update(limit=limit, aggregate=operation.selection.get("aggregate", "count"))
    elif handler == "relationship_navigation":
        descriptor.update(key_id=rng.randint(1, count), depth=int(params.get("depth", operation.selection.get("depth", 4))),
                          limit=min(int(operation.selection.get("limit", 100)), 1000))
    else:
        mode = params.get("lobMode", operation.selection.get("lobMode", "scalarOnly"))
        if mode not in {"scalarOnly", "clob", "blob", "both"}:
            raise ValueError("invalid LOB mode")
        descriptor.update(key_id=rng.randint(1, count), lob_mode=mode)
    return descriptor


def write_descriptor(run_seed: int, version: int, ordinal: int, operation, counts: dict[str, int], parameters: dict | None = None) -> dict:
    """Create deterministic write intent; ABL owns transactions and IDs."""
    from faker import Faker

    params = parameters or {}
    handler = operation.handler
    if handler not in {"append_narrow", "update_wide", "write_lob", "transaction_batch"}:
        raise ValueError(f"unsupported write handler: {handler}")
    rng = operation_rng(run_seed, version, ordinal, operation.id)
    faker = Faker("en_US")
    faker.seed_instance(operation_seed(run_seed, version, ordinal, operation.id))
    table = operation.table or (operation.tables[0] if operation.tables else None)
    if not table:
        raise ValueError("write operation has no table")
    allowed_tables = {
        "append_narrow": {"LoginEvent", "AuditLog"},
        "update_wide": {"Customer", "Loan"},
        "write_lob": {"CustomerNote", "StatementDocument"},
        "transaction_batch": {"Account"},
    }
    if table not in allowed_tables[handler]:
        raise ValueError(f"unsupported {handler} table: {table}")
    if operation.transaction.get("group") != "operation" or operation.transaction.get("commit") not in {"commit", "atomic"}:
        raise ValueError("write operation must be one committing transaction group")
    common = {"ordinal": ordinal, "operation_id": operation.id, "handler": handler,
              "table": table, "tables": list(operation.tables), "transaction": operation.transaction,
              "random_int10": rng.randint(1, 10), "random_int100": rng.randint(1, 100),
              "random_int1000": rng.randint(1, 1000),
              "identity": f"pbwork-{version}-{ordinal}-{operation.id}"}
    if handler == "append_narrow":
        if table == "LoginEvent":
            customer_count = int(counts.get("Customer", 0))
            if customer_count < 1:
                raise ValueError("LoginEvent append requires existing Customer rows")
            common["payload"] = {"customer_id": rng.randint(1, customer_count),
                                 "ip_address": faker.ipv4_public(), "device_id": faker.sha1()[:32],
                                 "event_kind": rng.choice(("LOGIN", "FAILED", "MFA", "LOGOUT"))}
        elif table == "AuditLog":
            account_count = int(counts.get("Account", 0))
            if account_count < 1:
                raise ValueError("AuditLog append requires existing Account rows")
            common["payload"] = {"table_name": "Account", "record_id": rng.randint(1, account_count),
                                 "change_summary": f"PBWORK:{version}:{ordinal}"[:60]}
        else:
            raise ValueError("unsupported narrow append table")
    elif handler == "update_wide":
        count = int(counts.get(table, 0))
        if count < 1:
            raise ValueError(f"{table} has no rows to update")
        distribution = operation.selection.get("keyDistribution", "distributed")
        if distribution == "hot":
            hot_set = int(params.get("hotSetSize", operation.selection.get("hotSetSize", 16)))
            if not 1 <= hot_set <= min(1024, count):
                raise ValueError("hotSetSize must fit the available row count and be 1..1024")
            upper_key = hot_set
        elif distribution == "distributed":
            key_range = int(params.get("keyRange", count))
            if key_range < 1:
                raise ValueError("keyRange must be positive")
            upper_key = min(key_range, count)
        else:
            raise ValueError("unsupported key distribution")
        common["key_id"] = rng.randint(1, upper_key)
        common["key_distribution"] = distribution
        common["payload"] = {"text": faker.sentence(nb_words=12)[:80]}
    elif handler == "write_lob":
        count = int(counts.get(table, 0))
        if count < 1:
            raise ValueError(f"{table} has no rows to update")
        size = int(params.get("lobBytes", 1024))
        if not 1 <= size <= 65536:
            raise ValueError("lobBytes must be 1..65536")
        common["key_id"] = rng.randint(1, count)
        lob_mode = operation.selection.get("lobMode")
        if lob_mode != ("clob" if table == "CustomerNote" else "blob"):
            raise ValueError("LOB mode must match the target table")
        common["lob_mode"] = lob_mode
        common["payload"] = {"text": (faker.paragraph(nb_sentences=5) * ((size // 100) + 2))[:size]}
    else:
        count = int(counts.get("Account", 0))
        if count < 1:
            raise ValueError("transaction batch requires existing Account rows")
        common["key_id"] = rng.randint(1, count)
        common["payload"] = {"amount_cents": rng.randint(1, 100000),
                             "reference": f"PB{version:02d}{ordinal:016d}"[-20:]}
    return common
