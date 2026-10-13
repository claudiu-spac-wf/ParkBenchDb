#!/usr/bin/env bash
# Build a new ParkBenchDB database from a binary dump made by db/dump_db.* (on any OS).
#
#   usage: db/load_db.sh <dump-dir> <target-dir> [db-name] [--bi-block-size <KB>] [--bi-cluster-size <MB>]
#          (db-name defaults to parkbench; before-image defaults: 16 KB blocks, 16 MB clusters)
#
# The new database uses this repository's parkbench.st (so extent paths are local), the UTF-8
# empty database and the schema.df from the dump. An existing database is never touched: if
# <target-dir>/<db-name>.db exists, nothing is done.
#
# Steps: 1 Check prerequisites   2 Create structure       3 Copy UTF-8 metaschema   4 Configure before-image
#        5 Load schema           6 Load data              7 Rebuild indexes         8 Restore sequences and verify
# Exit codes: 0 loaded and verified; 2 prerequisite missing or target exists (nothing changed);
#             3 a step failed (partial database left in place); 4 verification failed.
# Keep in step with db/load_db.bat: same steps, names, options, output and exit codes.

set -u

STEPS=8
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ST_FILE="$SCRIPT_DIR/parkbench.st"
LOAD_P="$SCRIPT_DIR/abl/load_df.p"
DUMPLOAD_P="$SCRIPT_DIR/abl/dumpload.p"

usage() {
    echo "usage: load_db.sh <dump-dir> <target-dir> [db-name] [--bi-block-size <KB>] [--bi-cluster-size <MB>]"
    echo "  Builds a new database <target-dir>/<db-name>.db (default name: parkbench) from a dump made by dump_db."
    echo "  --bi-block-size    before-image block size in KB, one of 1, 2, 4, 8, 16 (default 16)"
    echo "  --bi-cluster-size  before-image cluster size in MB, 1-255 (default 16)"
    echo "  DLC must point at the OpenEdge 12.8 installation."
}

BI_BLOCK_KB=16
BI_CLUSTER_MB=16
POSITIONAL=()
while [ $# -gt 0 ]; do
    case "$1" in
        --bi-block-size)   [ $# -ge 2 ] || { usage; exit 2; }; BI_BLOCK_KB="$2"; shift 2 ;;
        --bi-cluster-size) [ $# -ge 2 ] || { usage; exit 2; }; BI_CLUSTER_MB="$2"; shift 2 ;;
        -*)                usage; exit 2 ;;
        *)                 POSITIONAL+=("$1"); shift ;;
    esac
