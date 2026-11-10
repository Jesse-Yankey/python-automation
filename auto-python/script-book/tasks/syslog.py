"""
Configuration commands — equivalent to the 'tasks' in an Ansible playbook.

These are sent to every device in DEVICES, in order, exactly as if
typed at the CLI. The runner script automatically wraps these with
"configure terminal" before and "end" after — do NOT include those
here yourself, or they'll be sent twice.
"""

DESCRIPTION = "Configure Syslog"
VERSION = "1.0"
 
DEFAULTS = {
    "syslog_server_1": "172.18.200.65",
}
 
GLOBAL_COMMANDS = [
#    "info-center loghost 1 config {syslog_server_1} facility local7",
#    "info-center loghost 1 output-enable",
#    "info-center loghost 1 match level warnings",

    "no info-center loghost 2 config",
    "no info-center loghost 2 output-enable",
    "no info-center loghost 2 match",
]
