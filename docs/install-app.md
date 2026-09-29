# Install and start NTP Client Monitor

These instructions are for end users and UAT testers. **No terminal commands,
Python installation, or build tools are needed.** Obtain a built installer from
your IT team; the repository ZIP is source code, not the installer.

## Windows

1. Download `ntp-monitor-1.1.0-windows-x64-setup.exe` from the release supplied by IT.
2. Double-click it and approve the Windows administrator prompt.
3. Follow the installation wizard. Leave **Open NTP Client Monitor to finish setup** selected.
4. In the welcome window, review the primary and fallback time servers and interval.
5. Leave **Adjust system clock** unchecked for monitoring-only UAT, or enable it
   when your test plan requires actual clock correction.
6. Choose **Save and start**. The window confirms that monitoring has started.
7. You may close the window. Monitoring continues in the background and starts at boot.

Reopen the application from the Start menu to change settings or view status.

## Linux desktop

1. Obtain the DEB for Ubuntu 22.04+ or RPM for RHEL-compatible 9, both x86-64.
2. Double-click the package, choose Install in your desktop's package installer,
   and authenticate when requested.
3. Open **NTP Client Monitor** from your application menu and authenticate.
4. Complete the welcome window and choose **Save and start**.

A graphical package installer, desktop session and authentication agent must be
available. Desktop distributions differ: IT must validate these on the UAT image.
Headless servers need managed deployment and do not have this desktop workflow.

## If something goes wrong

- A settings error stays in the window; correct the indicated field and try again.
- If previous settings cannot be read, the welcome window lets you repair them.
  Saving preserves the previous file as a backup.
- If the service does not start, open **XML & diagnostics → View diagnostic details**.
  Use **Copy details** and send the result to IT. No terminal is needed.
- If the background service is missing, rerun the installer with administrator
  permission, reopen the app, and choose **Save and start** again.
- Cancelling first-run setup leaves monitoring stopped. Reopening the app resumes setup.
- Closing an already-configured app leaves the service running. Use Stop to stop it.

## UAT acceptance

- Install from the provided package with no development tools installed.
- Confirm fresh installation does not poll or change the clock before setup.
- Cancel setup, reopen the app, then complete Save and start.
- Test invalid fields and confirm the error can be resolved in the window.
- Confirm status/XML updates, fallback, start/stop, and settings changes.
- Close the app and reboot; confirm background monitoring resumes after completed setup.
- Test repair of invalid settings, access failures, and Copy details for support.
- Upgrade with existing settings and verify preservation; uninstall and verify retention.

Windows installer generation and target-desktop acceptance are release-team tasks.
Do not distribute a repository ZIP to testers as an application installer.
