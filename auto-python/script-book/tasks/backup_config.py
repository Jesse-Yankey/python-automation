#!/usr/bin/env python3
"""
Pull and save running configuration from all devices in devices.py.

Backups are saved to the ./backups/ folder on this server, one file
per device per run, timestamped so nothing gets overwritten.

Usage:
    python backup_config.py
"""

import os
from datetime import datetime

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from devices import DEVICES

# Folder where backup files will be saved (relative to this script)
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")


def backup_device(device):
    """SSH into a device, capture show running-config, save to file."""
    name = device["name"]
    host = device["host"]
    conn_params = {k: v for k, v in device.items() if k != "name"}

    result = {"name": name, "host": host, "status": None, "file": "", "error": ""}

    try:
        conn = ConnectHandler(**conn_params)

        # Capture the full running config
        output = conn.send_command_timing(
            "show running-config",
            strip_prompt=False,
            strip_command=False,
            delay_factor=4,   # give the switch time to dump the full config
            max_loops=1000,
        )

        conn.disconnect()

        # Save to backups/<DEVICE-NAME>_<YYYY-MM-DD_HHMMSS>.cfg
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"{name}_{timestamp}.cfg"
        filepath = os.path.join(BACKUP_DIR, filename)

        with open(filepath, "w") as f:
            f.write(output)

        result["status"] = "SUCCESSFUL"
        result["file"] = filepath

    except NetmikoAuthenticationException as e:
        result["status"] = "FAILED"
        result["error"] = f"Authentication failed: {e}"
    except NetmikoTimeoutException as e:
        result["status"] = "FAILED"
        result["error"] = f"Connection timeout: {e}"
    except Exception as e:
        result["status"] = "FAILED"
        result["error"] = f"Unexpected error: {e}"

    return result


def print_result(result):
    print(f"\n=== {result['name']} ({result['host']}) ===")
    if result["status"] == "SUCCESSFUL":
        print(f"Saved to: {result['file']}")
    else:
        print(f"ERROR: {result['error']}")
    print(f"--- {result['name']}: {result['status']} ---")


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Backup started : {timestamp}")
    print(f"Devices        : {len(DEVICES)}")
    print(f"Saving to      : {BACKUP_DIR}/")

    results = [backup_device(device) for device in DEVICES]

    for result in results:
        print_result(result)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok     = sum(1 for r in results if r["status"] == "SUCCESSFUL")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    for r in results:
        line = f"{r['name']:<20} : {r['status']}"
        if r["status"] == "SUCCESSFUL":
            line += f"  →  {r['file']}"
        print(line)
    print(f"\nTotal: {len(results)}  Successful: {ok}  Failed: {failed}")


if __name__ == "__main__":
    main()
