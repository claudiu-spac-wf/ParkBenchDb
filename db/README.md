# Building the ParkBenchDB database

This directory holds everything needed to create an empty ParkBenchDB database on **OpenEdge 12.8**, serve it, and fill it with generated data (see [docs/data-generation.md](../docs/data-generation.md)).

| File | What it is | Edit by hand? |
|------|-----------|---------------|
| `parkbench.df` | Data definitions: 32 sequences, 32 tables, 479 fields, 198 indexes | No, it's generated |
| `parkbench.st` | Structure: before-image, Schema Area, 14 Type II areas (one variable extent each) | No, it's generated |
| `parkbench.expect` | Expected counts and settings, read by the verify step | No, it's generated |
| `build_db.sh` / `build_db.bat` | One-command build for Linux/UNIX / Windows | Yes |
| `abl/load_df.p` | Batch wrapper around `prodict/load_df.p`, which fails on any error or warning | Yes |
| `abl/verify_db.p` | Post-build checks | Yes |
| `dump_db.sh` / `dump_db.bat` | Binary-dump a database (served or offline) into a portable dump directory | Yes |
| `load_db.sh` / `load_db.bat` | Build a new database from such a dump, on any OS | Yes |
| `abl/dumpload.p` | Schema, sequences and manifest for the dump; sequences and checks after the load | Yes |
| `server.sh` / `server.bat` | Start, stop or query the database server with bulk-load settings | Yes |
| `pbgen.sh` / `pbgen.bat` | Run the data generator (`python -m pbgen`) with the repository's virtual environment | Yes |
| `pbwork.sh` / `pbwork.bat` | Run the workload catalog, validator, and eight read profiles | Yes |
| `abl/pbwork_agent.p` | Persistent read workload agent (validated with OpenEdge 12.8 against the served 1 GB database) | Yes |
| `parkbench_loader.df` | Definitions of the generator's internal tables `LoaderRun` and `LoaderUnit` (loaded by `pbgen init`) | No, it's generated (`--loader`) |
| `abl/pbgen_init.p` | Loads `parkbench_loader.df` if the loader tables are missing | Yes |
| `abl/pbgen_agent.p` | The generator's database agent: plans, claims and loads work units | Yes |
| `abl/pbgen_check.p` | The in-database part of `pbgen check` | Yes |
| `abl/pbgen_counts.p`, `abl/pbgen_corrupt.p` | Test helpers for `tests/test_pbgen_integration.py` | Yes |

The three generated files come from [`schema/parkbench-schema.yaml`](../schema/parkbench-schema.yaml), the same source as the [schema documentation](../docs/schema/README.md), so the database always matches the docs.

