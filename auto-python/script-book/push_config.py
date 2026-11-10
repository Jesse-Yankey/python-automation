#!/usr/bin/env python3
"""
Push configuration tasks to network devices over SSH using Netmiko.

    devices.py                      -> inventory (which devices, how to connect)
    inventory/devices_trunks.py     -> trunk port map (discover_trunks.py)
    inventory/devices_interfaces.py -> per-device interface + management data
                                        (discover_interfaces.py)
    tasks/*.py                      -> one file per config goal. Each task can
                                        define:
                                          DESCRIPTION, VERSION, AUTHOR
                                                              - metadata, all optional
                                          DEFAULTS            - variables available
                                                                to {placeholder}
                                                                substitution
                                          REQUIRED_VARIABLES  - names that must
                                                                resolve to a real
                                                                value per-device or
                                                                that device is
                                                                skipped, with a
                                                                clear reason
                                          EXEC_COMMANDS       - privileged exec mode,
                                                                BEFORE "configure terminal"
                                          GLOBAL_COMMANDS     - top-level config, once
                                          INTERFACE_COMMANDS  - once PER trunk port
                                        (all optional except at least one command list)
    push_config.py                  -> the engine. Only pushes config — does NOT
                                        save it. Run save_config.py separately.

Any command string can reference {some_variable}. Variables come from:
  - the task's own DEFAULTS dict
  - build_variables(), which adds per-device data like {management_ip}
    and {hostname} from inventory/devices_interfaces.py

So a task can write:

    GLOBAL_COMMANDS = ["sflow agent-address {management_ip}"]

and every device gets its own IP substituted in automatically — no
per-feature special-casing needed in this file ever again.

If a command references a variable that was never defined anywhere
(a typo, e.g. {collecter_ip}), that's treated as a bug in the task
file and fails loudly with a clear message, rather than silently
skipping or crashing with a bare KeyError.

If a REQUIRED_VARIABLE has no value for a particular device (e.g. that
device's management_ip wasn't discovered), only THAT device is
skipped, with a clear reason — other devices still get pushed to.

Usage:
    python push_config.py sflow
    python push_config.py syslog ntp

Legacy task files (CONFIG_COMMANDS + optional PER_INTERFACE) still work.
"""

import sys
import argparse
import importlib

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from devices import DEVICES, GROUPS, get_group
from inventory.devices_trunks import TRUNK_PORTS
from inventory.devices_interfaces import DEVICE_INTERFACES

ERROR_MARKERS = [
    "% Invalid input",
    "Invalid input detected",
    "locked by other user",
    "% Unknown command",
    "% Ambiguous command",
    "% Incomplete command",
]

INTERFACE_EXIT_CMD = "exit"


def interface_enter_command(port):
    """Build the 'interface ...' command regardless of whether the
    stored port string is the bare suffix ("1/0/25") from older
    inventory files or the full name ("Ethernet1/0/25") that the
    current discover_trunks.py / discover_access.py produce."""
    if port.lower().startswith("ethernet"):
        return f"interface {port}"
    return f"interface Ethernet{port}"


def load_task(task_name):
    """Return a dict describing a task module: metadata, defaults,
    required variables, and its three command lists."""
    try:
        module = importlib.import_module(f"tasks.{task_name}")
    except ModuleNotFoundError:
        print(f"ERROR: no task file found at tasks/{task_name}.py")
        sys.exit(1)

    defaults    = getattr(module, "DEFAULTS", None)
    required    = getattr(module, "REQUIRED_VARIABLES", [])
    exec_cmds   = getattr(module, "EXEC_COMMANDS", None)
    global_cmds = getattr(module, "GLOBAL_COMMANDS", None)
    iface_cmds  = getattr(module, "INTERFACE_COMMANDS", None)

    # Legacy fallback: old-style tasks only had CONFIG_COMMANDS, optionally
    # with PER_INTERFACE=True meaning "wrap all of these per trunk port".
    if global_cmds is None and iface_cmds is None:
        if not hasattr(module, "CONFIG_COMMANDS"):
            print(f"ERROR: tasks/{task_name}.py needs GLOBAL_COMMANDS and/or "
                  f"INTERFACE_COMMANDS (or legacy CONFIG_COMMANDS)")
            sys.exit(1)
        legacy_cmds = module.CONFIG_COMMANDS
        if getattr(module, "PER_INTERFACE", False):
            global_cmds, iface_cmds = [], legacy_cmds
        else:
            global_cmds, iface_cmds = legacy_cmds, []

    defaults    = defaults or {}
    exec_cmds   = exec_cmds or []
    global_cmds = global_cmds or []
    iface_cmds  = iface_cmds or []

    if not exec_cmds and not global_cmds and not iface_cmds:
        print(f"ERROR: tasks/{task_name}.py has no commands defined")
        sys.exit(1)

    return {
        "task_name":   task_name,
        "description": getattr(module, "DESCRIPTION", ""),
        "version":     getattr(module, "VERSION", ""),
        "author":      getattr(module, "AUTHOR", ""),
        "defaults":    defaults,
        "required":    required,
        "exec_cmds":   exec_cmds,
        "global_cmds": global_cmds,
        "iface_cmds":  iface_cmds,
    }


