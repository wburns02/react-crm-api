# Watchful — From Breadboard to Real Septic Tank
**Version:** v0.1 — bridging the gap between bench prototype and deployed device
**Audience:** you, after you've completed the beginner build and seen telemetry on the dashboard
**Time:** ~2 hours additional shopping + 3–4 hours install on the tank
**Cost:** ~$120 in additional parts (one-time, on top of the beginner build)

> Prerequisite: complete the **First Device Beginner Build** first. That validates the cloud + firmware + cellular path on your bench. **Don't deploy to a real tank until simulator readings are landing reliably on the dashboard for at least 24 hours.**

---

## What changes between bench and real tank

The breadboard build deliberately uses simulator-grade sensors and a wide-open layout. You proved the entire stack works. Going to a real tank, **the firmware doesn't change** — it's the same cellular cloud connection, the same MQTT topics, the same alerting. **What changes is the physical world:**

| Concern | Bench | Real tank |
|---|---|---|
| **Sensor housing** | Bare PCB on breadboard | Sensors that survive water, methane, UV, and -10°F to +120°F |
| **Cabling** | 4" jumper wires | UV-rated outdoor cable, sometimes 30+ ft |
| **Enclosure** | Open breadboard | IP65 polycarbonate box mounted on a wall |
| **Power** | USB from your laptop | 12V wall adapter into a nearby exterior outlet, or the OEM panel's auxiliary terminal |
| **Alarm signal** | A pushbutton you press | A real OEM alarm panel's relay output, tapped via opto-isolator |
| **Drain field probe** | DFRobot in a glass of water | Same probe, but buried 12" deep at the field edge, sealed splice |
| **Pump current** | YHDC clipped on extension cord | YHDC clipped inside the OEM pump panel, around the pump's hot leg |

The **firmware does not need to change**. The same `nrf9160dk_nrf9160_ns` build that runs on your breadboard runs on the deployed device, reading the same sensor types, publishing to the same topics. **Confidence builder: this is by design.** It means you only ever debug one piece at a time.

---

## Minimum scope for "first real tank"

**Pick the smallest possible install for your first real deployment:**

1. **Use your own septic system if you have one** — or a friend/family member's, with permission. **Do not deploy to a paying customer's tank as your first real-world build.** You'll find issues. Learn on a system where the consequences are zero.
2. **Wire only the OEM alarm tap and pump current sensor** for the first install. Skip the level sensor and drain-field probe. Those add complexity (lid mounting, burial, sealing) and aren't needed to prove "we can detect a real failure event."
3. **Test it for 14 days minimum** before touching it again. Real-world telemetry shows you problems that bench testing can't (cellular flapping, methane corrosion patterns, condensation cycles).

This minimum scope cuts the cost and complexity by ~half versus a full install.

---

## What to add to your shopping cart

In addition to the parts you already have from the beginner build:

### Enclosure ($35)

