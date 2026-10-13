# Loading data into ParkBenchDB

`pbgen` fills a ParkBenchDB database (built with [`db/build_db.*`](../db/README.md)) with realistic, deterministic banking data made with [Faker](https://faker.readthedocs.io/). It is designed for large databases:

- **Parallel**: one command starts N workers.
- **Stoppable at any time**: Ctrl+C, a closed window or `kill -9` loses at most the work unit each worker had in flight. Running the same command again carries on.
- **Incremental**: start with about 1 GB, then grow by 4 GB, then by 15 GB, and so on. Growth adds customers (with all their accounts, transactions and documents) plus a proportional share of employees and merchants. IDs continue and no existing row is changed.
- **Deterministic**: the same seed and plan give identical data, whatever the number of workers and however often the run was interrupted.

The design is in [`specs/003-data-generation/`](../specs/003-data-generation/).

## Workload development status

The companion `pbwork` catalog declares 15 profiles to cover Tiny through
Very Large tables, narrow/wide/LOB rows, selective/range/scan/navigation reads,
and append/update/contention/mixed writes. All eight read profiles are enabled
and were exercised against a served 1 GB OpenEdge 12.8 database. The seven
write/mixed declarations remain disabled until isolated-copy execution passes
its safety gates. A Tiny reference-table point-read example is:

```bash
db/pbwork.sh catalog --json
db/pbwork.sh validate --db /data/pb/parkbench --profile read-reference-point
db/pbwork.sh run --db /data/pb/parkbench --profile read-reference-point \
  --operations 1000 --seed 20260929 --result /tmp/read-reference.json
```

The run result includes exact operation and row counters, bounded latency
samples with median/p95/p99, profile version, seed, coverage tags, and the
database target. Before running, complete a `pbgen check` on the source;
validation uses `BenchmarkTableInfo` row counts as a prerequisite gate. For a
representative 1 GB source, follow the existing workflow below with
`db/pbgen.sh plan --size-gb 1`, then `run` and `check`. A profile may need a
larger database if any representative table has fewer than its declared
`minimumRows` requirement.

| Read profile | Main pressure |
|--------------|---------------|
| `read-reference-point` | Tiny primary-key lookups |
| `read-small-table-scan` | Bounded small-table scans and counts |
| `read-medium-narrow-selective` | Indexed predicates on narrow rows |
| `read-medium-wide-selective` | Wide point and selective reads |
| `read-large-range` | Ordered large-table ranges |
| `read-very-large-selective` | Very-large point and indexed reads |
| `read-relationship-navigation` | Customer-to-account-to-transaction traversal |
| `read-lob-fetch` | Scalar, CLOB, BLOB, and combined LOB fetches |

Run each profile with `--operations N` or `--duration SECONDS` (not both),
optionally `--workers N`, `--seed N`, and `--param key=value`. Use
`catalog --json` to inspect profile-specific parameters and per-table
`minimumRows`.
The result JSON's `schema_version`, `run.profile_id`, `run.profile_version`,
`run.seed`, and `run.workers` identify a comparison baseline. `metrics`
reports attempted/completed/failed, rows, throughput, and median/p95/p99
latency from a bounded sample. `sample_count` and `sample_limit` state how
much data supports those percentiles. Read results must have zero committed,
rolled-back, and written rows. Use `compare` only on compatible profile
versions.

Write/mixed runs are deliberately rejected for now: source-baseline capture,
working-copy isolation, and safe cleanup are still pending. The planned
default is a dump/load working copy, a baseline manifest containing actual
row counts for all 32 benchmark tables, `BenchmarkTableInfo`, schema digest,
and sequence values, followed by stop-before-remove cleanup and an exact
source comparison. `--retain-changes` will require explicit opt-in and a
recoverable run ID once that path exists. Do not point a write profile at the
served source database. The PASOE image build and
smoke commands are documented in
[`ParkBench/docker/openedge-pasoe-parkbench/README.md`](../ParkBench/docker/openedge-pasoe-parkbench/README.md).

## Prerequisites

| What | Why |
|------|-----|
| OpenEdge 12.8 on the **database host**, with `DLC` set | Workers connect self-service (shared memory), which is about 7× faster than TCP. `--host/--port` works too, but is slow |
| Python ≥ 3.11 with `pip install -r requirements.txt` (PyYAML and **Faker 40.39.0**) | The generator. Faker is pinned, because a different version gives different data |
| A database built by `db/build_db.*` and **served** by `db/server.*` | `pbgen` refuses an unserved database and tells you the `server` command to run |

The wrappers `db/pbgen.sh` and `db\pbgen.bat` pick Python in this order: `PBGEN_PYTHON`, then the repository's `.venv` (Linux) or `.venv-win` (Windows), then `python3` or `python`. They set `PYTHONPATH` and run `python -m pbgen`.

```bat
rem Windows, once
python -m venv .venv-win
.venv-win\Scripts\pip install -r requirements.txt
```

## The server script

```bash
db/server.sh start  /data/pb/parkbench --workers 8     # Windows: db\server.bat
db/server.sh status /data/pb/parkbench
db/server.sh stop   /data/pb/parkbench
```

`start` runs `proserve` with bulk-load settings, then one before-image writer (`probiw`) and page writers (`proapw`), and waits for "connections enabled" (message 10471). Exit codes: 0 ok or running, 2 bad arguments or already running, 3 not running, 4 start timed out.

| Option | Default | Sets | Why |
|--------|---------|------|-----|
| `--workers N` | 8 | `-n` = N + 10, `-Mn` = 4 + N/4, and the lock-table default | Size it for the most workers you will run |
| `--lock-table N` | max(100,000, 40,000 × workers) | `-L` | Each work unit is one transaction of up to 35,000 rows, and every new row holds a lock until commit. `pbgen run` refuses more workers than `-L` supports |
| `--buffers N` | 200,000 | `-B` (8 KB each, ≈ 1.6 GB) | Keeps index blocks in memory during the load |
| `--apws N` | 2 | number of `proapw` | Page writers flush dirty buffers so workers don't have to. Measured: 4 workers on an untuned server were slower than 1 |
| `--port N` | 20931 | `-S` | For TCP clients and SQL |
| (fixed) | | `-bibufs 64 -spin 20000` | Before-image buffers and spin locks for many concurrent writers |

The generator never starts or stops the server: you do.

## Workflow

```bash
DB=/data/pb/parkbench
db/build_db.sh /data/pb                           # empty database
db/server.sh start $DB --workers 8
db/pbgen.sh init  --db $DB                        # adds the loader tables LoaderRun / LoaderUnit
db/pbgen.sh plan  --db $DB --size-gb 1            # or --scale 0.01, or --customers 10000; optional --seed N
db/pbgen.sh run   --db $DB --workers 8            # generates until the run is complete
db/pbgen.sh status --db $DB                       # progress, rate, ETA, estimated vs actual size
db/pbgen.sh check --db $DB                        # data check (add --full for every row)
```

| Command | What it does | Exit |
|---------|--------------|------|
| `init` | Loads `db/parkbench_loader.df` if the loader tables are missing. Safe to repeat | 0 / 2 |
| `plan (--size-gb G \| --scale S \| --customers C) [--seed N] [--as-of YYYY-MM-DD] [--calibrate]` | Defines run 1 on an empty database: every unit, row count and first ID is fixed now. Prints the per-table targets | 0; 2 refused |
| `grow (--add-gb G \| --add-scale S \| --add-customers C) [--calibrate]` | Defines the next growth run. Refused while a run is incomplete | 0; 2 refused |
| `run --workers N [--force-version]` | Starts N workers and supervises them until the open run is complete | 0 complete; 130 interrupted; 1 worker error |
| `status [--json]` | Progress report | 0 |
| `check [--full] [--json]` | Density, `BenchmarkTableInfo`, RandomInt ranges, foreign keys, derived totals and value distributions | 0 pass; 1 fail |
| `finalize` | Re-runs finalization (sequences, `BenchmarkTableInfo`, `ScaleFactor`). Idempotent | 0 |
| `release-claims [--older-than MIN]` | Releases claims of workers that are gone | 0 |

All commands take `--db <path>` (self-service), or `--db <name> --host H --port P` (TCP), and optionally `--spool DIR` (default `<db-dir>/pbgen-spool`, where workers write unit files and logs).

### Stopping and resuming

- **Ctrl+C** (or SIGTERM): workers drop the unit they are generating, finish nothing new, and exit. `run` exits 130.
- **A hard kill** (closed window, `kill -9`, Task Manager, power loss): the database rolls back the in-flight load transactions. OpenEdge may also **shut the database down** to protect it, when a killed self-service worker was inside a microtransaction (the log shows `(2256) SYSTEM ERROR: User N died during microtransaction` and `Begin ABNORMAL shutdown`). Then `db/server.sh status` says `stopped`, and `db/server.sh start` runs crash recovery before serving again. Nothing committed is lost. Prefer Ctrl+C when you can. The next `run` releases claims held by dead processes on this host straight away. Claims from other hosts are reclaimed after 5 minutes without a heartbeat, or with `release-claims`.
- **Resume**: (re)start the server if needed, then run the same `run` command again, with any number of workers. Running a second `run` while one is active adds workers.

`BenchmarkTableInfo` (and so every benchmark's idea of `MaxId`) only advances over a gap-free prefix of finished units, so IDs up to `MaxId` are always dense, even mid-run.

### Worked example: 1 GB, then +4 GB, then +15 GB

```bash
db/pbgen.sh plan --db $DB --size-gb 1 && db/pbgen.sh run --db $DB --workers 8     # ≈ SF 0.0075
db/pbgen.sh grow --db $DB --add-gb 4  && db/pbgen.sh run --db $DB --workers 8     # ≈ SF 0.05 in total
db/pbgen.sh grow --db $DB --add-gb 15 --calibrate && db/pbgen.sh run --db $DB --workers 8   # ≈ SF 0.22
```

Sizes mean the **approximate database size on disk** (data, indexes, LOBs and before-image), not the data volume. The model counts blocks and clusters, and was fitted on a real database with `proutil -C dbanalys`: about 1.2 GB at scale factor 0.01, 3 GB at 0.03 and 91 GB at 1 (1,000,000 customers). `status` shows the estimate next to the actual extent sizes. `--calibrate` corrects the next target by the last run's measured ratio. The smallest database is scale factor 0.005 (≈ 0.8 GB), where fixed per-table space starts to dominate.

### Versions

A run records the `pbgen` and Faker versions. `run` refuses to continue a run with a different version (the rest of the run would not match its first part) unless you pass `--force-version`.

## Moving the database to Linux

Generate on Windows, benchmark on Linux: stop the workers, then `db\dump_db.bat <db> <dump-dir>`, copy the directory, and `db/load_db.sh <dump-dir> <target-dir>` on Linux. The copy has the same rows, sequences, `BenchmarkTableInfo` and loader state, so `pbgen status`, `check` and `grow` work on it. See [db/README.md](../db/README.md#moving-a-database-to-another-os).

## Before-image options

`db/build_db.*` accepts `--bi-block-size <KB>` (1, 2, 4, 8, 16; default 16) and `--bi-cluster-size <MB>` (1-255; default 16). Larger clusters mean fewer checkpoints during a bulk load. See [db/README.md](../db/README.md#building-with-the-script).

## Why not SQL?

The plan was to insert through OpenEdge SQL if it worked correctly. On the development machine the ODBC driver fails to load (`system error 1114 … pgoe28.dll`, the same from Python, .NET and a bare `LoadLibrary`), and JDBC needs a JVM that isn't installed. Instead, Python writes each work unit as a JSON file, and a persistent ABL agent (`db/abl/pbgen_agent.p`, one per worker) reads it with `DATASET:READ-JSON` and inserts it with `BUFFER-COPY`, in one transaction together with marking the unit done. Every data type, including Unicode text, DATETIME-TZ and BLOBs, round-trips exactly. Details: [research R1](../specs/003-data-generation/research.md).

## Measured throughput

Windows desktop (8 CPUs), OpenEdge 12.8.11, self-service, server started by `db/server.bat --workers 4`, scale factor 0.01 (2,408,357 rows, 1.24 GB on disk):

| Workers | Time | Rows/s |
|---------|------|--------|
| 1 | 383 s | 6,285 |
| 4 | 241 s | 9,973 (×1.59) |

A resumed run (two hard kills, one abnormal shutdown and restart) loaded its remaining 176 units at 8,084 rows/s with 4 workers and produced data identical to the uninterrupted run. `pbgen check` on this database takes about 2.5 minutes.

The database side (index inserts, the before-image and a single disk) is the bottleneck, not Faker: each worker spends about 40% of its time generating and 60% waiting for its load transaction. On a benchmark server with more cores and faster storage, more page writers and a larger `-B` help most. At 10,000 rows/s a full scale-factor-1 database (≈ 244M rows) takes about 7 hours on this class of machine.

## Tests

- Offline, with the SQLite-backed `FakeAgent`: `.venv/bin/python -m unittest discover -s tests -p "test_pbgen_*.py"` (Faker must be installed in that Python).
- Real OpenEdge (about an hour; five databases under `.tmp/pbit/`): `PARKBENCH_OE_TESTS=1 .venv/bin/python -m unittest tests.test_pbgen_integration -v`.
