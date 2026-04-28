# Watchful — Your First Device (Beginner Build)
**Version:** v0.1 — beginner-friendly, **no soldering required**
**Time:** ~3–4 hours total (2 hours hands-on, plus 30 min for cellular activation + ~1 hour of waiting)
**Cost:** ~$475 in parts, one-time (updated 2026-04-27 — Nordic raised the DK price)
**Status:** This guide is for building **exactly one device** to validate the cloud pipeline end-to-end before committing to a custom PCB. Everything here uses plug-and-play parts you screw, plug, or jumper together.

> **For ordering:** the canonical, link-checked parts list lives in `iot-parts-list-with-links.md` (PDF #08). Prices and part numbers are verified live as of 2026-04-27. **Use that doc as your shopping cart**; this guide explains the *what* and *why*.

---

## What you're building

A single working Watchful device, sitting on your bench, that:
1. Reads simulated sensors (CT clamp around any plugged-in appliance, moisture probe in a glass of water, etc.)
2. Connects to LTE cellular (no WiFi)
3. Publishes telemetry every 10 seconds (faster than production for testing)
4. Shows up live on the MAC Septic CRM dashboard
5. Triggers an SMS alert when you "fire" the alarm tap by touching two wires together

That's it. No PCB design. No SMT. No solder paste. **The only "soldering" in this guide is two optional wire splices at the very end, and we'll use solderless butt-splice connectors instead.**

If you've used a Raspberry Pi to read sensors, this is the same skill set. The Nordic **nRF9160-DK** plays the role of the Pi.

---

## Why the nRF9160-DK?

The DK (Dev Kit) is a $129 board from Nordic Semiconductor with:
- **The same nRF9160 chip we'll use in production** (so the firmware you flash today runs on the production device tomorrow)
- **Built-in cellular modem + antenna + SIM slot** — no soldering RF parts
- **USB-C power and serial debug** — plug into your laptop, see logs in a terminal
- **40+ GPIO header pins** — read sensors with jumper wires
- **A few onboard sensors** for free (temperature, accelerometer, magnetometer) — useful for first telemetry tests
- **Buttons + LEDs** for diagnostics

It's the same board the firmware skeleton at `wburns02/mac-septic-iot-firmware` already targets. **The skeleton compiles for this exact hardware.**

---

## Shopping list (~$425)

**Order all of these in one Digi-Key cart for best shipping.** Everything is in stock as of 2026-04-27. Lead time: 2–3 days.

### The brain ($179.80)

| Part | Digi-Key # | Why | Notes |
|---|---|---|---|
| Nordic nRF9160-DK | NRF9160-DK-ND | The dev kit | Comes with iBasis SIM card pre-installed (test data — works in US for limited time). We'll use 1NCE for the longer-term test. **USB micro-B port** (not USB-C — Nordic ships a cable in the box, but you'll likely need a second one). |

### Cellular SIM ($10)

| Part | Source | Why |
|---|---|---|
| 1NCE Lifetime IoT SIM | 1nce.com | $10 buys 10 years of data. Multi-carrier roaming. The DK has a nano-SIM slot (be careful of size — the SIM ships in a 3-in-1 frame; punch out the smallest size). |

### Power ($25)

| Part | Digi-Key # | Why |
|---|---|---|
| 12V 1A wall-wart with 2.1mm barrel | T996-P5P-ND | The DK accepts USB power, but for a "real install" feel, use a 12V supply through a step-down. |
| 12V→5V DC-DC step-down (USB output) | DROK-buck-USB | Adafruit #1385 or similar. Plugs into 12V barrel, outputs USB-A 5V. **Optional** — you can power the DK directly from your laptop USB for v1. |

**For your first build, skip the 12V supply entirely. Power the DK from your laptop's USB-C port. Saves $20 and a step.**

### Sensors ($135 for the beginner-friendly set)

These are dramatically cheaper than the production sensor list because we're using Adafruit/SparkFun-style breakout boards with header pins instead of industrial-grade probes. Accuracy is "good enough for development."

