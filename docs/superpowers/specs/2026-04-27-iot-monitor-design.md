# MAC Septic IoT Monitor — Design Spec
**Codename:** Watchful
**Date:** 2026-04-27
**Author:** Claude (with Will Burns)
**Status:** Approved for build

---

## 1. Overview

A cellular IoT module that **notifies homeowners and the MAC Septic dispatch desk when problems develop in residential septic systems** — both aerobic treatment units (ATU) and conventional gravity/pump-to-field systems. The device is explicitly **a notification system, not an alarm system**: it relays the OEM alarm panel and adds predictive telemetry, but it never replaces the regulated alarm.

The product opens a wedge between two existing competitors: SeptiSense ($400 + $5.92/mo, WiFi-first, alarm-tap only) and Septilink ($499 + $22.50/mo, cellular-first, feature-shallow). MAC Septic's structural advantage is being a **multi-OEM service business managing 10K+ heterogeneous units** — a market segment that no incumbent serves, since OEM telemetry products (Norweco Service Pro MCD, Aquaworx Tracker, Bio-Microbics TRACK) lock to their own hardware.

## 2. Product positioning

### Notification, not alarm
- The OEM alarm panel remains the primary regulated safety device per TX 30 TAC §285, NSF 40, and equivalent state codes.
- Watchful **taps** the OEM alarm circuit via opto-isolated parallel connection. When the OEM panel fires its alarm, Watchful relays that event over cellular to the CRM and dispatches SMS to homeowner + on-call tech.
- Watchful **does not actuate, silence, suppress, or replace** any OEM alarm function.
- All marketing copy and contracts use "septic system notification service" — never "alarm system" or "monitoring guarantee."

This framing eliminates NSF/UL certification burden ($30K+, 12+ months) and dramatically narrows liability exposure.

### Differentiation features (competitively unowned)
- **Drain-field saturation monitoring** — soil-moisture probes at field edge detect biomat formation and hydraulic overload weeks before failure. Nobody else ships this.
- **Pump-current trending** — CT clamp on effluent pump leg detects bearing wear, dry-run, short-cycling, and degradation drift. ML baselining as v2.
- **Multi-OEM compatibility** — works with Norweco Singulair, Aquaworx, Bio-Microbics FAST, Hoot, Delta, Clearstream, and conventional pump panels via the same hardware.
- **TCEQ-approved electronic monitoring** — target inclusion on the TCEQ approved-hardware list to convert ATU customers from 3×/yr to 2×/yr inspection cadence (regulatory selling point).

## 3. Goals & non-goals

### Goals
- Notify customers and dispatch within 30 seconds of an OEM alarm fire.
- Predict pump and drain-field failures with at least one week of advance warning, captured as "service recommendations" in the CRM.
- Deploy autonomously at 10K+ unit scale on existing CRM infrastructure with no recurring per-device cloud fees.
- Pilot 5 devices on real customer sites within 90 days of pilot kickoff.
- Reach TCEQ approved-hardware list within 12 months of first ATU install.

### Non-goals (v1)
- Customer-facing mobile app (deferred to v2 buy-up package).
- Predictive ML rule engine (deferred to v2 once 6+ months of fleet telemetry exists).
- Replacement of OEM alarm panels (regulatory — NEVER).
- Battery-only installs (we always tap site AC; battery is UPS-only for power-loss notification).
- Customer self-install (always tech-installed for v1; v2 may explore plug-in retrofits).

## 4. System architecture

```
┌───────────────────┐         ┌──────────────────┐
│ Septic site       │         │ MQTT broker      │
│                   │         │ (EMQX, mTLS)     │
│ ┌──────────────┐  │  LTE-M  │                  │
│ │ Watchful     │──┼────────▶│ devices/+/       │
│ │ device       │  │         │   telemetry      │
│ │  - nRF9160   │  │         │   alarm-fire     │
│ │  - sensors   │  │         │   heartbeat      │
│ └──────────────┘  │         └────────┬─────────┘
└───────────────────┘                  │
                                       ▼
                            ┌──────────────────────┐
                            │ MQTT bridge          │
                            │ (Python, react-crm-  │
                            │  api process)        │
                            │  - validates payload │
                            │  - writes Timescale  │
                            │  - evaluates rules   │
                            │  - dispatches alerts │
                            └──────────┬───────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
       ┌──────────────┐      ┌────────────────┐      ┌────────────────┐
       │ TimescaleDB  │      │ Twilio SMS     │      │ WebSocket      │
       │ telemetry    │      │ (existing)     │      │ broadcast      │
       │ hypertable   │      │ → homeowner    │      │ → IoTDashboard │
       └──────────────┘      │ → on-call tech │      │   live updates │
                             └────────────────┘      └────────────────┘
```

