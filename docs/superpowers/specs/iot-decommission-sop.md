# Watchful IoT — Decommission / Removal SOP

**Codename:** Watchful
**Operation:** decommission (RMA, customer cancellation, replacement, end-of-life)
**Audience:** Field service technician
**Estimated time:** 45–60 minutes
**Document version:** v1.0 — 2026-04-27
**Related spec:** `react-crm-api/docs/superpowers/specs/2026-04-27-iot-monitor-design.md`
**Related SOPs:** `iot-install-sop-conventional.md`, `iot-install-sop-atu.md`

---

## 0. When this SOP applies

- **Customer cancellation** — homeowner stopping the subscription, or selling the home and the new owner not opting in.
- **RMA** — device suspected faulty, returning to depot for inspection.
- **Replacement** — swap-out for a newer revision; new device installed at the same site (also follow the relevant install SOP after decommission).
- **End-of-life** — pilot device pulled, end of useful service life.

In all cases the customer's **OEM alarm panel must remain fully functional** after we leave. That is the load-bearing requirement of this entire procedure.

---

## 1. Pre-arrival checklist

- [ ] CRM work order open with `decommission_reason` set (cancellation / rma / replacement / eol).
- [ ] Device serial confirmed against CRM record.
- [ ] Customer notified of appointment window.
- [ ] If RMA: RMA number issued by depot, RMA tag printed.
- [ ] Tools (see §9). You'll need essentially the same kit as install, plus a roll of fresh wire nuts and a small parts-bin to catalog removed sensors.
- [ ] Empty space in the truck to bring back the device + sensor cards.

---

## 2. On-site arrival

1. Greet homeowner. Confirm scope: removing the Watchful device, restoring the OEM panel to its pre-Watchful state.
2. Reassure them: **the OEM alarm panel will still work normally after this** — we're only removing the supplemental notification gear.
3. Photograph the **current state** (device mounted, sensors in place, OEM panel) before any work begins. CRM rejects decom completion below 4 photos.

---

## 3. CRM unbind (do this first, on-site)

> Do the software unbind **before** the physical removal. This stops the device from reporting "alarm: power loss" the moment you cut the AC tap, which would dispatch nuisance SMS to the homeowner.

1. CRM mobile → **IoT** → device search → select device by serial.
2. Press **Unbind**.
3. Required fields:
   - `unbind_reason` — pick from the dropdown.
   - `unbind_notes` — free text, ~50 char minimum (e.g., "customer sold property, new owner declined").
   - `restored_oem_verified` — defaults to false; you'll flip this at the end (§7).
4. Confirm the device is now in **decommissioning** state in CRM. The MQTT bridge will silently drop telemetry from this device until it's fully archived. Alerts are suppressed.

---

## 4. Power-down sequence

Same as install (conventional §3 / ATU §4 with both breakers):

1. Open OEM panel, identify pump breaker (and aerator breaker if ATU).
2. Trip OFF, verify with multimeter at motor terminals.
3. **Tape "DO NOT ENERGIZE" on the breaker.**
4. Open the Watchful enclosure. Confirm the status LED has gone dark (after a brief UPS-discharge — may take 30 sec).

---

## 5. Remove sensors (catalog as you go)

For each sensor, photograph in place, then disconnect, label, and bag. Catalog into the truck parts-bin with sticker labels indicating which device serial they came from. The depot inventories returned sensors and re-issues if reusable.

### 5.1 OEM-ALARM-TAP

1. Disconnect the opto-tap leads from the OEM alarm terminals.
2. Restore any wire nut, ferrule, or terminal cover that was on the OEM terminal originally — the OEM terminal must look exactly like it did before our install.
3. Confirm with multimeter: OEM alarm terminal still reads its quiescent voltage with no foreign load.
4. Pull the tap card from the Watchful chassis, label and bag.

### 5.2 PUMP-CT-30A

1. Open the CT clamp jaw, slide off the pump leg.
2. Inspect the CT — if jaws are dirty/corroded, mark "RMA — sensor cleaning" rather than "reusable."
3. Pull the card, label, bag.

### 5.3 LEVEL-ULTRASONIC

1. Loosen the bulkhead fitting on the pump-tank lid.
2. Pull the sensor head out.
3. **Plug the lid hole** with the supplied 1.5" plastic plug (in the install kit) — do not leave an open hole on the tank lid. If you don't have a plug, use a piece of EPDM rubber + stainless self-tapper as a temporary cap; note in CRM that a proper plug is owed on the next service call.
4. Pull cable through conduit, coil, label, bag.

### 5.4 SOIL-MOIST-RS485

1. Locate the probe (the flagged stake from install).
2. Pull straight up — sometimes the probe is reluctant after months in clay. A small auger around the probe makes it easier.
3. Backfill the hole.
4. Pull the cable from its conduit run, coil, label, bag.

### 5.5 ATU-only sensors (if applicable)

- `AERATOR-CT-15A` — same procedure as pump CT.
- `ATU-CONTROL-BUS` — same as alarm tap, but multiple terminals; document each disconnection on a sticky note attached to the OEM panel door so the next tech sees what we removed.
- `CHLORINATOR-FLOW` — pull from chlorinator housing, restore any plug or cap.

---

## 6. Remove the Watchful device

1. Disconnect the AC tap inside the OEM panel:
   - Remove the in-line 3 A fuse first.
   - Land the OEM-side wires on a fresh wire nut (capped, dead-ended) — do **not** leave bare ends in the panel.
   - Tape the dead-end wires off and tuck behind the OEM terminal block.
