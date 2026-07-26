# Dashboard Service CLI Specification

## Purpose

A bash CLI script (`scripts/dashboard.sh`) that manages the dashboard as a persistent background service with hot-reload dev mode. Wraps existing `scripts/run_dashboard.py` without modifying any `src/dashboard/` module.

## Requirements

### Requirement: Start production service

The system MUST launch the dashboard via `scripts/run_dashboard.py` as a detached background process, write its PID to `/tmp/dashboard.pid`, and confirm the process is alive before returning.

#### Scenario: Start fresh service

- GIVEN no dashboard process is running and no PID file exists at `/tmp/dashboard.pid`
- WHEN the user runs `scripts/dashboard.sh start`
- THEN the dashboard is launched as a background process via nohup
- AND the PID is written to `/tmp/dashboard.pid`
- AND the process is confirmed alive with `kill -0`

#### Scenario: Start when already running

- GIVEN a dashboard process is running and `/tmp/dashboard.pid` exists
- WHEN the user runs `scripts/dashboard.sh start`
- THEN the command exits with a non-zero status
- AND a message is printed indicating the service is already running

#### Scenario: Start on occupied port

- GIVEN port 3311 is already in use by another process
- WHEN the user runs `scripts/dashboard.sh start`
- THEN the command exits with a non-zero status
- AND a port conflict message is printed

### Requirement: Stop production service

The system MUST read the PID from `/tmp/dashboard.pid`, send SIGTERM to the process, wait for graceful termination, and remove the PID file.

#### Scenario: Stop running service

- GIVEN a dashboard process is running with PID stored in `/tmp/dashboard.pid`
- WHEN the user runs `scripts/dashboard.sh stop`
- THEN SIGTERM is sent to the recorded PID
- AND the process is terminated
- AND `/tmp/dashboard.pid` is removed

#### Scenario: Stop with stale PID file

- GIVEN `/tmp/dashboard.pid` exists but the recorded process is not running
- WHEN the user runs `scripts/dashboard.sh stop`
- THEN the stale PID file is removed
- AND a message is printed indicating no live process was found

### Requirement: Restart service

The system MUST stop the running service and start it again. If stop fails, start MUST NOT execute.

#### Scenario: Restart running service

- GIVEN a dashboard process is running
- WHEN the user runs `scripts/dashboard.sh restart`
- THEN the service is stopped
- AND the service is started again as a new background process
- AND the new PID is written to `/tmp/dashboard.pid`

### Requirement: Report service status

The system MUST check `/tmp/dashboard.pid`, validate the process is alive with `kill -0`, and report the PID and port.

#### Scenario: Status when running

- GIVEN a dashboard process is running with PID stored in `/tmp/dashboard.pid`
- WHEN the user runs `scripts/dashboard.sh status`
- THEN output shows the PID and port 3311
- AND the exit code is zero

#### Scenario: Status when not running

- GIVEN no PID file exists at `/tmp/dashboard.pid` (or the process is dead)
- WHEN the user runs `scripts/dashboard.sh status`
- THEN output indicates the service is not running
- AND the exit code is non-zero

### Requirement: Dev mode with hot-reload

The system MUST launch uvicorn in foreground with `--reload` enabled, watching `src/dashboard/templates/` and `src/dashboard/static/` for changes.

#### Scenario: Start dev mode

- GIVEN no dashboard process is running
- WHEN the user runs `scripts/dashboard.sh dev`
- THEN uvicorn starts in foreground with `--reload`
- AND no PID file is written
- AND the process exits when the user presses Ctrl+C

#### Scenario: Dev mode with live reload

- GIVEN `scripts/dashboard.sh dev` is running
- WHEN a file under `src/dashboard/templates/` or `src/dashboard/static/` is modified
- THEN uvicorn reloads the application automatically