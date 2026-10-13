#!/usr/bin/env bash
# Build an empty ParkBenchDB OpenEdge 12.8 database from the generated files in this directory.
#
#   usage: db/build_db.sh <target-dir> [db-name] [--bi-block-size <KB>] [--bi-cluster-size <MB>]
#          (db-name defaults to parkbench; before-image defaults: 16 KB blocks, 16 MB clusters)
#
# Steps (see specs/002-df-st-generation/research.md R8):
#   1 Check prerequisites   2 Create structure   3 Copy UTF-8 metaschema   4 Configure before-image
#   5 Confirm large files   6 Load schema        7 Verify database
#
# Exit codes: 0 built and verified; 2 prerequisite missing or database exists (nothing changed);
#             3 a build step failed (partial database left in place); 4 verification failed.
# Keep in step with db/build_db.bat: same steps, names, options, output and exit codes.

set -u

STEPS=7
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ST_FILE="$SCRIPT_DIR/parkbench.st"
DF_FILE="$SCRIPT_DIR/parkbench.df"
EXPECT_FILE="$SCRIPT_DIR/parkbench.expect"
LOAD_P="$SCRIPT_DIR/abl/load_df.p"
VERIFY_P="$SCRIPT_DIR/abl/verify_db.p"

usage() {
    echo "usage: build_db.sh <target-dir> [db-name] [--bi-block-size <KB>] [--bi-cluster-size <MB>]"
    echo "  Builds an empty OpenEdge 12.8 database <target-dir>/<db-name>.db (default name: parkbench)."
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
        -h|--help)         usage; exit 2 ;;
        -*)                usage; exit 2 ;;
        *)                 POSITIONAL+=("$1"); shift ;;
    esac
done
if [ ${#POSITIONAL[@]} -lt 1 ] || [ ${#POSITIONAL[@]} -gt 2 ]; then
    usage
    exit 2
fi
TARGET="${POSITIONAL[0]}"
DB="${POSITIONAL[1]:-parkbench}"
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

status_is_ok() {  # status_is_ok <status-file>; logs the reason when the status is not OK
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
[ -f "$DLC/prolang/utf/empty8.db" ] \
    || prereq_fail "UTF-8 empty database $DLC/prolang/utf/empty8.db not found"
for f in "$ST_FILE" "$DF_FILE" "$EXPECT_FILE" "$LOAD_P" "$VERIFY_P"; do
    [ -f "$f" ] || prereq_fail "$f not found; run tools/gen_db_files.py or restore the repository files"
done
[ -e "$TARGET/$DB.db" ] && prereq_fail "database $TARGET/$DB.db already exists; remove it or choose another target"
echo "ok"

# ---------------------------------------------------------------- 2-7. build
mkdir -p "$TARGET" || fail 2 "Create structure" 3
TARGET="$(cd "$TARGET" && pwd)"
LOG="$TARGET/${DB}_build.log"
: >"$LOG"
cd "$TARGET" || fail 2 "Create structure" 3
cp "$ST_FILE" "$TARGET/$DB.st" || fail 2 "Create structure" 3

LOAD_STATUS="$TARGET/${DB}_step6.status"
BI_EXPECT="biblocksize=$((BI_BLOCK_KB * 1024));biclustersize=$((BI_CLUSTER_MB * 1048576))"
VERIFY_STATUS="$TARGET/${DB}_step7.status"
rm -f "$LOAD_STATUS" "$VERIFY_STATUS"

# Large files are always on in OpenEdge 12.x (proutil -C enablelargefiles is retired, message 19352),
# so step 5 confirms the feature is active instead of trying to enable it.
confirm_large_files() {
    "$DLC/bin/proutil" "$DB" -C describe >"$TARGET/${DB}_describe.txt" 2>&1
    cat "$TARGET/${DB}_describe.txt"
    grep -Eq "Large Files[[:space:]]+Yes" "$TARGET/${DB}_describe.txt"
}

load_schema() {
    "$DLC/bin/_progres" -b -1 -db "$DB" -cpinternal UTF-8 -cpstream UTF-8 \
        -p "$LOAD_P" -param "$DF_FILE|$LOAD_STATUS" && status_is_ok "$LOAD_STATUS"
}

verify_database() {
    "$DLC/bin/_progres" -b -1 -db "$DB" -cpinternal UTF-8 -cpstream UTF-8 \
        -p "$VERIFY_P" -param "$EXPECT_FILE|$VERIFY_STATUS|$BI_EXPECT" && status_is_ok "$VERIFY_STATUS"
}

run_step 2 "Create structure"       3 "$DLC/bin/prostrct" create "$DB" "$DB.st" -blocksize 8192
run_step 3 "Copy UTF-8 metaschema"  3 "$DLC/bin/procopy" "$DLC/prolang/utf/empty8" "$DB"
run_step 4 "Configure before-image" 3 "$DLC/bin/proutil" "$DB" -C truncate bi -bi $((BI_CLUSTER_MB * 1024)) -biblocksize "$BI_BLOCK_KB"
run_step 5 "Confirm large files"    3 confirm_large_files
run_step 6 "Load schema"            3 load_schema
run_step 7 "Verify database"        4 verify_database

grep -E '^(CHECK|VERIFY)' "$LOG" | tail -n 20
echo "Database $TARGET/$DB.db built and verified."
exit 0
