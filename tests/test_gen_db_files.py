"""Tests for tools/gen_db_files.py (T003, T007, T014)."""

import contextlib
import copy
import io
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURE, REAL, real_dict, write_temp

from tools import gen_db_files as g
from tools import schema_model as m


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def parse_df(text: str):
    """Split a .df into (kind, name, attr_lines) blocks, stopping at the trailer."""
    body = text[: text.index("\n.\nPSC\n")]
    blocks = []
    for chunk in body.strip("\n").split("\n\n"):
        lines = chunk.split("\n")
        head = lines[0]
        mm = re.match(r'^ADD (SEQUENCE|TABLE|FIELD|INDEX) "([^"]+)"', head)
        assert mm, head
        blocks.append((mm.group(1), mm.group(2), head, lines[1:]))
    return blocks


def block(text: str, header: str) -> str:
    start = text.index(header + "\n")
    end = text.index("\n\n", start)
    return text[start:end]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = m.load_expanded(REAL)
        cls.plan = g.area_plan(cls.schema)
        cls.df = g.render_df(cls.schema, cls.plan)
        cls.st = g.render_st(cls.schema, cls.plan, ".")
        cls.blocks = parse_df(cls.df)


# --------------------------------------------------------------------------- foundational (T003)

class FoundationalTests(Base):
    def test_area_plan_matches_data_model(self):
        got = [(r.name, r.number, r.kind, r.rpb, r.bpc) for r in self.plan]
        self.assertEqual(got, [
            ("Schema Area", 6, "schema", 32, 1),
            ("PB_Ref_Data", 7, "data", 64, 8),
            ("PB_Master_Narrow", 8, "data", 32, 64),
            ("PB_Master_Std", 9, "data", 16, 64),
            ("PB_Master_Wide", 10, "data", 8, 64),
            ("PB_Txn_Debit", 11, "data", 32, 512),
            ("PB_Txn_CardAuth", 12, "data", 64, 512),
            ("PB_Txn_Audit", 13, "data", 32, 512),
            ("PB_Txn_Large", 14, "data", 32, 512),
            ("PB_Ref_Idx", 15, "index", 64, 8),
            ("PB_Master_Idx", 16, "index", 64, 64),
            ("PB_Txn_Idx", 17, "index", 64, 512),
            ("PB_Lob_Doc", 18, "lob", 8, 512),
            ("PB_Lob_Stmt", 19, "lob", 8, 512),
            ("PB_Lob_Text", 20, "lob", 8, 512),
        ])

    def test_lob_size_bytes(self):
        self.assertEqual(g.lob_size_bytes("64K"), 65536)
        self.assertEqual(g.lob_size_bytes("8K"), 8192)
        self.assertEqual(g.lob_size_bytes("1M"), 1048576)
        for bad in ("64", "64KB", "", "K"):
            with self.assertRaises(ValueError):
                g.lob_size_bytes(bad)

    def test_invalid_db_name_exits_2(self):
        out = tempfile.mkdtemp()
        try:
            for bad in ("9bad", "toolongname12", "bad name"):
                self.assertEqual(quiet(g.main, [str(REAL), "--out", out, "--db-name", bad]), 2, bad)
        finally:
            shutil.rmtree(out)

    def test_validation_failure_exits_1_and_writes_nothing(self):
        out = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(quiet(g.main, [str(FIXTURE), "--out", str(out)]), 1)
            self.assertEqual(list(out.iterdir()), [])
        finally:
            shutil.rmtree(out)

    def test_area_mismatch_exits_2(self):
        data = real_dict()
        data["tables"][0]["area"] = "PB_Ref_Idx"  # an index area used as a table area
        path = write_temp(data)
        out = tempfile.mkdtemp()
        try:
            # the schema checker flags V09 first (exit 1); check_areas is the second line of defence
            self.assertIn(quiet(g.main, [path, "--out", out]), (1, 2))
            schema = m.load_expanded(path)
            with self.assertRaises(ValueError):
                g.check_areas(schema, g.area_plan(schema))
        finally:
            shutil.rmtree(out)
            Path(path).unlink()


# --------------------------------------------------------------------------- US1 .df (T007)

