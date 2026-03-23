#!/usr/bin/env python3
"""
FIWARE Smart Rain Monitoring — Provisioning Script
===================================================
Provisions WaterLevelSensor, RainSensor, and FloodZone entities
in FIWARE (Orion Context Broker + IoT Agent over MQTT/UltraLight).

Stack:
  - Orion Context Broker  -> http://<HOST>:1026
  - IoT Agent (UL/MQTT)   -> http://<HOST>:4041
  - STH-Comet             -> http://<HOST>:8666

Usage:
  python provision_rain_monitoring.py --help
  python provision_rain_monitoring.py -W 10 -R 5 -F 3
  python provision_rain_monitoring.py -W 50 -R 20 -F 10 --host 192.168.1.10
"""

import argparse
import random
import logging

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIWARE_SERVICE     = "rainmonitoring"
FIWARE_SERVICEPATH = "/"
IOT_API_KEY        = "TEF"

HEADERS = {
    "Content-Type": "application/json",
    "fiware-service": FIWARE_SERVICE,
    "fiware-servicepath": FIWARE_SERVICEPATH,
}

# Random coordinate bounding box (Rio de Janeiro area)
LAT_MIN, LAT_MAX = -22.9500, -22.8700
LON_MIN, LON_MAX = -43.2200, -43.1200

# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def orion(host):
    return f"http://{host}:1026"

def iot(host):
    return f"http://{host}:4041"

def sth(host):
    return f"http://fiware-sth-comet:8666"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def post(url, payload, label):
    r = requests.post(url, headers=HEADERS, json=payload, timeout=10)
    if r.status_code in (200, 201, 204):
        log.info("OK   %s -> %s", label, r.status_code)
    else:
        log.warning("WARN %s -> %s: %s", label, r.status_code, r.text[:200])
    return r


def get(url, label, headers=None):
    if headers is None:
        headers = HEADERS
    r = requests.get(url, headers=headers, timeout=10)
    log.info("GET  %s -> %s", label, r.status_code)
    return r

# ---------------------------------------------------------------------------
# Device generators
# ---------------------------------------------------------------------------

def rand_coord():
    return (
        round(random.uniform(LAT_MIN, LAT_MAX), 6),
        round(random.uniform(LON_MIN, LON_MAX), 6),
    )


def make_water_sensors(n):
    sensors = []
    for i in range(1, n + 1):
        lat, lon = rand_coord()
        sensors.append({
            "id":   f"wls{i:04d}",
            "name": f"WaterLevelSensor:{i:04d}",
            "lat":  lat,
            "lon":  lon,
        })
    return sensors


def make_rain_sensors(n):
    sensors = []
    for i in range(1, n + 1):
        lat, lon = rand_coord()
        sensors.append({
            "id":   f"rs{i:04d}",
            "name": f"RainSensor:{i:04d}",
            "lat":  lat,
            "lon":  lon,
        })
    return sensors


def make_flood_zones(n):
    zones = []
    for i in range(1, n + 1):
        lat, lon = rand_coord()
        zones.append({
            "id":   f"fz{i:04d}",
            "name": f"FloodZone:{i:04d}",
            "lat":  lat,
            "lon":  lon,
        })
    return zones

# ---------------------------------------------------------------------------
# Provisioning steps
# ---------------------------------------------------------------------------

def provision_service_group(host):
    log.info("-- IoT Service Group --")
    post(
        f"{iot(host)}/iot/services",
        {
            "services": [{
                "apikey":      IOT_API_KEY,
                "cbroker":     orion(host),
                "entity_type": "WaterLevelSensor",
                "resource":    "",
            }]
        },
        "Service Group",
    )


