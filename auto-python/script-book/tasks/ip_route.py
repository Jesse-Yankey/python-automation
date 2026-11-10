"""
Task: ip_route
Configure static IP routes.

Run with:
    python push_config.py ip_route
"""
DESCRIPTION = "Configure static IP routes"
VERSION     = "1.0"
DEFAULTS = {
    "route1_network": "10.50.100.0",
    "route1_subnet": "255.255.255.0",
    "route2_network": "172.18.200.65",
    "route2_subnet": "255.255.255.255",
    "next_hop":        "192.168.10.254",
}
REQUIRED_VARIABLES = []
GLOBAL_COMMANDS = [
    "ip route {route1_network} {route1_subnet} {next_hop}",
    "ip route {route2_network} {route2_subnet} {next_hop}",
]
INTERFACE_COMMANDS = []