For workloads on a served, populated database, start with
`db/pbwork.sh catalog --json` (or `db\pbwork.bat catalog --json` on Windows),
then `validate --db <path> --profile read-reference-point`, and finally
`run --db <path> --profile read-reference-point --operations 1000 --result <file>`.
Run `pbgen check` before and after a read benchmark. Eight read profiles are
enabled; seven write/mixed profiles are catalogued but intentionally unavailable
until isolated-copy and cleanup gates pass. See the
[workload guide](../docs/data-generation.md#workload-development-status) for
profile coverage, scale prerequisites, and result fields.

## Regenerating the files

```bash
python3 tools/gen_db_files.py schema/parkbench-schema.yaml --out db           # write
python3 tools/gen_db_files.py schema/parkbench-schema.yaml --out db --check   # verify committed copies are current
python3 tools/gen_db_files.py schema/loader-schema.yaml --out db --loader     # parkbench_loader.df (add --check to verify)
```

Options:
- `--db-name` (default `parkbench`) sets the output file names.
- `--extent-dir` (default `.`) sets the directory written into the `.st`. Paths containing spaces are written `!"…"`.

The committed `.st` uses `.`, which the build scripts rely on.

## Building with the script

```bash
export DLC=/usr/dlc                  # your OpenEdge 12.8 installation
db/build_db.sh /data/parkbench       # optional 2nd argument: database name (default parkbench)
db/build_db.sh /data/pb8 --bi-block-size 8 --bi-cluster-size 64    # non-default before-image settings
```

```bat
set DLC=C:\Progress\OpenEdge
db\build_db.bat D:\data\parkbench
db\build_db.bat D:\data\pb8 --bi-block-size 8 --bi-cluster-size 64
```

| Option | Values | Default |
|--------|--------|---------|
| `--bi-block-size <KB>` | 1, 2, 4, 8, 16 | 16 |
| `--bi-cluster-size <MB>` | 1-255 | 16 |

Options may come before or after the positional arguments. An invalid value fails step 1 (exit 2) before anything is changed. The chosen values are applied in step 4 and checked in step 7.

Both scripts perform the same seven steps, print `[n/7] <step> ... ok` for each, and log all tool output to `<target>/<db>_build.log`:

| # | Step | What happens |
|---|------|--------------|
| 1 | Check prerequisites | `DLC` is set, `$DLC/version` says 12.8, the tools and `$DLC/prolang/utf/empty8.db` exist, and no database of that name exists in the target |
| 2 | Create structure | `prostrct create <db> <db>.st -blocksize 8192` |
| 3 | Copy UTF-8 metaschema | `procopy $DLC/prolang/utf/empty8 <db>` (UTF-8 codepage, BASIC collation) |
| 4 | Configure before-image | `proutil <db> -C truncate bi -bi <cluster MB × 1024> -biblocksize <KB>` (default 16 MB clusters, 16 KB blocks) |
| 5 | Confirm large files | `proutil <db> -C describe` must list "Large Files … Yes". Large files are always on in 12.8; `-C enablelargefiles` is retired (message 19352) |
| 6 | Load schema | `_progres -b -1 … -p abl/load_df.p`. Any error **or warning** fails the step |
| 7 | Verify database | `_progres -b -1 … -p abl/verify_db.p`: tables, table names, fields, indexes, no default indexes, sequences, UTF-8, 8 KB blocks, large files, BI block and cluster size |

| Exit code | Meaning |
|-----------|---------|
| 0 | Built and verified (`VERIFY OK`) |
| 2 | A prerequisite is missing, or the database already exists. Nothing was changed |
| 3 | A build step failed. The partial database is left in place; see the log |
| 4 | Built, but verification failed. The `CHECK …: FAIL` lines say what's wrong |

To rebuild, delete the target directory (or choose another one) and run the script again.

## Moving a database to another OS

OpenEdge database files can't be copied between operating systems, so a database generated on Windows is moved to Linux with a **binary dump and load**. The dump files are platform-independent.

```bat
rem Windows: dump (the source may stay served; stop pbgen workers first)
db\dump_db.bat data\parkbench\parkbench D:\xfer\pbdump
```

```bash
# copy D:\xfer\pbdump to the Linux host (scp, rsync, a share...), then:
export DLC=/usr/dlc
db/load_db.sh /xfer/pbdump /data/parkbench2            # optional: [db-name] --bi-block-size 8 --bi-cluster-size 64
db/server.sh start /data/parkbench2/parkbench --workers 8
db/pbgen.sh check --db /data/parkbench2/parkbench       # optional: the data check
```

**`dump_db <db-path> <dump-dir> [--allow-active]`** (4 steps; exit 0 dumped, 2 refused, 3 failed)
- Only reads the source. Served databases are dumped online; offline ones single-user (`-1`). A database open single-user by someone else is refused.
- `<dump-dir>` must be new or empty. It gets `<table>.bd` for every table (the 32 benchmark tables, plus `LoaderRun`/`LoaderUnit` once `pbgen init` has run, so `pbgen grow` works on the copy), LOBs included; `schema.df` (the source's own definitions); `manifest.txt` (tables, per-table row counts from `proutil`, sequence values); and `dump.log`.
- Refused while `pbgen` units are claimed (workers still writing would make the dump inconsistent), unless `--allow-active`.

**`load_db <dump-dir> <target-dir> [db-name] [--bi-block-size KB] [--bi-cluster-size MB]`** (8 steps; exit codes as `build_db`: 0, 2, 3, 4 verification failed)

| # | Step | What happens |
|---|------|--------------|
| 1 | Check prerequisites | `DLC` 12.8 and tools; the dump is complete (manifest, `schema.df`, a `.bd` and a row count for every table); **the target database does not exist** — an existing database is never overwritten |
| 2 | Create structure | this repository's `parkbench.st` (local extent paths, not the source's), `-blocksize 8192` |
| 3 | Copy UTF-8 metaschema | `procopy $DLC/prolang/utf/empty8` |
| 4 | Configure before-image | as `build_db` (default 16 KB blocks, 16 MB clusters) |
| 5 | Load schema | the dump's `schema.df` with `abl/load_df.p` |
| 6 | Load data | `proutil -C load <table>.bd -cpinternal UTF-8` per table; every loaded count must equal the dumped count |
| 7 | Rebuild indexes | `proutil -C idxbuild all -TB 64 -TM 32 -SG 64` (binary load leaves indexes inactive) |
| 8 | Restore sequences and verify | `abl/dumpload.p`: sets every sequence to its dumped value; checks the table list, the sequences and that no index is inactive |

Plan disk space for the dump (about the size of the data and LOBs, without indexes) and, on the target, for the database plus idxbuild's sort files (written to the target directory).

## Building by hand

From the target directory, with `DLC` set and `<repo>` being this repository:

```bash
cp <repo>/db/parkbench.st parkbench.st
prostrct create parkbench parkbench.st -blocksize 8192
procopy $DLC/prolang/utf/empty8 parkbench
proutil parkbench -C truncate bi -bi 16384 -biblocksize 16
proutil parkbench -C describe            # confirm "Large Files ... Yes"
_progres -b -1 -db parkbench -cpinternal UTF-8 -cpstream UTF-8 \
    -p <repo>/db/abl/load_df.p -param "<repo>/db/parkbench.df|load.status"
_progres -b -1 -db parkbench -cpinternal UTF-8 -cpstream UTF-8 \
    -p <repo>/db/abl/verify_db.p -param "<repo>/db/parkbench.expect|verify.status"
```

Alternatively, load `parkbench.df` interactively with the Data Dictionary (Admin → Load Data and Definitions → Data Definitions).

## Storage layout

Every area has **one variable (growable) extent**, so the same `.st` works for any data volume. It depends on large-file support, which OpenEdge 12.8 always provides. If a benchmark needs fixed-size extents, add them afterwards with `prostrct add`. Area numbers are 6 (Schema Area) and 7–20 in the order of `areas` in the schema source. New areas must be appended there, so existing numbers stay stable.

## Verified on OpenEdge

These files were built and verified on **OpenEdge 12.8.11 (Windows)** with `build_db.bat`. All 11 verify checks passed, and the load produced no errors or warnings. A dump of the loaded schema with `prodict/dump_df.p` is identical to `parkbench.df`, block for block.

To repeat that check:

```bash
PARKBENCH_OE_TESTS=1 python3 -m unittest tests.test_openedge_integration -v
```

This uses `PARKBENCH_OE_DLC` or the Windows `DLC`.

The Linux `build_db.sh` has been exercised only against the stub OpenEdge in `tests/fixtures/fake_dlc`. Its OpenEdge commands are the same as the Windows script's, but the first real Linux build is still worth watching.