def provision_water_sensors(host, sensors, batch_size):
    log.info("-- WaterLevelSensor devices (%d) --", len(sensors))
    devices = [
        {
            "device_id":   s["id"],
            "entity_name": f"urn:ngsi-ld:{s['name']}",
            "entity_type": "WaterLevelSensor",
            "protocol":    "PDI-IoTA-UltraLight",
            "transport":   "MQTT",
            "attributes": [
                {"object_id": "l",   "name": "level",    "type": "Number"},
                {"object_id": "loc", "name": "location", "type": "geo:point"},
            ],
            "static_attributes": [
                {"name": "location", "type": "geo:point", "value": f"{s['lat']}, {s['lon']}"}
            ],
        }
        for s in sensors
    ]
    for start in range(0, len(devices), batch_size):
        batch = devices[start : start + batch_size]
        post(
            f"{iot(host)}/iot/devices",
            {"devices": batch},
            f"WaterLevelSensor batch [{start + 1}-{start + len(batch)}]",
        )


def provision_rain_sensors(host, sensors, batch_size):
    log.info("-- RainSensor devices (%d) --", len(sensors))
    devices = [
        {
            "device_id":   s["id"],
            "entity_name": f"urn:ngsi-ld:{s['name']}",
            "entity_type": "RainSensor",
            "protocol":    "PDI-IoTA-UltraLight",
            "transport":   "MQTT",
            "attributes": [
                {"object_id": "i", "name": "intensity", "type": "Number"},
            ],
            "static_attributes": [
                {"name": "location", "type": "geo:point", "value": f"{s['lat']}, {s['lon']}"}
            ],
        }
        for s in sensors
    ]
    for start in range(0, len(devices), batch_size):
        batch = devices[start : start + batch_size]
        post(
            f"{iot(host)}/iot/devices",
            {"devices": batch},
            f"RainSensor batch [{start + 1}-{start + len(batch)}]",
        )


def provision_flood_zones(host, zones):
    log.info("-- FloodZone entities (%d) --", len(zones))
    for fz in zones:
        post(
            f"{orion(host)}/v2/entities",
            {
                "id":        f"urn:ngsi-ld:{fz['name']}",
                "type":      "FloodZone",
                "riskLevel": {"type": "Text",      "value": "LOW"},
                "location":  {"type": "geo:point", "value": f"{fz['lat']}, {fz['lon']}"},
            },
            f"FloodZone {fz['id']}",
        )


