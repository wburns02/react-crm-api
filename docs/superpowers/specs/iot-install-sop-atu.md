# Watchful IoT — ATU (Aerobic Treatment Unit) Install SOP

**Codename:** Watchful
**Install type:** `atu` (aerobic treatment with aerator + chlorinator)
**Audience:** Field service technician
**Estimated install time:** 150–180 minutes
**Document version:** v1.0 — 2026-04-27
**Related spec:** `react-crm-api/docs/superpowers/specs/2026-04-27-iot-monitor-design.md`

---

## 0. What you're installing

Same Watchful enclosure as the conventional SOP, but with the **full sensor stack**. ATU systems have additional moving parts (aerator pump, chlorinator) and the OEM control panel exposes additional signals worth tapping.

This SOP **adds** to the conventional one — the conventional steps still apply for OEM alarm, pump, level, and soil. Read `iot-install-sop-conventional.md` first; this document covers the deltas.

Sensor population for ATU install:

| Sensor card | Where it goes | Notes |
|---|---|---|
| `OEM-ALARM-TAP` | Opto-iso parallel tap on OEM alarm circuit | Same as conventional |
| `PUMP-CT-30A` | CT clamp around effluent pump's hot leg | Same as conventional |
| `LEVEL-ULTRASONIC` | Pump-tank or treatment-tank lid (per OEM) | Tank choice varies — see §3 |
| `SOIL-MOIST-RS485` | Drain field at field edge | Same as conventional |
| `AERATOR-CT-15A` | CT clamp around the aerator's hot leg | NEW |
| `ATU-CONTROL-BUS` | Reads ATU panel control signals (varies by OEM) | NEW — see OEM subsections |
| `CHLORINATOR-FLOW` | Mounted at chlorinator housing | NEW |

**Regulatory reminder:** ATUs are inspected 3×/year under TX 30 TAC §285. Watchful is supplemental; the OEM panel and contracted maintenance provider remain the regulated path.

---

## 1. Pre-arrival checklist (additions to conventional)

