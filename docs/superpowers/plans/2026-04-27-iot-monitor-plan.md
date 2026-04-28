# MAC Septic IoT Monitor — Implementation Plan
**Spec:** `docs/superpowers/specs/2026-04-27-iot-monitor-design.md`
**Date:** 2026-04-27
**Status:** In progress

## Methodology
- Use vibe-loop discipline: build → Playwright verify → fix → re-test → repeat (up to 30 iterations per home CLAUDE.md)
- Commit + push after every cohesive unit (per home CLAUDE.md hard rule)
- For backend-only changes without UI surface: substitute curl + log inspection + DB row check for Playwright
- Verification before completion: evidence before claiming done

## Repos touched
| Repo | Path | Role |
|---|---|---|
| react-crm-api | `/home/will/react-crm-api` | Backend, MQTT bridge, DB migrations, API routes |
| ReactCRM | `/home/will/ReactCRM` | Frontend dashboard wiring |
| mac-septic-iot-firmware | `/home/will/mac-septic-iot-firmware` (NEW) | Zephyr nRF9160 application |
| mac-septic-iot-tools | `/home/will/mac-septic-iot-tools` (NEW) | Simulator + provisioning + Playwright suite |

## Phase 1 — Database migrations + SQLAlchemy models
**Goal:** Schema in place, migration runs clean up + down, models importable.

Tasks:
1. Add `timescaledb` extension to Postgres (Alembic op).
2. Migration `115_iot_tables.py` — creates:
   - `iot_devices` (UUID PK, serial UNIQUE, public_key TEXT, customer_id FK, site_address JSONB, install_type ENUM, firmware_version TEXT, last_seen_at, created_at, archived_at)
   - `iot_telemetry` (PK composite (time, device_id, sensor_type), Timescale hypertable on `time`, columns per spec §8)
   - `iot_alerts` (UUID PK, device_id FK, alert_type ENUM, severity ENUM, fired_at, resolved_at, resolution_note, work_order_id FK)
   - `iot_firmware_versions` (UUID PK, version unique, signed_image_url, signature, target_install_types ARRAY, released_at)
   - `iot_device_bindings` (UUID PK, device_id FK, customer_id FK, bound_at, unbound_at, bound_by_user_id FK)
   - `iot_alert_rules` (UUID PK, rule_type ENUM, sensor_type, threshold_op, threshold_value JSONB, severity ENUM, message_template, active BOOL)
3. SQLAlchemy models in `app/models/iot_*.py` (one file per table, matching repo conv).
4. Update `app/models/__init__.py` to export new models.
5. Pydantic schemas in `app/schemas/iot_*.py`.
6. `alembic upgrade head`, verify table existence, then `alembic downgrade -1` and back up.

**Verify:** Migration up/down both succeed. `psql` confirms tables + hypertable. Models import without error in `python -c "from app.models import IoTDevice"`.

**Commit message:** `feat(iot): add IoT device + telemetry schema (Phase 1 of monitor)`

## Phase 2 — Replace iot.py stubs with real API
**Goal:** All `/api/v2/iot/*` routes implemented, returning real data.

Tasks:
1. Replace 441-line stub `app/api/v2/iot.py` with real implementation.
2. Endpoints per spec §9: list/create/get/bind/unbind devices, query telemetry, list/ack alerts, firmware release/dispatch/download.
3. Use `selectinload` for relationships (per backend.md rule).
4. Use `UUIDStr` Pydantic type (per backend.md rule).
5. Static routes BEFORE catch-all `/{id}` routes (per backend.md rule).
6. Activity middleware tracking on POST/PATCH/PUT/DELETE (already automatic).
7. WebSocket broadcast on device-bind, alert-fire, alert-ack events.

**Verify:** OpenAPI spec at `/openapi.json` shows new routes. curl-driven smoke test of each route. `pytest` passes.

**Commit message:** `feat(iot): implement real /api/v2/iot endpoints (Phase 2)`

## Phase 3 — MQTT broker + bridge
**Goal:** EMQX broker running on Railway, Python bridge subscribed, telemetry persisted, rules evaluated, alerts dispatched.

