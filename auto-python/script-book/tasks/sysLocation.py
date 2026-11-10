"""
Task: sysLocator
"""

DESCRIPTION = "Configuring sysLocation"

DEFAULTS = {
    "sysLocation": "SWITCHBACK",
}

REQUIRED_VARIABLES = []

EXEC_COMMANDS = []

INTERFACE_COMMANDS = []

GLOBAL_COMMANDS = [
    "sysLocation {sysLocation}",
]

