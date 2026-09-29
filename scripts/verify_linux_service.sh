#!/bin/bash
# Destructive acceptance test: disposable VM only, not a production endpoint.
set -euo pipefail
package=$(realpath "$1")
if [ "$(id -u)" != 0 ]; then echo 'Run as root on a disposable VM' >&2; exit 1; fi
if [ -e /etc/ntp-monitor/config.json ]; then echo 'Expected a fresh VM' >&2; exit 1; fi
install_package() {
    case "$package" in
        *.deb) dpkg -i "$package" ;;
        *.rpm) rpm -Uvh --replacepkgs "$package" ;;
        *) exit 1 ;;
    esac
}
install_package
if systemctl is-active --quiet ntp-monitor; then echo 'Fresh install started before setup' >&2; exit 1; fi
if systemctl is-enabled --quiet ntp-monitor; then echo 'Fresh install enabled before setup' >&2; exit 1; fi
systemctl stop ntp-monitor
cat > /etc/ntp-monitor/config.json <<'EOF'
{"primary_server":"127.0.0.1","timeout_seconds":0.1,"log_directory":"/var/log/ntp-monitor","sync_system_clock":false,"workstation_name":"package-test"}
EOF
chmod 0640 /etc/ntp-monitor/config.json
systemctl enable --now ntp-monitor
systemctl is-enabled ntp-monitor
systemctl is-active ntp-monitor
for attempt in $(seq 1 30); do
    test -f /var/log/ntp-monitor/package-test_ntpstatus.xml && break
    sleep 1
done
test -f /var/log/ntp-monitor/package-test_ntpstatus.xml
old_pid=$(systemctl show -p MainPID --value ntp-monitor)
kill -KILL "$old_pid"
sleep 15
systemctl is-active ntp-monitor
new_pid=$(systemctl show -p MainPID --value ntp-monitor)
test "$new_pid" != "$old_pid"
test "$new_pid" != 0
before=$(sha256sum /etc/ntp-monitor/config.json)
install_package
test "$before" = "$(sha256sum /etc/ntp-monitor/config.json)"
systemctl is-active ntp-monitor
case "$package" in
    *.deb) dpkg -r ntp-monitor ;;
    *.rpm) rpm -e ntp-monitor ;;
esac
test ! -e /opt/ntp-monitor/ntp-monitor
test -f /var/log/ntp-monitor/package-test_ntplog.xml
echo 'Install, startup, crash recovery, reinstall preservation and uninstall verified'
