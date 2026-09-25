#!/bin/sh
# Run inside a disposable target after package installation; no systemd required.
set -eu
if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
    echo 'Expected a clean target without a system Python interpreter' >&2
    exit 1
fi
task_tmp=$(mktemp -d)
trap 'rm -rf "$task_tmp"' EXIT
cat > "$task_tmp/config.json" <<EOF
{"primary_server":"127.0.0.1","timeout_seconds":0.1,"log_directory":"$task_tmp/logs","sync_system_clock":false,"workstation_name":"package-test"}
EOF
/opt/ntp-monitor/ntp-monitor --config "$task_tmp/config.json" --check-config
/opt/ntp-monitor/ntp-monitor --config "$task_tmp/config.json" --once
test -f "$task_tmp/logs/package-test_ntpstatus.xml"
grep -q 'no_usable_server' "$task_tmp/logs/package-test_ntpstatus.xml"
grep -q 'AllServersUnreachable' "$task_tmp/logs/package-test_ntplog.xml"
echo 'Bundled runtime and XML verified without system Python'