class DfTests(Base):
    def test_block_counts(self):
        kinds = [b[0] for b in self.blocks]
        self.assertEqual(kinds.count("SEQUENCE"), 32)
        self.assertEqual(kinds.count("TABLE"), 32)
        self.assertEqual(kinds.count("FIELD"), 479)
        self.assertEqual(kinds.count("INDEX"), 198)
        seqs = sorted(b[1] for b in self.blocks if b[0] == "SEQUENCE")
        self.assertEqual(seqs, sorted(f"Seq{t.name}Id" for t in self.schema.tables))

    def test_sequence_block(self):
        self.assertEqual(block(self.df, 'ADD SEQUENCE "SeqCustomerId"'),
                         'ADD SEQUENCE "SeqCustomerId"\n  INITIAL 1\n  INCREMENT 1\n  CYCLE-ON-LIMIT no\n'
                         '  MIN-VAL 1')

    def test_table_block(self):
        self.assertEqual(block(self.df, 'ADD TABLE "Customer"'),
                         'ADD TABLE "Customer"\n  AREA "PB_Master_Wide"\n  LABEL "Customer"\n'
                         '  DESCRIPTION "Individual or business bank customer"\n  DUMP-NAME "customer"')

    def test_id_field_block(self):
        b = block(self.df, 'ADD FIELD "CustomerId" OF "Customer" AS int64').split("\n")
        self.assertEqual(b[0], 'ADD FIELD "CustomerId" OF "Customer" AS int64')
        self.assertTrue(b[1].startswith('  DESCRIPTION "Dense sequential identifier'))
        self.assertEqual(b[2:], ['  FORMAT ">>>>>>>>>>>9"', '  INITIAL "0"', '  LABEL "Customer Id"',
                                 '  POSITION 2', '  MAX-WIDTH 8', '  COLUMN-LABEL "Customer Id"',
                                 '  ORDER 10', '  MANDATORY'])

    def test_clob_field_block(self):
        b = block(self.df, 'ADD FIELD "NoteText" OF "CustomerNote" AS clob').split("\n")
        self.assertIn('  FORMAT "x(8)"', b)
        self.assertIn('  INITIAL ?', b)
        i = b.index('  LOB-AREA "PB_Lob_Text"')
        self.assertEqual(b[i:i + 6], ['  LOB-AREA "PB_Lob_Text"', '  LOB-BYTES 8192', '  LOB-SIZE 8K',
                                      '  CLOB-CODEPAGE "UTF-8"', '  CLOB-COLLATION "BASIC"', '  CLOB-TYPE 1'])
        self.assertFalse(any(x.startswith("  MAX-WIDTH") for x in b))
        self.assertNotIn("  MANDATORY", b)

    def test_index_blocks(self):
        self.assertEqual(block(self.df, 'ADD INDEX "IxAccountPosted" ON "DebitTransaction"'),
                         'ADD INDEX "IxAccountPosted" ON "DebitTransaction"\n  AREA "PB_Txn_Idx"\n'
                         '  INDEX-FIELD "AccountId" ASCENDING\n  INDEX-FIELD "PostedAt" DESCENDING')
        self.assertEqual(block(self.df, 'ADD INDEX "WxSummary" ON "CustomerNote"'),
                         'ADD INDEX "WxSummary" ON "CustomerNote"\n  AREA "PB_Master_Idx"\n  WORD\n'
                         '  INDEX-FIELD "Summary" ASCENDING')
        self.assertEqual(block(self.df, 'ADD INDEX "PkCustomer" ON "Customer"'),
                         'ADD INDEX "PkCustomer" ON "Customer"\n  AREA "PB_Master_Idx"\n  UNIQUE\n  PRIMARY\n'
                         '  INDEX-FIELD "CustomerId" ASCENDING')

    def test_field_attribute_rules(self):
        widths = {"INTEGER": 4, "INT64": 8, "DECIMAL": 17, "LOGICAL": 1, "DATE": 4, "DATETIME": 8,
                  "DATETIME-TZ": 12}
        for t in self.schema.tables:
            for pos, f in enumerate(t.fields):
                lines = block(self.df, f'ADD FIELD "{f.name}" OF "{t.name}" AS {f.type.lower()}').split("\n")[1:]
                loc = f"{t.name}.{f.name}"
                self.assertIn(f"  POSITION {pos + 2}", lines, loc)
                self.assertIn(f"  ORDER {(pos + 1) * 10}", lines, loc)
                self.assertEqual("  MANDATORY" in lines, f.mandatory, loc)
                self.assertEqual(any(x.startswith("  DECIMALS") for x in lines), f.type == "DECIMAL", loc)
                if f.type == "CHARACTER":
                    self.assertIn(f"  MAX-WIDTH {2 * m.char_width(f.format)}", lines, loc)
                elif f.type in widths:
                    self.assertIn(f"  MAX-WIDTH {widths[f.type]}", lines, loc)
                if f.initial == "?":
                    self.assertIn("  INITIAL ?", lines, loc)
                if f.initial == "NOW":
                    self.assertIn('  INITIAL "now"', lines, loc)
                if f.type == "BLOB":
                    self.assertTrue(any(x.startswith("  LOB-AREA") for x in lines), loc)
                    self.assertFalse(any(x.startswith("  CLOB-") for x in lines), loc)

    def test_table_order_is_load_order_and_children_follow(self):
        order = [t for level in m.load_order(self.schema) for t in level]
        self.assertEqual([b[1] for b in self.blocks if b[0] == "TABLE"], order)
        current = None
        for kind, name, head, _ in self.blocks:
            if kind == "TABLE":
                current = name
            elif kind in ("FIELD", "INDEX"):
                self.assertTrue(head.endswith(f'"{current}"') or f'OF "{current}" AS' in head, head)
        t = self.schema.get_table("Customer")
        idx = [b[1] for b in self.blocks if b[0] == "INDEX" and b[2].endswith('ON "Customer"')]
        self.assertEqual(idx, [i.name for i in t.indexes])

    def test_trailer_offset(self):
        self.assertRegex(self.df, r"\n\.\nPSC\ncpstream=UTF-8\n\.\n\d{10}\n\Z")
        raw = self.df.encode("utf-8")
        expected = raw.index(b"\n.\nPSC\n") + 3
        self.assertEqual(int(self.df.rstrip("\n").rsplit("\n", 1)[1]), expected)
        self.assertTrue(raw[expected:].startswith(b"PSC\n"))

    def test_escaping_and_no_tabs(self):
        self.assertEqual(g.df_string('He said "hi" ~ ≈'), '"He said ""hi"" ~~ ≈"')
        self.assertEqual(g.df_string("a\nb"), '"a b"')
        schema = m.load_expanded(REAL)
        schema.get_table("Customer").description = 'He said "hi" ~ ≈'
        text = g.render_df(schema, g.area_plan(schema))
        self.assertIn('DESCRIPTION "He said ""hi"" ~~ ≈"', text)
        self.assertNotIn("\t", self.df)

    def test_deterministic(self):
        schema = m.load_expanded(REAL)
        self.assertEqual(g.render_df(schema, g.area_plan(schema)), self.df)

    def test_expect_file(self):
        exp = g.render_expect(self.schema)
        names = ",".join(sorted((t.name for t in self.schema.tables), key=str.lower))
        self.assertEqual(exp, "tables=32\nfields=479\nindexes=198\nsequences=32\ncodepage=UTF-8\nlargefiles=yes\n"
                              f"blocksize=8192\nbiblocksize=16384\nbiclustersize=16777216\ntable-list={names}\n")

    def test_check_detects_hand_edits(self):
        out = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(quiet(g.main, [str(REAL), "--out", str(out)]), 0)
            self.assertEqual(quiet(g.main, [str(REAL), "--out", str(out), "--check"]), 0)
            for name in ("parkbench.df", "parkbench.st", "parkbench.expect"):
                p = out / name
                orig = p.read_bytes()
                p.write_bytes(orig[:-2] + b"X" + orig[-1:])
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(g.main([str(REAL), "--out", str(out), "--check"]), 1)
                self.assertIn(f"out of date: {p}", buf.getvalue())
                p.write_bytes(orig)
                self.assertEqual(quiet(g.main, [str(REAL), "--out", str(out), "--check"]), 0)
        finally:
            shutil.rmtree(out)