- [ ] CRM work order open with `install_type=atu` AND OEM brand recorded (`norweco`, `aquaworx`, `hoot`, `bio-microbics`, `delta`, `clearstream`, or `other`).
- [ ] Brand-specific guidance reviewed (this document, §8).
- [ ] Sensor cards: all conventional cards plus `AERATOR-CT-15A`, `ATU-CONTROL-BUS`, `CHLORINATOR-FLOW`.
- [ ] OEM panel docs printed or downloaded offline (terminal pinouts vary).
- [ ] **Customer's maintenance contract status confirmed** — if they're under a non-MAC contract, the warranty implications of opening their OEM panel may differ. Check before touching the panel.
- [ ] Spare chlorinator tablets (sometimes a chlorinator is empty and the customer doesn't know — bring 2 lbs of trichlor pucks just in case).

---

## 2. On-site site survey (15–25 min — longer than conventional)

In addition to conventional §2:

5. Locate the **aerator pump** — typically a riser cap labeled "Aerator" or color-coded green. Confirm it's running (audible hum, vibration on the lid). If it's not running, that's a pre-existing service issue — log in CRM and follow shop policy (likely a separate work order before install proceeds).
6. Locate the **chlorinator** housing — usually a separate riser between the aerobic chamber and the discharge. Lift the lid:
   - Confirm tablets are present (replenish if not, log a service charge).
   - Note flow path orientation.
7. Locate the **OEM control panel** — for ATUs this is a more substantial enclosure than conventional, with multiple signal terminals exposed. Photo the panel face AND the inside of the door (where the wiring legend lives).
8. Pace the **aerator's electrical run** — sometimes aerator and effluent pump share a circuit, sometimes separate. Note which.

---

## 3. Tank choice for level sensor

ATUs have multiple tanks:
- **Trash/primary tank** (settling — tank level here is rarely interesting).
- **Aerobic chamber** (active treatment — level changes mean influent rate, useful for advanced telemetry but not v1).
- **Pump tank / clarifier** (where the effluent pump sits — this is where conventional level sensors go).

**v1 default:** mount the `LEVEL-ULTRASONIC` on the **pump tank lid**, same as conventional. Trash and aerobic levels deferred to v2.

If the OEM design doesn't have a separable pump tank (some Singulair models pump from the clarifier), mount on the clarifier lid above the high-water float.

---

## 4. Power-down sequence (additions to conventional §3)

ATUs typically have **two breakers** at the OEM panel: pump and aerator. Trip BOTH OFF and verify with multimeter at each motor's terminals before opening anything. Aerator runs continuously on most designs — if you touch a live aerator lead, it'll bite.

---

## 5. Wiring sequence (deltas)

After completing conventional §5.1–5.6:

### 5.7 Aerator CT clamp

1. Open the `AERATOR-CT-15A` clamp jaw, pass it around the **aerator's hot leg only**. Aerators are typically 1/3 hp single-phase, drawing 4–6 A continuous. The 15 A CT is sized for this with margin.
2. Snap closed, route to Watchful `CT2`.
3. Aerator runs continuously, so calibration is "running current" — you don't get a clean zero unless you cut power. The Watchful auto-calibrates by sampling the AC-off transient at the next power-loss event; for v1, just record the running value during commissioning.

### 5.8 ATU control bus

This is **OEM-specific** — see §8 for per-brand wiring.

The `ATU-CONTROL-BUS` card provides 6 opto-isolated digital inputs and one RS-485 channel. We tap whichever signals the OEM exposes:
- **Aerator-on** (most common — directly indicates aerator activity, redundant with CT but handy for fault correlation).
- **High-water alarm** (sometimes separate from main OEM alarm).
- **Aerator fault** (some panels expose a separate aerator-fail signal).
- **Chlorinator low** (rare; only Bio-Microbics FAST and some Norwecos expose this).

Land each used input on the bus card's terminals; in CRM during pairing, label which physical input maps to which signal (the install app prompts you brand-by-brand).

### 5.9 Chlorinator flow / presence sensor

1. Mount the `CHLORINATOR-FLOW` sensor at the chlorinator's discharge — depending on revision this is either a flow vane (mechanical) or a conductivity probe (detects flowing chlorinated water).
2. Cable run in same UV conduit family as conventional sensors.
3. Land on Watchful `4-20mA-2`.

This sensor's job is primarily to detect "chlorinator empty" — if flow is happening but conductivity is freshwater (no chlorine), tablets are out.

---

## 6. Power-up sequence (additions to conventional §6)

After the conventional power-up:

5. Restore the **aerator breaker**. Verify the aerator starts (hum, lid vibration). Some OEM panels have a 30–90 second startup delay — wait through it.
6. Watchful's `CT2` (aerator) should show ~4–6 A within a minute of aerator startup.
7. Verify the **chlorinator** sees flow during the next pump cycle — manually trigger a pump cycle if the OEM panel allows it (test button); otherwise log baseline and verify on next service call.

---

## 7. Pair, calibrate, verify, walk-through

Same as conventional §7–11, with additions:

### Calibration additions
- **Aerator CT running value** — sample 60 seconds with aerator running, store as nominal.
- **ATU control bus mapping** — install app walks you through each signal: "is this aerator-on right now? Y/N." Brand-keyed.
- **Chlorinator baseline** — sample 60 seconds during a pump cycle; mark "tablets present" or "empty" based on observation.

### Walk-through additions
- "We're also watching your aerator and your chlorinator. If your aerator stops or your chlorinator runs out of tablets, we'll know — and so will the tech who comes for your next quarterly inspection."

---

## 8. OEM-specific subsections

> **Universal warranty rule:** never cut, splice, or load down OEM signal terminals. Parallel taps only on the opto-isolated card. If you touch an OEM control wire with anything other than a multimeter probe or a parallel opto, you may void the OEM warranty.

### 8.1 Norweco Singulair (Green model, 960 / TNT)

- **Control board:** big green PCB at the top of the panel. Look for the labeled terminal strip on the right side: `AIR`, `ALM`, `PMP`, `COM`.
- **Aerator-on signal:** between `AIR` and `COM`. Reads ~24 VAC when aerator is running. Land opto across these two terminals.
- **Alarm signal:** between `ALM` and `COM`. Same 24 VAC nominal. (Use this for `OEM-ALARM-TAP` instead of the float terminals on Singulairs — cleaner signal.)
- **Common mistakes:**
  - Tapping the **buzzer** terminals instead of the alarm logic terminals — buzzer pulses, alarm logic is a stable level.
  - Ignoring the Service Pro MCD if the customer already has one — coexistence is fine, but document MCD presence in CRM (it doesn't conflict, but the homeowner may get duplicate notifications from Norweco).
- **Mounting:** Singulair panels often have spare conduit hubs on the bottom — use one for the Watchful AC tap if available.

### 8.2 Aquaworx (Infiltrator)

- **Control panel:** typically a smaller white enclosure with a 2-line LCD. Terminals are inside the panel under a separate cover.
- **Panel-tap notes:** Aquaworx exposes `AER`, `ALM`, `PMP`, `COM` similar to Norweco but at **12 VDC** signal levels, not 24 VAC. The opto card auto-detects polarity but you must respect the voltage range — confirm by multimeter before connecting.
- **Warranty considerations:**
  - Aquaworx warranty terms specifically prohibit any third-party connection that **draws current** from the control board. Our opto presents <1 mA — well under their stated limit (5 mA) — but document the current draw in your install notes for warranty defense if it's ever questioned.
  - Do NOT modify the firmware or replace the control board. Watchful is parallel only.
  - Photograph the warranty sticker on the inside of the panel door before opening — proves it was intact when we arrived.
- **Tracker product:** if the customer has the Aquaworx Tracker installed, coexistence is OK but document it. Tracker's cellular path is independent.

### 8.3 Hoot Aerobic

- **Control panel:** Hoot panels vary widely by year. Older units (pre-2015) often have only an alarm float and a pump contactor — no separate control signals to tap. In that case:
  - `OEM-ALARM-TAP` on the float (same as conventional).
  - `AERATOR-CT-15A` on the aerator leg (only telemetry from the aerator on these older units).
  - Skip `ATU-CONTROL-BUS` — log "no control bus available" in CRM during pairing.
- Newer Hoot units (post-2018) expose `AIR-RUN` and `ALM-OUT` on a small terminal strip at the bottom of the panel — typical 24 VAC.
- **Common control signals:**
  - `AIR-RUN` — aerator-on, normally high (24 VAC) when running.
  - `ALM-OUT` — alarm active, normally low (0 VAC) and goes high on alarm.
- **Common mistakes:** Hoot installers sometimes use the unused `EXT-OUT` terminal for unrelated wiring (heat tape, etc.). Verify with multimeter — don't assume it's a Hoot-defined signal.

### 8.4 Bio-Microbics FAST

- **Control panel layout:** rectangular gray enclosure, terminal blocks along the bottom edge, labeled `L1`, `L2`, `N`, `G`, then `AIR`, `PMP`, `ALM`, `CHL` in sequence.
- **Chlorinator-low signal:** Bio-Microbics is the only OEM in our v1 list that exposes a dedicated chlorinator-low contact (`CHL`). Tap it — saves the `CHLORINATOR-FLOW` sensor from having to infer.
- **`CHL` signal characteristics:** dry contact, normally closed (continuity = tablets present). Goes open when tablet level is below the float. Land on a free opto input on `ATU-CONTROL-BUS`.
- **Common mistakes:** treating `CHL` as a powered signal — it's not, it's a dry contact. The opto card supplies its own bias.
- **Bio-Microbics MicroFAST specific:** smaller residential model, same terminal layout but no `CHL` exposure — fall back to the `CHLORINATOR-FLOW` sensor.

### 8.5 Delta Whitewater / Delta ECOPOD

- **Control panel:** Delta panels are simpler — typically alarm + aerator-on indicator, no formal terminal strip for external integration.
- **Approach:** treat as conventional+aerator. Tap alarm at the float, aerator with CT only. Document "no external control bus" in CRM.
- Newer ECOPOD-N units have a `RS-485 Modbus` port — out of scope for v1, deferred to v2.

### 8.6 Clearstream / Other

For any OEM not listed above:
- Photograph the panel face, door, and inside terminal strip.
- Tap **only** what you can verify with a multimeter and a clear OEM diagram.
- If in doubt, fall back to: alarm at the float + aerator at the CT + skip the control bus. Log "control bus deferred — returning OEM doc to depot for engineering review."
- Engineering will add a per-brand subsection here once we've seen 3+ installs.

---

## 9. Common gotchas (in addition to conventional §13)

- **Aerator on a separate sub-panel.** Sometimes the aerator is fed from a different breaker panel than the OEM control box. CT is still installed at the aerator motor — but the sub-panel circuit may have a different breaker location. Document.
- **Customer's prior maintenance provider already has a "monitor."** Some customers under contract with their OEM have an MCD/Tracker/etc. already. Coexistence is fine but document it; ours adds drain-field saturation and pump-current trending that theirs doesn't have.
- **Chlorinator empty at install.** Common. Refill, charge for tablets, log so the next service call comes ready.
- **24 VAC vs 24 VDC vs dry contact.** Always verify with multimeter before landing the opto. Wrong assumption gets you a dead opto channel.
- **Aerator that won't restart after power-down.** Some old aerators have a thermal cutout that latches if they were running hot. Wait 15 minutes after power-down before restart, or expect a delay.
- **Warranty stickers torn during install.** Photograph BEFORE opening. If a sticker tears during normal access, customer's existing OEM warranty may already have been compromised by their last service tech — proves it wasn't us.
- **Singulair Service Pro MCD double-alerts.** Customer gets our SMS *and* a Norweco SMS. Address in walk-through: "you may get both for now; ours is supplemental."
- **Long aerator runs.** Some installs have the aerator 50+ ft from the OEM panel. CT lead extension is OK up to ~25 ft, after that use a junction box with shielded cable. Don't free-run beyond 25 ft.

---

## 10. Tools required (additions to conventional §14)

### Additional hand tools
- Small flathead screwdriver (control panel terminal blocks are tiny).
- Cable tone generator + probe (helpful for tracing OEM signals when labels are missing or wrong).

### Additional test gear
- Second clamp-on ammeter (so you can trend aerator + pump simultaneously without re-clamping).
- Continuity tester / dedicated dry-contact tester (for Bio-Microbics `CHL` and similar).

### Additional materials
- Spare 1/3 hp aerator-leg fuse (in case you trip something).
- Trichlor tablets (2 lb bag) — assume the chlorinator is empty.
- Gas-tight bushings for OEM panel knockouts (some OEMs require these for warranty).

### Additional safety
- N95 respirator — older aerobic chambers off-gas hard when opened.
- Hand sanitizer + nitrile gloves (you will touch effluent).

---

## 11. Sign-off (in addition to conventional §15)

- [ ] Aerator running and reading on `CT2` within nominal range.
- [ ] ATU control bus mapping recorded in CRM (or "deferred — no exposed bus" logged).
- [ ] Chlorinator status confirmed (tablets present + flow detected, or empty + replenished).
- [ ] OEM brand + model recorded in CRM device record.
- [ ] Warranty sticker photographed pre- and post-install.

---

**End of ATU install SOP.**
