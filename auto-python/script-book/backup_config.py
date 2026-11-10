#!/usr/bin/env python3
"""
Pull and save running configuration from all devices in devices.py.

Backups are saved to ./backups/<group>/ on this server — one subfolder
per device group (e.g. backups/switchback/, backups/captainhooks/),
one file per device per run, timestamped so nothing gets overwritten.

Usage:
    python backup_config.py
    python backup_config.py --switch 192.168.124.252
    python backup_config.py --group switchback
"""
import os
import sys
import argparse

from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
from devices import DEVICES, GROUPS

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")


def backup_device(device):
    name  = device["name"]
    host  = device["host"]
    group = device.get("group", "ungrouped")

    # Strip out keys that aren't valid ConnectHandler params
    params = {k: v for k, v in device.items() if k not in ("name", "group")}

    result = {"name": name, "host": host, "group": group,
              "status": None, "file": "", "error": ""}

    try:
        conn = ConnectHandler(**params)

        # ── Disable pagination FIRST so --More-- never appears ──────────
        # PLANET switches use the same command as Cisco
        conn.send_command_timing(
            "terminal length 0",
            strip_prompt=False,
            strip_command=False,
            delay_factor=2,
        )

        # ── Pull the full running config ─────────────────────────────────
        output = conn.send_command(
            "show running-config",
            expect_string=r"#",       # wait for the prompt to return
            read_timeout=120,         # large configs can take a while
            strip_prompt=False,
            strip_command=False,
        )

        conn.disconnect()

        # ── Sanity check — make sure we got a real config ────────────────
        if "hostname" not in output.lower() and "interface" not in output.lower():
            result["status"] = "FAILED"
            result["error"]  = "Output looks incomplete — no hostname/interface found"
            return result

        # ── Save to file, under backups/<group>/ ──────────────────────────
        group_dir = os.path.join(BACKUP_DIR, group)
        os.makedirs(group_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename  = f"{name}_{timestamp}.cfg"
        filepath  = os.path.join(group_dir, filename)

        with open(filepath, "w") as f:
            # Write a header so you know when/where this came from
            f.write(f"! Backup of {name} ({host})\n")
            f.write(f"! Group    : {group}\n")
            f.write(f"! Captured : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"! {'='*55}\n")
            f.write(output)

        result["status"] = "SUCCESSFUL"
        result["file"]   = filepath

    except NetmikoAuthenticationException as e:
        result["status"] = "FAILED"
        result["error"]  = f"Authentication failed: {e}"
    except NetmikoTimeoutException as e:
        result["status"] = "FAILED"
        result["error"]  = f"Connection timeout: {e}"
    except Exception as e:
        result["status"] = "FAILED"
        result["error"]  = f"Unexpected error: {e}"

    return result


def print_result(result):
    print(f"\n=== {result['name']} ({result['host']}) [{result['group']}] ===")
    if result["status"] == "SUCCESSFUL":
        print(f"  ✅ Saved to : {result['file']}")
    else:
        print(f"  ❌ ERROR    : {result['error']}")
    print(f"--- {result['name']}: {result['status']} ---")


def main():
    parser = argparse.ArgumentParser(
        description="Backup running-config from all network switches, grouped by site"
    )
    parser.add_argument(
        "--switch", default=None,
        help="Backup a single switch by IP (e.g. --switch 192.168.124.252)"
    )
    parser.add_argument(
        "--group", default=None,
        help=f"Backup only devices in one group. Available: {list(GROUPS.keys())}"
    )
    args = parser.parse_args()

    targets = DEVICES

    if args.group:
        if args.group not in GROUPS:
            print(f"❌ Unknown group '{args.group}'")
            print(f"   Available: {list(GROUPS.keys())}")
            sys.exit(1)
        targets = [d for d in targets if d["group"] == args.group]

    if args.switch:
        targets = [d for d in targets if d["host"] == args.switch]
        if not targets:
            print(f"❌ No switch found with IP {args.switch}")
            print(f"   Available: {[d['host'] for d in DEVICES]}")
            sys.exit(1)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Backup started : {timestamp}")
    print(f"Devices        : {len(targets)}")
    print(f"Saving to      : {BACKUP_DIR}/<group>/")
    print()

    results = [backup_device(d) for d in targets]

    for result in results:
        print_result(result)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok     = sum(1 for r in results if r["status"] == "SUCCESSFUL")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    for r in results:
        icon = "✅" if r["status"] == "SUCCESSFUL" else "❌"
        line = f"  {icon} {r['name']:<20} [{r['group']:<12}] : {r['status']}"
        if r["status"] == "SUCCESSFUL":
            line += f"  →  {r['file']}"
        else:
            line += f"  —  {r['error']}"
        print(line)
    print(f"\n  Total: {len(results)}  ✅ {ok}  ❌ {failed}")


if __name__ == "__main__":
    main()
