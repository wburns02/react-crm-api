"""Seed default IoT alert rules.

Idempotent — safe to re-run. Will skip rules that already exist by name.

Usage:
  python scripts/seed_iot_alert_rules.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from sqlalchemy import select

from app.database import async_session_maker
from app.models.iot import IoTAlertRule


DEFAULT_RULES = [
    {
        "name": "OEM Alarm Fire",
        "description": "OEM panel alarm circuit went high — immediate notification.",
        "rule_type": "digital_high",
        "sensor_type": "oem_alarm",
        "alert_type": "oem_alarm_fire",
        "severity": "critical",
        "config": {},
        "message_template": "OEM alarm panel is firing on {device_serial}. Tech roll required.",
    },
    {
        "name": "Power Loss",
        "description": "Device reports loss of AC power.",
        "rule_type": "digital_high",
        "sensor_type": "power_loss",
        "alert_type": "power_loss",
        "severity": "high",
        "config": {},
        "message_template": "Power lost at {device_serial}. Running on UPS battery.",
    },
    {
        "name": "Pump Stalled (Overcurrent)",
        "description": "Pump current >= stalled-rotor threshold.",
        "rule_type": "threshold_gt",
        "sensor_type": "pump_current",
        "alert_type": "pump_overcurrent",
        "severity": "high",
        "config": {"threshold": 8.0, "unit": "A"},
        "message_template": "Pump on {device_serial} at {value}A — possible stall.",
    },
    {
        "name": "Pump Dry Run",
        "description": "Pump current too low while runtime active.",
        "rule_type": "threshold_lt",
        "sensor_type": "pump_current",
        "alert_type": "pump_dry_run",
        "severity": "high",
        "config": {"threshold": 0.5, "unit": "A"},
        "message_template": "Pump on {device_serial} drawing only {value}A — possible dry run.",
    },
    {
        "name": "Pump Degradation Trend",
        "description": "Pump current trending up >5% over 7 days (predictive).",
        "rule_type": "rate_of_change",
        "sensor_type": "pump_current",
        "alert_type": "pump_degradation",
        "severity": "low",
        "config": {"window_hours": 168, "pct_change": 5.0, "direction": "up"},
        "message_template": "Pump on {device_serial} showing 5%+ current rise over 7 days.",
        "cold_start_grace_hours": 168,
    },
    {
        "name": "Drain Field Saturation",
        "description": "Soil moisture exceeds saturation threshold (kept for installs that include the optional soil probe).",
        "rule_type": "threshold_gt",
        "sensor_type": "soil_moisture",
        "alert_type": "drain_field_saturation",
        "severity": "high",
        "config": {"threshold": 70.0, "unit": "pct"},
        "message_template": "Drain field saturation at {value}% on {device_serial}.",
    },
    {
        "name": "ATU Air Pump Failure",
        "description": "Aerobic treatment unit air-line pressure dropped below operational threshold — bacteria die in 24-48h without aeration.",
        "rule_type": "threshold_lt",
        "sensor_type": "air_pressure",
        "alert_type": "air_pump_failure",
        "severity": "critical",
        "config": {"threshold": 1.0, "unit": "psi_gauge"},
        "message_template": "ATU air line on {device_serial} at {value} PSI — air pump may have failed. Roll a tech.",
        "install_types": ["atu"],
    },
    {
        "name": "ATU Air Pump Degradation",
        "description": "ATU air-line pressure trending down >10% over 7 days — diffuser may be clogging.",
        "rule_type": "rate_of_change",
        "sensor_type": "air_pressure",
        "alert_type": "air_pump_degradation",
        "severity": "low",
        "config": {"window_hours": 168, "pct_change": 10.0, "direction": "down"},
        "message_template": "ATU air pressure on {device_serial} trending down — diffuser cleaning may be due.",
        "install_types": ["atu"],
        "cold_start_grace_hours": 168,
    },
    {
        "name": "Tank Approaching Service Level",
        "description": "Tank level above pump-out threshold.",
        "rule_type": "threshold_gt",
        "sensor_type": "tank_level",
        "alert_type": "tank_high_level",
        "severity": "medium",
        "config": {"threshold": 85.0, "unit": "pct"},
        "message_template": "Tank on {device_serial} at {value}% — service due.",
    },
    {
        "name": "Missing Heartbeat",
        "description": "Device has not checked in for 36+ hours.",
        "rule_type": "missing_heartbeat",
        "sensor_type": None,
        "alert_type": "missing_heartbeat",
        "severity": "medium",
        "config": {"max_silence_hours": 36},
        "message_template": "{device_serial} has been silent for {value:.1f} hours.",
    },
    {
        "name": "Low Battery",
        "description": "UPS battery below 20%.",
        "rule_type": "threshold_lt",
        "sensor_type": "battery_pct",
        "alert_type": "low_battery",
        "severity": "low",
        "config": {"threshold": 20.0, "unit": "pct"},
        "message_template": "UPS battery at {value}% on {device_serial}.",
    },
    {
        "name": "Tamper Detected",
        "description": "Cabinet door opened off-schedule.",
        "rule_type": "digital_high",
        "sensor_type": "tamper",
        "alert_type": "tamper",
        "severity": "medium",
        "config": {},
        "message_template": "Cabinet on {device_serial} was opened.",
    },
]


async def seed():
    async with async_session_maker() as db:
        existing_q = select(IoTAlertRule.name)
        existing_names = set((await db.execute(existing_q)).scalars().all())
        created = 0
        skipped = 0
        for rule_def in DEFAULT_RULES:
            if rule_def["name"] in existing_names:
                skipped += 1
                continue
            rule = IoTAlertRule(
                id=uuid.uuid4(),
                name=rule_def["name"],
                description=rule_def["description"],
                rule_type=rule_def["rule_type"],
                sensor_type=rule_def["sensor_type"],
                alert_type=rule_def["alert_type"],
                severity=rule_def["severity"],
                config=rule_def["config"],
                message_template=rule_def["message_template"],
                cold_start_grace_hours=rule_def.get("cold_start_grace_hours"),
                active=True,
            )
            db.add(rule)
            created += 1
        await db.commit()
        print(f"Seeded {created} new rules, skipped {skipped} existing.")


if __name__ == "__main__":
    asyncio.run(seed())