def print_task_metadata(task):
    """Print a small header block for a task, if it has any metadata
    worth showing. Skips silently for tasks with no DESCRIPTION etc."""
    if not (task["description"] or task["version"] or task["author"]):
        return
    print("=" * 55)
    print("Task")
    print("-" * 55)
    print(f"Name        : {task['task_name']}")
    if task["description"]:
        print(f"Description : {task['description']}")
    if task["version"]:
        print(f"Version     : {task['version']}")
    if task["author"]:
        print(f"Author      : {task['author']}")
    print("=" * 55)


def build_variables(device_name, defaults):
    """Build every variable available to {placeholder} substitution.
    Tasks just reference {management_ip}, {hostname}, or whatever they
    put in their own DEFAULTS — no changes needed here to support a
    new variable a task introduces via DEFAULTS.
    """
    variables = dict(defaults)

    device = DEVICE_INTERFACES.get(device_name, {})
    variables["management_ip"] = device.get("management_ip")
    variables["hostname"] = device_name

    return variables


def validate_variables(device_name, variables, required):
    """Raise ValueError listing any REQUIRED_VARIABLES that resolved
    to nothing for this device (e.g. management_ip never discovered).
    Caller treats this as 'skip this one device', not a hard crash."""
    missing = [
        name for name in required
        if variables.get(name) is None or variables.get(name) == ""
    ]
    if missing:
        raise ValueError(
            f"{device_name}: missing required variable(s): {', '.join(missing)}"
        )


def format_command(cmd, variables):
    """Fill in {placeholders}. A KeyError here means the command
    references a variable that isn't in DEFAULTS, REQUIRED_VARIABLES,
    or build_variables() — i.e. a typo in the task file itself. That's
    a bug in the task, not a per-device data problem, so it's raised
    as a clear ValueError rather than a bare KeyError."""
    try:
        return cmd.format(**variables)
    except KeyError as err:
        raise ValueError(
            f"unknown variable {{{err.args[0]}}} in command: {cmd!r} "
            f"(check DEFAULTS / REQUIRED_VARIABLES in the task file for a typo)"
        )


def build_config_commands(device_name, variables, global_cmds, iface_cmds):
    """Build the command list that runs INSIDE 'configure terminal',
    combining global commands with per-trunk-port interface blocks."""
    commands = [format_command(cmd, variables) for cmd in global_cmds]

    if iface_cmds:
        ports = TRUNK_PORTS.get(device_name, [])
        if not ports:
            print(f"  ⚠️  No trunk ports found for {device_name} — skipping interface commands")
        else:
            filled_iface_cmds = [format_command(cmd, variables) for cmd in iface_cmds]
            for port in ports:
                commands.append(interface_enter_command(port))
                commands.extend(filled_iface_cmds)
                commands.append(INTERFACE_EXIT_CMD)

    return commands


