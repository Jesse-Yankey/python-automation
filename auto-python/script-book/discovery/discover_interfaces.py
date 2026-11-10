#!/usr/bin/env python3
"""
Discover:
    - VLAN interfaces
    - management IP addresses
    - interface mode

Creates:
inventory/devices_interfaces.py
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
    "devices_interfaces.py"
)


def parse_interfaces(config):
    interfaces={}
    current=None

    for line in config.splitlines():
        line=line.strip()

        match=re.match(
            r"interface\s+(Ethernet\S+|Vlan\d+)",
            line,
            re.I
        )

        if match:
            current=match.group(1)
            interfaces[current]={}
            continue

        if current:
            if "switchport mode trunk" in line:
                interfaces[current]["mode"]="trunk"
            elif "switchport mode access" in line:
                interfaces[current]["mode"]="access"
            vlan=re.search(
                r"switchport access vlan (\d+)",
                line
            )
            if vlan:
                interfaces[current]["vlan"]=int(
                    vlan.group(1)
                )
            ip=re.search(
                r"ip address (\d+\.\d+\.\d+\.\d+)",
                line
            )
            if ip:
                interfaces[current]["ip"]=ip.group(1)
    return interfaces


def main():
    dry_run = "--dry-run" in sys.argv

    inventory={}
    old=load_inventory(
        "inventory.devices_interfaces",
        "DEVICE_INTERFACES"
    )

    for device in DEVICES:
        name=device["name"]
        print(
            f"Checking {name}"
        )

        try:
            config=get_running_config(device)
            interfaces=parse_interfaces(config)
            management=None

            for iface,data in interfaces.items():
                if iface.lower()=="vlan1":
                    management=data.get(
                        "ip"
                    )
            inventory[name]={
                "management_ip":management,
                "interfaces":interfaces
            }
            print(
                " Management:",
                management
            )

        except Exception as e:
            print(
                "ERROR:",
                e
            )
            inventory[name]=old.get(
                name,
                {}
            )

    print("\n" + "=" * 70)
    print("DISCOVERED INTERFACES")
    print("=" * 70)
    for name, data in inventory.items():
        print(f"{name}: management_ip={data.get('management_ip')}, "
              f"{len(data.get('interfaces', {}))} interfaces")

    if dry_run:
        print("\n--dry-run set: devices_interfaces.py NOT modified.")
        return

    write_python_file(
        OUTPUT_FILE,
        "Device interface inventory generated automatically",
        "DEVICE_INTERFACES",
        inventory
    )
    print(
        "devices_interfaces.py updated"
    )


if __name__=="__main__":
    main()
