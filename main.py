#!/usr/bin/env python3
"""
NTP Client Monitor -- entry point.

Usage:
    python main.py                     # run continuously using ./config.json
    python main.py --config myconf.json
    python main.py --once              # single check, then exit (good for cron/Task Scheduler)
    python main.py --verbose           # debug-level console logging
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ntp_client.config import load_config  # noqa: E402
from ntp_client.monitor import NtpMonitor  # noqa: E402

if getattr(sys, "frozen", False):
    DEFAULT_CONFIG_PATH = (
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "NTPClientMonitor", "config.json")
        if sys.platform == "win32" else "/etc/ntp-monitor/config.json"
    )
else:
    DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def setup_logging(verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main():
    parser = argparse.ArgumentParser(description="NTP Client Monitor (PRTG-style, XML logging)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config.json")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit without network or clock changes")
    parser.add_argument("--require-setup", action="store_true", help="Require completed first-run setup during validation")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("ntp_monitor")

    try:
        config = load_config(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to load config '%s': %s", args.config, e)
        sys.exit(1)

    if args.require_setup and not config["setup_complete"]:
        logger.error("Open NTP Client Monitor and choose Save and start to complete setup.")
        sys.exit(2)

    if args.check_config:
        logger.info("Configuration is valid: %s", args.config)
        return

    try:
        monitor = NtpMonitor(config)
    except (OSError, ValueError) as e:
        logger.error("Failed to initialize monitor: %s", e)
        sys.exit(1)

    if args.once:
        monitor.check_once()
    else:
        try:
            monitor.run_forever()
        except KeyboardInterrupt:
            logger.info("Stopped by user")


if __name__ == "__main__":
    main()
