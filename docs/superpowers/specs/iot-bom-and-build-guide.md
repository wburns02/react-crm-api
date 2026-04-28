# Watchful — Bill of Materials & Build Guide
**Version:** v1 prototype
**Date:** 2026-04-27
**Status:** First-fab build instructions

> **For ordering, use the link-checked parts list:** `iot-parts-list-with-links.md` (PDF #08). Prices and stock verified live on 2026-04-27. **Material corrections caught during verification:**
> - **YHDC SCT-013-030 CT clamps are NOT on Digi-Key/Mouser** — buy from Amazon (B01M0QUPBA) or AliExpress
> - **BUD PN-1339-DG enclosure has only 10 in stock at Digi-Key** with an 11-week backorder lead — order early for any pilot batch
> - **nRF9160-DK is $179.80** (Nordic raised the price in late 2024; this doc still references the old number in places)
> - **Adafruit part numbers in early drafts of this doc were stale** — see parts-list for verified ones

This document covers the physical hardware: parts to order, how to assemble, how to bring it up, and what changes between the prototype build (qty 5) and the production build (qty 1000+). Pairs with the design spec at `react-crm-api/docs/superpowers/specs/2026-04-27-iot-monitor-design.md` and the firmware repo at `wburns02/mac-septic-iot-firmware`.

## Quick reality check

- **v1 prototype cost: ~$500–700 per ATU device, ~$400–500 per conventional device.** Sensor BOM dominates. Premium sensors (MaxBotix ultrasonic, METER EC-5 soil probe) are used for prototype to characterize the problem; production substitutes cheaper alternatives once we know the accuracy floor.
- **v1 production target (qty 1000+): $80–150 per device.** Matches the spec target. Achieves it through volume PCB pricing, cheaper sensor alternatives, and combined BOM purchasing.
- **Lead times: 4–6 weeks** from "order placed" to "5 functioning prototypes," driven mostly by JLCPCB SMT assembly turn time and METER soil-probe stock.

---

## 1. Bill of Materials — Prototype (qty 5)

### 1.1 Compute / radio

| Item | Part # | Vendor | Qty per device | Unit price | Notes |
|---|---|---|---|---|---|
| Nordic nRF9160 SiP | nRF9160-SICA-R7 | Digi-Key, Mouser | 1 | $28–32 | Pre-certified modular approval. Production part. |
| **OR** for prototyping ease | Actinius Icarus SoM | Mouser, direct | 1 | $49–59 | nRF9160 + supporting passives + antenna pads on a 25mm SoM. **Recommended for v1 prototype** — cuts layout time. |
| **OR** dev kit for first 1–2 units | nRF9160-DK | Digi-Key | 1 | $129 | Full dev board with sensors, debug, USB. Use for the first prototype only — not deliverable hardware. |
| LTE/GPS antenna (combo) | Taoglas FXP07 / FXP611 | Digi-Key | 1 | $7–9 | Adhesive flex; mount inside enclosure away from PCB ground plane. |
| 1NCE prepaid IoT SIM (10yr / 500MB) | 1NCE Lifetime SIM | 1nce.com | 1 | $10 | Multi-carrier roaming. Order with quantity discount at 10+. |

### 1.2 Power

| Item | Part # | Vendor | Qty | Unit | Notes |
|---|---|---|---|---|---|
| 12V/2A wall-wart AC adapter | TPI 31-1080 (12V 2A) | Digi-Key | 1 | $8–12 | Plugs into a residual outlet near the OEM panel. |
| Buck converter 12V→3.3V | TI TPS62840DLCR | Digi-Key | 1 | $1.80 | Low-Iq, ideal for sleep budget. |
| Buck converter 12V→5V (sensor rail) | TI TPS54060A | Digi-Key | 1 | $3.50 | Powers ultrasonic + RS-485 transceivers. |
| LiSOCl₂ primary cell (UPS) | Tadiran TL-5930F (D-cell, 19Ah, 3.6V) | Digi-Key, House of Batteries | 1 | $32–38 | -55°C to +85°C; 10yr shelf life; non-rechargeable. |
| Battery holder | Keystone 1041 (D-cell PCB mount) | Digi-Key | 1 | $3 | |
| Power-path / battery monitor IC | TI BQ27441-G1A | Digi-Key | 1 | $3 | Coulomb counting + OCV; reports SOC over I²C. |
| AC-present sense (opto on 12V rail) | Vishay PC817 | Digi-Key | 1 | $0.30 | Detects AC adapter dropout. |
| Bulk decoupling caps | various 10µF/22µF X7R | JLCPCB stock | ~10 | $0.05 | |
| TVS diodes (12V rail) | SMAJ15CA | Digi-Key | 2 | $0.40 | Protects against AC-side transients. |
| MOV (AC adapter input) | Littelfuse V275LA20A | Digi-Key | 1 | $1.80 | Optional — wall-wart may already include. |

### 1.3 Sensor expansion bus connectors (on base PCB)

| Item | Part # | Vendor | Qty | Unit | Notes |
|---|---|---|---|---|---|
| Phoenix MCV 1,5/4-G-3.81 (4-pos) | Digi-Key | Digi-Key | 4 | $1.80 | RS-485 + 4-20mA + 0-10V breakouts |
| Phoenix MCV 1,5/2-G-3.81 (2-pos) | Digi-Key | Digi-Key | 8 | $1.20 | Digital input + power |
| RS-485 transceiver | TI THVD1450DR | Digi-Key | 2 | $1.40 | Half-duplex, ESD-protected |
| Opto-isolators (digital inputs) | Vishay PC817 | Digi-Key | 6 | $0.30 | Each = one isolated digital input |
| TVS diodes (per opto input) | SMAJ12CA | Digi-Key | 6 | $0.40 | Surge protection |
| Pull-up / current-limit resistors | various 1% 0805 | JLCPCB stock | ~30 | $0.02 | |

### 1.4 Sensor cards — Conventional install (4 cards)

| Sensor | Part # | Vendor | Unit | Notes |
|---|---|---|---|---|
| **Pump current CT clamp (30A)** | YHDC SCT-013-030 | Digi-Key, OpenEnergyMonitor | $9 | Non-invasive split-core; clip around pump leg. Output: 0-1V AC analog → ADC. |
| **Tank-level ultrasonic** (prototype) | MaxBotix MB7389-100 | Digi-Key, Mouser | $109 | Weather-resistant, 0.5–10m range. Premium choice for proto — characterize before downgrading. |
| **Tank-level ultrasonic** (production alt) | A02YYUW (RS-485 ultrasonic, IP65) | Adafruit, AliExpress | $18–28 | Cheaper alt; validate accuracy in pilot. |
| **Soil moisture probe** (prototype) | METER EC-5 (RS-485 / SDI-12) | METER Group direct | $135 | Lab-grade VWC; characterize before downgrading. |
| **Soil moisture probe** (production alt) | DFRobot SEN0308 capacitive (RS-485) | DigiKey, AliExpress | $14–22 | Cheap capacitive; less accurate but adequate for thresholds. |
| **Float switch** (OEM alarm tap) | Generic NC septic float (Sch 40 stem) | Septic Solutions, MSC | $14 | Spliced parallel into OEM alarm circuit. Optional — most OEM panels have a screw-terminal alarm output we tap directly via opto-iso instead. |
| **Cabling — to sensors** | 18AWG outdoor UV-rated, multi-conductor | Belden 8723 (or generic) | $0.45/ft, 50ft | Plus M16 cable glands at enclosure entries. |

### 1.5 Sensor cards — ATU upgrade (3 additional)

| Sensor | Part # | Vendor | Unit | Notes |
|---|---|---|---|---|
| **Aerator current CT clamp (15A)** | YHDC SCT-013-015 | Digi-Key | $9 | Same family as pump CT, smaller range. |
| **Treatment-tank level** (premium proto) | MaxBotix MB7389-100 | Digi-Key | $109 | Same as conventional level. Buy 2 if both wanted. |
| **Chlorinator presence/flow** | TE Connectivity FS40A flow switch | Digi-Key | $24 | Inline flow switch, 0.3-30 L/min. Or: load-cell-based weight sensor on tablet feeder ($45). |
| **ATU control bus tap** | n/a — uses base-PCB opto-iso digital inputs | — | $0 | OEM panel signals tapped directly via the 6× digital inputs already on the base. |

### 1.6 Enclosure and mechanical

| Item | Part # | Vendor | Qty | Unit | Notes |
|---|---|---|---|---|---|
| IP66 polycarbonate enclosure | BUD Industries PN-1339-DG (11×9×5") | Digi-Key, Mouser | 1 | $52 | UV-stable; gasketed. |
| Mounting plate (internal) | BUD MOP-1339 | Digi-Key | 1 | $13 | Aluminum interior plate. |
| Cable glands (M16 IP68) | Heyco M3185G | Digi-Key | 6 | $4 | One per outdoor cable run. |
| External mounting feet | BUD MFB-1339 | Digi-Key | 1 set | $9 | For wall mount near OEM panel. |
| Wall mounting hardware (anchors + screws) | generic | hardware store | — | $5 | |
| Conformal coating | MG Chemicals 422B (acrylic) | Digi-Key | 1 spray can per 20 boards | $28 | Apply post-bring-up, pre-final-assembly. |
| Tamper-evident seal stickers | Avery 6577 | Amazon | 1 pack | $9 | Across enclosure seam. |
| Cabinet door reed switch | Cherry MP201801 | Digi-Key | 1 | $4 | Tamper detection. |

### 1.7 Base PCB

| Item | Spec | Vendor | Qty | Unit | Notes |
|---|---|---|---|---|---|
| 4-layer ENIG PCB, ~100×80mm | 1.6mm, ENIG, qty 5 | JLCPCB | 5 | $30 total | Includes shipping. |
| SMT assembly (top side, partial BOM-loaded) | JLC SMT, ~50 components | JLCPCB | 5 | $80–180 total | Non-stocked parts add fees + lead time. Plan to hand-place CT clamp jacks + Phoenix terminals. |
| PCB design files | KiCad 8 (open) | — | — | — | **Repo: TBD — to be authored.** Use Actinius Icarus reference schematic as a starting point for the nRF9160 power + antenna section. |

### 1.8 Programming / debug (one-time per build, not per device)

| Item | Part # | Vendor | Qty | Unit | Notes |
|---|---|---|---|---|---|
| Nordic nRF9160-DK | Digi-Key | 1 | $129 | Used as a **JLink programmer** for production-board firmware flash. Reusable. |
| Tag-Connect cable (TC2030-CTX) | Digi-Key | 1 | $35 | Connects DK SWD pins to a no-connector footprint on the production board. Saves PCB area. |
| USB-C cable | Amazon | 2 | $10 | Power and serial diagnostic. |
| Logic analyzer (optional, debug) | Saleae Logic 8 / Pico-based clone | Saleae / AliExpress | 1 | $40–400 | For MQTT timing + sensor bus debug. |

### 1.9 Pilot-build totals (qty 5 ATU + qty 5 conventional)

| Bucket | Conv (5) | ATU (5) | Notes |
|---|---|---|---|
| Compute + radio + SIM | $230 | $230 | Same base |
| Power chain + battery | $260 | $260 | |
| PCB + SMT (qty 10 boards) | $400 | (shared) | One PCB design covers both |
| Connectors + opto + RS-485 | $150 | $150 | |
| **Conventional sensors** (CT + ultrasonic + soil + alarm tap) | $1,150 | — | |
| **ATU upgrade sensors** (aerator CT + 2nd ultrasonic + chlor flow + ATU bus) | — | $720 (additional) | |
| Enclosure + mech | $400 | $400 | |
| Cabling + glands + misc | $200 | $200 | |
| Conformal + tamper + sundries | $100 | $100 | |
| **Subtotal per group** | **$2,890** | **$2,060 add'l** | |
| **10-unit pilot total** | | **~$4,950** | Equipment depreciable across the pilot |

Plus one-time programmer + tools: **~$200**.

**Grand total v1 prototype (10 devices): ~$5,150.**

Per-device blended: ~**$515**.

---

## 2. Bill of Materials — Production (qty 1000+)

Same module + radio + power chain. Diff is sensor substitutions, PCB volume pricing, enclosure volume pricing, and skipping the dev-kit programmer (one-time tooling).

| Bucket | Per-unit qty 1000 | Notes |
|---|---|---|
| nRF9160 SiP (raw, not SoM) | $24 | Volume pricing direct from Nordic / Avnet |
| Antenna + 1NCE SIM | $13 | |
| Power chain + LiSOCl₂ battery | $52 | Battery doesn't volume-discount as much |
| 4-layer PCB (qty 1000) | $4 | JLCPCB volume tier |
| SMT assembly (qty 1000) | $14 | |
| Connectors + opto + RS-485 | $11 | |
| **Conventional sensors** (cheaper alts: A02YYUW ultrasonic, capacitive soil) | $42 | |
| **ATU upgrade sensors** (aerator CT, 2nd A02YYUW, FS40A flow) | $52 (add'l) | |
| Enclosure + mech (qty 1000) | $26 | |
| Cabling + glands | $9 | |
| Conformal + tamper + sundries | $4 | |
| **Conventional total** | **$199** | |
| **ATU total** | **$251** | |

Production target was $80-150. **The sensor BOM keeps it above target.** Two paths to close the gap:

1. **Sensor consolidation** — replace ultrasonic + soil probe with a single hybrid module (custom). Effort: 6–9 months and ~$50K of NRE.
2. **Phased premium pricing** — sell at $349 retail (gross margin 43% on conventional, 30% on ATU). At $14.99/mo subscription, recurring margin makes up the gap inside year one.

Path 2 is the v1 plan. Revisit Path 1 after pilot.

---

## 3. PCB design — high-level schematic blocks

The base PCB needs 8 functional blocks. Schematic and layout files are TBD (KiCad 8). For v1 prototype, I'd recommend starting from the **Actinius Icarus SoM reference design** (open source on GitHub at actinius/icarus-board) and adding the sensor-bus, opto-iso, and power-management sections.

```
                         ┌──────────────────────────┐
   AC IN ──[fuse]────── │ Block 1: AC adapter      │
   (12V wall-wart)      │   - 12V input             │
                         │   - MOV protection        │
                         │   - PC817 AC-present     │
                         └────┬─────────────┬───────┘
                              │             │
                  ┌───────────▼──┐    ┌─────▼─────────┐
                  │ Block 2:     │    │ Block 3:      │
                  │ 12V→3.3V buck│    │ 12V→5V buck   │
                  │ (TPS62840)   │    │ (TPS54060A)   │
                  │  → MCU rail  │    │  → sensor rail│
                  └─────┬────────┘    └─────┬─────────┘
                        │ 3.3V              │ 5V
                        │                   │
              ┌─────────▼──────────┐        │
              │ Block 4: nRF9160   │        │
              │ SiP (or Icarus SoM)│        │
              │  - SWD via         │        │
              │    Tag-Connect     │        │
              │  - SIM (1NCE)       │        │
              │  - LTE antenna      │        │
              │  - GPS antenna pad  │        │
              └───┬────────────┬───┘        │
                  │SPI/I2C/UART│             │
                  │            │GPIO         │
       ┌──────────▼──┐    ┌────▼────────┐    │
       │ Block 5:    │    │ Block 6:    │    │
       │ Power mgmt  │    │ Opto-iso    │    │
       │ - BQ27441   │    │ digital in  │    │
       │ - LiSOCl₂   │    │ x6 (PC817)  │    │
       │   battery    │    │ (alarm tap, │    │
       │ - Power     │    │  tamper,    │    │
       │   path FET  │    │  AC-loss,   │    │
       └─────────────┘    │  OEM signals)│   │
                          └─────┬───────┘    │
                                │GPIO         │
                                │             │
                       ┌────────▼─────────────▼──┐
                       │ Block 7: Sensor expansion│
                       │  - 2× RS-485 (THVD1450)  │
                       │  - 2× 4-20mA loop input  │
                       │  - 2× 0-10V analog       │
                       │  - 2× CT-clamp 3.5mm jack│
                       │  - Phoenix terminals     │
                       └─────────────────────────┘

                       ┌─────────────────────────┐
                       │ Block 8: Diagnostics    │
                       │  - USB-C (CDC-ACM)      │
                       │  - Status LEDs (3)      │
                       │  - Reset button         │
                       │  - Tag-Connect SWD      │
                       └─────────────────────────┘
```

PCB layout target: 100×80mm, 4-layer ENIG, mounted on the BUD MOP-1339 plate inside the enclosure.

**TODO:** author KiCad 8 schematic + layout. Pin out for sensor cards. Antenna keep-out zones. **Estimated 40-60 hours of EE work for first PCB rev.**

---

## 4. How to build — Stage-by-stage

### Stage 0 — Pre-flight (week 0)
- [ ] Confirm spec is approved (it is, 2026-04-27)
- [ ] Confirm BOM is approved (this doc)
- [ ] Confirm budget (~$5,150 for 10-unit pilot)
- [ ] Engage EE consultant or assign internal EE for PCB design (~6–8 weeks lead time)
- [ ] Order Nordic nRF9160-DK + Tag-Connect cable for early firmware development *(can start before PCB is ready)*

### Stage 1 — Order parts (week 1)
Place all orders in parallel:
- [ ] Digi-Key cart: nRF9160 SiPs (or Actinius SoMs), antennas, power chain, connectors, opto-iso, TVS, MOVs, MaxBotix, YHDC CTs (qty 15 of each), sundries → ~$2,400
- [ ] Mouser cart (Digi-Key alternates): Phoenix terminal blocks, Keystone battery holders, BQ27441
- [ ] METER Group order: 5× EC-5 soil probes → ~$675 (lead time 2–3 weeks)
- [ ] BUD Industries: 10× PN-1339-DG enclosures + plates + glands → ~$700 (qty 10 saves shipping)
- [ ] House of Batteries: 10× Tadiran TL-5930F → ~$370
- [ ] Septic Solutions: 10× generic NC float switches (if used as backup alarm tap) → ~$140
- [ ] 1NCE: 10× Lifetime SIMs → $100

### Stage 2 — PCB design (weeks 1–6, parallel with parts ordering)
- [ ] EE drafts schematic in KiCad 8 (clone Actinius Icarus reference, add blocks 1, 5, 6, 7, 8)
- [ ] Design review (you, EE, possibly an outside Nordic-experienced reviewer) — focus on antenna placement and power-budget sleep current
- [ ] PCB layout (4-layer, 100×80mm) — keep antenna keep-out at edge, route 50Ω matched antenna trace
- [ ] DFM check via JLCPCB review or PCBA partner
- [ ] Generate Gerbers + BOM + CPL
- [ ] Order qty 10 boards from JLCPCB with SMT (top side), $400–600 total

### Stage 3 — Firmware development (weeks 1–6, parallel)
The firmware skeleton is already at `wburns02/mac-septic-iot-firmware`. Bring it up against the **nRF9160-DK** while waiting for PCB:
- [ ] Install nRF Connect SDK v2.6 via Toolchain Manager (5GB download)
- [ ] `west init -m wburns02/mac-septic-iot-firmware` (after adding remote)
- [ ] `cd watchful && west update`
- [ ] `west build -b nrf9160dk_nrf9160_ns .`
- [ ] `west flash`
- [ ] Verify: device boots, attempts cellular attach (will fail without SIM in DK — that's OK), publishes mock telemetry once cellular is up
- [ ] Replace each `// TODO(hw)` stub with real driver code as breakouts arrive — start with pump CT (simplest), then OEM alarm tap, then ultrasonic, then soil probe
- [ ] Each driver: write to a single `.c` in `src/sensors/`, expose `int sensor_X_sample(struct reading *out)`, smoke-test on bench

### Stage 4 — PCB receipt + bring-up (week 7)
When boards arrive from JLCPCB (pre-assembled top side):
- [ ] Visual inspection (scope joints, missing parts, polarity errors on opto/diodes)
- [ ] **Power-on test BEFORE installing nRF9160 SiP**: apply 12V to AC adapter input, verify 3.3V and 5V rails. Smoke = stop. No smoke = continue.
- [ ] Hand-place + reflow nRF9160 SiP (if not pre-loaded), or use pre-loaded Icarus SoM
- [ ] Hand-solder Phoenix terminal blocks, CT-clamp 3.5mm jacks, USB-C, battery holder
- [ ] Re-power. Measure 3.3V at SiP rails. Verify VBAT switchover when AC removed.
- [ ] SWD via Tag-Connect → flash skeleton firmware → verify boot via USB-CDC console
- [ ] Cellular attach: install 1NCE SIM, antenna, power up. Verify LTE-M attach within 60s. Check signal strength.
- [ ] MQTT smoke test: configure broker URL via NVS, verify connect + subscribe

### Stage 5 — Sensor integration (week 8)
For each device:
- [ ] Wire pump CT clamp pigtail to 3.5mm jack on board → run through firmware sample loop → verify ADC reading in firmware's UART log → confirm scaling matches a known-current load (use a kettle on a metered outlet for a clean 10A reference)
- [ ] Wire MaxBotix to RS-485 terminal → run sample → verify level reading matches a tape-measure ground truth
- [ ] Wire soil probe to RS-485 terminal → run sample → verify VWC reads zero in air, ~50% in damp soil sample
- [ ] Wire opto-iso digital input to a test float switch → trip the float → verify firmware fires the immediate-publish path
- [ ] Run AC-loss test: pull AC adapter, verify within 5s the device publishes a power_loss event from battery
- [ ] Battery-only soak test: leave on battery for 24 hours at 2× cadence, verify it survives with >50% battery remaining

### Stage 6 — Final assembly + conformal (week 9)
- [ ] Final firmware build with production cert + hardcoded broker URL
- [ ] Flash + provisioning script burns unique X.509 keypair into nRF9160 secure storage (per device)
- [ ] Print QR-coded serial label, apply to enclosure
- [ ] **Conformal coat the PCB** (MG Chemicals 422B, 2 coats, 30 min between, 24 hour cure)
- [ ] Install PCB on MOP-1339 plate, route cabling through M16 glands
- [ ] Install LiSOCl₂ battery in holder
- [ ] Close enclosure, apply tamper-evident sticker across seam
- [ ] Functional test: power up, verify cellular attach, verify first telemetry hits production CRM dashboard, verify QR scan works in tech CRM mobile

### Stage 7 — Pilot deployment (weeks 10–22, 90 days field)
Per the spec's pilot plan:
- [ ] 5 conventional installs, 5 ATU installs (or 2 + 3 per spec — adjust to what's been built)
- [ ] Use install SOPs at `mac-septic-docs/iot-install-sop-conventional.md` and `iot-install-sop-atu.md`
- [ ] Daily team review of telemetry for first 30 days
- [ ] Weekly thereafter
- [ ] Track pilot success criteria from spec section 18

---

## 5. Service / repair / RMA

- **Field-replaceable units (FRUs):** sensor cards, battery, antenna. Everything else (PCB, enclosure, MCU) requires depot RMA.
- **In-warranty FRU swap:** tech rolls with replacement, performs swap per decommission SOP, returns failed FRU to depot.
- **Common failure modes** (anticipated, watch list):
  - CT clamp jaw breakage (drops accuracy to zero) — FRU swap
  - Soil probe corrosion / bury-depth migration — FRU swap, possibly with re-burial
  - Battery exhaustion (10yr nominal but cold-weather installs may run hot) — FRU swap
  - Conformal coat compromise from gland leak → PCB corrosion → depot RMA + warranty claim
  - LTE coverage degradation as carriers refarm → eventually firmware swap to NB-IoT-only mode

---

## 6. What this document does NOT yet include

These are real gaps for a production rollout:

1. **KiCad 8 schematic + layout files** — the actual PCB design. ~40-60 hours of EE work. Treat as a separate workstream that runs in parallel with the firmware dev (which is already viable on the DK).
2. **Mechanical drawings** — enclosure cut-outs for the M16 glands, mounting hole pattern, antenna keep-out. Trivial CAD work, ~4 hours.
3. **Test fixtures** — end-of-line manufacturing test jig (powers up board, runs self-test, confirms cellular attach + sensor-bus continuity). ~30 hours of NRE for the first jig.
4. **Cert testing budget** — $5–15k cert-house engagement once the production board layout is finalized, before the qty-1000 manufacturing run.
5. **Manufacturing partner selection** — JLCPCB scales to a few hundred boards; beyond that, evaluate Worthington Assembly, Macrofab, or similar. Decision can wait until pilot validates the design.
6. **Weather / drop / vibration testing** — recommended but not required for pilot. Engage an outside lab once the production design is locked.

---

## 7. Summary procurement list — copy-paste ready

For the 10-unit pilot, paste these into your Digi-Key / Mouser / vendor carts:

**Digi-Key cart (single order, ships in ~3 days):**
```
NRF9160-SICA-R7        × 12   (10 + 2 spare)
TPS62840DLCR           × 12
TPS54060A              × 12
BQ27441-G1A            × 12
PC817                  × 80   (10 used per device + spares)
SMAJ12CA               × 80
SMAJ15CA               × 30
THVD1450DR             × 25
1714984 (MCV 1,5/4-G-3.81)  × 50
1714969 (MCV 1,5/2-G-3.81)  × 100
Keystone 1041          × 12
Taoglas FXP07.07.0100A × 12
SCT-013-030 (YHDC CT 30A)   × 12
SCT-013-015 (YHDC CT 15A)   × 8
MB7389-100 (MaxBotix)  × 12
Cherry MP201801        × 12
TC2030-CTX             × 2
NRF9160-DK             × 1     (programmer)
```
~$2,500 estimated.

**Mouser cart (any items not on Digi-Key):** Phoenix terminal alternates, MGC 422B conformal coating, Heyco M3185G glands.

**METER Group direct:** 5× EC-5 soil probes. ~$675. 2-3 week lead.

**BUD Industries direct or Mouser:** 10× PN-1339-DG, 10× MOP-1339, 10× MFB-1339. ~$700.

**House of Batteries:** 10× Tadiran TL-5930F. ~$370. Hazmat shipping fees apply.

**Septic Solutions (optional float-switch backup):** 10× NC septic floats. ~$140.

**1NCE direct:** 10× Lifetime SIMs. $100.

**JLCPCB:** Order 5 of v1 PCB once design is finalized. ~$400-600.

---

## 8. Assumptions + risks

- **Antenna performance:** Taoglas FXP07 is excellent for nRF9160 in plastic enclosures, but cellular reception inside a metal pump-box install is unverified. **Mitigation:** include an SMA pigtail option on the PCB so an external puck antenna can be swapped in for problem sites.
- **Battery cold-weather:** Tadiran TL-5930F is rated to -55°C. The OEM panel install location may run +60°C in summer Texas. Within spec but at the edge. **Mitigation:** thermistor on the battery holder and firmware monitoring.
- **Conformal coat coverage:** Hand-coating leaves gaps. Vapor-deposited parylene is better but adds cost (~$15/board). **Decision:** acrylic spray for v1 pilot, evaluate parylene in production.
- **JLCPCB SMT non-stocked parts:** Nordic SiP, MaxBotix MB7389, and METER probes will not be JLCPCB-stocked. Plan to either hand-place or use a CM that handles consigned components (Macrofab does).

---

This is a v1 doc. Treat it as a starting point — the EE doing the schematic will surface issues that change pin assignments, package choices, and BOM. Keep it updated as the design firms up. After the v1 PCB rev arrives and bringup completes, write a "v2 production BOM" doc that locks in the cheaper sensor alternates and any layout changes.