done
if [ ${#POSITIONAL[@]} -lt 2 ] || [ ${#POSITIONAL[@]} -gt 3 ]; then
    usage
    exit 2
fi
DUMP="${POSITIONAL[0]}"
TARGET="${POSITIONAL[1]}"
DB="${POSITIONAL[2]:-parkbench}"
LOG=""

prereq_fail() {
    echo "FAILED"
    echo "FAILED at step 1 (Check prerequisites): $*"
    exit 2
}

fail() {  # fail <step> <name> <exit-code>
    echo "FAILED at step $1 ($2)"
    if [ -n "$LOG" ] && [ -f "$LOG" ]; then
        echo "---- last 40 lines of $LOG ----"
        tail -n 40 "$LOG"
    fi
    exit "$3"
}

run_step() {  # run_step <step> <name> <exit-code-on-failure> <command...>
    local n="$1" name="$2" code="$3"
    shift 3
    printf '[%d/%d] %s ... ' "$n" "$STEPS" "$name"
    echo "==== [$n/$STEPS] $name: $*" >>"$LOG"
    if "$@" >>"$LOG" 2>&1; then
        echo "ok"
    else
        echo "FAILED"
        fail "$n" "$name" "$code"
    fi
}

status_is_ok() {  # status_is_ok <status-file>
    if [ -f "$1" ] && [ "$(head -n 1 "$1" | tr -d '\r')" = "OK" ]; then
        return 0
    fi
    echo "status ($1): $( [ -f "$1" ] && head -n 1 "$1" || echo 'missing - the ABL procedure did not finish')"
    return 1
}

# ---------------------------------------------------------------- 1. prerequisites (no changes made)
printf '[1/%d] Check prerequisites ... ' "$STEPS"
[[ "$DB" =~ ^[A-Za-z][A-Za-z0-9_-]{0,10}$ ]] \
    || prereq_fail "invalid db-name '$DB': letters, digits, _ and -; at most 11 characters; must start with a letter"
[[ "$BI_BLOCK_KB" =~ ^(1|2|4|8|16)$ ]] \
    || prereq_fail "invalid --bi-block-size '$BI_BLOCK_KB' (KB); allowed: 1, 2, 4, 8, 16"
[[ "$BI_CLUSTER_MB" =~ ^[0-9]{1,3}$ ]] && [ "$BI_CLUSTER_MB" -ge 1 ] && [ "$BI_CLUSTER_MB" -le 255 ] \
    || prereq_fail "invalid --bi-cluster-size '$BI_CLUSTER_MB' (MB); allowed: 1-255"
[ -n "${DLC:-}" ] || prereq_fail "DLC is not set; point it at an OpenEdge 12.8 installation"
[ -f "$DLC/version" ] || prereq_fail "$DLC/version not found; DLC does not look like an OpenEdge installation"
grep -q "12\.8" "$DLC/version" || prereq_fail "OpenEdge 12.8 is required; $DLC/version says: $(head -n 1 "$DLC/version")"
for tool in prostrct procopy proutil _progres; do
    [ -x "$DLC/bin/$tool" ] || prereq_fail "$DLC/bin/$tool not found or not executable"
done
[ -f "$DLC/prolang/utf/empty8.db" ] || prereq_fail "UTF-8 empty database $DLC/prolang/utf/empty8.db not found"
for f in "$ST_FILE" "$LOAD_P" "$DUMPLOAD_P"; do
    [ -f "$f" ] || prereq_fail "$f not found; restore the repository files"
done
[ -d "$DUMP" ] || prereq_fail "dump directory $DUMP not found"
DUMP="$(cd "$DUMP" && pwd)"
MANIFEST="$DUMP/manifest.txt"
grep -q "^format=parkbench-dump-1" "$MANIFEST" 2>/dev/null \
    || prereq_fail "$MANIFEST is missing or not a dump_db manifest"
[ -s "$DUMP/schema.df" ] || prereq_fail "$DUMP/schema.df is missing"
TABLES=$(sed -n 's/^table=//p' "$MANIFEST" | tr -d '\r')
[ -n "$TABLES" ] || prereq_fail "$MANIFEST lists no tables"
for t in $TABLES; do
    [ -f "$DUMP/$t.bd" ] || prereq_fail "$DUMP/$t.bd is missing; the dump is incomplete"
    grep -q "^rows=$t=" "$MANIFEST" || prereq_fail "$MANIFEST has no row count for $t; the dump did not finish"
done
[ -e "$TARGET/$DB.db" ] && prereq_fail "database $TARGET/$DB.db already exists; it is never overwritten - choose another target or name"
echo "ok"

# ---------------------------------------------------------------- 2-8. build and load
mkdir -p "$TARGET" || fail 2 "Create structure" 3
TARGET="$(cd "$TARGET" && pwd)"
LOG="$TARGET/${DB}_load.log"
: >"$LOG"
cd "$TARGET" || fail 2 "Create structure" 3
cp "$ST_FILE" "$TARGET/$DB.st" || fail 2 "Create structure" 3
SCHEMA_STATUS="$TARGET/${DB}_step5.status"
FINISH_STATUS="$TARGET/${DB}_step8.status"
rm -f "$SCHEMA_STATUS" "$FINISH_STATUS"

load_schema() {
    "$DLC/bin/_progres" -b -1 -db "$DB" -cpinternal UTF-8 -cpstream UTF-8 \
        -p "$LOAD_P" -param "$DUMP/schema.df|$SCHEMA_STATUS" && status_is_ok "$SCHEMA_STATUS"
}

load_data() {
    local t out rows want bad=0
    for t in $TABLES; do
        out="$("$DLC/bin/proutil" "$DB" -C load "$DUMP/$t.bd" -cpinternal UTF-8 2>&1)" || { echo "$out"; return 3; }
        echo "$out"
        rows="$(echo "$out" | sed -n 's/.*Loaded \([0-9][0-9]*\) records.*/\1/p' | head -n 1)"
        want="$(sed -n "s/^rows=$t=//p" "$MANIFEST" | tr -d '\r')"
        if [ "$rows" != "$want" ]; then
            echo "COUNT $t: FAIL (loaded ${rows:-none}, dumped $want)"
            bad=$((bad + 1))
        else
            echo "COUNT $t: ok ($rows)"
        fi
    done
    [ $bad -eq 0 ] || return 4
}

rebuild_indexes() {
    local out
    out="$(echo y | "$DLC/bin/proutil" "$DB" -C idxbuild all -TB 64 -TM 32 -SG 64 -cpinternal UTF-8 2>&1)"
    local rc=$?
    echo "$out"
    [ $rc -eq 0 ] && echo "$out" | grep -q " 0 error(s) encountered"
}

finish() {
    "$DLC/bin/_progres" -b -1 -db "$DB" -cpinternal UTF-8 -cpstream UTF-8 \
        -p "$DUMPLOAD_P" -param "finish|$DUMP|$FINISH_STATUS" && status_is_ok "$FINISH_STATUS"
}

run_step 2 "Create structure"       3 "$DLC/bin/prostrct" create "$DB" "$DB.st" -blocksize 8192
run_step 3 "Copy UTF-8 metaschema"  3 "$DLC/bin/procopy" "$DLC/prolang/utf/empty8" "$DB"
run_step 4 "Configure before-image" 3 "$DLC/bin/proutil" "$DB" -C truncate bi -bi $((BI_CLUSTER_MB * 1024)) -biblocksize "$BI_BLOCK_KB"
run_step 5 "Load schema"            3 load_schema

printf '[6/%d] Load data ... ' "$STEPS"
echo "==== [6/$STEPS] Load data" >>"$LOG"
load_data >>"$LOG" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
    echo "FAILED"
    grep "^COUNT .*FAIL" "$LOG"
    fail 6 "Load data" "$rc"
fi
echo "ok"

run_step 7 "Rebuild indexes"        3 rebuild_indexes
run_step 8 "Restore sequences and verify" 4 finish

grep -E '^(CHECK|FINISH)' "$LOG" | tail -n 10
ROWS=$(grep -c "^COUNT .*: ok" "$LOG")
echo "Database $TARGET/$DB.db loaded from $DUMP ($ROWS tables) and verified."
exit 0