Tasks:
1. EMQX Railway service (Dockerfile + railway.json or templated deploy).
2. mTLS configuration: server cert (Let's Encrypt or Railway-managed), per-device client cert validation.
3. ACL rules: device CN matches topic UUID.
4. Python bridge service `app/services/iot/mqtt_bridge.py`:
   - `paho-mqtt` async client
   - Subscribes `devices/+/+`
   - Validates payload schema (Pydantic)
   - Writes telemetry to `iot_telemetry` hypertable
   - Evaluates `iot_alert_rules` synchronously
   - Creates `iot_alerts` rows
   - Dispatches SMS via existing `Message` row → APScheduler → Twilio path
   - Broadcasts WebSocket events
5. Bridge runs as APScheduler-managed startup task, restarts on failure.
6. Rule engine v1 — threshold/rate-of-change/digital-high/missing-heartbeat per spec §8.

**Verify:** Local `mosquitto_pub` to dev EMQX → bridge processes → DB row appears → Twilio test number gets SMS.

**Commit message:** `feat(iot): add MQTT broker + bridge service (Phase 3)`

## Phase 4 — Frontend dashboard wiring
**Goal:** IoT dashboard renders real data; device detail page works; bind modal works; nav shows IoT.

Tasks:
1. Wire `useDevices()`, `useDeviceAlerts()`, `useMaintenanceRecommendations()` hooks to real endpoints.
2. Update `src/api/types/iot.ts` to match real schema.
3. New page `src/features/iot/DeviceDetail.tsx` with telemetry charts (recharts) and alert history.
4. New `src/features/iot/DeviceBindModal.tsx` for tech onboarding.
5. Add **Devices** to main nav (sidebar/topnav).
6. Mobile responsive verification.
7. Filter known console errors per frontend.md rule.

**Verify:** Playwright login → click "Devices" nav → see device list (using simulated data) → click device → see detail charts → bind a new device → see alert fire.

**Commit message:** `feat(iot): wire dashboard, build DeviceDetail + BindModal (Phase 4)`

## Phase 5 — Simulated device + Playwright E2E
**Goal:** Repeatable end-to-end test without hardware: simulated device → MQTT → bridge → DB → dashboard → SMS.

Tasks:
1. `mac-septic-iot-tools/simulator.py` — Python script using paho-mqtt, generates client cert on first run, publishes plausible telemetry on cadence, can fire simulated alarm/alarm-resolve events.
2. Playwright spec at `ReactCRM/tests/iot-e2e.spec.ts`:
   - Login as admin
   - Navigate to /iot
   - Assert device list contains simulator's device
   - Trigger simulator alarm
   - Wait for WebSocket event
   - Assert alert appears in dashboard
   - Acknowledge alert
   - Assert alert state updated
3. Wire test to CI (or document local-run command).

**Verify:** `npx playwright test iot-e2e.spec.ts` passes from clean DB.

**Commit message:** `feat(iot): add device simulator + Playwright E2E tests (Phase 5)`

## Phase 6 — Firmware skeleton (Zephyr / nRF9160)
**Goal:** Compilable firmware that, given hardware, would publish telemetry per spec. Hardware-untested but lint/compile clean.

Tasks:
1. New repo `mac-septic-iot-firmware` with Zephyr application skeleton (NCS).
2. `prj.conf` — LTE-M + NB-IoT, MQTT, mTLS, MCUBoot dual-bank, sleep modes.
3. Sensor drivers (mocked at compile time, real code in source):
   - GPIO opto-isolated digital input (alarm tap)
   - ADC for CT clamp current sensors
   - I²C/SPI for ultrasonic level sensor
   - RS-485 for soil moisture probe
4. Main loop: deep sleep → RTC wake → sample → publish → confirm → sleep.
5. MQTT client with mTLS using Nordic's secure key storage.
6. OTA receiver: subscribe `devices/{uuid}/cmd`, parse manifest, fetch image, verify Ed25519, MCUBoot swap.
7. Cert provisioning hook (read from secure storage at boot).

**Verify:** `west build` succeeds for `nrf9160dk_nrf9160_ns` target. Static analysis (`compiledb`, `clang-tidy`) passes.

**Commit message:** `feat(iot): firmware skeleton for nRF9160 — compile clean, hardware-untested (Phase 6)`

## Phase 7 — Provisioning tooling + install SOPs
**Goal:** Manufacturing path documented + scripted; field tech can bind a device end-to-end.

Tasks:
1. `mac-septic-iot-tools/provisioning.py` — generates serial + X.509 keypair, programs nRF9160 via Nordic Programmer, registers public key with CRM, prints QR label.
2. SOP doc: `mac-septic-docs/iot-install-sop-conventional.md`.
3. SOP doc: `mac-septic-docs/iot-install-sop-atu.md`.
4. SOP doc: `mac-septic-docs/iot-decommission-sop.md`.
5. Tech-facing UI walk: bind modal → calibrate sensors → complete install.

**Verify:** Walkthrough in CRM dashboard binds simulator-generated device.

**Commit message:** `feat(iot): add provisioning tooling + tech install SOPs (Phase 7)`

## Definition of done
- All 7 phases committed + pushed to GitHub
- Railway deploy verified via `railway status` (per home rule)
- Playwright E2E test (Phase 5) green
- Spec + plan referenced in `mac-septic-docs/ROADMAP.md` so future sessions can pick up
- Open hardware dependencies clearly listed (DK purchase, sensor card vendor selection, enclosure fabricator)