## 5. Hardware design

### Compute / radio
- **Nordic nRF9160 SiP** (System-in-Package). Integrates ARM Cortex-M33, LTE-M / NB-IoT modem, GPS, and secure key storage in one part. Pre-certified modular approval (FCC ID, PTCRB, AT&T, Verizon, T-Mobile). No separate host MCU.
- **Reference antenna design** (Nordic Thingy:91 reference) — deviation requires intentional-radiator FCC testing; we follow the reference.

### Sensor expansion bus
A modular base PCB exposes:
- **2× RS-485** (industrial sensor backbone — soil moisture probes, ATU-specific signals)
- **2× 4–20mA loop** (pressure transducers, level sensors)
- **2× 0–10V analog** (legacy sensor compatibility)
- **6× opto-isolated digital input** (alarm taps, float switches, pump-on signal)
- **2× CT clamp current sensor input** (pump current, aerator current)

This lets one chassis cover both conventional installs (4 sensors populated) and ATU installs (full stack), without different SKUs.

### Sensor cards (v1 catalog)
| Card | Use | Install type |
|---|---|---|
| `OEM-ALARM-TAP` | Opto-isolated parallel to OEM alarm circuit | Both |
| `PUMP-CT-30A` | Effluent pump current sensor | Both |
| `LEVEL-ULTRASONIC` | Pump-tank or treatment-tank level | Both |
| `SOIL-MOIST-RS485` | Drain-field saturation probe | Both |
| `AERATOR-CT-15A` | ATU aerator current sensor | ATU |
| `ATU-CONTROL-BUS` | Reads ATU panel control signals | ATU |
| `CHLORINATOR-FLOW` | Chlorinator presence / flow | ATU |

### Power
- **AC tap** at OEM panel (always required — site has 120V or 240V at the panel).
- **LiSOCl₂ primary cell UPS** — Tadiran TL-5930F or equivalent. Cold-tolerant (-55°C to +85°C), 10-year shelf life, sized for 7 days of post-power-loss notification cadence.
- **Power-loss event** — immediate cellular notification, then sleep until power restoration or battery exhaustion.

### Enclosure
- **IP66 polycarbonate** with UV-stable additive package (10-yr outdoor service life).
- Internal **conformal coating** on PCB (methane + condensation tolerance — septic gas eats bare copper in weeks).
- **Surge protection**: TVS diodes on every external input, MOVs on AC tap, isolated current sensors.
- **Tamper-evident seal** + cabinet-door reed switch.

### BOM target
- $80–90 at 1K-unit volume to support $349 retail (75% hardware margin).
- Validated against competitive research: Septilink BOM estimated at $50–60, SeptiSense BOM estimated at $40–50; our higher BOM reflects sensor expansion + ATU compatibility.

## 6. Firmware design

