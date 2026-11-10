#!/usr/bin/env python3
"""
Common discovery functions.
Shared by:
    discover_interfaces.py
    discover_trunks.py
    discover_access.py
Handles:
    - SSH connection
    - running config retrieval
    - fallback loading
    - inventory writing
"""
import importlib
from pprint import pformat
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException


def get_running_config(device):
    conn_params = {k: v for k, v in device.items() if k != "name"}
    conn = ConnectHandler(**conn_params)
    try:
        # Disable paging first, or a long running-config hangs on "--More--"
        # waiting for a prompt that never comes. Worth confirming the right
        # command per platform if this hangs on a given switch.
        conn.send_command_timing(
            "terminal length 0", strip_prompt=False, strip_command=False,
            delay_factor=2,
        )

        output = conn.send_command_timing(
            "show running-config", strip_prompt=False, strip_command=False,
            delay_factor=4, max_loops=2000,
        )
        return output
    finally:
        # Always disconnect, even on failure — a leaked session can cause
        # the NEXT device's connection to get reset if there's a
        # session-count limit.
        try:
            conn.disconnect()
        except Exception:
            pass


def load_inventory(module_name, variable):
    """
    Load existing inventory.
    Used as fallback if a switch is unreachable.
    """
    try:
        module = importlib.import_module(module_name)
        importlib.reload(module)
        return getattr(module, variable)
    except Exception:
        return {}


def write_python_file(
        filename,
        header,
        variable,
        data
):
    """
    Write discovered inventory as a Python dictionary.
    """
    with open(filename, "w") as f:
        f.write('"""')
        f.write("\n")
        f.write(header)
        f.write("\n")
        f.write('"""\n\n')
        f.write(
            f"{variable} = {pformat(data, indent=4)}"
        )
        f.write("\n")
