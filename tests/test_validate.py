"""Tests for tools/validate_schema.py: one failing-fixture case per rule (T019, T026, T031, T035)."""

import contextlib
import copy
import io
import os
import unittest

from helpers import REAL, field, fixture_dict, mutated, table, write_temp

from tools import schema_model as m
from tools import validate_schema as v


def rules_for(data: dict, profile: str = "structure", post=None) -> set[str]:
    """Load a schema dict, optionally mutate the expanded model, and return the rule ids reported."""
    path = write_temp(data)
    try:
        schema = m.load_expanded(path)
    finally:
        os.unlink(path)
    if post:
        post(schema)
    return {f.rule for f in v.validate(schema, profile=profile)}


def rules_after(mutator, profile: str = "structure") -> set[str]:
    return rules_for(mutated(mutator), profile)


def add_field(tname: str, **fd):
    base = {"mandatory": True, "initial": "0", "description": "x", "gen": "x"}
    base.update(fd)
    return lambda d: table(d, tname)["fields"].append(base)


class BaselineTests(unittest.TestCase):
    def test_fixture_is_clean_in_structure_profile(self):
        self.assertEqual(rules_for(fixture_dict()), set())

    def test_real_schema_is_clean_in_full_profile(self):
        findings = v.validate(m.load_expanded(REAL), profile="full")
        self.assertEqual(findings, [], "\n".join(map(str, findings)))

    def test_cli_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self._cli_exit_codes()

    def _cli_exit_codes(self):
        self.assertEqual(v.main([str(REAL)]), 0)
        path = write_temp(mutated(lambda d: table(d, "Parent").update(name="Bad-Name")))
        try:
            self.assertEqual(v.main([path]), 1)
        finally:
            os.unlink(path)
        path = write_temp(mutated(lambda d: table(d, "Parent").update(bogus=1)))
        try:
            self.assertEqual(v.main([path]), 2)
        finally:
            os.unlink(path)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            v.validate(m.load_expanded(REAL), profile="nope")


class US1StructureRules(unittest.TestCase):
    def test_v01_invalid_identifier(self):
        self.assertIn("V01", rules_after(lambda d: field(d, "Parent", "ParentName").update(name="Parent_Name")))
        self.assertIn("V01", rules_after(lambda d: field(d, "Parent", "ParentName").update(name="P" * 33)))

    def test_v02_duplicates(self):
        def dup_field(d):
            t = table(d, "Parent")
            t["fields"].append(copy.deepcopy(t["fields"][0]))
        self.assertIn("V02", rules_after(dup_field))

        def dup_index(d):
            t = table(d, "Parent")
            t["indexes"].append(copy.deepcopy(t["indexes"][0]))
        self.assertIn("V02", rules_after(dup_index))

    def test_v03_missing_format_or_decimals(self):
        self.assertIn("V03", rules_after(lambda d: field(d, "Parent", "ParentName").pop("format")))
        self.assertIn("V03", rules_after(add_field("Parent", name="Price", type="DECIMAL", format=">>9.99")))

    def test_v04_bad_type(self):
        self.assertIn("V04", rules_after(lambda d: field(d, "Parent", "ParentName").update(type="VARCHAR")))

    def test_v05_unknown_component(self):
        self.assertIn("V05", rules_after(lambda d: table(d, "Parent")["indexes"][0]["components"][0].update(field="Nope")))

    def test_v06_bad_word_index(self):
        def word_on_int(d):
            table(d, "Child")["indexes"].append({"name": "WxParent", "word": True, "purpose": "x",
                                                  "components": [{"field": "ParentId", "order": "asc"}]})
        self.assertIn("V06", rules_after(word_on_int))

    def test_v07_primary_on_table_index(self):
        self.assertIn("V07", rules_after(lambda d: table(d, "Parent")["indexes"][0].update(primary=True)))

    def test_v08_lob_spec(self):
        self.assertIn("V08", rules_after(lambda d: field(d, "Child", "NoteText").pop("lob")))
        self.assertIn("V08", rules_after(lambda d: field(d, "Child", "NoteText")["lob"].update(area="FxData")))
        self.assertIn("V08", rules_after(lambda d: field(d, "Child", "NoteText")["lob"].pop("codepage")))

    def test_v09_areas(self):
        self.assertIn("V09", rules_after(lambda d: table(d, "Parent").update(area="FxIdx")))
        self.assertIn("V09", rules_after(lambda d: table(d, "Parent").update(indexArea="FxData")))

    def test_v10_empty_descriptions(self):
        self.assertIn("V10", rules_after(lambda d: table(d, "Parent").update(description="")))
        self.assertIn("V10", rules_after(lambda d: field(d, "Parent", "ParentName").update(description=" ")))
        self.assertIn("V10", rules_after(lambda d: table(d, "Parent")["indexes"][0].update(purpose="")))

    def test_v29_reserved_words(self):
        self.assertIn("V29", rules_after(lambda d: field(d, "Parent", "ParentName").update(name="Action")))
        self.assertNotIn("V29", rules_after(lambda d: field(d, "Parent", "ParentName").update(name="AuditAction")))
        self.assertIn("V29", rules_after(lambda d: table(d, "Parent")["indexes"][0].update(name="Statement")))


