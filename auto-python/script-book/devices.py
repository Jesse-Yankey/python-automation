"""
Device inventory — equivalent to Ansible's inventory/host.ini,
but organized into groups instead of one flat list.

Add or remove devices under the relevant group. Each device entry
is a dict of connection parameters that gets passed straight into
Netmiko's ConnectHandler.

To use a specific group in a script:
    from devices import GROUPS
    for device in GROUPS["switchback"]:
        ...

To use every device regardless of group (each tagged with its group name):
    from devices import all_devices
    for device in all_devices():
        print(device["group"], device["name"])
"""

GROUPS = {
    "switchback": [
        {
            "name": "ONYX-SW1-BRR",
            "device_type": "generic_termserver",
            "host": "192.168.10.250",
            "username": "admin",
            "password": "admin",
        },
        {
            "name": "ONYX-SW2-NW",
            "device_type": "generic_termserver",
            "host": "192.168.10.245",
            "username": "admin",
            "password": "admin",
        },
        {
            "name": "RUBY-SW1-PAA",
            "device_type": "generic_termserver",
            "host": "192.168.10.248",
            "username": "admin",
            "password": "admin",
        },
        {
            "name": "RUBY-SW2-REC",
            "device_type": "generic_termserver",
            "host": "192.168.10.249",
            "username": "admin",
            "password": "admin",
        },
        {
            "name": "RUBY-SW3-APP",
            "device_type": "generic_termserver",
            "host": "192.168.10.247",
            "username": "admin",
            "password": "admin",
        },
        {
            "name": "RUBY-SW4-APP",
            "device_type": "generic_termserver",
            "host": "192.168.10.246",
            "username": "admin",
            "password": "admin",
        },
        {
            "name": "DC-SW2-HRP",
            "device_type": "generic_termserver",
            "host": "192.168.10.252",
            "username": "admin",
            "password": "admin",
        },
#        {
#            "name": "CORE-LAN-SW",
#            "device_type": "generic_termserver",
#            "host": "192.168.10.253",
#            "username": "admin",
#            "password": "123qwertY!!",
#        },
    ],

    "captainhooks": [
       {
            "name": "CH-FF-SW",
            "device_type": "generic_termserver",
            "host": "192.168.12.248",
            "username": "admin",
            "password": "123qwertY!!",
       },
#       {
#            "name": "CH-NEWSTAR-SW",
#            "device_type": "generic_termserver",
#            "host": "192.168.12.249",
#            "username": "admin",
#            "password": "123qwertY!!",
#       },
	{
	    "name": "CH-RCR-SW",
	    "device_type": "generic_termserver",
	    "host": "192.168.12.250",
	    "username": "admin",
	    "password": "123qwertY!!",
	},
        {
             "name":"CH-SLO-SW",
             "device_type":"generic_termserver",
             "host": "192.168.12.251",
             "username": "admin",
             "password": "123qwertY!!",
        },
        {
             "name": "CH-ACC-SW",
             "device_type": "generic_termserver",
             "host": "192.168.12.252",
             "username": "admin",
             "password": "123qwertY!!",
        },
#        {
#            "name": "CH-CORE-SW",
#            "device_type": "generic_termserver",
#            "host": "192.168.12.253",
#            "username": "admin",
#            "password": "123qwertY!!",
#        },
    ],

    "kanda": [
        # Add kanda devices here
    ],

    "newgas": [
        # Add newgas devices here
    ],

    "tof": [
        # Add tof devices here
    ],

    "atuabo": [
        # Add atuabo devices here
    ],
}


def all_devices():
    """
    Return a flat list of every device across all groups.

    Each returned dict is a copy of the original device entry with an
    added "group" key, so callers know which group folder / context a
    device belongs to without having to cross-reference GROUPS.
    """
    devices = []
    for group_name, group_devices in GROUPS.items():
        for device in group_devices:
            tagged = dict(device)
            tagged["group"] = group_name
            devices.append(tagged)
    return devices


def get_group(name):
    """Return the device list for a given group name (raises KeyError if unknown)."""
    return GROUPS[name]


# Backwards-compatible alias: some scripts may still `from devices import DEVICES`
# expecting a flat list of all devices. Each entry now also carries a "group" key.
DEVICES = all_devices()
