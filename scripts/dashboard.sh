#!/usr/bin/env bash
# scripts/dashboard.sh — Dashboard service lifecycle CLI
#
# Wraps scripts/run_dashboard.py for background process management
# and uvicorn dev mode with hot-reload.
#
# Usage:
#   ./scripts/dashboard.sh start|stop|restart|status|dev

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — resolved from script location
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
UVICORN="${PROJECT_ROOT}/.venv/bin/uvicorn"
PID_FILE="/tmp/dashboard.pid"
PORT="${DASHBOARD_PORT:-3311}"

export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") {start|stop|restart|status|dev}

Manage the dashboard service.

Commands:
  start     Launch dashboard as a detached background process
  stop      Stop the running dashboard process
  restart   Restart the dashboard process
  status    Check if the dashboard process is running
  dev       Start uvicorn in foreground with hot-reload
  help      Show this help message
EOF
}

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
is_pid_alive() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null
}

read_pid() {
    if [[ -f "$PID_FILE" ]]; then
        cat "$PID_FILE"
    fi
}

clean_stale_pid() {
    local pid
    pid="$(read_pid)"
    if [[ -n "$pid" ]] && ! is_pid_alive "$pid"; then
        rm -f "$PID_FILE"
        return 0
    fi
    return 1
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
start_cmd() {
    local pid
    pid="$(read_pid)"

    # Guard: already running
    if [[ -n "$pid" ]] && is_pid_alive "$pid"; then
        echo "Dashboard is already running with PID ${pid}." >&2
        exit 1
    fi

    # Clean stale PID if present
    clean_stale_pid || true

    # Check port availability via /dev/tcp (bash built-in)
    if { exec 7<>"/dev/tcp/127.0.0.1/${PORT}"; } 2>/dev/null; then
        exec 7>&-
        echo "ERROR: Port ${PORT} is already in use." >&2
        exit 1
    fi

    # Launch background process
    nohup "$VENV_PYTHON" "${PROJECT_ROOT}/scripts/run_dashboard.py" \
        > /dev/null 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    # Brief wait then confirm alive
    sleep 1
    if is_pid_alive "$new_pid"; then
        echo "Dashboard started (PID ${new_pid}, port ${PORT})."
    else
        echo "ERROR: Dashboard failed to start." >&2
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_cmd() {
    local pid
    pid="$(read_pid)"

    if [[ -z "$pid" ]]; then
        echo "No PID file found at ${PID_FILE}. Nothing to stop."
        return 0
    fi

    if ! is_pid_alive "$pid"; then
        echo "Warning: PID ${pid} is not running. Cleaning up stale PID file." >&2
        rm -f "$PID_FILE"
        return 0
    fi

    echo "Stopping dashboard (PID ${pid})..."
    kill "$pid" 2>/dev/null || true

    # Wait up to 5 seconds for graceful shutdown
    local waited=0
    while is_pid_alive "$pid" && [[ $waited -lt 5 ]]; do
        sleep 1
        waited=$((waited + 1))
    done

    if is_pid_alive "$pid"; then
        echo "Warning: Process did not exit after 5s, sending SIGKILL." >&2
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    echo "Dashboard stopped."
}

restart_cmd() {
    stop_cmd
    start_cmd
}

status_cmd() {
    local pid
    pid="$(read_pid)"

    if [[ -z "$pid" ]]; then
        echo "Dashboard is not running (no PID file found)."
        return 1
    fi

    if is_pid_alive "$pid"; then
        echo "Dashboard is running."
        echo "  PID:  ${pid}"
        echo "  Port: ${PORT}"
        return 0
    else
        echo "Dashboard is not running (PID ${pid} found but process is dead)."
        rm -f "$PID_FILE"
        return 1
    fi
}

dev_cmd() {
    # Foreground uvicorn with hot-reload — no PID file written
    "$UVICORN" \
        "src.dashboard.server:app" \
        --host "0.0.0.0" \
        --port "$PORT" \
        --reload \
        --reload-dir "${PROJECT_ROOT}/src/dashboard/templates" \
        --reload-dir "${PROJECT_ROOT}/src/dashboard/static"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
main() {
    if [[ $# -ne 1 ]]; then
        usage
        exit 1
    fi

    case "${1}" in
        start)   start_cmd ;;
        stop)    stop_cmd ;;
        restart) restart_cmd ;;
        status)  status_cmd ;;
        dev)     dev_cmd ;;
        help)    usage ;;
        *)
            echo "Unknown command: ${1}" >&2
            usage
            exit 1
            ;;
    esac
}

main "$@"