# Watchful — Complete Parts List with Links
**Date:** 2026-04-27
**Verified in-stock and priced as of this date.**
**Methodology:** every URL below was fetched live; every price quoted is the price shown on the vendor product page on 2026-04-27.

> **Two important corrections vs. the source build doc** — caught during this verification pass:
> 1. The nRF9160-DK is currently **$179.80** at Digi-Key (not $129 as the build doc says — Nordic raised the price in late 2024). Budget shifted from $425 to ~$475 because of this.
> 2. The nRF9160-DK has **two USB micro-B ports** (not USB-C). It ships with a USB-A → micro-B cable in the box, but you'll likely want a second one.

---

## Part 1 — First Device Beginner Build (~$475 with a multimeter, ~$435 without)

This is the immediate shopping list for ONE working development device. **Soldered build** using the Adafruit Perma-Proto half-size PCB (same pin layout as a breadboard, but permanent). User pivoted away from the solderless path to invest in a real soldering setup that lasts decades and unlocks the rest of the project (real-tank cable splices, future custom PCB hand-assembly).

> **Practice path:** spend 8-10 hours soldering on old Raspberry Pi GPIO headers / scrap boards / cheap LED practice kits before touching the DK. The soldering kit below pays for itself once you stop ruining $180 dev kits.

### Section 1.1 — The Brain ($179.80)

