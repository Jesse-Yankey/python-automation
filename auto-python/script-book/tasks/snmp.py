"""
Task: snmp
Configure SNMPv2c on PLANET switches.

Discovered syntax from RUBY-SW2-REC (SGS-6341, firmware 7.5.3.2):
  snmp-server enable
  snmp-server enable traps
  snmp-server community {ro|rw} 0 {community-string}
  snmp-server host {ip} v2c {community-string}

Notes:
  - Use '0' for plaintext community string (switch auto-encrypts to type 7)
  - 'no snmp-server community' uses format: no snmp-server community 0 {string}
  - SNMPv3 not configured here — v2c only for now
  - No per-interface SNMP commands needed

Run with:
    python push_config.py snmp
"""

DESCRIPTION = "Configure SNMPv2c communities, trap host and enable traps"
VERSION     = "1.0"

DEFAULTS = {
    "snmp_ro_community": "public_ro",
    "trap_host_ip":      "172.18.200.65",
    "trap_community":    "switchback",
}

REQUIRED_VARIABLES = []

EXEC_COMMANDS = []

INTERFACE_COMMANDS = []

GLOBAL_COMMANDS = [
#    "service password-encryption",
    "snmp-server enable",
    "snmp-server securityip disable",
    "snmp-server enable traps",

    # Communities — type 0 = plaintext (switch stores as type 7 encrypted)
    "snmp-server community ro 0 {trap_community}",
    "snmp-server host {trap_host_ip} v2c {trap_community}",
]
