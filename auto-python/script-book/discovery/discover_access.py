#!/usr/bin/env python3
"""
Discover access-mode interfaces on each device by pulling and parsing
"show running-config", then write the results into devices_access.py
as ACCESS_PORTS — mirrors discover_trunks.py / devices_trunks.py, kept
as a separate file/dict so trunk and access port lists don't collide.
 
Assumes Cisco-style config: sections separated by "!" lines, interfaces
named like "interface Ethernet1/0/25", access ports containing a
"switchport mode access" line somewhere in their block.
 
Usage:
    python discover_access.py             # discover and overwrite devices_access.py
    python discover_access.py --dry-run   # just print what would be found
"""

import sys
import os
import re
import importlib

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

from devices import DEVICES

from discovery.common import (
    get_running_config,
    load_inventory,
    write_python_file
)


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

OUTPUT_FILE = os.path.join(
    BASE_DIR,
    "inventory",
    "devices_access.py"
)


def load_existing_access_ports():
    """Best-effort load of the current devices_access.py, used as a
    fallback for any device that fails to respond this run."""
    try:
        module = importlib.import_module("devices_access")
        importlib.reload(module)
        return dict(module.ACCESS_PORTS)
    except Exception:
        return {}


def find_access_ports(config_text):
    """Return a list of port identifiers (e.g. "1/0/5") for every
    interface that's in access mode.
 
    Access mode is the default on most platforms, so "switchport mode
    access" is frequently left out of running-config entirely — the
    reliable signal is usually just "switchport access vlan <N>" on its
    own. We treat either line as qualifying, and explicitly exclude any
    interface that also shows "switchport mode trunk" so a misordered
    or leftover trunk line can't get double-classified.
    """
    interfaces = {}   # port -> list of config lines in its block
    current_iface = None
 
    for line in config_text.splitlines():
        stripped = line.strip()
 
        iface_match = re.match(r"^interface\s+Ethernet(\S+)", stripped, re.IGNORECASE)
        if iface_match:
            current_iface = iface_match.group(1)
            interfaces.setdefault(current_iface, [])
            continue
 
        if stripped == "!":
            current_iface = None
            continue
 
        if current_iface is not None:
            interfaces[current_iface].append(stripped.lower())
 
    access_ports = []
    for port, lines in interfaces.items():
        is_trunk = any("switchport mode trunk" in l for l in lines)
        if is_trunk:
            continue
        is_access = any(
            "switchport mode access" in l or "switchport access vlan" in l
            for l in lines
        )
        if is_access:
            access_ports.append(port)
 
    return access_ports


def main():
    dry_run = "--dry-run" in sys.argv
    fallback = load_existing_access_ports()
    discovered = {}
 
    for device in DEVICES:
        name = device["name"]
        print(f"Checking {name} ({device['host']})...")
        try:
            config_text = get_running_config(device)
            ports = find_access_ports(config_text)
            discovered[name] = ports
            print(f"  Access ports found: {ports if ports else '(none)'}")
        except NetmikoAuthenticationException as e:
            print(f"  ERROR: authentication failed: {e}")
            discovered[name] = fallback.get(name, [])
            print(f"  Keeping previous entry: {discovered[name]}")
        except NetmikoTimeoutException as e:
            print(f"  ERROR: connection timeout: {e}")
            discovered[name] = fallback.get(name, [])
            print(f"  Keeping previous entry: {discovered[name]}")
        except Exception as e:
            print(f"  ERROR: {e}")
            discovered[name] = fallback.get(name, [])
            print(f"  Keeping previous entry: {discovered[name]}")
 
    print("\n" + "=" * 70)
    print("DISCOVERED ACCESS PORTS")
    print("=" * 70)
    for name, ports in discovered.items():
        print(f"{name:<20} : {ports}")
 
    if dry_run:
        print("\n--dry-run set: devices_access.py NOT modified.")
        return
 
    write_devices_access(discovered)
    print(f"\n{OUTPUT_FILE} updated.")
 
 
if __name__ == "__main__":
    main()
