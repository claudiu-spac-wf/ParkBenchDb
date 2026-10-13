"""Schema-aware profile catalog coverage and safety checks."""

import tempfile
import unittest
from pathlib import Path

import yaml

from pbwork.catalog import CATALOG_FILE, CatalogError, load_catalog
from pbwork.model import READ_HANDLERS


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_catalog()

    def test_shape_and_access_matrix(self):
        read = [p for p in self.profiles if p.kind == "read"]
        self.assertEqual(len(read), 8)
        self.assertEqual(len(self.profiles), 15)
        for dimension, expected in {
            "volume": {"Tiny", "Small", "Medium", "Large", "Very Large"},
            "shape": {"Narrow", "Standard", "Wide", "LOB"},
            "lob": {"none", "CLOB", "BLOB", "both"},
            "access": {"point", "selective", "range", "scan", "aggregate", "navigate"},
        }.items():
            observed = {value for p in read for value in p.coverage[dimension]}
            self.assertTrue(expected <= observed, (dimension, expected - observed))

    def test_all_profiles_have_numeric_minimum_rows(self):
        for profile in self.profiles:
            minimums = {row["name"]: row["minimumRows"] for row in profile.prerequisites["tables"]}
            for table in profile.tables:
                self.assertIs(type(minimums[table]), int)
                self.assertGreaterEqual(minimums[table], 0)

    def test_eight_read_profiles_are_executable_and_metadata_matches_operations(self):
        read = [profile for profile in self.profiles if profile.kind == "read"]
        self.assertEqual({profile.id for profile in read}, {
            "read-reference-point", "read-small-table-scan", "read-medium-narrow-selective",
            "read-medium-wide-selective", "read-large-range", "read-very-large-selective",
            "read-relationship-navigation", "read-lob-fetch"})
        for profile in read:
            with self.subTest(profile=profile.id):
                self.assertTrue(profile.purpose)
                self.assertEqual(profile.cleanup, "none")
                self.assertFalse(profile.requires_writable_database)
                self.assertTrue(profile.coverage["transaction"])
                self.assertTrue(profile.coverage["pressure"])
                self.assertTrue(profile.coverage["key_distribution"])
                declared = {row["name"] for row in profile.prerequisites["tables"]}
                self.assertTrue(set(profile.tables) <= declared)
                self.assertTrue(all(operation.handler in READ_HANDLERS and operation.weight > 0
                                    for operation in profile.operations))
                self.assertTrue(all(operation.expected.get("minimumRows") == 0
                                    and isinstance(operation.expected.get("maximumRows"), int)
                                    and operation.expected["maximumRows"] > 0
                                    for operation in profile.operations))
                self.assertTrue(all((set(operation.tables) if operation.tables else {operation.table}) <= set(profile.tables)
                                    for operation in profile.operations))
        lob = next(profile for profile in read if profile.id == "read-lob-fetch")
        self.assertEqual({operation.selection["lobMode"] for operation in lob.operations},
                         {"scalarOnly", "clob", "blob", "both"})

    def test_free_form_code_is_rejected(self):
        data = yaml.safe_load(CATALOG_FILE.read_text(encoding="utf-8"))
        data["profiles"][0]["operations"][0]["selection"]["sql"] = "DROP TABLE Customer"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.yaml"
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "free-form"):
                load_catalog(path)

    def test_unknown_handler_is_rejected(self):
        data = yaml.safe_load(CATALOG_FILE.read_text(encoding="utf-8"))
        data["profiles"][0]["operations"][0]["handler"] = "arbitrary"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.yaml"
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "unknown handler"):
                load_catalog(path)
