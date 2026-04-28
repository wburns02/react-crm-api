# Watchful IoT — Conventional Septic Install SOP

**Codename:** Watchful
**Install type:** `conventional` (gravity tank + pump-to-field, no aerator)
**Audience:** Field service technician
**Estimated install time:** 90–120 minutes
**Document version:** v1.0 — 2026-04-27
**Related spec:** `react-crm-api/docs/superpowers/specs/2026-04-27-iot-monitor-design.md`

---

## 0. What you're installing

A Watchful cellular notification module mounted near the OEM septic alarm panel. It **taps** the OEM circuit but never replaces it — the OEM panel is, and remains, the regulated primary safety device per TX 30 TAC §285.

Sensor population for this install type:

| Sensor card | Where it goes |
|---|---|
| `OEM-ALARM-TAP` | Opto-isolated parallel tap on the OEM alarm circuit |
| `PUMP-CT-30A` | CT clamp around the effluent pump's hot leg |
| `LEVEL-ULTRASONIC` | Mounted on pump-tank lid, sensing toward water |
| `SOIL-MOIST-RS485` | Driven into drain field at the field edge |

If the customer's system is ATU (aerator present), STOP — use `iot-install-sop-atu.md` instead.

---

## 1. Pre-arrival checklist (do before leaving the shop)

- [ ] Customer confirmed home, gates unlocked, dogs put up.
- [ ] CRM work order open with `install_type=conventional`.
- [ ] Watchful enclosure (serialized, QR label intact, tamper seal not broken).
- [ ] Sensor cards: `OEM-ALARM-TAP`, `PUMP-CT-30A`, `LEVEL-ULTRASONIC`, `SOIL-MOIST-RS485`.
- [ ] 1NCE SIM pre-installed at depot (verify on packing slip).
- [ ] Service agreement printed, two copies.
- [ ] Tools (see §10).
- [ ] Phone / tablet logged into CRM mobile, camera works, QR scanner works offline.
- [ ] Spare wire nuts, butt splices, dielectric grease, UV-resistant zip ties.
- [ ] Multimeter — verified working at the shop on a known live outlet.

---

## 2. On-site site survey (10–15 min)

