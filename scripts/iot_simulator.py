"""IoT device simulator — publishes plausible MQTT telemetry for testing.

Stands in for real hardware during development. Lets us verify the cloud
pipeline (broker → bridge → DB → rule engine → alert dispatch → SMS + WS)
end-to-end without nRF9160 silicon.

Usage:
  # Register a simulated device first:
  python scripts/iot_simulator.py register --serial SIM001 --crm-url https://...
  # Then publish telemetry:
  python scripts/iot_simulator.py run --serial SIM001 --duration 60

  # Trigger a simulated alarm:
  python scripts/iot_simulator.py alarm --serial SIM001
"""
import argparse
import asyncio
import json
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import aiomqtt  # noqa
except ImportError:
    print("Install: pip install aiomqtt requests cryptography")
    sys.exit(1)

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def gen_keypair_and_cert(serial: str, ca_subject: str = "mac-septic-iot-ca-dev"):
    """Generate a self-signed cert for a simulated device.

    In production, devices use certs signed by the real CA. For local dev,
    self-signed is fine if the broker is configured to accept them.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"device-{serial}"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 10))
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return cert_pem, key_pem


def register_device(args):
    cert_pem, key_pem = gen_keypair_and_cert(args.serial)
    keys_dir = Path(args.keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{args.serial}.crt").write_text(cert_pem)
    (keys_dir / f"{args.serial}.key").write_text(key_pem)
    print(f"Wrote cert + key to {keys_dir}/{args.serial}.{{crt,key}}")

    headers = {"Authorization": f"Bearer {args.crm_token}"} if args.crm_token else {}
    payload = {
        "serial": args.serial,
        "public_key": cert_pem,
        "hardware_revision": "SIM-1.0",
        "firmware_version": "sim-0.1.0",
        "notes": "Simulated device for E2E testing",
    }
    resp = requests.post(
        f"{args.crm_url}/api/v2/iot/devices",
        json=payload,
        headers=headers,
        timeout=15,
    )
    if resp.status_code == 201:
        device = resp.json()
        print(f"Registered device {args.serial} (id={device['id']})")
        (keys_dir / f"{args.serial}.uuid").write_text(device["id"])
    elif resp.status_code == 409:
        print(f"Device {args.serial} already registered")
    else:
        print(f"Registration failed: {resp.status_code} {resp.text}")
        sys.exit(1)


def _device_uuid_for(serial: str, keys_dir: Path) -> str:
    p = keys_dir / f"{serial}.uuid"
    if not p.exists():
        print(f"No UUID file for {serial} — register first.")
        sys.exit(1)
    return p.read_text().strip()


def _cert_paths_for(serial: str, keys_dir: Path) -> tuple[str, str]:
    return (
        str(keys_dir / f"{serial}.crt"),
        str(keys_dir / f"{serial}.key"),
    )


def _client_kwargs(args, serial: str):
    kwargs = {
        "hostname": args.broker_host,
        "port": args.broker_port,
        "client_id": f"device-{serial}",
    }
    if args.tls:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE if args.insecure else ssl.CERT_REQUIRED
        if args.ca_cert:
            ctx.load_verify_locations(cafile=args.ca_cert)
        cert, key = _cert_paths_for(serial, Path(args.keys_dir))
        ctx.load_cert_chain(certfile=cert, keyfile=key)
        kwargs["tls_context"] = ctx
    if args.username:
        kwargs["username"] = args.username
        kwargs["password"] = args.password
    return kwargs


def _telemetry_payload(install_type: str = "atu") -> dict:
    """Plausible telemetry payload for one check-in."""
    now = datetime.now(timezone.utc).isoformat()
    base = [
        {
            "sensor_type": "pump_current",
            "value": round(random.uniform(2.0, 5.5), 2),
            "raw": {"unit": "A", "samples": 60},
        },
        {
            "sensor_type": "tank_level",
            "value": round(random.uniform(20, 60), 1),
            "raw": {"unit": "pct"},
        },
        {
            "sensor_type": "soil_moisture",
            "value": round(random.uniform(15, 45), 1),
            "raw": {"unit": "pct"},
        },
        {
            "sensor_type": "battery_pct",
            "value": round(random.uniform(85, 100), 1),
            "raw": {"unit": "pct"},
        },
        {
            "sensor_type": "power_loss",
            "value": 0.0,
        },
        {
            "sensor_type": "tamper",
            "value": 0.0,
        },
    ]
    if install_type == "atu":
        base.extend([
            {"sensor_type": "aerator_current", "value": round(random.uniform(1.5, 3.0), 2)},
            {"sensor_type": "treatment_tank_level", "value": round(random.uniform(40, 70), 1)},
            {"sensor_type": "chlorinator_flow", "value": round(random.uniform(0.5, 2.0), 2)},
        ])
    return {"time": now, "readings": base}


async def run_simulator(args):
    serial = args.serial
    keys_dir = Path(args.keys_dir)
    device_uuid = _device_uuid_for(serial, keys_dir)
    topic_telemetry = f"devices/{device_uuid}/telemetry"
    topic_heartbeat = f"devices/{device_uuid}/heartbeat"

    stop_evt = asyncio.Event()

    def _sigterm(*_):
        stop_evt.set()
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)

    end_time = time.monotonic() + args.duration if args.duration > 0 else None

    async with aiomqtt.Client(**_client_kwargs(args, serial)) as client:
        print(f"[{serial}] Connected to {args.broker_host}:{args.broker_port}")
        while not stop_evt.is_set():
            payload = _telemetry_payload(args.install_type)
            await client.publish(topic_telemetry, json.dumps(payload).encode("utf-8"))
            print(f"[{serial}] Published {len(payload['readings'])} readings to {topic_telemetry}")
            await client.publish(
                topic_heartbeat,
                json.dumps({"time": datetime.now(timezone.utc).isoformat()}).encode("utf-8"),
            )
            if end_time and time.monotonic() >= end_time:
                break
            try:
                await asyncio.wait_for(stop_evt.wait(), timeout=args.interval)
            except asyncio.TimeoutError:
                pass


async def fire_alarm(args):
    serial = args.serial
    keys_dir = Path(args.keys_dir)
    device_uuid = _device_uuid_for(serial, keys_dir)
    topic = f"devices/{device_uuid}/alarm"
    async with aiomqtt.Client(**_client_kwargs(args, serial)) as client:
        payload = {
            "time": datetime.now(timezone.utc).isoformat(),
            "active": not args.clear,
            "panel_signal": "high_water" if not args.clear else "clear",
        }
        await client.publish(topic, json.dumps(payload).encode("utf-8"))
        print(f"[{serial}] {'CLEARED' if args.clear else 'FIRED'} alarm on {topic}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys-dir", default="/tmp/iot-sim-keys")
    parser.add_argument("--broker-host", default=os.environ.get("IOT_MQTT_BROKER_HOST", "localhost"))
    parser.add_argument("--broker-port", type=int, default=int(os.environ.get("IOT_MQTT_BROKER_PORT", "1883")))
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS hostname/cert verification (dev only)")
    parser.add_argument("--ca-cert", default=None)
    parser.add_argument("--username", default=os.environ.get("IOT_MQTT_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("IOT_MQTT_PASSWORD"))

    sub = parser.add_subparsers(dest="cmd", required=True)

    reg = sub.add_parser("register", help="Generate cert + register device with CRM")
    reg.add_argument("--serial", required=True)
    reg.add_argument("--crm-url", required=True)
    reg.add_argument("--crm-token", default=os.environ.get("CRM_BEARER_TOKEN"))

    runp = sub.add_parser("run", help="Publish telemetry on a cadence")
    runp.add_argument("--serial", required=True)
    runp.add_argument("--interval", type=float, default=10.0)
    runp.add_argument("--duration", type=float, default=0.0, help="0 = forever")
    runp.add_argument("--install-type", choices=["conventional", "atu"], default="atu")

    al = sub.add_parser("alarm", help="Fire (or clear) an OEM alarm event")
    al.add_argument("--serial", required=True)
    al.add_argument("--clear", action="store_true", help="Clear the alarm rather than fire it")

    args = parser.parse_args()
    if args.cmd == "register":
        register_device(args)
    elif args.cmd == "run":
        asyncio.run(run_simulator(args))
    elif args.cmd == "alarm":
        asyncio.run(fire_alarm(args))


if __name__ == "__main__":
    main()
