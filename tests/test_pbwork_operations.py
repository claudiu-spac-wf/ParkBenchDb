"""Deterministic operation selection and bounded point-key tests."""

import unittest
from pathlib import Path

from pbwork.catalog import find_profile, load_catalog
from pbwork.model import OperationSpec
from pbwork.operations import point_descriptor, read_descriptor, write_descriptor
from pbwork.seeds import operation_seed, select_operation
from tools.schema_model import load_expanded


class ReadSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = find_profile(load_catalog(), "read-reference-point")

    def test_selection_is_worker_independent(self):
        profile = self.profile
        counts = {table: 100 for table in profile.tables}
        first = []
        for ordinal in range(1, 1001):
            operation = select_operation(20260929, profile.version, ordinal, profile.operations)
            first.append(point_descriptor(20260929, profile.version, ordinal, operation, counts))
        second = []
        for ordinal in range(1, 1001):
            operation = select_operation(20260929, profile.version, ordinal, profile.operations)
            second.append(point_descriptor(20260929, profile.version, ordinal, operation, counts))
        self.assertEqual(first, second)
        self.assertEqual({row["ordinal"] for row in first}, set(range(1, 1001)))
        self.assertTrue(all(1 <= row["key_id"] <= 100 for row in first))
        self.assertTrue(all(len(row["retry_keys"]) == 3 and all(1 <= key <= 100 for key in row["retry_keys"])
                            for row in first))

    def test_empty_table_is_rejected(self):
        operation = self.profile.operations[0]
        with self.assertRaisesRegex(ValueError, "no rows"):
            point_descriptor(1, 1, 1, operation, {operation.table: 0})

    def test_seed_includes_profile_version_and_operation_id(self):
        a = operation_seed(1, 1, 1, "currency-by-id")
        self.assertNotEqual(a, operation_seed(1, 2, 1, "currency-by-id"))
        self.assertNotEqual(a, operation_seed(1, 1, 1, "branch-by-id"))

    def test_each_read_family_has_bounded_deterministic_descriptor(self):
        for profile in load_catalog():
            if profile.kind != "read":
                continue
            counts = {table: 10000 for table in profile.tables}
            for operation in profile.operations:
                if operation.selection.get("parent"):
                    counts[operation.selection["parent"]] = 10000
                with self.subTest(profile=profile.id, operation=operation.id):
                    first = read_descriptor(12, profile.version, 42, operation, counts)
                    second = read_descriptor(12, profile.version, 42, operation, counts)
                    self.assertEqual(first, second)
                    self.assertEqual(first["handler"], operation.handler)
                    if "limit" in first:
                        self.assertGreater(first["limit"], 0)
                        self.assertLessEqual(first["limit"], 10000)
                    if "key_id" in first:
                        self.assertGreaterEqual(first["key_id"], 1)
                        self.assertLessEqual(first["key_id"], 10000)

    def test_selective_field_ranges(self):
        for profile in load_catalog():
            for operation in profile.operations:
                if operation.handler != "indexed_selective":
                    continue
                descriptor = read_descriptor(1, profile.version, 1, operation, {operation.table: 10000})
                maximum = {"RandomInt10": 10, "RandomInt100": 100, "RandomInt1000": 1000}[descriptor["field"]]
                self.assertTrue(1 <= descriptor["predicate_value"] <= maximum)

    def test_all_random_int_domains_and_empty_selection_semantics(self):
        for field, maximum in (("RandomInt10", 10), ("RandomInt100", 100), ("RandomInt1000", 1000)):
            operation = OperationSpec(f"select-{field.lower()}", "indexed_selective", 1,
                                      table="Currency", selection={"field": field, "limit": 50})
            values = [read_descriptor(44, 1, ordinal, operation, {"Currency": 1})["predicate_value"]
                      for ordinal in range(1, 101)]
            self.assertTrue(all(1 <= value <= maximum for value in values))
            self.assertEqual(values, [read_descriptor(44, 1, ordinal, operation, {"Currency": 1})["predicate_value"]
                                      for ordinal in range(1, 101)])

    def test_ordered_bounded_range_and_parent_navigation(self):
        range_profile = find_profile(load_catalog(), "read-large-range")
        operation = range_profile.operations[0]
        first = read_descriptor(23, 1, 17, operation, {operation.table: 50000}, {"rangeWidth": 111})
        self.assertEqual(first["limit"], 111)
        self.assertTrue(1 <= first["range_start"] <= 50000)
        self.assertEqual(first, read_descriptor(23, 1, 17, operation, {operation.table: 50000}, {"rangeWidth": 111}))
        scan_profile = find_profile(load_catalog(), "read-small-table-scan")
        scan = read_descriptor(23, 1, 17, scan_profile.operations[0], {scan_profile.operations[0].table: 2}, {"scanLimit": 7})
        self.assertEqual(scan["limit"], 7)
        self.assertEqual(scan["aggregate"], "count")
        navigation = find_profile(load_catalog(), "read-relationship-navigation").operations[0]
        selected = read_descriptor(23, 1, 17, navigation, {"Customer": 1000}, {"depth": 3})
        self.assertEqual(selected["table"], "Customer")
        self.assertEqual(selected["depth"], 3)
        self.assertTrue(1 <= selected["key_id"] <= 1000)

    def test_write_payloads_are_reproducible_and_range_valid(self):
        counts = {"Customer": 100, "Account": 100, "Loan": 100,
                  "CustomerNote": 100, "StatementDocument": 100,
                  "LoginEvent": 100, "AuditLog": 100}
        for profile in load_catalog():
            if profile.kind == "read":
                continue
            for operation in profile.operations:
                if operation.handler not in {"append_narrow", "update_wide", "write_lob", "transaction_batch"}:
                    continue
                with self.subTest(profile=profile.id, operation=operation.id):
                    first = write_descriptor(20260929, profile.version, 3, operation, counts)
                    self.assertEqual(first, write_descriptor(20260929, profile.version, 3, operation, counts))
                    self.assertTrue(1 <= first["random_int10"] <= 10)
                    self.assertTrue(1 <= first["random_int100"] <= 100)
                    self.assertTrue(1 <= first["random_int1000"] <= 1000)
                    self.assertIn("pbwork", first["identity"])

    def test_write_ordinal_changes_payload_identity(self):
        profile = find_profile(load_catalog(), "write-narrow-append")
        operation = profile.operations[0]
        counts = {"Customer": 100}
        first = write_descriptor(1, 1, 1, operation, counts)
        second = write_descriptor(1, 1, 2, operation, counts)
        self.assertNotEqual(first["identity"], second["identity"])

    def test_hot_and_cold_write_keys_follow_declared_distributions(self):
        catalog = load_catalog()
        hot = find_profile(catalog, "write-hot-key-contention").operations[0]
        cold = find_profile(catalog, "write-cold-distributed").operations[0]
        counts = {"Customer": 5000}
        hot_keys = {write_descriptor(77, 1, ordinal, hot, counts)["key_id"] for ordinal in range(1, 1001)}
        cold_keys = {write_descriptor(77, 1, ordinal, cold, counts)["key_id"] for ordinal in range(1, 1001)}
        self.assertLessEqual(max(hot_keys), 16)
        self.assertGreater(len(cold_keys), 500)
        self.assertLessEqual(max(cold_keys), 5000)
        override = write_descriptor(77, 1, 1, hot, counts, {"hotSetSize": 3})
        self.assertLessEqual(override["key_id"], 3)

    def test_write_payloads_have_schema_sized_text_and_supported_identity(self):
        catalog = load_catalog()
        counts = {"Customer": 1000, "Account": 1000, "Loan": 1000,
                  "CustomerNote": 1000, "StatementDocument": 1000,
                  "LoginEvent": 1000, "AuditLog": 1000}
        identities = set()
        for profile in catalog:
            if profile.kind == "read":
                continue
            for operation in profile.operations:
                if operation.handler == "point_lookup":
                    continue
                descriptor = write_descriptor(19, profile.version, 17, operation, counts)
                identities.add(descriptor["identity"])
                self.assertTrue(1 <= descriptor["random_int10"] <= 10)
                self.assertTrue(1 <= descriptor["random_int100"] <= 100)
                self.assertTrue(1 <= descriptor["random_int1000"] <= 1000)
                if operation.handler == "append_narrow" and operation.table == "LoginEvent":
                    self.assertNotIn("LoginEventId", descriptor)
                    self.assertNotIn("key_id", descriptor)
                    self.assertTrue(1 <= descriptor["payload"]["customer_id"] <= counts["Customer"])
                    self.assertLessEqual(len(descriptor["payload"]["ip_address"]), 39)
                    self.assertLessEqual(len(descriptor["payload"]["device_id"]), 32)
                if operation.handler == "append_narrow" and operation.table == "AuditLog":
                    self.assertNotIn("AuditLogId", descriptor)
                    self.assertLessEqual(len(descriptor["payload"]["change_summary"]), 60)
                if operation.handler == "write_lob":
                    self.assertEqual(len(descriptor["payload"]["text"]), 1024)
                    self.assertIn(descriptor["lob_mode"], {"clob", "blob"})
                if operation.handler == "transaction_batch":
                    self.assertTrue(1 <= descriptor["key_id"] <= counts["Account"])
                    self.assertTrue(1 <= descriptor["payload"]["amount_cents"] <= 100000)
                    self.assertLessEqual(len(descriptor["payload"]["reference"]), 20)
                    self.assertNotIn("current_balance", descriptor["payload"])
                    self.assertNotIn("statement_total", descriptor["payload"])
        self.assertGreaterEqual(len(identities), 7)

    def test_append_uses_existing_foreign_keys_and_abl_owned_sequences(self):
        root = Path(__file__).resolve().parents[1]
        schema = load_expanded(root / "schema" / "parkbench-schema.yaml")
        definitions = (root / "db" / "parkbench.df").read_text(encoding="utf-8")
        profile = find_profile(load_catalog(), "write-narrow-append")
        counts = {"Customer": 31, "Account": 87, "LoginEvent": 0, "AuditLog": 0}
        for operation in profile.operations:
            descriptor = write_descriptor(101, profile.version, 1, operation, counts)
            table = schema.get_table(operation.table)
            self.assertIsNotNone(table.get_field(operation.table + "Id"))
            self.assertIn(f'ADD SEQUENCE "Seq{operation.table}Id"', definitions)
            self.assertNotIn("key_id", descriptor)
            if operation.table == "LoginEvent":
                self.assertTrue(1 <= descriptor["payload"]["customer_id"] <= 31)
                self.assertEqual(table.get_field("CustomerId").fk.table, "Customer")
            else:
                self.assertEqual(descriptor["payload"]["table_name"], "Account")
                self.assertTrue(1 <= descriptor["payload"]["record_id"] <= 87)

    def test_write_builder_rejects_unsupported_targets_and_lob_modes(self):
        counts = {"Currency": 10, "CustomerNote": 10}
        for operation in (
            OperationSpec("bad-update", "update_wide", 1, table="Currency",
                          transaction={"group": "operation", "commit": "commit"}),
            OperationSpec("bad-lob", "write_lob", 1, table="CustomerNote",
                          selection={"lobMode": "blob"}, transaction={"group": "operation", "commit": "commit"}),
            OperationSpec("bad-group", "write_lob", 1, table="CustomerNote",
                          selection={"lobMode": "clob"}, transaction={"group": "batch", "commit": "commit"}),
        ):
            with self.subTest(operation=operation.id), self.assertRaises(ValueError):
                write_descriptor(1, 1, 1, operation, counts)