1. Greet homeowner. Re-confirm scope: **supplemental notification, not a replacement alarm.** Required language.
2. Locate the **OEM alarm panel** — usually on an exterior wall, near the tank, or on a 4×4 post next to the tank. Photograph the panel face (labels, brand, model). Upload to CRM under the work order.
3. Verify **AC at the panel**: lift the cover, identify the line side. Multimeter to ground — should read 120V AC (or 240V if a 2-pole pump). Note voltage in CRM.
4. Locate the **pump tank access lid**. Confirm the lid will lift (it sometimes won't on older installs — note for later).
5. Walk the **drain field**. Identify the **field edge** — typically the down-gradient side of the laterals. Pick a probe spot:
   - 18–24" off the last lateral run
   - Not in a vehicle path
   - Not directly over a lateral (avoid puncturing pipe)
   - Soft enough to drive the probe (no caliche slab)
6. Photo-document each location before any work begins.

---

## 3. Power-down sequence (do not skip)

1. Open the OEM panel. Identify the **pump breaker** (usually a single-pole or 2-pole at the panel itself, or back at the house sub-panel).
2. Trip the breaker to OFF. Verify pump-off with multimeter at the pump terminals — should read 0V.
3. Leave the OEM **alarm circuit live** if the panel is wired such that alarm and pump are independent. (Most are — alarm float runs on its own low-voltage transformer.) If they share the same breaker, you'll be working alarm-cold; that's fine.
4. Tape a "DO NOT ENERGIZE" tag over the breaker. Tell the homeowner you'll be working on the panel for the next ~90 min.

---

## 4. Mount the Watchful enclosure

1. Pick a mount location **within 6 ft of the OEM panel** (wire run constraint) and **above expected splash/flood line**.
2. Surface preference: side of the post the OEM panel is on, or the same exterior wall, ~12" away. Never inside the OEM enclosure.
3. IP66 mounting requirements:
   - Lid faces down or sideways — never lid-up (water pools).
   - Conduit hubs go in through the **bottom** of the enclosure (gravity drains).
   - Use the supplied stainless mounting bracket; never lag-screw straight through the back wall (breaks the IP66 seal).
   - Apply silicone bead behind the bracket, not on the enclosure body.
4. Mount, level, snug. Do not over-torque the lid screws — gasket will deform.

---

## 5. Wiring sequence

**Order matters.** Follow this exactly.

### 5.1 AC tap → Watchful

1. From the OEM panel's line side (after the breaker, before the pump contactor), pull a **fused 3A tap** to the Watchful AC input.
2. Run UV-resistant `THWN-2` 16 AWG inside `LFMC` or **gray UV-rated PVC conduit** (no `EMT` outdoors).
3. Land L1, N, ground. Torque to spec on the Watchful AC terminal block (8 in-lb).
4. **Do not energize yet.**

### 5.2 OEM alarm tap (opto-isolated)

1. Identify the OEM alarm float's signal terminals on the OEM panel. (Not the buzzer — the float input.)
2. Land the `OEM-ALARM-TAP` card's two opto-input wires **in parallel** with the OEM float terminals. Polarity does not matter on the opto side; it does on the panel side — match what the OEM diagram shows.
3. **Do not cut, splice into, or load down the OEM alarm circuit.** Parallel tap only. The opto presents >10 kΩ — the OEM panel will not see the difference.
4. Verify with multimeter: with the alarm float un-tripped, you should read the OEM float's quiescent voltage at both the OEM terminals AND the opto input terminals. Same value, both sides.

### 5.3 Pump CT clamp

1. Open the CT-clamp jaw, pass it around the **pump's hot leg only** (not both legs, not the neutral, not the ground bundle). Wrong leg = wrong reading.
2. Snap closed, route the CT lead to the Watchful `CT1` terminal.
3. Bundle excess CT lead — do **not** loop the CT lead around any current-carrying conductor (induces noise).

### 5.4 Ultrasonic level sensor — pump tank

1. Drill a **1.5" hole** through the pump-tank access lid at a location that gives a clear shot to the water below (no riser pipe, no float arm in the cone).
2. Mount the `LEVEL-ULTRASONIC` head with the supplied bulkhead fitting. Apply butyl gasket — not silicone (silicone fails on PE lids in 6 months).
3. Cable run: same UV-rated conduit as AC; do not zip-tie the level cable to the AC conduit at less than 6" intervals (capacitive coupling causes false readings).
4. Land at Watchful `RS485-1` (or `4-20mA-1` depending on probe revision — check sensor card label).

### 5.5 Soil moisture probe — drain field

1. Drive the `SOIL-MOIST-RS485` probe to **full insertion depth** (24" typical) at the spot identified in §2.5.
2. Backfill — do not leave the probe sticking up where a mower will hit it. Probe head should sit ~1" below grade with a small flag stake nearby.
3. Cable run: direct-bury rated, in 1/2" `LFMC` from probe head to the Watchful enclosure. Mark the cable path on the CRM site map photo.
4. Land at Watchful `RS485-2`.

### 5.6 Cabling protection

- All outdoor runs in UV-resistant conduit (`PVC schedule 40 gray` or `LFMC`).
- Drip loops at every enclosure entry — water runs down the cable, not into the enclosure.
- Seal conduit hubs with `Duct Seal` or equivalent putty after wiring.
- No cable lengths longer than 25 ft on any sensor without a junction box (ground-loop risk).

---

## 6. Power-up sequence

**Order matters here too.**

1. Close the **OEM panel** — restore its cover before energizing. (Reduces arc-flash exposure if a wire was missed.)
2. Restore the pump breaker.
3. Verify the OEM panel **wakes up normally** — its own LEDs/indicators in their normal state.
4. Manually trip the OEM alarm float (push the float up by hand). Confirm:
   - OEM panel alarms (buzzer, light) — **this is the regulated primary, must work.**
   - Watchful would also see the tap (LED on the `OEM-ALARM-TAP` card lights). Don't expect a CRM alert yet — device hasn't paired.
5. Release the float, alarm clears.

If the OEM alarm did not fire as expected — **stop, troubleshoot the OEM circuit, do not leave the site until OEM alarm is verified working.** Customer must never lose primary alarm functionality.

---

## 7. Pair the device

1. Open the CRM mobile app → **IoT** → **New Install**.
2. Scan the QR code on the Watchful enclosure (Code 128, serial-encoded).
3. Form auto-fills: serial, manufactured-at. Fill in:
   - Customer (search) — verify name and address match the work order.
   - `install_type=conventional`.
   - `site_address` (CRM may auto-populate from customer address — verify on-site).
   - Brand/model of the OEM panel (free text).
4. Press **Bind**. Wait for green checkmark — backend writes `iot_device_bindings` row and updates `iot_devices.customer_id`.
5. Confirm WebSocket pushed an event — the **last_seen_at** field on the device record should update within 5 minutes of pairing (first scheduled check-in).

---

## 8. Calibrate sensors

Each sensor needs a baseline before alerts can fire.

1. **Pump CT zero** — with pump off, press **Calibrate → CT1** in CRM. Device samples 30 sec, stores zero-current offset.
2. **Pump CT span** — manually run the pump (toggle the float, or use the OEM panel's **Test** button if it has one). Press **Calibrate → CT1 span** while pump is running. Device captures the pump's nominal current. Note value (typically 4–9 A for a 1/2 hp effluent pump).
3. **Level sensor zero** — with the tank at its normal water line, press **Calibrate → Level**. Stores reference distance. (Future readings reported as delta from this reference.)
4. **Soil moisture baseline** — press **Calibrate → Soil**. Captures dry-baseline reading (assumes you're not installing during a flood). Note: will re-baseline on its own over the first 7 days post-install — **suppress alerts on this sensor for 7 days** (the CRM does this automatically based on `created_at` of the device).

All four calibrations must show **green** before leaving the site.

---

## 9. Verify cellular connectivity

1. On the device — the **status LED** should be solid green (LTE-M attached, MQTT connected). Blinking green = connecting; red = no signal.
2. If red after 5 minutes:
   - Try moving the device 2–3 ft (sometimes a steel meter base is shielding it).
   - Verify the SIM is seated.
   - In CRM, check `last_seen_at` — if it hasn't updated, dispatch a tech-support escalation before leaving site.
3. In CRM **device detail page**, confirm:
   - `last_seen_at` within the last 5 minutes.
   - At least one telemetry row per sensor — pump CT, level, soil, alarm state.
   - No active alerts.

---

## 10. Walk-through with homeowner (5 min, do not skip)

Required language to convey:

- "This device **notifies us and you** when it sees something unusual. Your existing OEM alarm panel is still your primary safety device — that one is regulated, and we're not replacing it."
- "If your OEM panel alarms, you'll get a text message within ~30 seconds and so will our on-call tech."
- "We'll also get early-warning data — like if your pump starts working harder than normal, or if your drain field is showing saturation."
- "If you ever lose power at the panel, we get a heads-up. The device runs on a backup battery for up to a week of notification."
- "If you have a question, you call us — same number as always."

Show them where the device is mounted. Show them the tamper seal (so they know what an opened device looks like). Confirm they got the install confirmation SMS.

---

## 11. Sign service agreement

1. Two-copy signature: one stays with homeowner, one goes back to office.
2. CRM mobile: capture signature on device, upload PDF.
3. Mark the work order as **complete** with all required fields.

---

## 12. Photo documentation (required)

Upload all to the CRM work order:

- **Before:** OEM panel face, pump tank, drain field, intended Watchful mount location.
- **During:** every sensor in place — CT clamp on pump leg, level sensor in lid, soil probe at field edge with the small flag stake, opto tap inside OEM panel.
- **After:** Watchful enclosure mounted and closed, conduit runs visible, OEM panel restored, drain field with flag.

Minimum 8 photos. CRM rejects work-order completion below this threshold.

---

## 13. Common gotchas

- **Wrong CT leg.** If the CT is on the neutral or both legs, you'll read near-zero or chaos. Always verify with a clamp-on ammeter on the same leg as a sanity check.
- **Loaded-down OEM alarm.** If you accidentally land the opto across a 24V buzzer instead of the float input, you'll get continuous "alarm" telemetry. Re-verify against the OEM wiring diagram.
- **Lid-up enclosure mounting.** Water pools in the gasket channel and seeps through the screws. Always lid-down or lid-side.
- **Soil probe over a lateral.** Driving the probe through your customer's drain pipe is a bad day. Pace the laterals before driving.
- **Caliche soil.** If you can't drive the probe, switch to a sleeve install: drill a 24" hole with a fence post auger, slurry the probe in with native soil + water, let it settle 30 min before calibration.
- **Pump that won't run during commissioning.** Some controls pump-on only on float lift. If you can't get pump-on telemetry, mark the work order as "CT span calibration deferred — return on next service call." Don't fake the calibration.
- **Customer with WiFi-only mindset.** Reassure them: this is **cellular**, no WiFi password needed, no router config, no "smart home" anything.
- **Customer who wants the device removed if they sell the house.** That's fine — see `iot-decommission-sop.md`. Note in CRM that this customer is decommission-on-sale.
- **Drip loops missing.** In a heavy rain, water tracks down the cable into the enclosure. Failed installs from this in pilot — do not skip.

---

## 14. Tools required

### Hand tools
- 4-in-1 screwdriver
- Linesman pliers
- Wire strippers (10–22 AWG)
- Side cutters
- Crescent wrench
- Cordless drill + 1.5" hole saw + 1/4" bit
- Step bit (for conduit knockouts)
- Fence post auger (for soil probe in hard ground)
- Rubber mallet
- Tape measure

### Test gear
- Multimeter (true-RMS, AC/DC, continuity)
- Clamp-on ammeter
- Non-contact voltage tester
- Phone/tablet with CRM mobile

### Materials
- 16 AWG `THWN-2` (red, white, green) — 25 ft
- Gray PVC schedule 40 conduit + fittings — 10 ft assortment
- Liquid-tight flexible metal conduit (`LFMC`) — 6 ft
- Wire nuts, butt splices, ferrules
- UV-resistant zip ties (black only)
- Duct Seal
- Silicone (only on bracket-to-wall, never on enclosure)
- Butyl gasket roll (for tank lid)
- Dielectric grease
- Stainless lag screws (for bracket)
- "DO NOT ENERGIZE" tags

### Safety
- Insulated gloves (Class 0)
- Safety glasses
- Knee pads
- GFCI extension cord (if drilling on ungrounded post)

---

## 15. Sign-off

- [ ] OEM alarm verified working post-install.
- [ ] All four sensors calibrated, green in CRM.
- [ ] Cellular connectivity verified — `last_seen_at` within 5 min.
- [ ] No active alerts on the device.
- [ ] Homeowner walk-through complete, service agreement signed.
- [ ] Minimum 8 photos uploaded.
- [ ] Work order marked complete.

If any of the above is missing — work order stays open. Do not close.

---

**End of conventional install SOP.**
