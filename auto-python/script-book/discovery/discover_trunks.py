#!/usr/bin/env python3
"""
Discover trunk-mode interfaces on each device by pulling and parsing
"show running-config", then write the results into devices_trunks.py
as TRUNK_PORTS — so push_interface_config.py can use them directly,
with no manual editing required.
 
Assumes Cisco-style config: sections separated by "!" lines, interfaces
named like "interface Ethernet1/0/25", trunk ports containing a
"switchport mode trunk" line somewhere in their block.
 
Usage:
    python discover_trunks.py             # discover and overwrite devices_trunks.py
    python discover_trunks.py --dry-run   # just print what would be found
"""


import sys
import re
import os

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


def load_existing_trunk_ports():
    """Best-effort load of the current devices_trunks.py, used as a
    fallback for any device that fails to respond this run."""
    try:
        module = importlib.import_module("devices_trunks")
        importlib.reload(module)
        return dict(module.TRUNK_PORTS)
    except Exception:
        return {}
 
 
def find_trunk_ports(config_text):
    """Return a list of port identifiers (e.g. "1/0/25") for every
    interface whose block contains "switchport mode trunk"."""
    trunk_ports = []
    current_iface = None
 
    for line in config_text.splitlines():
        stripped = line.strip()
 
        iface_match = re.match(r"^interface\s+Ethernet(\S+)", stripped, re.IGNORECASE)
        if iface_match:
            current_iface = iface_match.group(1)
            continue
 
        if stripped == "!":
            current_iface = None
            continue
 
        if current_iface and "switchport mode trunk" in stripped.lower():
            if current_iface not in trunk_ports:
                trunk_ports.append(current_iface)
 
    return trunk_ports


def main():
    dry_run = "--dry-run" in sys.argv
    fallback = load_existing_trunk_ports()
    discovered = {}
 
    for device in DEVICES:
        name = device["name"]
        print(f"Checking {name} ({device['host']})...")
        try:
            config_text = get_running_config(device)
            ports = find_trunk_ports(config_text)
            discovered[name] = ports
            print(f"  Trunk ports found: {ports if ports else '(none)'}")
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
    print("DISCOVERED TRUNK PORTS")
    print("=" * 70)
    for name, ports in discovered.items():
        print(f"{name:<20} : {ports}")
 
    if dry_run:
        print("\n--dry-run set: devices_trunks.py NOT modified.")
        return
 
    write_devices_trunks(discovered)
    print(f"\n{OUTPUT_FILE} updated.")
 
 
if __name__ == "__main__":
    main()