def push_to_device(device, defaults, required, exec_cmds, global_cmds, iface_cmds):
    name = device["name"]
    host = device["host"]
    conn_params = {k: v for k, v in device.items() if k not in ("name", "group")}

    result = {"name": name, "host": host, "status": None, "output": "", "error": ""}

    # Pre-flight: resolve variables, validate required ones are present,
    # and format every command — all BEFORE opening any connection.
    try:
        variables = build_variables(name, defaults)
        validate_variables(name, variables, required)
        filled_exec_cmds = [format_command(cmd, variables) for cmd in exec_cmds]
        config_commands = build_config_commands(name, variables, global_cmds, iface_cmds)
    except ValueError as e:
        result["status"] = "SKIPPED"
        result["error"]  = str(e)
        return result

    if not filled_exec_cmds and not config_commands:
        result["status"] = "SKIPPED"
        result["error"]  = "No commands to push (no trunk ports found for an interface-only task?)"
        return result

    try:
        conn = ConnectHandler(**conn_params)

        output = ""

        # Exec-mode commands run first, outside config mode
        for cmd in filled_exec_cmds:
            output += conn.send_command_timing(
                cmd, strip_prompt=False, strip_command=False, delay_factor=2,
            )

        if config_commands:
            output += conn.send_command_timing(
                "configure terminal",
                strip_prompt=False, strip_command=False, delay_factor=2,
            )

            for cmd in config_commands:
                output += conn.send_command_timing(
                    cmd, strip_prompt=False, strip_command=False, delay_factor=2,
                )

            output += conn.send_command_timing(
                "end", strip_prompt=False, strip_command=False,
            )

        conn.disconnect()

        # Only flag errors that appear near a command we actually sent
        # (avoids false positives from banners/MOTD). Capture the couple
        # of lines BEFORE the error too, since that's where the echoed
        # command that triggered it actually is — a bare "% Invalid
        # input" line alone doesn't tell you which command failed.
        all_sent = filled_exec_cmds + config_commands
        output_lines = output.splitlines()
        found_errors = []
        for i, line in enumerate(output_lines):
            if any(m in line for m in ERROR_MARKERS):
                snippet_lines = output_lines[max(0, i - 2):i + 1]
                context = " ".join(snippet_lines).lower()
                if any(cmd.lower()[:10] in context for cmd in all_sent):
                    found_errors.append("\n".join(snippet_lines))

        if found_errors:
            result["status"] = "FAILED"
            result["error"]  = "Device rejected commands:\n\n" + "\n\n".join(found_errors)
            result["output"] = output
        else:
            result["status"] = "SUCCESSFUL"
            result["output"] = output

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
    print(f"\n=== {result['name']} ({result['host']}) ===")
    if result["status"] == "SUCCESSFUL":
        print(result["output"])
    elif result["status"] == "SKIPPED":
        print(f"  SKIPPED — {result['error']}")
    else:
        print(f"  ERROR — {result['error']}")
    print(f"--- {result['name']}: {result['status']} ---")


def main():
    parser = argparse.ArgumentParser(
        description="Push configuration tasks to network devices."
    )
    parser.add_argument("tasks", nargs="+", help="Task name(s), e.g. syslog sflow")
    parser.add_argument("--group", help="Only push to devices in this group (e.g. captainhooks)")
    parser.add_argument("--switch", help="Only push to a single device by name")
    args = parser.parse_args()

    task_names = args.tasks

    # Resolve target device list
    if args.switch:
        target_devices = [d for d in DEVICES if d["name"] == args.switch]
        if not target_devices:
            print(f"ERROR: no device named '{args.switch}' found")
            sys.exit(1)
    elif args.group:
        try:
            group_devices = get_group(args.group)
        except KeyError:
            print(f"ERROR: no group named '{args.group}' (available: {', '.join(GROUPS)})")
            sys.exit(1)
        target_devices = [dict(d, group=args.group) for d in group_devices]
    else:
        target_devices = DEVICES

    all_defaults = {}
    all_required = []
    all_exec, all_global, all_iface = [], [], []

    for task_name in task_names:
        task = load_task(task_name)
        print_task_metadata(task)
        all_defaults.update(task["defaults"])
        all_required.extend(task["required"])
        all_exec.extend(task["exec_cmds"])
        all_global.extend(task["global_cmds"])
        all_iface.extend(task["iface_cmds"])

    print(f"Task(s)          : {', '.join(task_names)}")
    print(f"Defaults         : {all_defaults}")
    print(f"Required vars    : {all_required}")
    print(f"Exec commands    : {len(all_exec)}")
    print(f"Global commands  : {len(all_global)}")
    print(f"Per-iface cmds   : {len(all_iface)}")
    print(f"Devices          : {len(target_devices)}")
    if all_iface:
        print(f"Trunk ports      : {dict((d['name'], TRUNK_PORTS.get(d['name'], [])) for d in target_devices)}")
    print()

    results = [
        push_to_device(d, all_defaults, all_required, all_exec, all_global, all_iface)
        for d in target_devices
    ]

    for result in results:
        print_result(result)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok      = sum(1 for r in results if r["status"] == "SUCCESSFUL")
    failed  = sum(1 for r in results if r["status"] == "FAILED")
    skipped = sum(1 for r in results if r["status"] == "SKIPPED")
    for r in results:
        icon = "✅" if r["status"] == "SUCCESSFUL" else ("⚠️ " if r["status"] == "SKIPPED" else "❌")
        print(f"  {icon} {r['name']:<20} : {r['status']}")
    print(f"\nDevices: {len(results)}  ✅ {ok}  ❌ {failed}  ⚠️  {skipped}")
    print("\nNote: push_config.py only pushes config. Run save_config.py")
    print("separately once you're satisfied with the changes.")


if __name__ == "__main__":
    main()