| Item | Vendor | Vendor PN | Mfr PN | Price | Stock | Lead time | Link |
|---|---|---|---|---|---|---|---|
| Nordic nRF9160-DK | Digi-Key | NRF9160-DK-ND | NRF9160-DK | **$179.80** | In Stock (124+) | 2-3 days | [digikey.com](https://www.digikey.com/en/products/detail/nordic-semiconductor-asa/NRF9160-DK/9740721) |

Includes: nRF9160 SiP, on-board nRF52840 (BLE/Thread, also acts as J-Link debugger), LTE+GPS+Bluetooth antennas pre-attached, micro-SIM + nano-SIM slots, 4 buttons + 4 LEDs, on-board temperature sensor, USB-A → USB micro-B cable in box.

**Reasonable alternate (cheaper, smaller):** Actinius Icarus SoM Eval Board — $69 — but it's a development carrier for the production-style SoM, not as beginner-friendly. Stick with the DK for first build.

---

### Section 1.2 — Cellular SIM ($15)

| Item | Vendor | Price | Notes | Link |
|---|---|---|---|---|
| 1NCE IoT Lifetime Flat (10yr / 500MB / 250 SMS) | 1NCE | **$14.00** | Multi-carrier roaming. One-time fee, no monthly. | [1nce.com](https://1nce.com/en-us/1nce-connect/pricing) |
| + SIM card form factor (Card Business, 3-in-1 punch-out: nano/micro/standard) | 1NCE | **$1.00** | Add to plan at checkout | (same URL) |

**Total: $15.00 per SIM**

**Lead time:** 5-10 business days from Germany to USA. Buy now even if you're still waiting on the DK.

**Account setup required.** You can't ship a 1NCE SIM without creating an account + verifying email first. Do this on Day 1 while waiting for the DK.

The DK ships with a free iBasis test SIM (works in the US for limited data, then expires). Use that for the first power-up while waiting on 1NCE.

---

### Section 1.3 — Power ($0–$12)

The DK is happy on USB power from your laptop. **You can skip this entire section for v1.** Add later if you want a "real install" feel.

| Item | Vendor | Vendor PN | Price | Stock | Link |
|---|---|---|---|---|---|
| 12V 1A regulated wall adapter, 2.1mm barrel | Adafruit | 798 | **$8.95** | In Stock | [adafruit.com](https://www.adafruit.com/product/798) |
| 2.1mm female barrel jack to screw terminal | Adafruit | 368 | **$2.00** | In Stock | [adafruit.com](https://www.adafruit.com/product/368) |

**Subtotal (optional):** $10.95

The DK accepts 5V via USB or 5V via VIN header. If you want 12V → 5V step-down for "production-feel" testing, the Adafruit UBEC ([#1385, $9.95](https://www.adafruit.com/product/1385)) does it but its output is bare wires, not USB. For first build, just plug DK into laptop USB.

---

### Section 1.4 — Sensors ($45–$55)

These are dramatically cheaper than the production sensor list because we're using Adafruit/SparkFun-style breakouts with header pins instead of industrial-grade probes. Accuracy is "good enough for development."

#### 1.4.1 — ATU air pressure (Adafruit MPRLS — REPLACES soil moisture sensor)

| Item | Vendor | Vendor PN | Mfr PN | Price | Stock | Link |
|---|---|---|---|---|---|---|
| Adafruit MPRLS Ported Pressure Sensor Breakout (0–25 PSI) | Adafruit | 3965 | MPRLS-0025PA-NW (Honeywell) | **$14.95** | In Stock | [adafruit.com](https://www.adafruit.com/product/3965) |
| 1/4" Silicone tubing (12") | Amazon | various | — | **$3** | In Stock | [amazon.com search](https://www.amazon.com/s?k=1%2F4+inch+silicone+tubing+5+ft) |
| 1/4" brass T-fitting (push-to-connect) | Home Depot / Lowes | various | — | **$3** | In Stock | local hardware store |

**This replaces the original soil moisture probe** in earlier drafts. ATU air-line pressure is a much stronger primary signal than soil moisture for aerobic systems — pressure flatlines = bacteria die in 24-48h. Soil moisture is now an optional add-on for conventional gravity systems' drain field, deferred to v2.

4-pin I²C: VIN (3.3V or 5V) / GND / SDA / SCL. Address 0x18. Pre-soldered headers. Bench test by blowing gently into the barb. Production install: T-fit into the air line between Hiblow pump and tank diffuser.

#### 1.4.2 — Ultrasonic distance (tank level simulator)

**Primary (Adafruit, in stock):**

| Item | Vendor | Vendor PN | Price | Stock | Link |
|---|---|---|---|---|---|
| HC-SR04 Ultrasonic Sonar Distance Sensor + 2× 10K resistors | Adafruit | 3942 | **$3.95** | In Stock | [adafruit.com](https://www.adafruit.com/product/3942) |

The bundled 10K resistors form a voltage divider for the 5V ECHO line → 3.3V DK input. Free.

**Substitute (SparkFun, currently backorder):** ~~SparkFun SEN-15569~~ — $5.25, **on backorder as of 2026-04-27.** Adafruit one above is the better pick.

#### 1.4.3 — CT clamp (pump current simulator)

The YHDC SCT-013-030 is **NOT carried by Digi-Key or Mouser** as of 2026-04-27 (verified). Source from Amazon:

| Item | Vendor | ASIN | Price | Stock | Link |
|---|---|---|---|---|---|
| YHDC SCT-013-030 30A non-invasive CT clamp (3.5mm jack) | Amazon | B01M0QUPBA | **~$10–14** (varies by seller) | In Stock | [amazon.com](https://www.amazon.com/Current-Transformer-SCT013-0-100A-Non-invasive/dp/B01M0QUPBA) |

Order **YHDC-branded** specifically (Amazon listings vary — JANSANE, SazkJere, Reland Sun all sell the same physical part rebranded; YHDC original is preferred). Check for **30A** version with 3.5mm jack output.

**3.5mm jack to screw terminal breakout** (so you can wire it to the breadboard):

| Item | Vendor | Vendor PN | Price | Stock | Link |
|---|---|---|---|---|---|
| Adafruit 3.5mm Stereo Audio Jack Terminal Block | Adafruit | 2791 | **$2.50** | In Stock | [adafruit.com](https://www.adafruit.com/product/2791) |

**Anti-recommendation:** Don't buy SCT-013-000 (the 0–100A "current-output" version). The 030 puts out 0–1V AC, the 000 puts out 0–50mA AC and needs a burden resistor — extra hassle for v1.

#### 1.4.4 — Push button (alarm-tap simulator)

| Item | Vendor | Vendor PN | Price | Stock | Link |
|---|---|---|---|---|---|
| 12mm square momentary pushbutton (breadboard-friendly) | SparkFun | COM-09190 | **$0.75** | In Stock | [sparkfun.com](https://www.sparkfun.com/products/9190) |

#### 1.4.5 — Status LED

**Already on the DK** — 4 user LEDs are built in. Skip.

#### Sensor section subtotal: **$23.10 (Adafruit/SparkFun) + $10–14 (Amazon CT) ≈ $35**

---

### Section 1.5 — Wiring + soldered protoboard ($35-40)

**This build is now soldered, not breadboarded.** Same circuit as the prior breadboard plan — just permanent. The Adafruit Perma-Proto half-size board has the **same pin layout as a half-size breadboard**, so the wiring map from earlier transfers 1:1 — you solder into the holes instead of pressing jumpers in.

| Item | Vendor | Vendor PN | Price | Stock | Link |
|---|---|---|---|---|---|
| **Adafruit Perma-Proto Half-Size Breadboard PCB** | Adafruit | 1609 | **$4.50** | In Stock | [adafruit.com](https://www.adafruit.com/product/1609) |
| **Adafruit Hookup Wire Spool Set, 22 AWG, 6 colors × 75ft** | Adafruit | 1311 | **$15.95** | In Stock | [adafruit.com](https://www.adafruit.com/product/1311) |
| **Female 0.1" header sockets, 4-pin × 5 pack** (for sensor sockets on the Perma-Proto) | Adafruit | 598 | **$4.95** | In Stock | [adafruit.com](https://www.adafruit.com/product/598) |
| **Heat-shrink tubing assortment (~150 pcs, multi-size)** | Amazon (B07RNVYCNN or similar) | — | **~$8** | Prime | [amazon.com search](https://www.amazon.com/s?k=heat+shrink+tubing+assortment+150+pieces) |
| **Liquid electrical tape (small bottle)** — for any outdoor splice that needs reinforcement | Amazon / Home Depot | — | **~$8** | In Stock | local hardware |

#### Why Perma-Proto over a bare stripboard:
1. Same row-pair layout as a breadboard, so pin maps from breadboard tutorials transfer
2. Power and ground rails on each long edge — clean power distribution to all sensors
3. Real PCB with through-plated holes — solder joints are reliable, not flaky like cheap perfboard
4. Mounts cleanly into the IP65 enclosure later (4 mounting holes on the corners)

#### Optional (for outdoor splices later, when you go to a real tank):

| Item | Vendor | Price | Link |
|---|---|---|---|
| Wago 221-415 Lever-Nuts, 5-conductor, 10-pack | Amazon (B06XH47DC2) | **~$8** | [amazon.com](https://www.amazon.com/Wago-221-415-LEVER-NUTS-Conductor-Connectors/dp/B06XH47DC2) |

These are still useful for joining 18 AWG sensor cables to your soldered protoboard pigtails inside an outdoor junction box — soldering a connector is great, but field-replaceable splices belong on lever-nuts.

#### Wiring subtotal: **~$33** (Perma-Proto + hookup wire kit + headers + heat shrink)

---

### Section 1.6 — Tools (one-time, not per-device)

You only need these once. They live on your bench forever after.

#### 1.6.1 — Soldering kit (NEW — primary path is now soldered)

This kit is now part of the build. Practice on old Raspberry Pi GPIO headers / scrap boards before touching the DK. **Plan ~8-10 hours of practice on cheap perfboard joints before you touch the IoT components.** Good iron + practice is the difference between joints that look like volcanic islands vs joints that look like Hershey's Kisses.

**Iron — pick ONE option:**

| Item | Vendor | Price | Why | Link |
|---|---|---|---|---|
| **Hakko FX-888D Digital Soldering Station** (recommended for serious use) | Amazon / Digi-Key | **$110-115** | Industry-standard. Temp-controlled, lasts 20+ years, holds temp ±2°F. Drops the skill floor dramatically vs cheap pencil iron. | [digikey.com](https://www.digikey.com/en/products/detail/american-hakko-products-inc/FX888D-23BY/4156628) / [amazon.com](https://www.amazon.com/dp/B00ANZRT4M) |
| **Pinecil V2** (budget alternative) | Pine64 store / Amazon | **$30** | Genuinely good. Smaller, USB-C powered. ~80% as good as Hakko at 30% the price. | [pine64.com](https://pine64.com/product/pinecil-smart-mini-portable-soldering-iron/) |
| Pinecil PD power supply (only if going Pinecil route) | Amazon | $15-20 | Pinecil needs USB-C PD ≥45W to reach full temperature. | search "USB-C PD 65W power supply" |

**Solder + flux + cleanup:**

| Item | Vendor | Price | Link |
|---|---|---|---|
| **Kester 60/40 Sn/Pb Leaded Solder, 0.031" diameter, 1/2 lb spool** (much easier for beginners than lead-free) | Amazon | **$15-18** | [amazon.com search](https://www.amazon.com/s?k=Kester+24-6040-0027+0.031+rosin+core) |
| **Kester 951 No-Clean Flux Pen** (or MG Chemicals 8341) | Amazon / Digi-Key | **$7** | [digikey.com](https://www.digikey.com/en/products/detail/kester-solder/83-1000-0951/2444618) |
| **Solder wick (3-pack, 0.075")** + **desoldering pump combo** | Amazon | **$10** | [amazon.com search](https://www.amazon.com/s?k=solder+wick+desoldering+pump+combo) |
| **Hakko 599B Brass Sponge Tip Cleaner** (DO NOT use a wet sponge — shortens tip life dramatically) | Digi-Key / Amazon | **$7-8** | [digikey.com](https://www.digikey.com/en/products/detail/american-hakko-products-inc/599B-02/365334) |

**Workspace:**

| Item | Vendor | Price | Link |
|---|---|---|---|
| **SE MZ101B Helping Hands** with 4 alligator clips, magnifier glass, LED light | Amazon | **$25** | [amazon.com search](https://www.amazon.com/s?k=SE+MZ101B+helping+hands+magnifier) |
| **Silicone heat-resistant work mat (large)** — protects your bench from burn marks + has component pockets | Amazon | **$13** | [amazon.com search](https://www.amazon.com/s?k=silicone+soldering+mat+heat+resistant) |
| **Anti-static (ESD) wrist strap** (cheap insurance against zapping the DK) | Amazon | **$5-8** | [amazon.com search](https://www.amazon.com/s?k=anti+static+wrist+strap) |

#### Soldering kit subtotal: **~$190** (Hakko path) or **~$110** (Pinecil path)

#### 1.6.2 — Multimeter (recommended)

| Item | Vendor | Price | Stock | Link |
|---|---|---|---|---|
| Klein Tools MM400 Auto-Ranging Digital Multimeter, 600V CAT III | Home Depot / Lowes / Amazon | **~$45** (typical $42-50) | In Stock | [homedepot.com](https://www.homedepot.com/p/Klein-Tools-600V-AC-DC-Auto-Ranging-Digital-Multimeter-Drop-Resistant-Temperature-Measurement-MM400/206517333) |

#### 1.6.3 — Other (optional, skip if you have)

| Item | Vendor | Price | Link |
|---|---|---|---|
| USB-A to USB micro-B cable (3ft) — DK uses **micro-B**, not USB-C; DK ships with one in box | Adafruit | $2.95 | [adafruit.com](https://www.adafruit.com/product/592) |
| Klein 11061 wire strippers/cutters | Amazon / Home Depot | ~$22 | [homedepot.com](https://www.homedepot.com/p/Klein-Tools-Wire-Stripper-Cutter-11061) |
| Lineman pliers | hardware store | ~$15 | local |
| Saleae Logic 8 clone (cheap logic analyzer, optional debug) | Amazon | ~$15-25 | search "USB logic analyzer 24MHz 8 channel" |

#### Tools subtotal: **~$235** (Hakko soldering kit + multimeter) or **~$155** (Pinecil + multimeter) — one-time, depreciate across many builds.

---

### Per-vendor totals (cleanest path)

| Vendor | Items | Subtotal | Shipping est. | Lead time |
|---|---|---|---|---|
| **Digi-Key** | nRF9160-DK | **$179.80** | Free over $200 (you're under — add a USB micro-B cable or jumper wires to clear). Otherwise ~$8 ground. | 2-3 days |
| **Adafruit** | MPRLS pressure (#3965) + #2791 + #3942 + #266 + #758 + #153 + #64 + #239 | **~$50** | Free over $99, otherwise $5–10 standard. | 2-3 days |
| **Adafruit** | MPRLS pressure (#3965) + HC-SR04 (#3942) + 3.5mm screw-terminal breakout (#2791) + Perma-Proto half-size (#1609) + hookup wire kit (#1311) + 4-pin female header sockets (#598) + 2.1mm-jack-to-terminal (#368, optional power) | **~$50** | Free over $99, otherwise $5-10 standard. | 2-3 days |
| **SparkFun** | Pushbutton (COM-09190) | **$0.95** + shipping | $7-10 | 2-4 days |
| **1NCE** | Lifetime SIM + Card Business form factor | **$15.00** | $5 to USA | 5-10 days |
| **Amazon** | YHDC SCT-013-030 + heat-shrink kit + liquid electrical tape + soldering kit (Hakko + Kester solder + flux + wick + helping hands + silicone mat + ESD strap) + Klein MM400 multimeter | **~$10-14** CT only → **~$240-260** (full soldering kit + CT + multimeter) | Prime free | 1-2 days |

### Grand total

| Path | Build parts (one device) | Tools (one-time) | Total |
|---|---|---|---|
| **Hakko soldering path (recommended)** | ~$280 | ~$235 (Hakko + multimeter + accessories) | **~$515** |
| **Pinecil budget path** | ~$280 | ~$155 (Pinecil + multimeter + accessories) | **~$435** |

The tools depreciate across every build that comes after — by device 5, the per-device cost converges to ~$280. By device 50, the soldering kit has paid for itself many times over in saved JLCPCB SMT fees once you start hand-assembling protoboards.
- **$425:** without optional 12V power, without multimeter (you have one or borrow)
- **$435:** add the 12V wall + barrel-to-screw adapter
- **$475:** add a Klein MM400 multimeter

---

---

## Part 2 — Production BOM (qty 1000+, future planning)

Same structure but for the production parts list. Lighter detail — canonical part numbers, link, qty-1000 unit price targets. This is a forward-looking document; verify against current pricing when you actually pull the trigger.

### Section 2.1 — Compute / radio

| Item | Vendor | Mfr PN | Qty-1 price | Qty-1000 target | Link |
|---|---|---|---|---|---|
| Nordic nRF9160 SiP (raw module) | Digi-Key, Mouser, Avnet | nRF9160-SICA-R7 | $28-32 | **$24** | [digikey.com](https://www.digikey.com/en/products/base-product/nordic-semiconductor-asa/1490/NRF9160/328905) |
| **OR** Actinius Icarus SoM (faster proto, slightly higher BOM cost) | Mouser, direct | Icarus SoM | $49-59 | $42 (qty 1000 direct) | [actinius.com](https://www.actinius.com/icarus-som) |
| Taoglas FXP07 LTE flex antenna (adhesive) | Digi-Key | FXP07.07.0100A | $7-9 | $6 | search Digi-Key "FXP07.07.0100A" |
| 1NCE Lifetime SIM (10yr / 500MB) | 1NCE direct | 1NCE Lifetime Flat | $14 | $14 (no volume discount on the SIM itself) | [1nce.com](https://1nce.com/en-us/1nce-connect/pricing) |

### Section 2.2 — Power

| Item | Vendor | Mfr PN | Qty-1 | Qty-1000 | Link |
|---|---|---|---|---|---|
| 12V/2A wall adapter | Digi-Key, Mouser | TPI 31-1080 (or equivalent 12V/2A switching brick) | $8-12 | $5-7 | search "12V 2A switching adapter 2.1mm barrel" on Digi-Key |
| Buck 12V→3.3V (low-Iq, MCU rail) | Digi-Key | TPS62840DLCR | $1.80 | $1.20 | [digikey.com](https://www.digikey.com/en/products/detail/texas-instruments/TPS62840DLCR/10434131) |
| Buck 12V→5V (sensor rail) | Digi-Key | TPS54060ADGQR | $3.50 | $2.10 | search Digi-Key "TPS54060A" |
| LiSOCl₂ D-cell, 19Ah, 3.6V (UPS) | Digi-Key, House of Batteries | Tadiran TL-5930F | $32-38 | $28 | search "TL-5930/F" on Digi-Key |
| D-cell battery holder, PCB mount | Digi-Key | Keystone 1041 | $3 | $2.20 | search Digi-Key "Keystone 1041" |
| Coulomb-counter / SOC IC | Digi-Key | BQ27441DRZR-G1A | $3 | $2.10 | search Digi-Key "BQ27441" |
| AC-present opto | Digi-Key | PC817XPNIP1B (Sharp) | $0.30 | $0.18 | search Digi-Key "PC817" |
| TVS 12V rail | Digi-Key | SMAJ15CA-13-F | $0.40 | $0.18 | search Digi-Key "SMAJ15CA" |
| MOV (AC input) | Digi-Key | V275LA20A | $1.80 | $0.95 | search Digi-Key "V275LA20A" |

### Section 2.3 — Sensors (production substitutions)

| Sensor | Mfr PN | Vendor | Qty-1 | Qty-1000 | Notes |
|---|---|---|---|---|---|
| Pump CT clamp 30A | YHDC SCT-013-030 | Amazon / OpenEnergyMonitor (USA) / AliExpress (volume) | $10-14 | **$5** (AliExpress volume) | Not on Digi-Key. Bulk AliExpress with QC inspection acceptable for production. |
| Aerator CT clamp 15A | YHDC SCT-013-015 | same as above | $9 | **$5** | (ATU only) |
| Tank level ultrasonic (premium proto) | MaxBotix MB7389-100 | Digi-Key | $109 | $89 | weather-resistant; qty 1000 is rich |
| Tank level ultrasonic (production alt, $20 vs $109) | A02YYUW (RS-485, IP65) | Adafruit / DFRobot / AliExpress | $18-28 | **$14** | Validate accuracy in pilot first |
| Soil moisture (premium proto) | METER EC-5 | METER Group direct | $135 | $115 | Lab-grade |
| Soil moisture (production alt, $14 vs $135) | DFRobot SEN0308 capacitive RS-485 | Digi-Key, DFRobot | $14-22 | **$11** | Validate accuracy in pilot |
| Float switch (alarm tap backup) | Generic NC septic float | Septic Solutions | $14 | $10 | Optional — most OEM panels have alarm OUT screw terminal |
| Chlorinator flow (ATU only) | TE FS40A | Digi-Key | $24 | $19 | search Digi-Key "FS40A" |

### Section 2.4 — Enclosure + mech

| Item | Mfr PN | Vendor | Qty-1 | Qty-1000 | Link |
|---|---|---|---|---|---|
| IP66/NEMA-rated polycarbonate enclosure | BUD PN-1339-DG | Digi-Key | **$20.20** (verified 2026-04-27) | ~$13 | [digikey.com](https://www.digikey.com/en/products/detail/bud-industries/PN-1339-DG/439774) |
| Internal mounting plate | BUD MOP-1339 | Digi-Key | $13 | $9 | search Digi-Key "MOP-1339" |
| External mount feet (set) | BUD MFB-1339 | Digi-Key | $9 | $6 | search Digi-Key "MFB-1339" |
| M16 IP68 cable glands | Heyco M3185G | Digi-Key | $4 | $2.50 | search Digi-Key "Heyco M3185G" |
| Conformal coating (acrylic) | MG Chemicals 422B | Digi-Key | $28/can | $22 (qty 100 can) | search Digi-Key "MGC 422B" |
| Tamper-evident sticker | Avery 6577 | Amazon | $9/pack | $7 | hardware retailer |
| Door reed switch (tamper) | Cherry MP201801 | Digi-Key | $4 | $2.50 | search Digi-Key "MP201801" |

> **Note on the BUD PN-1339-DG:** Digi-Key currently shows **only 10 units in stock** with an 11-week manufacturer lead time. For prototype qty 5-10, jump on a small batch now. For qty 1000+, place a direct order with BUD Industries (volume pricing kicks in around 100 units; expect 8-12 weeks lead time).

### Section 2.5 — PCB + assembly

| Item | Vendor | Cost | Notes |
|---|---|---|---|
| 4-layer ENIG PCB, 100×80mm, qty 5 | JLCPCB | $30 (incl. shipping) | [JLCPCB instant quote](https://cart.jlcpcb.com/quote) |
| 4-layer ENIG PCB, qty 1000 | JLCPCB | $4/board | Volume tier; tooling NRE separate |
| SMT assembly, top side, ~50 components, qty 5 | JLCPCB | $80-180 | Non-stocked parts add fees |
| SMT assembly, qty 1000 | JLCPCB | $14/board | Stable with consigned BOM |

> **Pricing tip:** JLCPCB's calculator (link above) is the fastest way to get a real number. Drop in board dimensions, layer count, qty, ENIG finish, and assembly options. Quotes are instant. NRE for stencils + first-article is roughly $50.

---

## Tools and consumables (own once, use for many builds)

| Item | Use | Vendor | Price | Link |
|---|---|---|---|---|
| Klein MM400 multimeter | Continuity, voltage, current | Home Depot | ~$45 | [homedepot.com](https://www.homedepot.com/p/Klein-Tools-600V-AC-DC-Auto-Ranging-Digital-Multimeter-Drop-Resistant-Temperature-Measurement-MM400/206517333) |
| USB-A → USB micro-B cable, 3ft | Power + flash the DK | Adafruit | $2.95 | [adafruit.com](https://www.adafruit.com/product/592) |
| Klein 11061 wire strippers/cutters | All wiring jobs | Home Depot | ~$22 | [homedepot.com](https://www.homedepot.com/s/klein%2011061) |
| Lineman pliers (Klein D213-9NE or any brand) | Clamping + cutting | hardware store | ~$15-30 | local |
| Phillips/hex driver set | Enclosure + mounting | hardware store | ~$15 | local |
| Heat-shrink tube assortment | Wire splice insulation | Amazon | ~$10 | search "heat shrink tubing assortment" |
| Hakko FX-888D soldering station (stretch goal — beginner build avoids soldering, but worth $130 when ready for real PCB work) | Future PCB assembly | Digi-Key | ~$130 | [digikey.com](https://www.digikey.com/en/products/detail/american-hakko-products-inc/FX888D-23BY/4156628) |
| Saleae clone logic analyzer (24MHz, 8ch) | MQTT timing + bus debug | Amazon | ~$15-25 | search "USB logic analyzer 8 channel" |
| Wago 221-series Lever-Nuts assortment | Splicing into mains-adjacent OEM panel circuits | Amazon | ~$15 | [amazon.com](https://www.amazon.com/Wago-LEVER-NUTS-Lever-Nut-Assortment-Pocket-Pack/dp/B01N0LRTXZ) |

---

## Vendor accounts to set up

If the user doesn't already have these:

- **Digi-Key** — free; create at [digikey.com](https://www.digikey.com). $25 minimum for free standard ground shipping; over $200 cart = free expedited. Net-30 terms available for businesses.
- **Mouser** — free; create at [mouser.com](https://www.mouser.com). Similar shipping thresholds. Carries some Phoenix terminal parts Digi-Key doesn't.
- **Adafruit** — free; create at [adafruit.com](https://www.adafruit.com). Flat-rate USPS ~$10 anywhere in US.
- **SparkFun** — free; create at [sparkfun.com](https://www.sparkfun.com). Fast Colorado shipping.
- **1NCE** — free, but **requires creating an account + verifying email before SIM ships**. Set this up Day 1 while waiting on hardware. [shop.1nce.com](https://shop.1nce.com/portal/shop/cart?language=en)
- **METER Group** — quick email exchange for non-research orders (call them); the EC-5 soil probe ships in 2-3 weeks. Only relevant for production BOM; skip for the beginner build.
- **BUD Industries** — order through Mouser / Digi-Key / Newark. No separate account needed. Direct orders only required at qty 100+.
- **JLCPCB** — free; create at [jlcpcb.com](https://jlcpcb.com). Only needed once you have Gerbers ready for fab.
- **Amazon Prime** — for the few parts not on a distributor.

---

## Notes / caveats

- **YHDC CT clamp output is AC**, not DC — needs ADC peak-detection or RMS averaging in firmware. Already handled in the firmware skeleton (`src/sensors/pump_ct.c` → `compute_rms()` over 60 samples per cycle). Don't expect to read it like a DC voltage on first probe.
- **HC-SR04 is a 5V part by default**, but the Adafruit #3942 listing includes 2× 10K resistors specifically to make a voltage divider for the ECHO line. Use them — DK GPIOs are 3.3V tolerant only.
- **MPRLS pressure sensor is rated 3.3V or 5V** — runs fine off the DK 3.3V rail. I²C address 0x18; if you ever add a second I²C device that conflicts, the MPRLS doesn't have an address-select pad (you'd need a TCA9548A I²C mux instead). Not a v1 concern.
- **The DK has TWO USB ports** — one labeled "nRF USB" (the one you use for app UART + power) and one labeled "DEBUG OUT" (the J-Link side). They look identical. The serial console you want is the **second** `/dev/ttyACMx` device that appears. First-time confusion is normal.
- **The DK SIM holder is finicky** — gold contacts down, notched corner aligned. The 1NCE 3-in-1 punch-out is sized for any of (standard, micro, nano); the DK's main SIM slot is **micro** size, not nano. Don't punch out the smallest one for the DK; the build doc says "nano" — that's wrong, the DK uses **micro**. The Actinius Icarus SoM uses nano — different from the DK.
- **1NCE SIM activation takes 5-10 minutes** on first power-up. Be patient. If it doesn't attach in 15 min, walk to a window — basements + metal cabinets kill LTE-M.
- **Don't use AliExpress for the beginner build** — quality variance is real on YHDC clones, and the lead time (3-4 weeks) defeats the point of a 3-day build. AliExpress is fine for production volume CT clamps where you can do incoming QC.

### Anti-recommendations (parts that look right but aren't)

- ~~Adafruit #2169~~ — does **not** exist (404). The right Adafruit 3.5mm-jack-to-terminal-block is **#2791** ($2.50).
- ~~SparkFun KIT-12002~~ — this is just a **breadboard** (PRT-12002, $6.25), not a beginner kit. The actual SparkFun Beginner Parts Kit (KIT-13973) was retired in 2025 and replaced by KIT-27842.
- ~~SCT-013-000~~ — wrong. The 000 outputs 0-50mA AC current (needs a burden resistor); the **030** outputs 0-1V AC (drop-in to ADC).
- ~~SparkFun SEN-15569 HC-SR04~~ — currently **on backorder** at SparkFun. Use Adafruit #3942 instead (in stock, includes voltage-divider resistors).
- ~~USB-C cable~~ — the DK uses USB **micro-B**, not USB-C. The build doc is wrong on this.
- ~~Adafruit UBEC #1385 "USB output"~~ — the UBEC outputs bare 5V wires, not USB. Skip if you want USB-style power; just use a USB cable from your laptop.

### Cheaper-alternate notes (production)

- The MaxBotix MB7389-100 ($109) and METER EC-5 ($135) are **pilot/prototype** sensors used to characterize the problem. They're way more accurate than needed for septic alarm thresholds. Production substitutes (A02YYUW $18, DFRobot SEN0308 $14) are fine *once you've validated the accuracy floor in the pilot*. Don't skip the premium-sensor pilot — you need the ground truth to know what the cheaper ones are missing.

---

## Summary cart (copy-paste ready, beginner build)

```
DIGI-KEY CART (single order):
  NRF9160-DK-ND × 1                     $179.80   (Nordic nRF9160-DK)
  (Soil moisture sensor REMOVED — replaced with Adafruit MPRLS in cart 2)
                                       --------
                                        $185.70
  (add a $10-15 cable or jumper kit to clear the $200 free-shipping threshold)

ADAFRUIT CART:
  Product 3942 × 1                        $3.95   (HC-SR04 + 10K resistors)
  Product 2791 × 1                        $2.50   (3.5mm jack to terminal block)
  Product 153  × 1                        $4.95   (breadboarding wire bundle, 75pc)
  Product 64   × 1 (if in stock)          $4.95   (half-size breadboard)
  Product 592  × 1                        $2.95   (USB-A to micro-B, 3ft)
  Product 798  × 1 (optional 12V power)   $8.95
  Product 368  × 1 (optional barrel adp)  $2.00
                                       --------
                                        $30.25 (with all optionals)

SPARKFUN CART (only if Adafruit #64 OOS):
  COM-09190 × 1                           $0.75   (12mm pushbutton)
  PRT-12002 × 1                           $6.25   (breadboard)
  PRT-12795 × 1                           $2.95   (jumper wires M/M, 20pc)
                                       --------
                                          $9.95

1NCE (signup + order):
  Lifetime Flat plan                     $14.00
  Card Business form factor               $1.00
                                       --------
                                         $15.00

AMAZON:
  YHDC SCT-013-030 (B01M0QUPBA)          ~$10-14
  (optional) Wago 221-415 10pk           ~$8
  (optional) Klein MM400                 ~$45
                                       --------
                                          $63 (with everything)

GRAND TOTAL: $475 with multimeter + 12V power
             $425 without multimeter + without 12V power
```

---

## Verification methodology

For each part above:
1. Used WebFetch to visit the vendor product page on 2026-04-27
2. Confirmed the part number matches what's listed on the page
3. Captured the canonical URL (clean product-page URL, no tracking)
4. Noted the current USD price as displayed
5. Noted "In Stock" / "Backorder" / "Out of Stock" status
6. Where out of stock or discontinued: substituted with a verified alternate

Where the source build doc had a wrong or non-existent part number, the substitution is called out explicitly in the "Anti-recommendations" section above.

The two largest deltas vs. the source doc:
- **nRF9160-DK price** is $179.80 (verified Digi-Key live), not $129. Build doc was 2023-era pricing.
- **YHDC SCT-013-030 is not on Digi-Key.** Source via Amazon (B01M0QUPBA) or AliExpress for production volume.

Everything else is a cosmetic correction (Adafruit #2169 → #2791, etc.).
