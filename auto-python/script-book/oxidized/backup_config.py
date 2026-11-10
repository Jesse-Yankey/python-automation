#!/usr/bin/env python3
"""
Pull running configuration from all devices — sourced live from
LibreNMS's API — and save each one to a flat file on this server:
    backups/<name>.cfg

Each run overwrites the file — no history, no git, just "what does
this device look like right now." That current file is what
oxidized_api.py serves to LibreNMS.

Run status (success/failure/time/error) for every device is written
to backups/.status.json — oxidized_api.py reads this to answer
LibreNMS's /nodes.json and /node/show/<node> queries.

Usage:
    python backup_config.py
    python backup_config.py --switch 192.168.124.252
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from inventory import get_dynamic_inventory

BASE_DIR    = os.path.dirname(__file__)
BACKUP_DIR  = os.path.join(BASE_DIR, "backups")
STATUS_FILE = os.path.join(BACKUP_DIR, ".status.json")


def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE) as f:
            return json.load(f)
    return {}


def save_status(status):
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


def backup_device(device):
    name   = device["name"]
    host   = device["host"]
    params = {k: v for k, v in device.items() if k != "name"}

    result = {
        "name": name, "host": host,
        "status": None, "error": "",
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    try:
        conn = ConnectHandler(**params)

        conn.send_command_timing(
            "terminal length 0",
            strip_prompt=False,
            strip_command=False,
            delay_factor=2,
        )

        output = conn.send_command(
            "show running-config",
            expect_string=r"#",
            read_timeout=120,
            strip_prompt=False,
            strip_command=False,
        )

        conn.disconnect()

        if "hostname" not in output.lower() and "interface" not in output.lower():
            result["status"] = "failure"
            result["error"]  = "Output looks incomplete — no hostname/interface found"
            return result

        os.makedirs(BACKUP_DIR, exist_ok=True)
        filepath = os.path.join(BACKUP_DIR, f"{name}.cfg")
        with open(filepath, "w") as f:
            f.write(output)

        result["status"] = "success"

    except NetmikoAuthenticationException as e:
        result["status"] = "failure"
        result["error"]  = f"Authentication failed: {e}"
    except NetmikoTimeoutException as e:
        result["status"] = "failure"
        result["error"]  = f"Connection timeout: {e}"
    except Exception as e:
        result["status"] = "failure"
        result["error"]  = f"Unexpected error: {e}"

    return result


def print_result(result):
    print(f"\n=== {result['name']} ({result['host']}) ===")
    if result["status"] == "success":
        print(f"  ✅ Saved to backups/{result['name']}.cfg")
    else:
        print(f"  ❌ ERROR: {result['error']}")


def main():
    parser = argparse.ArgumentParser(description="Backup running-config from all devices")
    parser.add_argument("--switch", default=None, help="Backup a single switch by IP")
    args = parser.parse_args()

    os.makedirs(BACKUP_DIR, exist_ok=True)

    all_targets = get_dynamic_inventory()
    targets = all_targets
    if args.switch:
        targets = [d for d in all_targets if d["host"] == args.switch]
        if not targets:
            print(f"❌ No switch found with IP {args.switch}")
            print(f"   Available: {[d['host'] for d in all_targets]}")
            sys.exit(1)

    print(f"Backup started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Devices        : {len(targets)}")
    print(f"Saving to      : {BACKUP_DIR}/")
    print()

    status = load_status()
    results = []
    for d in targets:
        r = backup_device(d)
        results.append(r)
        status[r["name"]] = {
            "status": r["status"], "time": r["time"], "error": r["error"],
        }
        print_result(r)
    save_status(status)

    ok = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failure")
    print("\n" + "=" * 60)
    print(f"Total: {len(results)}  ✅ OK: {ok}  ❌ Failed: {failed}")


if __name__ == "__main__":
    main()
