#!/usr/bin/env bash
# Binary-dump a ParkBenchDB database so it can be loaded on another OS with db/load_db.*.
#
#   usage: db/dump_db.sh <db-path> <dump-dir> [--allow-active]
#
# The source is only read. It may be served (the dump connects to the server) or offline.
# <dump-dir> must be new or empty. It receives <table>.bd for every table (LOBs included),
# schema.df, manifest.txt (tables, row counts, sequence values) and dump.log.
# The binary dump format is platform-independent: copy the directory to the other host as-is.
#
# Steps: 1 Check prerequisites   2 Dump schema and sequences   3 Dump tables   4 Summary
# Exit codes: 0 dumped; 2 prerequisite missing or refused (nothing written); 3 a step failed.
# Keep in step with db/dump_db.bat: same steps, names, options, output and exit codes.

set -u

STEPS=4
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMPLOAD_P="$SCRIPT_DIR/abl/dumpload.p"

usage() {
    echo "usage: dump_db.sh <db-path> <dump-dir> [--allow-active]"
    echo "  Binary-dumps every table of <db-path> (served or offline) into <dump-dir> (new or empty)."
    echo "  --allow-active  dump even while pbgen workers hold claimed units (the dump may be inconsistent)"
    echo "  DLC must point at the OpenEdge 12.8 installation."
}

ALLOW_ACTIVE=0
POSITIONAL=()
while [ $# -gt 0 ]; do
    case "$1" in
        --allow-active) ALLOW_ACTIVE=1; shift ;;
        -*)             usage; exit 2 ;;
        *)              POSITIONAL+=("$1"); shift ;;
    esac
done
if [ ${#POSITIONAL[@]} -ne 2 ]; then
    usage
    exit 2
fi
DB="${POSITIONAL[0]%.db}"
OUT="${POSITIONAL[1]}"
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

# ---------------------------------------------------------------- 1. prerequisites (nothing written)
printf '[1/%d] Check prerequisites ... ' "$STEPS"
[ -n "${DLC:-}" ] || prereq_fail "DLC is not set; point it at an OpenEdge 12.8 installation"
[ -f "$DLC/version" ] || prereq_fail "$DLC/version not found; DLC does not look like an OpenEdge installation"
grep -q "12\.8" "$DLC/version" || prereq_fail "OpenEdge 12.8 is required; $DLC/version says: $(head -n 1 "$DLC/version")"
for tool in proutil _progres; do
    [ -x "$DLC/bin/$tool" ] || prereq_fail "$DLC/bin/$tool not found or not executable"
done
[ -f "$DUMPLOAD_P" ] || prereq_fail "$DUMPLOAD_P not found; restore the repository files"
[ -f "$DB.db" ] || prereq_fail "database $DB.db not found"
if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
    prereq_fail "dump directory $OUT is not empty; choose a new or empty directory"
fi
DB="$(cd "$(dirname "$DB")" && pwd)/$(basename "$DB")"
"$DLC/bin/proutil" "$DB" -C holder >/dev/null 2>&1
case $? in
    16) CONNECT=(); MODE="served" ;;
    0)  CONNECT=(-1); MODE="offline" ;;
    *)  prereq_fail "database $DB is open single-user (or its state is unknown); close that session first" ;;
esac
echo "ok ($MODE)"

# ---------------------------------------------------------------- 2-4. dump
mkdir -p "$OUT" || fail 2 "Dump schema and sequences" 3
OUT="$(cd "$OUT" && pwd)"
LOG="$OUT/dump.log"
: >"$LOG"
MANIFEST="$OUT/manifest.txt"

printf '[2/%d] Dump schema and sequences ... ' "$STEPS"
echo "==== [2/$STEPS] Dump schema and sequences" >>"$LOG"
"$DLC/bin/_progres" -b "${CONNECT[@]}" -db "$DB" -cpinternal UTF-8 -cpstream UTF-8 \
    -p "$DUMPLOAD_P" -param "dump|$OUT" >>"$LOG" 2>&1
if ! grep -q "^format=parkbench-dump-1" "$MANIFEST" 2>/dev/null || [ ! -s "$OUT/schema.df" ]; then
    echo "FAILED"
    fail 2 "Dump schema and sequences" 3
fi
ACTIVE="$(sed -n 's/^activeClaims=//p' "$MANIFEST" | tr -d '\r')"
if [ "${ACTIVE:-0}" != "0" ] && [ "$ALLOW_ACTIVE" = "0" ]; then
    echo "FAILED"
    rm -f "$MANIFEST" "$OUT/schema.df"
    echo "FAILED at step 2 (Dump schema and sequences): $ACTIVE pbgen unit(s) are claimed, so workers are still"
    echo "writing. Stop them (Ctrl+C on pbgen run) and dump again, or pass --allow-active."
    exit 2
fi
echo "ok"

printf '[3/%d] Dump tables ... ' "$STEPS"
echo "==== [3/$STEPS] Dump tables" >>"$LOG"
TABLES=$(sed -n 's/^table=//p' "$MANIFEST" | tr -d '\r')
TOTAL=0
N=0
for t in $TABLES; do
    OUTPUT="$("$DLC/bin/proutil" "$DB" -C dump "$t" "$OUT" 2>&1)"
    rc=$?
    echo "$OUTPUT" >>"$LOG"
    rows="$(echo "$OUTPUT" | sed -n 's/.*Dumped \([0-9][0-9]*\) records.*/\1/p' | head -n 1)"
    if [ $rc -ne 0 ] || [ -z "$rows" ] || [ ! -f "$OUT/$t.bd" ]; then
        echo "FAILED"
        echo "table $t: proutil dump did not complete" >>"$LOG"
        fail 3 "Dump tables" 3
    fi
    echo "rows=$t=$rows" >>"$MANIFEST"
    TOTAL=$((TOTAL + rows))
    N=$((N + 1))
done
echo "ok"

printf '[4/%d] Summary ... ok\n' "$STEPS"
BYTES=$(du -sk "$OUT" | cut -f1)
echo "Dumped $N tables, $TOTAL rows ($((BYTES / 1024)) MB) from $DB into $OUT."
echo "Copy the directory to the target host, then run db/load_db.sh <dump-dir> <target-dir> there."
exit 0