def provision_subscriptions(host, notification_url):
    log.info("-- Subscriptions --")
    url = f"{orion(host)}/v2/subscriptions"

    post(url, {
        "description": "Heavy rain alert",
        "subject": {
            "entities": [{"idPattern": ".*", "type": "RainSensor"}],
            "condition": {"attrs": ["intensity"], "expression": {"q": "intensity>70"}},
        },
        "notification": {
            "http": {"url": notification_url},
            "attrs": ["intensity", "location"],
        },
        "throttling": 5,
    }, "Sub: heavy rain (intensity>70)")

    post(url, {
        "description": "High water level alert",
        "subject": {
            "entities": [{"idPattern": ".*", "type": "WaterLevelSensor"}],
            "condition": {"attrs": ["level"], "expression": {"q": "level>2.0"}},
        },
        "notification": {
            "http": {"url": notification_url},
            "attrs": ["level", "location"],
        },
        "throttling": 5,
    }, "Sub: high water level (level>2.0)")

    post(url, {
        "description": "WaterLevelSensor history",
        "subject": {
            "entities": [{"idPattern": ".*", "type": "WaterLevelSensor"}],
            "condition": {"attrs": ["level"]},
        },
        "notification": {
            "http": {"url": f"{sth(host)}/notify"},
            "attrs": ["level", "location"],
            "attrsFormat": "legacy",
        },
    }, "Sub: WaterLevelSensor -> STH-Comet")

    post(url, {
        "description": "RainSensor history",
        "subject": {
            "entities": [{"idPattern": ".*", "type": "RainSensor"}],
            "condition": {"attrs": ["intensity"]},
        },
        "notification": {
            "http": {"url": f"{sth(host)}/notify"},
            "attrs": ["intensity"],
            "attrsFormat": "legacy",
        },
    }, "Sub: RainSensor -> STH-Comet")

    post(url, {
        "description": "FloodZone risk level change",
        "subject": {
            "entities": [{"idPattern": ".*", "type": "FloodZone"}],
            "condition": {"attrs": ["riskLevel"]},
        },
        "notification": {
            "http": {"url": notification_url},
            "attrs": ["riskLevel", "location"],
        },
    }, "Sub: FloodZone risk change")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health_check(host):
    log.info("-- Health Checks --")
    get(f"{orion(host)}/version", "Orion", {})
    get(f"{iot(host)}/iot/about", "IoT Agent")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="provision_rain_monitoring.py",
        description=(
            "Provision a FIWARE Smart Rain Monitoring stack.\n\n"
            "Creates WaterLevelSensor and RainSensor devices via the IoT Agent,\n"
            "FloodZone entities directly in Orion, and all required subscriptions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  # Default: 3 water, 2 rain, 2 flood zones on localhost\n"
            "  %(prog)s\n\n"
            "  # Custom fleet on a remote host\n"
            "  %(prog)s -W 20 -R 10 -F 5 --host 192.168.1.10\n\n"
            "  # Skip subscriptions (provision devices only)\n"
            "  %(prog)s -W 10 -R 5 -F 3 --skip-subs\n\n"
            "  # Large fleet for load testing prep\n"
            "  %(prog)s -W 100 -R 50 -F 20 --host 192.168.1.10 --batch-size 50\n"
        ),
    )

    conn = p.add_argument_group("connection")
    conn.add_argument("--host", "-H", default="localhost", metavar="HOST",
                      help="FIWARE stack hostname or IP (default: localhost)")
    conn.add_argument(
        "--notification-url",
        "-n",
        default="http://fiware-sth-comet:8666/notify",
        metavar="URL",
        help="Webhook URL for Orion subscription notifications "
        "(default: http://fiware-sth-comet:8666/notify)",
    )

    fleet = p.add_argument_group("fleet size")
    fleet.add_argument("--water-sensors", "-W", type=int, default=10, metavar="N",
                       help="Number of WaterLevelSensor devices (default: 10)")
    fleet.add_argument("--rain-sensors", "-R", type=int, default=5, metavar="N",
                       help="Number of RainSensor devices (default: 5)")
    fleet.add_argument("--flood-zones", "-F", type=int, default=3, metavar="N",
                       help="Number of FloodZone entities (default: 3)")
    fleet.add_argument("--batch-size", type=int, default=50, metavar="N",
                       help="Devices per IoT Agent request batch (default: 50)")

    steps = p.add_argument_group("provisioning steps")
    steps.add_argument("--skip-iot", action="store_true",
                       help="Skip IoT Agent service group and device provisioning")
    steps.add_argument("--skip-orion", action="store_true",
                       help="Skip FloodZone entity creation in Orion")
    steps.add_argument("--skip-subs", action="store_true",
                       help="Skip subscription creation")

    return p


def main():
    args = build_parser().parse_args()

    log.info("FIWARE Smart Rain Monitoring — host=%s", args.host)
    health_check(args.host)

    water_sensors = make_water_sensors(args.water_sensors)
    rain_sensors  = make_rain_sensors(args.rain_sensors)
    flood_zones   = make_flood_zones(args.flood_zones)

    log.info("Fleet: %d WaterLevelSensor | %d RainSensor | %d FloodZone",
             len(water_sensors), len(rain_sensors), len(flood_zones))

    if not args.skip_iot:
        provision_service_group(args.host)
        provision_water_sensors(args.host, water_sensors, args.batch_size)
        provision_rain_sensors(args.host, rain_sensors, args.batch_size)

    if not args.skip_orion:
        provision_flood_zones(args.host, flood_zones)

    if not args.skip_subs:
        provision_subscriptions(args.host, args.notification_url)

    log.info("Provisioning complete.")


if __name__ == "__main__":
    main()