# --------------------------------------------------------------------------- US2 .st (T014)

class StTests(Base):
    def test_default_st(self):
        lines = self.st.split("\n")
        self.assertEqual(lines[0], "# ParkBenchDB structure file - generated from schema/parkbench-schema.yaml by "
                                   "tools/gen_db_files.py.")
        self.assertEqual(lines[1], "# One variable extent per area; requires large-file support "
                                   "(enabled by db/build_db.*).")
        body = [x for x in lines if x and not x.startswith("#")]
        self.assertEqual(body[0], "b .")
        self.assertEqual(body[1], 'd "Schema Area":6,32;1 .')
        self.assertEqual(body[2], 'd "PB_Ref_Data":7,64;8 .')
        self.assertEqual(body[-1], 'd "PB_Lob_Text":20,8;512 .')
        self.assertEqual(len(body), 16)
        self.assertFalse(any(" f " in x for x in body))
        self.assertTrue(self.st.endswith("\n"))

    def test_rpb_and_bpc_values(self):
        for line in self.st.split("\n"):
            mm = re.match(r'^d "[^"]+":(\d+),(\d+);(\d+) ', line)
            if mm and int(mm.group(1)) >= 7:
                self.assertIn(int(mm.group(2)), {1, 2, 4, 8, 16, 32, 64, 128, 256})
                self.assertIn(int(mm.group(3)), {8, 64, 512})

    def test_extent_dir_quoting(self):
        spaced = g.render_st(self.schema, self.plan, "/data/pb test")
        self.assertIn('b !"/data/pb test"', spaced)
        self.assertIn('d "PB_Ref_Data":7,64;8 !"/data/pb test"', spaced)
        plain = g.render_st(self.schema, self.plan, "/data/pb")
        self.assertIn("b /data/pb\n", plain)

    def test_bad_extent_dir_exits_2(self):
        out = tempfile.mkdtemp()
        try:
            for bad in ('/data/"x"', "/data/a\nb"):
                self.assertEqual(quiet(g.main, [str(REAL), "--out", out, "--extent-dir", bad]), 2)
        finally:
            shutil.rmtree(out)

    def test_deterministic(self):
        self.assertEqual(g.render_st(self.schema, self.plan, "."), self.st)

    def test_areas_referenced_in_df_exist_in_st(self):
        st_areas = set(re.findall(r'^d "([^"]+)"', self.st, re.M))
        df_areas = set(re.findall(r'^  (?:AREA|LOB-AREA) "([^"]+)"', self.df, re.M))
        self.assertTrue(df_areas <= st_areas, df_areas - st_areas)


if __name__ == "__main__":
    unittest.main()