### Stack
- **Zephyr RTOS** on nRF9160 (Nordic's official SDK ships Zephyr).
- Build via **nRF Connect SDK (NCS)** with `west` build system.
- C, no Rust for v1 (NCS support for Rust is alpha-grade).

### Behavior
- **Default cadence: 2 check-ins per day** (12:00 UTC, 00:00 UTC) — sleeps 12 hours between, wakes, samples all populated sensors, batch-publishes via MQTT, sleeps again.
- **Immediate fire on OEM alarm interrupt** — opto-isolated digital input wired to GPIO with hardware interrupt; wakes from System OFF mode, publishes alarm event, returns to sleep within 5 seconds.
- **Adaptive cadence** — when a predictive threshold is trending toward an alert (e.g., pump current up 5% over 7 days, drain field >70% saturation), cadence steps to hourly until cleared. Caps at 24 events/day to bound data usage.
- **Battery telemetry every check-in** (voltage, AC-present flag).

### Power budget (target)
- Sleep current: <5 µA (System OFF mode, RAM retention off)
- Wake/sample/publish: <30 seconds, ~80 mA peak during LTE-M TX
- Daily energy: ~20 J at 2× cadence
- LiSOCl₂ TL-5930F: ~50,000 J usable energy → 7+ years on battery alone (we run on AC; this just sizes the UPS)

### OTA firmware update
- **Modem firmware (Nordic-managed):** delta updates via Nordic's modem image manager.
- **Application firmware (us):** server publishes a firmware manifest to the device's MQTT command topic (`devices/{uuid}/cmd`); manifest includes target version + signed download URL. Device fetches binary, verifies Ed25519 signature, swaps via MCUBoot dual-bank, reboots into new image. If the new image fails to confirm-good within 60 seconds of boot, MCUBoot reverts.
- **Pre-OTA pilot path:** USB DFU via Nordic Programmer for the 5-device pilot (faster iteration during firmware shakedown). OTA goes live before pilot exit.

### Cert-based device identity
- Each device manufactured with unique X.509 client cert burned into nRF9160 secure key storage at provisioning.
- Cert is the device's MQTT auth credential (mTLS to broker).
- Public key registered in CRM `device` table at manufacture; device can't impersonate another device.

## 7. Connectivity

### Cellular
- **1NCE prepaid IoT SIM** — $10/SIM for 10 years / 500 MB. Multi-carrier roaming (T-Mobile, AT&T, Verizon, plus international). No SaaS in path. Flat upfront cost matches "no recurring fees" stance.
- **LTE-M primary, NB-IoT fallback** — nRF9160 supports both. LTE-M for normal ops; NB-IoT for rural dead zones where LTE-M coverage is poor.
- **Data budget:** 2 events/day × ~1 KB/event = ~700 KB/year + alarm-fire events (<10/year typical) = ~1 MB/year per device. 500 MB SIM = 500-year theoretical headroom.

### Why not Blues Notecard / Particle / WiFi
Decision matrix locked during brainstorming:
- WiFi: out (rural panel boxes 50ft from house, homeowner reboots).
- Particle Boron: out (~$50/device/yr, unnecessary lock-in at scale).
- Blues Notecard: rejected in favor of fully sovereign stack (Notehub SaaS dependency, SIM lock, Notecard internal MCU runs closed-source firmware).
- BYO with nRF9160 + 1NCE SIM + self-hosted MQTT: chosen. Eliminates every SaaS dependency in the device-to-CRM path.

## 8. Cloud / backend

### MQTT broker
- **EMQX 5** (open-source edition) — scales to millions of concurrent connections, mTLS native, ACL by client cert CN, MQTT 5.0 features (subscription identifiers, server redirects, message expiry).
- Deployed as its own Railway service (`emqx-broker`) or self-hosted on r730 with Cloudflare Tunnel for public TLS endpoint.
- ACL: device with cert CN `device-{uuid}` can publish to `devices/{uuid}/+` and subscribe to `devices/{uuid}/cmd` only.

### MQTT bridge service
- Python process inside `react-crm-api` (Railway service) — subscribes to `devices/+/+`, validates payload, writes telemetry to TimescaleDB, evaluates rules, dispatches alerts via existing Twilio path.
- Uses `paho-mqtt` async client. Single subscriber for v1; horizontal scaling via shared subscriptions when fleet exceeds ~5K devices.

### Database
- **Existing PostgreSQL on Railway** (CRM database) — extend with **TimescaleDB extension** for telemetry hypertable. Already a Postgres extension, no new database.
- New tables (Alembic migration):
  - `iot_devices` — device registry (id, serial, public_key, customer_id, site_address, install_type, firmware_version, last_seen_at, created_at, archived_at)
  - `iot_telemetry` — time-series readings (Timescale hypertable, partitioned by `time`; columns: device_id, sensor_type, value_numeric, value_text, raw_payload JSONB)
  - `iot_alerts` — fired alerts (id, device_id, alert_type, severity, fired_at, resolved_at, resolution_note, work_order_id FK)
  - `iot_firmware_versions` — firmware release registry (version, signed_image_url, signature, target_install_types, released_at)
  - `iot_device_bindings` — audit log of device-to-customer pairing events
  - `iot_alert_rules` — threshold + adaptive rules (rule_type, sensor_type, threshold_op, threshold_value, severity, message_template, active)

### Rule engine v1
Simple threshold-based, evaluated synchronously in the MQTT bridge on every telemetry write. Rule types:
- `THRESHOLD_GT` / `THRESHOLD_LT` — fire when sensor reading crosses threshold
- `RATE_OF_CHANGE` — fire when reading changes >X% over Y hours
- `DIGITAL_HIGH` — fire when digital input goes high (alarm tap)
- `MISSING_HEARTBEAT` — fire when device hasn't checked in within expected window (cron-driven, every 15 min)

Rule outcomes create `iot_alerts` rows + dispatch SMS via existing Twilio path + WebSocket broadcast to dashboard.

### v2 ML extension
Reserved schema fields for ML feature scores (`prediction_score`, `prediction_confidence`, `model_version`) on the alerts table. Not populated v1.

## 9. CRM integration

### Replacing the existing IoT stub
- `/home/will/react-crm-api/app/api/v2/iot.py` (441 lines, currently returns empty stubs with comment "IoT not yet implemented") — replaced with real implementation.
- Existing route shapes match what the frontend already calls — minimize frontend churn.

### New API surface
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v2/iot/devices` | List devices (filter by customer, status) |
| `POST` | `/api/v2/iot/devices` | Register a manufactured device (admin) |
| `GET` | `/api/v2/iot/devices/{id}` | Device detail with recent telemetry |
| `POST` | `/api/v2/iot/devices/{id}/bind` | Pair device to customer + site (tech action) |
| `POST` | `/api/v2/iot/devices/{id}/unbind` | Unpair (decommission, transfer) |
| `GET` | `/api/v2/iot/telemetry` | Query telemetry (device, sensor, time range) |
| `GET` | `/api/v2/iot/alerts` | List alerts (filter by device, severity, status) |
| `PATCH` | `/api/v2/iot/alerts/{id}` | Acknowledge / resolve alert |
| `GET` | `/api/v2/iot/firmware/download/{token}` | Signed-URL firmware binary download (token-bound, short-lived) |
| `POST` | `/api/v2/iot/firmware` | Release a firmware version (admin) |
| `POST` | `/api/v2/iot/firmware/{version}/dispatch` | Trigger OTA rollout (publishes manifest via MQTT to target device set) |

### Auth
- All routes use existing `get_current_user` dependency (cookie/JWT auth, same as other CRM routes).
- Firmware OTA does NOT use HTTP — instead, the server publishes a firmware manifest to `devices/{uuid}/cmd` (MQTT, mTLS-authenticated). The manifest includes a signed download URL (short-lived, server-issued) for the binary. Device verifies Ed25519 signature on the image before flash, regardless of how it was fetched. This avoids HTTP mTLS termination complexity.

### Reusing existing patterns
- **Alert SMS:** create outbound `Message` row → APScheduler picks up → Twilio sends. Identical to existing flow used for booking confirmations and missed-call SMS.
- **WebSocket broadcast:** `await manager.broadcast_event("iot_alert", payload)` — identical to RingCentral SMS-received broadcast.
- **Notification table:** create `Notification` row for ops dashboard inbox.

## 10. Dashboard / frontend

### Existing scaffold
`/home/will/ReactCRM/src/features/iot/IoTDashboard.tsx` already has shell components:
- Stats cards (total devices, online, warnings, critical, offline, active alerts, maintenance due)
- Device list section
- Alerts section
- Maintenance recommendations section
- Hooks: `useDevices()`, `useDeviceAlerts()`, `useMaintenanceRecommendations()`
- Types: `/home/will/ReactCRM/src/api/types/iot.ts`

### v1 work
- Wire hooks to real endpoints (currently stubbed).
- Add `<DeviceDetail />` page at `/iot/devices/{id}` with telemetry charts (recharts) and alert history.
- Add `<DeviceBindModal />` for tech onboarding flow.
- Add **Devices** to the main nav (currently no link).
- Mobile responsive (per home `frontend.md` rule).

### Customer portal extension (deferred to v2)
- Customer-facing dashboard at `/portal/iot` — read-only view of their device, recent alerts, system status.
- Buy-up package, separate spec.

## 11. Provisioning & onboarding

### Manufacturing flow
1. PCB assembled with unique 128-bit serial burned at programming station.
2. Nordic Programmer burns nRF9160 firmware + generates X.509 keypair, stores private key in nRF9160 secure storage, exports public key.
3. Provisioning script POSTs `(serial, public_key, manufactured_at)` to `/api/v2/iot/devices` (admin endpoint). Creates an unbound `iot_devices` row.
4. QR code label printed with serial encoded — applied to enclosure.

### Field install flow
1. Tech arrives at customer site with device + sensor cards per install type.
2. Mounts device, runs sensor wiring per install SOP.
3. Powers on device. First check-in publishes "I'm alive, here's my serial."
4. Tech opens CRM mobile (or new install-app page), scans QR code, selects customer + site, presses "Bind."
5. Backend creates `iot_device_bindings` row, updates `iot_devices.customer_id`, broadcasts WebSocket event.
6. Tech runs sensor calibration (zero-out CT clamps, water-line calibration on level sensor) via "Calibrate" button. Completes install.

### Decommission / RMA flow
1. Tech presses "Unbind" on device record.
2. Device flagged `archived_at`, sensor cards inventoried, physical device returned to depot or RMA'd.

## 12. Alert taxonomy & dispatch

### Alert types
| Type | Severity | Trigger | Recipients | Marketing language |
|---|---|---|---|---|
| `OEM_ALARM_FIRE` | Critical | Digital tap goes high | Homeowner SMS, on-call tech SMS, dashboard | "Your septic alarm is on" |
| `POWER_LOSS` | High | AC-present flag false | Homeowner SMS, dashboard | "We've lost power at your septic system" |
| `PUMP_OVERCURRENT` | High | Pump current > stalled-rotor threshold | Tech SMS, dashboard | "Pump may be stalled" |
| `PUMP_DRY_RUN` | High | Pump current low + runtime > threshold | Tech SMS, dashboard | "Pump may be running dry" |
| `PUMP_SHORT_CYCLE` | Medium | Cycles/hour > threshold | Dashboard | Service recommendation |
| `PUMP_DEGRADATION` | Low | 7-day current trend up >5% (suppressed for first 7 days post-install) | Dashboard | Service recommendation |
| `DRAIN_FIELD_SATURATION` | High | Soil moisture > saturation threshold | Tech SMS, dashboard | "Drain field showing saturation" |
| `TANK_HIGH_LEVEL` | Medium | Tank level > pump-out threshold | Dashboard | "Tank approaching service level" |
| `MISSING_HEARTBEAT` | Medium | No check-in for 36+ hours | Dashboard | "Device has gone quiet" |
| `LOW_BATTERY` | Low | UPS battery <20% | Dashboard | Service recommendation |
| `TAMPER` | Medium | Cabinet door opened off-schedule | Dashboard | "Cabinet accessed" |

### Dispatch routing
- Critical → SMS to homeowner + on-call tech + dashboard alert + WebSocket push.
- High → SMS to on-call tech + dashboard alert + WebSocket push.
- Medium → dashboard alert + WebSocket push (no SMS to avoid alert fatigue).
- Low → dashboard alert only (rolls up to daily digest).

## 13. Security

- **mTLS** on all device-to-broker connections (X.509 client cert per device).
- **Ed25519 signatures** on all OTA firmware images; device verifies before swap.
- **Postgres at rest:** unchanged from existing CRM (Railway-managed encryption at rest).
- **MQTT topic ACLs:** device CN restricted to `devices/{own-uuid}/+`.
- **No shared secrets** in firmware (no API key per device — cert is the credential).
- **Penetration test** before first paying customer (engage external firm).

## 14. Scaling

### v1 capacity (10K devices)
- 10K × 2 events/day = 20K events/day baseline (negligible for EMQX + Timescale).
- Alarm-fire events ~1% of devices/day worst case = ~100 events/day extra.
- Adaptive cadence escalations bounded at 24/day per device — worst case 240K events/day if every device escalates simultaneously (won't happen).
- Total worst-case ingest: <1M events/day, ~30M/month. TimescaleDB on a single Postgres node handles this with comfortable margin given hypertable partitioning.

### Beyond 10K
- EMQX horizontal scale via cluster mode.
- Timescale partitioning by `time` (1-day chunks) and optionally by `device_id` once beyond 50K devices.
- MQTT bridge horizontal scale via shared subscriptions.

## 15. Liability, contracts, regulatory

### Service agreement (must-have, not optional)
- Device is **supplemental notification only**; OEM alarm panel is the primary safety device.
- No SLA on notification delivery (cellular outages, broker downtime, customer's panel maintenance issues).
- Customer maintains OEM panel under separate maintenance contract.
- Customer responsible for payment of Watchful subscription; non-payment suspends notifications.
- Hardware warranty: 1 year manufacturing defect; sensor cards 90 days.
- Disclaimer language reviewed by attorney before first install.

### Insurance
- Product liability + technology E&O insurance review with broker before first install.
- Target: Hippo / Roost / Notion partnership for homeowner premium discount (greenfield — no septic-specific program exists today). Pursue post-pilot.

### Regulatory
- **TCEQ approved-hardware list** — Septilink already approved; we replicate their submission process. Target: approval within 12 months of first ATU install.
- **TX 30 TAC §285** — device documented as supplemental, not replacement. No filing required.
- **TN, SC** — confirm equivalent positioning is acceptable before first install in each state.
- **FCC** — modular approval inherited from nRF9160 SiP, contingent on reference antenna design.

## 16. v1 scope (build now)

### In scope
- Cloud: MQTT broker (EMQX), MQTT bridge service, TimescaleDB hypertable, all API routes, rule engine v1, alert dispatch.
- Frontend: wire IoTDashboard hooks, build `<DeviceDetail />`, `<DeviceBindModal />`, add nav link.
- Firmware: Zephyr application for nRF9160, all sensor card drivers, MQTT client with mTLS, OTA receiver, sleep/wake/cadence logic.
- Provisioning: manufacturing script, QR labeling, field bind/unbind flow.
- Simulated-device script (Python, publishes MQTT) for end-to-end testing without hardware.
- Playwright tests for the dashboard.
- Documentation: install SOP per install type, tech training material, customer-facing one-pager.

### Out of scope (deferred)
- Predictive ML rule engine (v2).
- Customer-facing mobile app (v2 buy-up).
- Customer self-install kits (v2/v3).
- Hardware verification on real silicon (until DK acquired and pilot units fabricated).
- Cellular cert testing (handled by manufacturing partner for production runs).

## 17. v2 / v3 roadmap

### v2 (after 6 months of fleet telemetry)
- Predictive ML rule engine — pump bearing wear detection, drain-field saturation forecasting.
- Customer-facing mobile app (React Native, reuse existing customer portal auth).
- Insurance carrier integration (Hippo/Roost-style discount program).
- Bulk install tooling for service-business resale.

### v3 (post-pilot validation)
- Self-install retrofit kit for non-MAC-customer DIY market.
- Multi-tenant white-label for other septic service businesses.
- Integration with regulatory reporting systems (TCEQ, TDEC, SC DHEC) for automated inspection logs.

## 18. Pilot plan

- **5 devices, 90 days, ASAP.**
- Mix: 2 conventional installs (pump + drain field focus), 3 ATU installs (full sensor stack).
- All on existing MAC Septic customers with active service relationships and willingness to call when something's weird.
- Daily team telemetry review for first 30 days, weekly thereafter.
- Capture: install-time gotchas, sensor calibration drift, methane/condensation effects, false positives, missed events, cellular dead spots.
- **Pilot success criteria:**
  - All 5 devices online and reporting at expected cadence
  - Zero false-positive alarm fires
  - At least 1 successful predictive alert resulting in proactive service call
  - Battery + power-loss notification verified on at least 2 sites
  - Drain-field saturation telemetry validated against tech ground-truth at 30-day mark

## 19. Pricing & business model

Per competitive research:
- **Hardware retail:** $349 (between SeptiSense $400 and Septilink $499; positioning as cellular-first with broader sensor coverage)
- **Subscription:** $14.99/mo (between SeptiSense $5.92 and Septilink $22.50)
- **Annual prepay:** $149/yr (15% discount, improves cash and reduces churn)
- **Bundled with maintenance contract:** $9.99/mo addon (45% discount as customer-retention play)
- **Dealer wholesale:** $249 hardware + $9/mo subscription split

Margin model:
- Hardware: $80 BOM, $349 retail = 75% gross margin
- Subscription: $14.99/mo × 12 = $179.88/yr; recurring costs ~$25/device/yr (cell, cloud, support) = 86% gross margin
- 10K-device target: $1.27M/yr recurring gross profit + one-time hardware GP

## 20. Implementation methodology

### Tools & skills
- **Build phase:** `superpowered-vibe` or `vibe-loop` skills for autonomous build/test/fix loops.
- **Verification:** Playwright on every meaningful change to the CRM dashboard surface; simulated-device script + curl + log inspection for backend-only changes.
- **Fix-test-repeat loop:** per home `CLAUDE.md` rule — when Playwright shows breakage, build a fix plan, execute, retest. Up to 30 iterations max before escalating.
- **Verification before completion:** evidence before assertions; never claim a feature works without showing test output.

### Repos
- `/home/will/react-crm-api` (existing, GitHub: wburns02/react-crm-api) — backend changes
- `/home/will/ReactCRM` (existing, GitHub: wburns02/ReactCRM) — frontend changes
- `/home/will/mac-septic-iot-firmware` (NEW) — Zephyr application + sensor drivers
- `/home/will/mac-septic-iot-mqtt-bridge` (or sub-service in react-crm-api — TBD during build)

### Commit cadence
- Commit + push after every cohesive unit of work (per home `CLAUDE.md`).
- Railway auto-deploy on push to main; verify with `railway status` per `feedback_railway_deploy_check.md`.

### Build order
1. **Database migrations** — `iot_devices`, `iot_telemetry` (Timescale), `iot_alerts`, `iot_firmware_versions`, `iot_device_bindings`, `iot_alert_rules`. Test migration up + down.
2. **SQLAlchemy models + Pydantic schemas** for above.
3. **API routes** — replace iot.py stubs with real implementation. Test each via curl + Playwright.
4. **MQTT broker** — deploy EMQX as Railway service; configure mTLS + ACL.
5. **MQTT bridge service** — Python subscriber, telemetry write path, rule engine v1.
6. **Frontend wiring** — IoTDashboard real data, DeviceDetail page, BindModal, nav link.
7. **Simulated device** — Python script publishing MQTT; validates entire cloud path end-to-end.
8. **Playwright test suite** — login → IoT dashboard → device detail → trigger simulated alarm → see SMS scheduled → see alert resolved.
9. **Firmware** — Zephyr app skeleton, sensor drivers (write-but-not-hardware-verified), MQTT client, OTA receiver. Compile clean, lint clean, simulated-device parity.
10. **Provisioning tooling** — manufacturing script, QR generator, field bind UI.
11. **Install SOPs** — per install type (conventional, ATU), written for tech consumption.
12. **Pilot prep** — purchase 5 nRF9160 DKs + sensor cards, fabricate 5 enclosures, plan first 5 customer sites.

## 21. Open questions / risks

### Open questions (will not block v1 build)
- **MQTT bridge process model — v1 decision: inside `react-crm-api` for simplicity.** Extract to its own service when fleet exceeds ~5K devices or when operational fault-isolation becomes worth the deployment cost.
- **EMQX placement — v1 decision: Railway service.** Re-evaluate r730 self-hosted with Cloudflare Tunnel once fleet grows past 1K devices and Railway egress costs become non-trivial.
- Customer-facing alert SMS phrasing — homeowner-friendly vs technical? (Decide during pilot from customer feedback.)
- Pilot timeline — "ASAP" subject to hardware lead time. Realistic minimum: 2–4 weeks from spec approval to first device on a customer site (covers nRF9160 DK + sensor card sourcing + enclosure fab + customer scheduling). Software path completes faster than that and waits on hardware.

### Risks
- **Firmware verification gap.** Until a Nordic nRF9160 DK is in hand, firmware is code-complete but unverified on silicon. Mitigation: simulated-device parity gives high confidence on protocol correctness; firmware behavior on real radio + sensors is the residual gap.
- **Cellular cert lift for production** — modular approval covers most of it, but final product cert testing may surface antenna or layout issues. Budget $5K–15K for cert testing on the production board revision.
- **Sensor calibration drift in real septic environments** — methane, condensation, ant nests. Pilot is the only way to learn this; expect at least one sensor model revision before scale.
- **TCEQ approval timeline** — Septilink took ~9 months from submission. Plan accordingly.
- **OEM panel diversity** — many OEMs don't expose alarm signals on accessible terminals. Tech training and per-OEM tap procedures essential. Document during pilot.

---

**End of spec.**
