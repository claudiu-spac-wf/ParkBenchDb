#!/usr/bin/env bash
# Start, stop or query the ParkBenchDB database server with bulk-load-friendly settings.
#
#   usage: db/server.sh start  <db-path> [--port N] [--workers N] [--buffers N] [--apws N] [--lock-table N]
#          db/server.sh stop   <db-path>
#          db/server.sh status <db-path>
#
# start: proserve + 1 before-image writer + N page writers; waits for "connections enabled".
# Exit codes: 0 ok / running; 2 bad arguments or already running; 3 not running; 4 start timed out.
# Keep in step with db/server.bat. See docs/data-generation.md for the settings.

set -u

usage() {
    echo "usage: server.sh start <db-path> [--port N] [--workers N] [--buffers N] [--apws N] [--lock-table N]"
    echo "       server.sh stop <db-path>"
    echo "       server.sh status <db-path>"
    exit 2
}

[ $# -ge 2 ] || usage
CMD="$1"; DB="${2%.db}"; shift 2
PORT=20931; WORKERS=8; BUFFERS=200000; APWS=2; LOCKTABLE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="${2:-}"; shift 2 ;;
        --workers) WORKERS="${2:-}"; shift 2 ;;
        --buffers) BUFFERS="${2:-}"; shift 2 ;;
        --apws) APWS="${2:-}"; shift 2 ;;
        --lock-table) LOCKTABLE="${2:-}"; shift 2 ;;
        *) echo "unknown option: $1"; usage ;;
    esac
done
for v in "$PORT" "$WORKERS" "$BUFFERS" "$APWS" ${LOCKTABLE:+"$LOCKTABLE"}; do
    [[ "$v" =~ ^[0-9]+$ ]] || { echo "option values must be whole numbers (got '$v')"; exit 2; }
done
[ -n "${DLC:-}" ] || { echo "DLC is not set; point it at the OpenEdge 12.8 installation"; exit 2; }
[ -f "$DB.db" ] || { echo "database $DB.db not found"; exit 2; }
[ -n "$LOCKTABLE" ] || LOCKTABLE=$(( WORKERS * 40000 > 100000 ? WORKERS * 40000 : 100000 ))

is_running() {  # proutil -C holder exits 16 when the database is served
    "$DLC/bin/proutil" "$DB" -C holder >/dev/null 2>&1
    [ $? -eq 16 ]
}

case "$CMD" in
    start)
        if is_running; then echo "database $DB is already running"; exit 2; fi
        MN=$(( 4 + (WORKERS + 3) / 4 ))
        MARK=$(wc -l < "$DB.lg" 2>/dev/null || echo 0)
        echo "starting $DB: -S $PORT -n $((WORKERS + 10)) -Mn $MN -L $LOCKTABLE -B $BUFFERS, 1 BIW, $APWS APW(s)"
        setsid "$DLC/bin/proserve" "$DB" -S "$PORT" -n $((WORKERS + 10)) -Mn "$MN" -L "$LOCKTABLE" \
            -B "$BUFFERS" -bibufs 64 -spin 20000 >/dev/null 2>&1 < /dev/null &
        for _ in $(seq 1 120); do
            tail -n +"$((MARK + 1))" "$DB.lg" 2>/dev/null | grep -q "(10471)" && break
            sleep 0.5
        done
        if ! tail -n +"$((MARK + 1))" "$DB.lg" 2>/dev/null | grep -q "(10471)"; then
            echo "server did not report 'Database connections have been enabled' within 60s; see $DB.lg"
            exit 4
        fi
        setsid "$DLC/bin/probiw" "$DB" >/dev/null 2>&1 < /dev/null &
        for _ in $(seq 1 "$APWS"); do
            setsid "$DLC/bin/proapw" "$DB" >/dev/null 2>&1 < /dev/null &
        done
        echo "running on port $PORT, -L $LOCKTABLE"
        exit 0 ;;
    stop)
        if ! is_running; then echo "stopped"; exit 3; fi
        "$DLC/bin/proshut" "$DB" -by
        exit $? ;;
    status)
        if is_running; then echo "running"; exit 0; fi
        echo "stopped"; exit 3 ;;
    *) usage ;;
esac
