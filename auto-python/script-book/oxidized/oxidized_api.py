#!/usr/bin/env python3
"""
oxidized_api.py — a minimal stand-in for the real Oxidized REST API,
backed by plain flat files (no git, no history).

LibreNMS's "Configs" tab polls a handful of HTTP endpoints on whatever
URL you set as `oxidized.url` — it doesn't know or care what actually
generated the configs. This server answers those endpoints out of
backups/<name>.cfg, so LibreNMS shows the CURRENT config for each
device exactly like it would with real Oxidized. There's no history
or diff view in this version — that needs git, which we're skipping
for now.

Device inventory is pulled live from LibreNMS (same source as
backup_config.py) rather than a static file, and cached in memory.
Hit /reload to refresh that cache after adding/removing devices in
LibreNMS — same convention as real Oxidized's `oxidized.reload_nodes`.

Endpoints implemented:
    GET  /nodes.json                    -> list of all nodes + last status
    GET  /node/show/<name>              -> raw current config (text/plain)
    GET  /node/show/<name>?format=json  -> node metadata + config content
    GET  /node/fetch/<name>             -> raw current config (text/plain)
                                            (this is what LibreNMS actually
                                            reads to render the Config tab
                                            when versioning is off / only
                                            one version exists)
    GET  /node/next/<name>              -> trigger a live backup now
                                            ("move to head of queue" /
                                            "Fetch now")
    GET  /node/version                  -> mock single-version history
    GET  /reload                        -> refresh the device list from
                                            LibreNMS

"""

import os

from flask import Flask, jsonify, Response, request

from inventory import get_dynamic_inventory
from backup_config import BACKUP_DIR, backup_device, load_status, save_status

app = Flask(__name__)

# Cached in memory, refreshed on startup and whenever /reload is hit —
# avoids calling out to LibreNMS on every single request.
DEVICES = get_dynamic_inventory()
DEVICE_BY_NAME = {d["name"]: d for d in DEVICES}


def file_mtime_iso(name):
    filepath = os.path.join(BACKUP_DIR, f"{name}.cfg")
    if not os.path.exists(filepath):
        return None
    from datetime import datetime, timezone
    ts = os.path.getmtime(filepath)
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def resolve_config_path(name):
    """
    Given whatever identifier LibreNMS sends us (device name, sysName,
    or IP — it isn't always consistent), figure out which backups/*.cfg
    file actually corresponds to it. Shared by node_show and node_fetch
    so both endpoints resolve names the same way.
    """
    name = str(name).split("?")[0].strip()

    # If LibreNMS passes group details in path (e.g., default/192.168.10.247)
    if "/" in name:
        name = name.split("/")[-1]

    filepath = os.path.join(BACKUP_DIR, f"{name}.cfg")

    # Fallback 1: name is a device dict key -> resolve to its IP filename
    if not os.path.exists(filepath) and name in DEVICE_BY_NAME:
        ip_addr = DEVICE_BY_NAME[name]["host"]
        filepath = os.path.join(BACKUP_DIR, f"{ip_addr}.cfg")

    # Fallback 2: blank/mangled name — use the last path segment directly
    if not os.path.exists(filepath) or not name or name in ['""', "''"]:
        last_segment = request.path.split("/")[-1]
        filepath = os.path.join(BACKUP_DIR, f"{last_segment}.cfg")

    # Fallback 3: check query-string params LibreNMS sometimes sends
    if not os.path.exists(filepath):
        node_param = request.args.get("node") or request.args.get("node_full")
        if node_param:
            if "/" in node_param:
                node_param = node_param.split("/")[-1]
            filepath = os.path.join(BACKUP_DIR, f"{node_param}.cfg")

    return name, filepath


def node_info(name):
    device = DEVICE_BY_NAME.get(name)
    status = load_status().get(name, {})
    return {
        "name": name,
        "full_name": name,
        "ip": device["host"] if device else None,
        "group": "default",
        "model": "ios",  # adjust per-device if you mix vendors
        "last": {
            "start": status.get("time"),
            "end": status.get("time"),
            "status": status.get("status", "never"),
            "error": status.get("error") or None,
        },
        "mtime": file_mtime_iso(name),
    }


