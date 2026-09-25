#!/bin/sh
# Disposable display test. No service actions or clock changes are performed.
set -eu
if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
    echo 'Expected a target without system Python' >&2
    exit 1
fi
task_tmp=$(mktemp -d)
Xvfb :97 -screen 0 1024x768x24 -ac -nolisten tcp > "$task_tmp/display.log" 2>&1 &
display_pid=$!
trap 'kill "$display_pid" 2>/dev/null || true; rm -rf "$task_tmp"' EXIT
sleep 1
kill -0 "$display_pid"
cat > "$task_tmp/config.json" <<EOF
{"primary_server":"127.0.0.1","log_directory":"$task_tmp/logs","sync_system_clock":false}
EOF
set +e
DISPLAY=:97 timeout 5 /opt/ntp-monitor/gui/ntp-monitor-gui --config "$task_tmp/config.json" > "$task_tmp/gui.log" 2>&1
result=$?
set -e
cat "$task_tmp/gui.log"
test "$result" = 124
if grep -q 'Traceback' "$task_tmp/gui.log"; then exit 1; fi
echo 'Bundled desktop remained running on a display without system Python'
