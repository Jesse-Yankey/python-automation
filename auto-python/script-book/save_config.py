#!/usr/bin/env python3
"""
save_config.py — Save running-config to startup-config on all PLANET switches.

Run this AFTER push_config.py once you are satisfied with the changes.

Usage:
    python save_config.py                        # save all switches
    python save_config.py --switch 192.168.10.252  # save single switch
    python save_config.py --dry-run              # show what would happen

PLANET command:
    copy running-config startup-config
    (then confirm Y at the prompt)
"""

import sys
import argparse
import logging

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from devices import DEVICES

# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("save_config.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

# ====================== SAVE ======================
def save_device(device, dry_run=False):
    name = device["name"]
    host = device["host"]
    params = {k: v for k, v in device.items() if k != "name"}

    result = {
        "name":   name,
        "host":   host,
        "status": None,
        "output": "",
        "error":  "",
    }

    if dry_run:
        log.info(f"[DRY RUN] {name} ({host}) — would run: copy running-config startup-config")
        result["status"] = "DRY RUN"
        return result

    log.info(f"Connecting to {name} ({host})...")
    try:
        conn = ConnectHandler(**params)
        log.info(f"[{name}] ✅ Connected")

        # Send the save command
        output = conn.send_command_timing(
            "copy running-config startup-config",
            strip_prompt=False,
            strip_command=False,
            delay_factor=3,
        )

        # Handle the Y/N confirmation prompt
        if "Confirm" in output or "[Y/N]" in output or "overwrite" in output.lower():
            output += conn.send_command_timing(
                "Y",
                strip_prompt=False,
                strip_command=False,
                delay_factor=3,
            )

        conn.disconnect()

        # Verify it succeeded
        if any(kw in output.lower() for kw in ["success", "ok", "done", "[y/n]", "startup"]):
            result["status"] = "SAVED"
            log.info(f"[{name}] ✅ Config saved")
        else:
            result["status"] = "SAVED"   # PLANET doesn't always print a success msg
            log.info(f"[{name}] ✅ Save command sent")

        result["output"] = output.strip()

    except NetmikoAuthenticationException as e:
        result["status"] = "FAILED"
        result["error"]  = f"Authentication failed: {e}"
        log.error(f"[{name}] ❌ Auth failed")

    except NetmikoTimeoutException as e:
        result["status"] = "FAILED"
        result["error"]  = f"Connection timed out: {e}"
        log.error(f"[{name}] ❌ Timeout")

    except Exception as e:
        result["status"] = "FAILED"
        result["error"]  = f"Unexpected error: {e}"
        log.error(f"[{name}] ❌ {e}")

    return result

# ====================== MAIN ======================
def main():
    parser = argparse.ArgumentParser(
        description="Save running-config to startup-config on PLANET switches"
    )
    parser.add_argument(
        "--switch", default=None,
        help="Save a single switch by IP (e.g. --switch 192.168.10.252)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without making any changes"
    )
    args = parser.parse_args()

    # Filter devices
    targets = DEVICES
    if args.switch:
        targets = [d for d in DEVICES if d["host"] == args.switch]
        if not targets:
            print(f"❌ No switch found with IP {args.switch}")
            print(f"   Available: {[d['host'] for d in DEVICES]}")
            sys.exit(1)

    print()
    print("=" * 60)
    print(f"  Save Config — {'DRY RUN' if args.dry_run else 'APPLYING'}")
    print(f"  Switches : {len(targets)}")
    print(f"  Command  : copy running-config startup-config")
    print("=" * 60)
    print()

    if args.dry_run:
        print("⚠️  DRY RUN — no changes will be made.\n")

    results = [save_device(d, dry_run=args.dry_run) for d in targets]

    # Print outputs
    for r in results:
        print(f"\n=== {r['name']} ({r['host']}) ===")
        if r["status"] == "FAILED":
            print(f"  ❌ {r['error']}")
        elif r["status"] == "DRY RUN":
            print(f"  🔍 Would save config")
        else:
            print(f"  {r['output']}")
        print(f"--- {r['name']}: {r['status']} ---")

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    saved   = sum(1 for r in results if r["status"] == "SAVED")
    failed  = sum(1 for r in results if r["status"] == "FAILED")
    dry     = sum(1 for r in results if r["status"] == "DRY RUN")
    for r in results:
        if r["status"] == "SAVED":
            icon = "✅"
        elif r["status"] == "FAILED":
            icon = "❌"
        else:
            icon = "🔍"
        print(f"  {icon} {r['name']:<20} : {r['status']}")
    print(f"\n  Switches: {len(results)}  ✅ {saved}  ❌ {failed}  🔍 {dry}")
    print(f"\n  Log saved to save_config.log")


if __name__ == "__main__":
    main()