2. Disconnect the Watchful AC input terminal block.
3. Remove the Watchful enclosure from its bracket (loosen bracket screws, lift off).
4. Bracket: remove if reusable; if lag screws are deeply set, leave the bracket and remove only the enclosure (note in CRM).
5. Pull the conduit between OEM panel and Watchful — coil and bring back. If conduit is glued or otherwise non-recoverable, leave it but cap the ends weatherproof with end caps.
6. Disconnect the cellular SIM:
   - **For RMA:** leave the SIM in the device. Depot will inspect and re-issue.
   - **For replacement at the same site:** transfer the SIM to the new device (depot will reprovision before re-deployment) — do not transfer SIMs in the field.
   - **For cancellation:** leave the SIM in the device. Depot will rotate the SIM into the spare pool.

---

## 7. Restore OEM panel cabling to original state

This is the load-bearing step. Walk through it carefully.

1. Close the OEM panel cover.
2. Remove the "DO NOT ENERGIZE" tag.
3. Restore the pump breaker (and aerator breaker, if ATU).
4. Verify OEM panel wakes up normally — same indicators as pre-install.
5. **Manually trip the OEM alarm float** by lifting it. Confirm:
   - OEM panel buzzer fires.
   - OEM panel alarm light comes on.
   - Test silence/reset functionality on the OEM panel works.
6. Release float. Alarm clears.
7. If ATU: confirm aerator re-starts within the OEM's normal startup window.

> **If the OEM alarm does not work post-removal:** stop. Do not leave site. Troubleshoot the OEM circuit — the most likely cause is a wire nut backed off when we disconnected our tap, or a control wire bumped during sensor removal. Restore OEM functionality before any other completion step.

In CRM, flip `restored_oem_verified=true` only after this verification is complete and the OEM alarm has been successfully tripped and cleared.

---

## 8. Tag device for RMA / depot

1. Apply RMA tag to the device with the printed RMA number, decommission reason, and your tech ID.
2. Bag the device + sensors together — same physical bin, single label.
3. Note in CRM:
   - Photo of the tagged device.
   - Photo of the OEM panel post-restoration.
   - Photo of the location where the Watchful was mounted (now empty / bracket only).
   - Free-text decommission notes (anything unusual about the install — corroded contacts, missing sensors, customer feedback, etc.).
4. Mark the work order as **complete**. CRM will:
   - Set `iot_devices.archived_at` = now.
   - Insert an `iot_device_bindings` row with `unbind_reason` and `restored_oem_verified=true`.
   - Suppress all future telemetry/alerts from this device serial (until it's re-provisioned).

---

## 9. Tools required

Same as install (conventional + ATU as applicable), plus:

- Empty parts-bin (sensors travel back labeled and bagged).
- Sharpie + sticker-label sheets (label each pulled sensor).
- Fresh wire nuts (replace any that loosen during removal).
- 1.5" lid plug (for ultrasonic sensor's pump-tank lid hole).
- End caps for any abandoned conduit runs.
- RMA tag printout (one per device).
- Camera-ready phone (CRM mobile open).

---

## 10. Common gotchas

- **Decommissioning before unbinding in CRM.** Disconnecting AC before pressing Unbind triggers a `POWER_LOSS` alert that SMS-blasts the homeowner. Always unbind first.
- **Forgetting to plug the pump-tank lid hole.** Bugs, water, debris into the tank. Customer complaint guaranteed within a week.
- **Not verifying OEM alarm post-removal.** Highest-risk failure mode of this entire SOP. Customer loses primary alarm without knowing it. **Do not skip §7 step 5.**
- **Restoring OEM wiring sloppily.** A backed-off wire nut on the OEM alarm float circuit looks fine on the multimeter at one moment and intermittents the next time the float lifts. Re-torque every OEM connection you touched.
- **Leaving live AC wires capped but loose in the OEM panel.** Wire-nut + tuck behind the terminal block, not free-floating where they can rub the metal door. Document with a photo.
- **Walking off without the SIM accounted for.** SIMs are tracked. Per-device asset tracking will catch a missing SIM at depot and bill it back to the work order.
- **Forgetting the soil probe in the ground.** The flag stake is small, the probe is buried. If you don't follow the conduit run on purpose, you'll miss it. Asset-tracker complains; sensor goes uncatalogued.
- **Aerator that doesn't restart after the breaker comes back.** Same thermal-cutout latch as install — wait 15 minutes, it'll start. If it still doesn't, that's a pre-existing issue, not something we caused — log and recommend service.
- **Customer wants to keep the Watchful enclosure mounted "just in case they sign back up."** Standard policy: enclosure goes back. If the customer specifically requests we leave the bracket on the wall, fine — log a "bracket-only on site" note. Never leave the enclosure on a decommissioned site (asset control).

---

## 11. Sign-off

- [ ] CRM unbind completed BEFORE physical removal.
- [ ] All sensors removed, cataloged, bagged, labeled.
- [ ] Watchful enclosure removed; SIM accounted for.
- [ ] OEM panel restored, wires properly capped.
- [ ] OEM alarm float tripped and verified — alarm fired, then cleared.
- [ ] (ATU only) Aerator restarted post-power restore.
- [ ] `restored_oem_verified=true` flipped in CRM.
- [ ] Minimum 4 photos uploaded (before, during, OEM-restored, RMA-tagged device).
- [ ] Work order marked complete with decommission notes.

---

**End of decommission SOP.**