| Part | Digi-Key # | Why | Hookup |
|---|---|---|---|
| YHDC SCT-013-030 CT clamp + 3.5mm jack adapter | 1597-1389-ND + Adafruit #2169 | "Pump current" simulation. Clip around any extension cord powering an appliance. | 3.5mm jack to 2-pin screw terminal. Plug CT into jack. Wire the two screw terminals to two DK header pins (analog input + GND). |
| Capacitive soil moisture sensor (3-pin breakout) | DFRobot SEN0193 | "Drain field saturation" simulation. Stick in a glass of water, then a glass of dry sand. | 3 jumper wires: VCC→DK 3.3V, GND→DK GND, AOUT→any DK analog pin. |
| HC-SR04 ultrasonic distance sensor (4-pin) | SparkFun SEN-15569 | "Tank level" simulation. Point at a wall, move it back and forth. | 4 jumper wires: VCC→5V, GND, TRIG→GPIO, ECHO→GPIO. The 5V output → 3.3V input on ECHO needs a voltage divider (two cheap resistors), or you can ignore for first test (DK input pins tolerate 5V briefly). |
| 4-pin push button (alarm-tap simulator) | SparkFun COM-09190 | Press the button to "fire" an alarm. | 2 jumper wires + 2 header pins on the DK's GPIO. Internal pull-up enabled in firmware. |
| 1× LED + 1× 220Ω resistor (status LED) | already on DK | The DK has 4 onboard LEDs — use those instead of an external one. | None — built in. |

### Wiring + tools ($45)

