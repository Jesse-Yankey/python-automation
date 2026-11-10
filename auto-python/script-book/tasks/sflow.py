"""
Task: sFlow
"""

DESCRIPTION = "Configure sFlow"
VERSION = "1.0"

DEFAULTS = {
#    "collector_ip": "192.168.124.161",
#    "priority": 1,
#    "input_rate": 1000,
#    "output_rate": 1000,
#    "counter_interval": 20,
}

REQUIRED_VARIABLES = [
    "management_ip",
]

GLOBAL_COMMANDS = [
    "no sflow agent-addres",
    "no sflow destination",
    "no sflow priority",
]

INTERFACE_COMMANDS = [
    "no sflow destination",
    "no sflow rate input",
    "no sflow rate output",
    "no sflow counter-interval",
]