| Part | Source | Why |
|---|---|---|
| Hammond 1554J3GY (8x6x3" IP65 polycarbonate) | [Digi-Key HM997-ND](https://www.digikey.com/en/products/detail/hammond-manufacturing/1554J3GY/1646193) | $22 — bigger than the BUD enclosure listed in the production BOM, easier to work with for a first install. UV-stable polycarbonate. |
| Cable glands M16 IP68, qty 4 | [Amazon B07FXBKVN1](https://www.amazon.com/s?k=Heyco+M16+cable+gland+IP68) | $12 / 10-pack — one per cable entering the enclosure |
| Mounting feet / wall-mount bracket | included with Hammond, or McMaster | $0 |

### Cabling ($30)

| Part | Source | Why |
|---|---|---|
| 18 AWG outdoor 4-conductor cable, 50 ft | [Amazon — Belden 1330A or Southwire equivalent](https://www.amazon.com/s?k=18+AWG+outdoor+4+conductor+UV+rated+cable) | $25 — runs from device to drain-field probe + sensor lines. UV-rated. |
| Wago 221-415 lever-nut connectors (10 pack) | [Amazon B0758CWB6Z](https://www.amazon.com/dp/B0758CWB6Z) | $7 — for splicing inside junction boxes |
| Outdoor junction box (4x4x2") | [Home Depot — Carlon B121R-CAR or similar](https://www.homedepot.com/) | $5 | for any outdoor splice point (e.g., where drain-field probe cable meets device cable) |

### OEM alarm tap interface ($15)

| Part | Source | Why |
|---|---|---|
| 24VAC-tolerant opto-isolated relay module | [Amazon B07PJ6T4XK](https://www.amazon.com/s?k=Songle+SRD+24V+optocoupler+relay+module) | $7 — wires between the OEM panel's alarm output and the DK's digital input. Crucially: galvanic isolation = the DK can't be damaged by a panel surge. |
| Connecting wires (already have) | — | $0 |

If your OEM panel has a **dry-contact alarm output** (most do — read the panel's wiring diagram or just Google your panel's manual), you can skip the opto-relay and wire the dry contact directly to a DK GPIO with a pull-up. Cheaper but less safe; pick the opto-relay for your first install.

### Weatherproof ultrasonic (optional — only if doing tank level on first install)

If you really want tank level on day one — but I'd skip this for the first install:

| Part | Source | Why |
|---|---|---|
| JSN-SR04T weatherproof ultrasonic | [Amazon B07JZGMWMT](https://www.amazon.com/s?k=JSN-SR04T+waterproof+ultrasonic) | $9 — the IP67-rated cousin of the HC-SR04. Same firmware, same wiring, can sit on a tank lid. |

The JSN-SR04T's sensor head is sealed; the controller board is not. Mount the head through a hole in the tank lid (drill a 22mm hole, gasket the back), and put the controller board inside the device enclosure with a 5–10 ft pigtail between them.

### Total: ~$120 additional

---

## Installation procedure — first real tank

### Phase 1: Site survey (30 min, before you bring anything)

**Visit the site first, with no parts.** Map out:

- [ ] Where is the OEM panel? Take a photo of the inside (after killing the breaker — see safety below). Find the alarm output terminals — usually labeled "ALARM," "AUX," or similar. Read the panel's installation manual if you can find it (Norweco, Aquaworx, Hoot, Bio-Microbics, etc. all have PDFs online).
- [ ] Is there a 120V exterior outlet within 6 ft of where you'll mount the device? If not, plan for an extension cord initially; permanent power is a later task.
- [ ] How does the pump's hot leg run? You'll need to clip a CT clamp around it inside the panel. Confirm it's accessible.
- [ ] What's cellular coverage like at the site? Use your phone in airplane mode + LTE-only mode and check signal strength near the pump panel. A 5-bar phone is fine; <2 bars and you'll need to move the device or add an external antenna.
- [ ] Photo-document everything before you change anything. Saves debug time later.

### Phase 2: Safety (CRITICAL — read every line)

**Septic pump panels carry 120V or 240V. Fatal. Don't touch live wiring.**

- [ ] At the breaker panel, **turn OFF the dedicated breaker for the septic pump and OEM alarm**. Tag it (electrical tape with your name + date) so nobody else flips it back on.
- [ ] Verify dead with a non-contact voltage tester at the OEM panel screw terminals before opening anything. Touch the tester to the line side of the breaker first to confirm the tester is working — then to the panel terminals — should beep at the breaker, NOT beep at the panel.
- [ ] If the OEM panel has a 24VAC alarm circuit on a separate transformer, **that's still energized** — kill its breaker too, or unplug the transformer.
- [ ] If you've never done this before: ask a licensed electrician to handle the panel-side wiring. The savings of doing it yourself are not worth the consequences. **Wire nuts on a hot circuit will burn your house down.**

### Phase 3: Enclosure prep (30 min, on your bench)

- [ ] Mount the DK and breadboard inside the Hammond enclosure. Use velcro or 3M VHB tape (no drilling — the IP65 seal needs to stay intact except where you intentionally route cable glands).
- [ ] Drill 4 holes for cable glands in the enclosure: 1 for AC power input, 1 for OEM alarm tap line, 1 for pump CT cable, 1 for drain-field probe (even if not used yet — easier to plan now).
- [ ] Install cable glands, finger-tight + 1/4 turn with a wrench. Each gland comes with a rubber gasket — make sure it's on the outside.
- [ ] Verify enclosure closes cleanly, gasket seats fully.

### Phase 4: Sensor pre-routing (30 min)

- [ ] Cut three lengths of 18 AWG outdoor cable: ~3 ft (panel to device), ~10 ft (drain-field probe pigtail — even if not deployed today), and a short pigtail for the CT clamp pass-through if needed.
- [ ] Pre-route cables through their cable glands BEFORE you mount the enclosure on the wall — much easier on a workbench.

### Phase 5: Mount the device (15 min, at the site)

- [ ] Pick a wall location near (within 3 ft of) the OEM panel, at adult eye level, sheltered from direct rain if possible.
- [ ] Mount the Hammond enclosure with the supplied flange or two screws into a stud / pressure-treated wood block.
- [ ] Plug the device into the nearby exterior 120V outlet via the 12V wall-wart.
- [ ] Power on. Verify the DK boots and connects to LTE within 60 seconds (if you have a phone, watch the dashboard at react.ecbtx.com/iot for the device coming online).

### Phase 6: OEM alarm tap (45 min)

This is the **only step that touches the OEM panel.** Take your time.

1. Open the OEM panel (breaker still OFF — verify dead AGAIN before touching anything).
2. Locate the alarm output terminals. They're usually a 2-screw block labeled `ALARM`, `AUX`, or similar, with a low-voltage signal (24VAC dry contact, or 5–12VDC).
3. Run two conductors of your 18 AWG cable from the alarm terminals back to your device's enclosure (through the cable gland). **Use the existing knockouts on the OEM panel — don't drill new ones.**
4. Inside the device enclosure: connect the two cable conductors to the IN+ and IN- of the opto-isolated relay module.
5. Wire the opto-relay's OUT terminals to a DK GPIO + GND (same pins as the breadboard pushbutton).
6. Cap any unused conductors with a wire nut and stuff into a junction box — never leave bare copper.
7. Close the OEM panel. Restore breaker. Verify OEM alarm panel powers up normally (should see a power LED or hear the test buzzer briefly).
8. Test the alarm circuit: most OEM panels have a "TEST" button that fires the alarm output. Press it. **The dashboard should fire a critical alert within 5 seconds and your phone should buzz with an SMS.**
9. If it doesn't fire: check the relay module's onboard LED — if the LED lit when you pressed TEST, the panel side is working. If the LED didn't light, you've got the panel-side polarity wrong (try swapping the two conductors).

### Phase 7: Pump CT clamp (30 min)

1. Re-kill the breaker. Verify dead.
2. Inside the OEM panel, locate the pump's HOT (black) wire — it's the conductor running from the breaker to the pump's contactor coil.
3. Clip the YHDC SCT-013-030 CT clamp around the BLACK wire only. Not the neutral, not both. Just the hot.
4. Run the CT's pigtail cable back to the device enclosure through the cable gland.
5. Inside the enclosure, connect the CT's 3.5mm jack to the Adafruit screw-terminal breakout, and the breakout's terminals to the DK ADC pins (same as the bench build).
6. Restore breaker. The pump won't run unless the float trips, but you can verify the CT is reading correctly by checking the dashboard — current should read ~0A when pump is off, then jump to 3–7A when the pump kicks on (often happens once or twice a day for residential systems).

### Phase 8: Walk away (the hard part)

- [ ] Close the enclosure, finger-tighten + 1/4 turn each gland.
- [ ] Photograph everything for your records.
- [ ] Leave the site.
- [ ] **Do not return for 14 days.** Watch the dashboard. Look for:
  - Daily check-in cadence holding steady
  - Pump current readings landing in expected ranges
  - No spurious alarm fires (means your tap is good)
  - No telemetry gaps longer than ~1 hour (means cellular is solid)
- [ ] Day 14: revisit, check for visible water ingress, condensation inside the enclosure, gasket integrity. Make notes.

---

## Common first-install gotchas

**Cellular signal is fine on your phone but the device won't attach.** The DK's antenna is omnidirectional but small. Try moving the device 10 ft, or add an external SMA antenna (DK has a U.FL connector). Sometimes proximity to the OEM panel's switching power supply causes interference — move the device 3+ ft away.

**OEM alarm fires within seconds of installing the tap and won't clear.** Most likely the panel's alarm circuit is normally-OPEN (dry contact closes on alarm) but you wired it normally-CLOSED. Swap your firmware's logic in `src/sensors/sensor_alarm_tap.c` from `GPIO_PULL_UP / active-low` to `GPIO_PULL_DOWN / active-high`. Or just swap the two wires at the relay module.

**Pump current reads 0A even though the pump runs.** CT clamp didn't latch fully closed — open it and re-clip until you hear it click. Or you clipped around BOTH conductors instead of just one — they cancel out. Or you're reading the neutral leg, not the hot — re-route to the hot.

**Condensation inside the enclosure on day 3.** Cable glands not tightened enough, or one of the conduit entries is sealed but the other side of the cable run isn't. Add a small desiccant pack inside (silica gel, 5g, $2 on Amazon). Add a Gore vent (M12 size, $3) to the enclosure — equalizes pressure without letting water in.

**The device went silent for 6 hours overnight.** Two likely causes: cellular coverage degraded after dark (rare but happens with weak signal), or the wall-wart died (cheap ones do). The device's onboard battery (LiSOCl₂ if you ordered one — optional in the beginner build) should keep it alive for power-loss alerts. Check the dashboard for a `power_loss` event before you blame cellular.

---

## What this gets you

A working device, in the field, on a real septic system, with:
- ✅ Cellular telemetry every 12 hours
- ✅ Immediate alert if the OEM alarm fires
- ✅ Pump current trend (predictive — catches stalled, dry-run, or short-cycling)
- ✅ Power-loss notification
- ✅ The same firmware that will run on the production hardware

What it does NOT get you yet (deferred to phase 2 and 3 of the install):
- ❌ Tank level monitoring (needs JSN-SR04T mounted in tank lid, or floats)
- ❌ Drain field saturation (needs probe buried at field edge)
- ❌ Aerator current (ATU-only, needs second CT clamp)
- ❌ Tamper / cabinet door

Add those in phases over the following weeks once the basic install proves stable.

---

## When you're ready to install on a paying customer's tank

You're ready when:
- [ ] You've had at least one device running on your own (or a friend's) tank for 30 consecutive days with no false positives, no missed events, and no manual intervention
- [ ] You can install a device end-to-end in under 2 hours
- [ ] You have a service agreement template (covers liability — see the spec's section 15) signed by the customer
- [ ] Your insurance broker has reviewed and approved your product liability + technology E&O coverage

That's the gate to commercial deployment. The first 5 customer installs follow `iot-install-sop-conventional.md` (or `-atu.md` for aerobic systems) — those docs are tech-facing, written for installers who don't need to know the cloud architecture, just the field procedure.

---

## TL;DR

The breadboard build is a deliberate **simulator** — point it at the cloud, prove every layer of the system works, on your bench, with no risk. **The firmware doesn't change between breadboard and real tank.** What changes is enclosure, cabling, OEM alarm tap, and physical sensor mounting. Total additional cost ~$120; total additional time ~6 hours. **Always do the first real install on your own septic system, never a customer's, and let it soak for 14 days before touching it.**