| Part | Source | Why |
|---|---|---|
| Half-size breadboard + 65 jumper wires | SparkFun KIT-12002 | Your build surface. No solder needed. | $20 |
| 2.1mm DC barrel-jack-to-terminal-block adapter | Adafruit #368 | Lets you plug the wall-wart in and grab 12V from screw terminals. | $3 |
| 3.5mm-jack-to-screw-terminal breakout | Adafruit #2169 | Mates the CT clamp's 3.5mm jack to header pins. | $3 |
| **Wire nuts (3M / Wago Lever-Nut 221-415)** | Lowes / Amazon | If you ever splice into a real OEM alarm circuit, use these instead of soldering. **Way more reliable than amateur solder joints.** | $10 |
| **Solderless butt-splice connectors (16-22 AWG)** | Amazon / hardware store | For the optional alarm-tap splice. Squeeze with pliers. | $5 |
| Multimeter (if you don't have one) | Klein MM400 or similar | $30–50, you'll use this every time you build something. | optional but recommended |

### Total: ~$475 (without optional 12V supply or multimeter)

> Exact, link-checked totals are in `iot-parts-list-with-links.md` (PDF #08). That doc is the ordering source of truth — prices and stock are verified there.

---

## Skill check

Before you start, here's what each step expects of you:

| Skill | Required? | Why |
|---|---|---|
| Plugging USB cables | yes | Power + flash the DK |
| Running shell commands (terminal/bash) | yes | Install toolchain, build firmware, run flash |
| Reading a wiring diagram (like a Pi GPIO chart) | yes | Match jumper wires to header pins |
| Pressing breadboard wires into holes | yes | Sensors connect via breadboard |
| **Soldering** | **no** | We avoid it entirely with screw terminals + jumpers + wire nuts |
| Using a multimeter (continuity, voltage check) | nice-to-have | Helps debug "why isn't this working" — borrow one if you don't have one |

---

## Stage 1 — Order parts, install toolchain (Day 1, ~30 min hands-on, then wait)

### 1.1 Place the order
Throw everything from the shopping list into a Digi-Key cart, plus separate orders for:
- Adafruit (DC jack adapter, 3.5mm breakout)
- SparkFun (breadboard kit, ultrasonic, button)
- 1NCE (SIM)

Most arrives in 2–3 days. 1NCE SIM ships from Germany, ~7–10 days.

### 1.2 While you wait — install nRF Connect for Desktop
- Go to https://www.nordicsemi.com/Products/Development-tools/nrf-connect-for-desktop
- Download for your OS (Windows / macOS / Linux)
- Install, launch, sign in with a free Nordic Developer account
- Inside, install the **Toolchain Manager** app
- Inside Toolchain Manager, install **nRF Connect SDK v2.6.0** (this downloads ~5GB — leave it running while you do other things)
- Once installed, click "Open VS Code" — this launches VS Code with the nRF Connect extension preconfigured

### 1.3 Clone the firmware repo
In a terminal:
```bash
mkdir -p ~/iot
cd ~/iot
git clone https://github.com/wburns02/mac-septic-iot-firmware.git watchful
cd watchful
```

### 1.4 Verify your build environment
In VS Code with nRF Connect extension:
- Click **"Add an existing application"** → select `~/iot/watchful`
- Click **"Build configuration"** → select board `nrf9160dk_nrf9160_ns`
- Click **"Build"** (hammer icon)
- Wait 3–5 minutes for first build
- Should end with: **"BUILD SUCCESSFUL"** in green

If the build fails, copy the error and ask Claude — most first-time errors are missing SDK pieces or wrong board target.

---

## Stage 2 — Flash the DK + cellular bring-up (Day ~3, ~30 min)

When the DK arrives:

### 2.1 Insert SIM
- Open the small flap on the DK labeled "SIM"
- The 1NCE SIM ships in a 3-in-1 holder. Punch out the **nano** size (smallest)
- Insert nano-SIM into DK, gold contacts down, notched corner matching the slot
- Close flap

### 2.2 Plug it in
- USB **micro-B** cable from your laptop into the **port labeled "nRF USB"** on the DK (NOT the J-Link port — both look similar, the right one is on the long edge of the board). The DK is older hardware and uses micro-B, not USB-C — Nordic includes a cable in the box, but having a second one nearby helps.
- Two LEDs should light up: power (red) and status (green blinking)

### 2.3 Open serial console (in a second terminal window)
On Linux/macOS:
```bash
ls /dev/tty* | grep -i acm  # find the right device, usually /dev/ttyACM0
screen /dev/ttyACM1 115200   # the SECOND ttyACM — first is JLink, second is the app's UART
```
On Windows, use PuTTY → COM port → 115200 baud.

### 2.4 Flash the firmware
Back in VS Code:
- Click the **"Flash"** button (downward arrow icon next to Build)
- Watch the serial console — should see boot messages like:
  ```
  *** Booting Zephyr OS ***
  [00:00:00.123,000] <inf> watchful: Booting...
  [00:00:00.234,000] <inf> watchful: Sensors init OK (stubs)
  [00:00:00.345,000] <inf> watchful: Connecting to LTE...
  ```
- After ~30–60 seconds:
  ```
  [00:00:45.678,000] <inf> watchful: LTE attached, RSSI: -85 dBm
  [00:00:46.789,000] <inf> watchful: Connecting to MQTT broker...
  ```

If LTE doesn't attach in 90 seconds:
- Check the SIM is fully seated and the right size
- Make sure the antenna labeled "LTE" on the DK is plugged in (small white wire to a U.FL connector — should already be from the factory)
- Walk the DK to a window with cellular signal

### 2.5 Find your device's UUID
The DK generates a UUID on first boot and prints it to the console:
```
[00:00:00.500,000] <inf> watchful: Device UUID: 7c4d2f8a-8b6e-4a1c-a7d2-1e5b3f9c4d8a
```
**Write this down.** You need it for the cloud-side registration.

---

## Stage 3 — Register the device with the CRM (Day 3, ~10 min)

### 3.1 Get a CRM API token
You need a Bearer token to register the device. Two ways:
- Easiest: log in to the CRM web UI, open browser dev tools → Network tab → click any API call → copy the `Authorization: Bearer ...` header value
- Or: ask Claude / your team for a long-lived token via the auth API

### 3.2 Run the registration command
In a terminal on your laptop:
```bash
cd ~/iot
git clone https://github.com/wburns02/mac-septic-iot-tools.git
cd mac-septic-iot-tools
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Use the provisioning script
python provisioning.py \
  --serial WATCHFUL-001 \
  --uuid 7c4d2f8a-8b6e-4a1c-a7d2-1e5b3f9c4d8a \
  --crm-url https://react-crm-api-production.up.railway.app \
  --crm-token YOUR_BEARER_TOKEN \
  --commit
```
(Substitute your UUID from Stage 2.5.)

### 3.3 Verify in the CRM
- Open https://react.ecbtx.com/iot
- You should see one device in the list:
  - Serial: WATCHFUL-001
  - Status: offline (last_seen_at not set yet — will update on first telemetry)

If the dashboard shows "offline" for now, that's expected. Step 4 fixes that.

---

## Stage 4 — Wire up the sensors (Day 3, ~45 min)

This is the breadboard part. **No soldering.**

### 4.1 Prepare the breadboard
- Place the breadboard next to the DK
- Power: jumper from DK's `VCC_3V3` pin (top-right header) to the breadboard's `+` rail
- Ground: jumper from any DK `GND` to the breadboard's `−` rail

### 4.2 Hook up the soil moisture sensor (capacitive, "drain field" simulator)
The DFRobot SEN0193 has 3 pins: VCC, GND, AOUT.
- VCC → breadboard `+` rail
- GND → breadboard `−` rail
- AOUT → DK pin `P0.13` (analog input AIN0)

Stick the probe in a glass of water for "saturated" readings. Move it to dry air for "dry" readings.

### 4.3 Hook up the ultrasonic ("tank level" simulator)
HC-SR04 has 4 pins: VCC, TRIG, ECHO, GND.
- VCC → breadboard `+` rail (the DK 3.3V is enough — don't use 5V here, the DK's input pins don't like 5V)
- GND → `−` rail
- TRIG → DK pin `P0.04`
- ECHO → DK pin `P0.05`

Point it at a wall to read distance. Move closer/farther to simulate tank level changing.

### 4.4 Hook up the CT clamp ("pump current" simulator)
- Clip the CT clamp around **one wire** of an extension cord (NOT both wires — only one. The white wire works fine. **Don't strip the cord — clip around it intact.**)
- Plug the CT clamp's 3.5mm jack into the Adafruit 3.5mm-to-screw-terminal breakout
- The breakout has 3 screw terminals (tip, ring, sleeve). For a YHDC SCT-013-030, only tip and sleeve carry signal.
- Tip terminal → DK pin `P0.14` (analog AIN1)
- Sleeve terminal → DK GND
- Plug an appliance into the extension cord (lamp, coffee maker — anything 1A+). The CT outputs ~0.3V AC when current flows. Firmware reads peak-to-peak via ADC.

### 4.5 Hook up the alarm button
The pushbutton has 4 pins (two pairs that close when pressed).
- One pin → DK pin `P0.06` (digital input)
- Diagonally opposite pin → breadboard GND
- Internal pull-up handles the rest (firmware sets `GPIO_PULL_UP`)

When you press the button, P0.06 goes from HIGH to LOW. That's our "OEM alarm fired" event. Firmware will fire the immediate-publish path within a couple seconds.

### 4.6 Sanity check before powering up
- Re-trace every wire by eye — particularly check: no DK pin connected directly to 5V, no power-rail-to-ground short
- Use multimeter continuity mode (if you have one) to confirm no `+` ↔ `−` short
- Smoke is bad. If you see any, unplug immediately.

---

## Stage 5 — Watch it work (Day 3, ~15 min)

### 5.1 Power up
- Plug DK USB-C back into laptop
- In VS Code, click "Flash" again to load the latest firmware (or just press the DK reset button)
- Open serial console — should see boot messages, then telemetry every 10 seconds:
  ```
  [00:00:30.000,000] <inf> watchful: Sampling sensors...
  [00:00:30.015,000] <inf> watchful: pump_current: 1.2 A (RMS over 60 samples)
  [00:00:30.020,000] <inf> watchful: tank_level: 45.3 cm (HC-SR04)
  [00:00:30.025,000] <inf> watchful: soil_moisture: 32.1 % (capacitive)
  [00:00:30.030,000] <inf> watchful: Publishing to devices/<uuid>/telemetry...
  [00:00:30.789,000] <inf> watchful: Published 4 readings (412 bytes)
  ```

### 5.2 See it live in the CRM
- Open https://react.ecbtx.com/iot in a browser
- Click on your device (WATCHFUL-001)
- The DeviceDetail page should show:
  - "Last seen" updated to within the last minute
  - Telemetry chart with three lines (pump_current, soil_moisture, tank_level) updating live
  - Online status indicator green

### 5.3 Fire the alarm
- Press the breadboard button
- Within 5 seconds, the dashboard should show a red alert: "OEM alarm panel is firing on WATCHFUL-001. Tech roll required."
- Your phone should buzz with an SMS (assuming you've added yourself as a technician with your number in the CRM)

### 5.4 Trigger a soil saturation alert
- Move the moisture probe from dry air into a glass of water
- Wait one telemetry cycle (~10 sec)
- Dashboard should show a high-severity alert: "Drain field saturation at <value>% on WATCHFUL-001"

---

## Stage 6 — Stretch goals (optional, after the above works)

### 6.1 Read the dashboard on your phone
- Open the CRM URL on your phone, log in
- Check that the IoT dashboard renders mobile-responsively
- Acknowledge an alert from your phone

### 6.2 Reduce the cadence to production-realistic
- Edit `src/app_config.h` in the firmware repo
- Change `BASELINE_CADENCE_SEC` from 10 to 43200 (12 hours)
- Re-flash
- The DK now sleeps deep most of the day, wakes 2× to publish. Battery life — well, the DK runs from USB so this is more about realistic behavior than power.

### 6.3 Substitute one real sensor
- If a friend or service customer has a working OEM septic alarm panel, ask if you can tap the alarm circuit (low-voltage 24VAC or 12VDC alarm signal) to drive the breadboard button input via a relay
- This is the **only** step in this guide where soldering or wire-nut splicing into mains-adjacent equipment is involved
- Cut power at the breaker first
- Use a relay (Songle SRD-05VDC-SL-C or similar) wired such that the OEM alarm circuit's hot wire goes through the relay coil; the relay's NO contact closes our DK button input
- Or simpler: many OEM panels have a low-voltage alarm OUTPUT screw terminal (24VAC or dry contact). Wire that directly to a 24VAC-tolerant opto-isolator → DK input

### 6.4 Replace the DK with the production module
This is where soldering would matter. Skip until comfortable. Production module options when ready:
- Actinius Icarus SoM ($49) — same nRF9160 on a 25mm module with castellated edges. Reflow-friendly but still requires SMT.
- Custom PCB with raw nRF9160 SiP — proper EE work, ~6-8 weeks lead, see `iot-bom-and-build-guide.md`.

---

## Troubleshooting

### "Build failed" in VS Code
- Make sure Toolchain Manager finished its 5GB download
- Make sure `west update` was run inside `~/iot/watchful` (the nRF Connect extension does this automatically the first time, but sometimes hiccups)
- Re-target the build for `nrf9160dk_nrf9160_ns` exactly (not `_nrf9160` without the `_ns`)

### "LTE attach failed" in serial log
- Check SIM is the right size (nano), inserted gold-down, notched corner matching slot
- Check antenna cable from DK to U.FL connector marked LTE (factory-default, but may have come unplugged)
- Walk to a window — basement / metal cabinets block LTE
- 1NCE SIMs need 5–10 minutes to register on first activation. Be patient.

### "MQTT connect failed"
- The broker is at `mqtt-broker-production-a88e.up.railway.app:1883` (TCP only for now). The DK firmware will use this hostname automatically.
- If the bridge isn't seeing your messages, check Railway logs on the `react-crm-api` service — search for "iot bridge connected" and "iot bridge error".
- Public TCP from cellular to Railway can sometimes be flaky on cheap MVNOs. 1NCE has been reliable in testing.

### "I see no telemetry on the dashboard"
- Open browser dev tools → Network → check that `/api/v2/iot/devices` is returning your device with a recent `last_seen_at`
- If `last_seen_at` is null but serial log shows publishes, the bridge is failing to subscribe. Check Railway logs.
- If the dashboard is showing the device but no chart data, the Zod schema may be rejecting the payload. Check browser console for "API Schema Violation" warnings.

### "I'm getting ESD shocks from the breadboard"
- Touch a grounded metal surface before handling the DK
- Don't work in carpeted rooms with rubber-soled shoes if you can help it
- The DK's ESD protection is good but not infinite

---

## What you've proved

By the time you finish this guide, you've validated the entire IoT stack end-to-end:
- Cellular connectivity ✅
- MQTT publish + bridge subscribe ✅
- Telemetry persistence to Postgres ✅
- Rule engine evaluation ✅
- Alert dispatch to Twilio SMS ✅
- WebSocket broadcast to live dashboard ✅
- Device pairing flow ✅

This is the same firmware, the same cloud, the same dashboard that production will use. The only thing different is the chassis: a DK on a breadboard vs. a custom PCB in an IP66 enclosure.

**Once you have one device working, the rest of the build is repetition + ruggedization, not new technology.**

---

## What's next, after one device works

1. **Build the same thing again — that's device 2.** Validates that the build is repeatable.
2. **Take device 1 to a customer site** (one with a working OEM panel and your service contract). Wire it parallel to the alarm circuit. Leave it for 30 days. See what the real environment does to it (moisture? methane? signal?).
3. **Substitute one cheap sensor with one production sensor** (e.g., MaxBotix ultrasonic instead of HC-SR04). Compare accuracy.
4. **Engage an EE for the v1 PCB** — see `iot-bom-and-build-guide.md`. While that's in flight, keep iterating on the DK in your lab.
5. **Manufacturing-line test fixture, cert testing, pilot SOP** — those come after the PCB is in hand.

For now: just get one device blinking. Everything else follows.

---

*Questions, getting stuck, or want to pair on a step? Ask Claude — share the serial console log + what you see on the dashboard, and the answer is usually 30 seconds away.*