class US2RandomAccessRules(unittest.TestCase):
    def test_v11_standard_field_missing_or_wrong(self):
        def drop_random(s):
            t = s.get_table("Parent")
            t.fields = [f for f in t.fields if f.name != "RandomInt100"]
        self.assertIn("V11", rules_for(fixture_dict(), post=drop_random))

        def wrong_type(s):
            s.get_table("Parent").get_field("RandomInt10").type = "INT64"
        self.assertIn("V11", rules_for(fixture_dict(), post=wrong_type))

        def moved(s):
            t = s.get_table("Parent")
            t.fields.append(t.fields.pop(0))
        self.assertIn("V11", rules_for(fixture_dict(), post=moved))

    def test_v12_standard_index_missing_or_wrong(self):
        def drop_index(s):
            t = s.get_table("Child")
            t.indexes = [i for i in t.indexes if i.name != "IxRandomInt1000"]
        self.assertIn("V12", rules_for(fixture_dict(), post=drop_index))

        def wrong_leading(s):
            s.get_table("Child").get_index("IxRandomInt10").components.reverse()
        self.assertIn("V12", rules_for(fixture_dict(), post=wrong_leading))

    def test_v13_fk_without_leading_index(self):
        self.assertIn("V13", rules_after(lambda d: table(d, "Child")["indexes"][0]["components"].reverse()))

    def test_v14_unindexed_fk_needs_reason(self):
        def unindexed(d):
            table(d, "Child")["indexes"].clear()
            field(d, "Child", "ParentId")["fk"]["indexed"] = False
        self.assertIn("V14", rules_after(unindexed))

        def with_reason(d):
            unindexed(d)
            field(d, "Child", "ParentId")["fk"]["reason"] = "lookup only"
        self.assertEqual(rules_after(with_reason), set())

    def test_v15_fk_target_missing(self):
        self.assertIn("V15", rules_after(lambda d: field(d, "Child", "ParentId")["fk"].update(table="Nope")))
        self.assertIn("V15", rules_after(lambda d: field(d, "Child", "ParentId")["fk"].update(field="Nope")))

    def test_v16_metadata_table(self):
        self.assertIn("V16", rules_after(lambda d: d["tables"].pop()))
        self.assertIn("V16", rules_after(lambda d: table(d, "BenchmarkTableInfo")["fields"].pop(1)))
        self.assertIn("V16", rules_after(lambda d: table(d, "BenchmarkTableInfo")["indexes"].clear()))


class US3CoverageRules(unittest.TestCase):
    """Full-profile rules; the fixture is far too small to satisfy them, which is the point."""

    def setUp(self):
        self.fixture_full = rules_for(fixture_dict(), profile="full")

    def test_coverage_rules_fire_on_fixture_only_in_full_profile(self):
        for rule in ("V17", "V18", "V19", "V22"):
            self.assertIn(rule, self.fixture_full)
        self.assertEqual(rules_for(fixture_dict()), set())

    def test_v20_all_types_used(self):
        self.assertIn("V20", self.fixture_full)

    def test_v21_index_shapes(self):
        def no_desc(d):
            for c in table(d, "Child")["indexes"][0]["components"]:
                c["order"] = "asc"
        self.assertIn("V21", rules_after(no_desc, profile="full"))

    def test_v23_money_rules(self):
        self.assertIn("V23", rules_after(add_field("Parent", name="Price", type="DECIMAL",
                                                   format="->>>,>>>,>>>,>>9.99", decimals=4), profile="full"))
        self.assertIn("V23", rules_after(add_field("Parent", name="TotalAmount", type="DECIMAL",
                                                   format=">>9.99", decimals=2), profile="full"))
        clean = rules_after(add_field("Parent", name="InterestRate", type="DECIMAL",
                                      format=">>9.9999", decimals=4), profile="full")
        self.assertNotIn("V23", clean)

    def test_v23_fx_rate_decimals(self):
        schema = m.load_expanded(REAL)
        schema.get_table("ExchangeRate").get_field("Rate").decimals = 4
        self.assertIn("V23", {f.rule for f in v.validate(schema, profile="full")})


class US4GenerationRules(unittest.TestCase):
    def test_v24_missing_gen(self):
        self.assertIn("V24", rules_after(lambda d: field(d, "Parent", "ParentName").update(gen="")))

    def test_v25_incomplete_lob(self):
        self.assertIn("V25", rules_after(lambda d: field(d, "Child", "NoteText")["lob"].pop("content")))
        self.assertIn("V25", rules_after(lambda d: field(d, "Child", "NoteText")["lob"].update(minBytes=5000)))

    def test_v26_cardinality_format(self):
        self.assertIn("V26", rules_after(lambda d: field(d, "Child", "ParentId")["fk"].update(cardinality="–")))
        self.assertIn("V26", rules_after(lambda d: field(d, "Child", "ParentId")["fk"].pop("cardinality")))
        ok = rules_after(lambda d: field(d, "Child", "ParentId")["fk"].update(cardinality="33 / 0–400 (skewed)"))
        self.assertNotIn("V26", ok)

    def test_v26_polymorphic_recordid_not_flagged(self):
        schema = m.load_expanded(REAL)
        rid = schema.get_table("AuditLog").get_field("RecordId")
        self.assertIsNone(rid.fk)
        self.assertNotIn("V26", {f.rule for f in v.validate(schema, profile="full")})

    def test_v27_size_window(self):
        schema = m.load_expanded(REAL)
        schema.get_table("DebitTransaction").rows = 400_000_000
        self.assertIn("V27", {f.rule for f in v.validate(schema, profile="full")})

    def test_v28_minimum_scale_factor(self):
        schema = m.load_expanded(REAL)
        schema.get_table("Employee").rows = 4000  # 40 rows at SF 0.01 < 50
        self.assertIn("V28", {f.rule for f in v.validate(schema, profile="full")})


if __name__ == "__main__":
    unittest.main()
