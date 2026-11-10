#!/usr/bin/env python3
import requests

# NOTE: must point at the actual API endpoint, not the LibreNMS homepage.
# The base URL below is just the server address — /api/v0/oxidized is the
# path that returns the device list in the format Oxidized expects.
LIBRENMS_URL = "http://192.168.124.161/api/v0/oxidized"
API_TOKEN = "c2e92280c7360dd0d0a48e2e01d1fb47"


def get_dynamic_inventory():
    headers = {"X-Auth-Token": API_TOKEN}
    devices = []

    try:
        response = requests.get(LIBRENMS_URL, headers=headers, timeout=10)
        response.raise_for_status()  # turns 401/403/404/500 into a clear exception

        nodes = response.json()

        for node in nodes:
            hostname = node.get("hostname")
            if not hostname:
                continue

            # Prefer the IP LibreNMS has on file for the actual SSH/telnet
            # connection — hostname is kept as "name" so it matches the
            # device's hostname in LibreNMS exactly (needed for the
            # Configs tab lookup later).
            host = node.get("ip") or hostname

            password = "123qwertY!!" if "CORE" in hostname.upper() else "admin"

            devices.append({
                "name": hostname,
                "host": host,
                "device_type": "generic_termserver",  # forces Netmiko to use Telnet
                "username": "admin",
                "password": password,
            })

    except requests.exceptions.HTTPError as e:
        print(f"⚠️ LibreNMS API returned an error: {e}")
        print(f"   URL: {LIBRENMS_URL}")
        print(f"   Response body (first 300 chars): {response.text[:300]!r}")
        print("   Common causes: wrong/expired X-Auth-Token, or the token's")
        print("   user doesn't have API read permission.")
    except requests.exceptions.ConnectionError as e:
        print(f"⚠️ Could not reach LibreNMS at {LIBRENMS_URL}: {e}")
    except requests.exceptions.JSONDecodeError:
        print(f"⚠️ LibreNMS didn't return JSON from {LIBRENMS_URL}.")
        print(f"   Response body (first 300 chars): {response.text[:300]!r}")
        print("   This usually means the URL is wrong (e.g. missing /api/v0/oxidized)")
        print("   and you're hitting the web UI instead of the API.")
    except Exception as e:
        print(f"⚠️ Warning: Failed to fetch inventory from LibreNMS API ({e}). Falling back.")

    return devices