@app.route("/nodes.json")
def nodes_json():
    return jsonify([node_info(d["name"]) for d in DEVICES])


@app.route("/node/show/<path:name>")
def node_show(name=""):
    name, filepath = resolve_config_path(name)

    # If the format request parameter asks for JSON schema parameters metadata
    if request.args.get("format") == "json":
        config_text = None
        if os.path.exists(filepath):
            with open(filepath) as f:
                config_text = f.read()

        return jsonify({
            "name": name if name else "Unknown-Switch",
            "full_name": name if name else "Unknown-Switch",
            "ip": name if name else "0.0.0.0",
            "group": "default",
            "model": "ios",
            "last": {"status": "success"},
            "mtime": file_mtime_iso(name) or file_mtime_iso(request.path.split("/")[-1]),
            "config": config_text,
        })

    if not os.path.exists(filepath):
        return f"node not found (Tried looking for file path context: {filepath})", 404

    with open(filepath) as f:
        return Response(f.read(), mimetype="text/plain")


@app.route("/node/fetch/<path:name>")
def node_fetch(name=""):
    """
    This is the endpoint LibreNMS's Config tab actually reads from when
    oxidized.features.versioning is false (or only one version exists) —
    it takes the raw text response body verbatim as the displayed config.
    Real Oxidized's /node/fetch behaves the same way: it returns the
    currently stored config, it does NOT trigger a fresh device pull.
    For that, see /node/next below.
    """
    name, filepath = resolve_config_path(name)

    if not os.path.exists(filepath):
        return f"node not found (Tried looking for file path context: {filepath})", 404

    with open(filepath) as f:
        return Response(f.read(), mimetype="text/plain")


@app.route("/node/next/<path:name>", methods=["GET", "POST"])
def node_next(name):
    """
    Real Oxidized's "move to head of queue" — trigger an immediate live
    backup of just this device. This is what should back LibreNMS's
    "Fetch now" / "Refresh" button.
    """
    name = name.split("/")[-1]  # handle group/name form
    device = DEVICE_BY_NAME.get(name)
    if not device:
        return jsonify({"status": "err", "error": f"node {name} not found"}), 404

    result = backup_device(device)

    status = load_status()
    status[name] = {"status": result["status"], "time": result["time"], "error": result["error"]}
    save_status(status)

    return jsonify({
        "status": "ok" if result["status"] == "success" else "err",
        "error": result["error"] or None,
    })


@app.route("/reload")
def reload_nodes():
    global DEVICES, DEVICE_BY_NAME
    DEVICES = get_dynamic_inventory()
    DEVICE_BY_NAME = {d["name"]: d for d in DEVICES}
    return jsonify({"status": "ok", "nodes": len(DEVICES)})


@app.route("/node/version")
def node_version():
    node_name = request.args.get("node_full") or request.args.get("node")
    if not node_name:
        return jsonify({"status": "err", "error": "missing node parameter"}), 400

    # Strip group if it's passed in node_full (e.g., default/192.168.10.245)
    if "/" in node_name:
        node_name = node_name.split("/")[-1]

    # Return a mock version history representing our current flat file.
    # NOTE: LibreNMS reads the "oid" key specifically (not "hash") to build
    # its subsequent /node/version/view request — this must be present.
    mtime = file_mtime_iso(node_name) or "unknown"
    return jsonify([
        {
            "index": 0,
            "oid": "current",
            "date": mtime,
            "author": {"name": "Python-Automation", "email": ""},
            "message": "Current Flat File Backup"
        }
    ])


@app.route("/node/version/view")
def node_version_view():
    """
    LibreNMS calls this (with ?node=<name>&oid=<oid>&format=text) once it
    has picked a version from /node/version to display. Since we only ever
    keep the current flat-file config (no real history), we just serve
    whatever's currently on disk for that node regardless of oid.
    """
    node_name = request.args.get("node")
    if not node_name:
        return jsonify({"status": "err", "error": "missing node parameter"}), 400

    _, filepath = resolve_config_path(node_name)

    if not os.path.exists(filepath):
        return f"node not found (Tried looking for file path context: {filepath})", 404

    with open(filepath) as f:
        return Response(f.read(), mimetype="text/plain")


if __name__ == "__main__":
    os.makedirs(BACKUP_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=8888)
