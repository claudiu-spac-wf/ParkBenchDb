# ParkBenchDB

ParkBenchDB is the schema documentation for a synthetic retail-banking transaction database targeting **Progress OpenEdge 12.8**, designed for benchmarking. Every table carries a dense sequential ID plus `RandomInt10` / `RandomInt100` / `RandomInt1000` fields (each indexed), so benchmark scripts can select random subsets or single rows without knowing valid IDs.

**At a glance:** 32 tables, 479 fields and 198 indexes, spanning Tiny to Very Large tables (up to 50 million rows) and Narrow to Wide records, with a mix of CLOB and BLOB fields. The estimated data total is ≈ 40 GB at scale factor 1 (≈ 1,000,000 customers), plus ≈ 15–20 GB of indexes; measured on disk, a loaded database is about 91 GB at scale factor 1 (block and cluster overhead, see [docs/data-generation.md](docs/data-generation.md)). Start with the [schema overview](docs/schema/README.md).

The schema is defined once in [`schema/parkbench-schema.yaml`](schema/parkbench-schema.yaml). The published documentation in [`docs/schema/`](docs/schema/README.md) is generated from it.

## Requirements

- Python ≥ 3.11
- PyYAML and Faker (`pip install -r requirements.txt`; the data generator tests need Faker, e.g. in `.venv`)

## Commands

```bash
# 1. Validate the schema source
python3 tools/validate_schema.py schema/parkbench-schema.yaml

# 2. Generate the documentation
python3 tools/gen_docs.py schema/parkbench-schema.yaml --out docs/schema

# 3. Verify the committed docs are up to date
python3 tools/gen_docs.py schema/parkbench-schema.yaml --out docs/schema --check

# 4. Run the unit tests
python3 -m unittest discover -s tests -v

# 5. Generate the OpenEdge .df / .st files (add --check to verify the committed copies)
python3 tools/gen_db_files.py schema/parkbench-schema.yaml --out db

# 6. Build an empty OpenEdge 12.8 database (DLC must be set; Windows: db\build_db.bat)
db/build_db.sh /data/parkbench        # optional: --bi-block-size 8 --bi-cluster-size 64

# 7. Serve it and load data (Windows: db\server.bat, db\pbgen.bat)
db/server.sh start /data/parkbench/parkbench --workers 8
db/pbgen.sh init --db /data/parkbench/parkbench
db/pbgen.sh plan --db /data/parkbench/parkbench --size-gb 1
db/pbgen.sh run  --db /data/parkbench/parkbench --workers 8

# 8. Move it to another OS (binary dump/load; files are platform-independent)
db/dump_db.sh /data/parkbench/parkbench /xfer/pbdump       # on the source host
db/load_db.sh /xfer/pbdump /data/parkbench2                # on the target host
```

See [`db/README.md`](db/README.md) for the build steps, exit codes and manual alternative, and [`docs/data-generation.md`](docs/data-generation.md) for loading, stopping, resuming and growing data.

## Workload runner (in development)

`db/pbwork.sh catalog --json` lists the 15 planned read, write, and mixed
profiles. The eight read profiles are activated and have passed both offline
tests and read-only runs against a served 1 GB OpenEdge 12.8 database; the
seven write/mixed profiles remain disabled until isolated-copy execution is
safe. With OpenEdge 12.8 and a populated, served database, run:

```bash
db/pbwork.sh validate --db /data/parkbench/parkbench --profile read-reference-point
db/pbwork.sh run --db /data/parkbench/parkbench --profile read-reference-point --operations 1000 --seed 20260929 --result /tmp/read-reference.json
```

The write/mixed catalog entries currently fail with an unavailable-handler
error. Do not run write profiles against a production or shared source
database until working-copy isolation and cleanup are implemented. Profile
coverage, scale prerequisites, result interpretation, and the planned
isolation/retention model are in
[`docs/data-generation.md`](docs/data-generation.md#workload-development-status).

The custom PASOE image definition is in
[`ParkBench/docker/openedge-pasoe-parkbench/`](ParkBench/docker/openedge-pasoe-parkbench/README.md).
Set `PARKBENCH_PASOE_BUILD_CONTEXT` in `ParkBench/.env.local` to select another
definition folder. The default approved base is `parkbench/openedge-pasoe:dev`;
the custom image installs Python 3.11, pip, Faker, and PyYAML on top of it.

**Do not edit `docs/schema/` by hand.** Change the YAML or the tools, then regenerate.

Design documents live in [`specs/`](specs/): `001` schema, `002` .df/.st generation and build, `003` data generation, `004` workloads.
