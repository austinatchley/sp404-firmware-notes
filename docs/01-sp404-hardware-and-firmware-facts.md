# 01 — SP-404MK2 hardware and firmware facts

Everything below is labeled **[FACT]** (verified, cited), **[PRACTICE]** (common
in comparable gear), or **[GUESS]** (inference). **The headline is that almost
nothing about the SoC is publicly confirmed** — the most specific claims come from
community reverse-engineering and are unverified.

## Model confirmation

This project targets the **SP-404MK2** (Roland, released Oct 2021), current
official firmware **5.52**. It is the only SP-404 that DOOM OS supports and the
only one whose firmware is `SP404MKII_APP1.bin`.

## Officially documented facts **[FACT]**

- **Storage:** 16 GB internal storage (incl. preload), 2,560 samples
  (16 pads × 10 banks × 16 projects), 2,560 patterns, 32-voice polyphony,
  16-bit linear 48 kHz, up to ~16-minute samples.
  https://www.roland.com/global/products/sp-404mk2/specifications/
- **I/O:** SD/SDHC/SDXC card slot, USB-C (audio + MIDI + exposes the SD card as a
  drive), 6×AA or USB bus power or AC adapter.
  https://www.roland.com/global/products/sp-404mk2/specifications/
- **Update mechanism:** firmware ships as a zip containing two files,
  `SP404MKII_APP0.bin` and `SP404MKII_APP1.bin`. The user copies both to the root
  of an SD card (formatted on the SP), powers on while holding **SHIFT** to enter
  UPDATER mode, presses **ENTER**, and the unit reports
  "APP0 UPDATER OK" / "APP1 UPDATER OK".
  https://support.roland.com/hc/en-us/articles/4409641783579-SP-404MK2-System-Program-Version-Update
- **Firmware 5.52 is the current release** and the one DOOM OS targets.
  https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/
  (direct: `.../updates_drivers/174cc2fc-ddb2-4128-87a0-848b882cdcea/`)
- The exact stock file DOOM OS patches: `SP404MKII_APP1.bin`, 5.52, SHA-256
  `4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80`; patched output
  2,803,536 bytes, SHA-256
  `79525d514784bbdcc70cb9c05b5fb987500e99ddf02aa4ceeb875bf9070fa26d`.
  https://github.com/klangfeld-labs/doom-os/blob/main/checksums.txt

## SoC / CPU — NOT publicly confirmed

- Roland publishes **no chip information** for the MK2 **[FACT]**.
- **Leading community claim (unverified):** the r/sp404mk2 research project says,
  from analysis of the 5.52 firmware, that the platform is an **NXP i.MX RT1060/62
  (Arm Cortex-M7)**, that APP1 is a "scatter-loaded image", and that the OS is
  **µT-Kernel**. https://www.reddit.com/r/sp404mk2/  — **[GUESS from community, unverified]**
- **Older community theory (unverified):** Roland's marketing "BMC (Behavior
  Modeling Core)" (also used in the GT-1000) is the main processor; some forum
  speculation describes custom ARM multi-core chips.
  https://www.reddit.com/r/SP404/comments/1eryyga/decompilation_modding_efforts_for_the_404/
  — **[GUESS from community, unverified]**
- **Teardown video exists but no chip markings are published in text:** "Taking
  Apart The Roland SP-404 MKII" (Feb 2022) shows the mainboard on camera.
  https://www.youtube.com/watch?v=wTqpxwjcDRg — **[FACT] that video exists; chip ID from it not confirmed**
- **No public service manual for the MK2** (only SP-404 / SP-404SX-era notes).
  https://www.manualslib.com/guide/3619857/roland-sp-404mkii-sp-404mk2-manual.html

For context, an i.MX RT1060/62 (if that's what it is): 600 MHz single-core
Cortex-M7, **1 MB on-chip SRAM (512 KB SRAM + 512 KB TCM)**, **no internal flash**,
executes XIP from external QSPI flash (the RT1064 variant has 4 MB on-chip flash).
https://www.nxp.com/products/i.MX-RT1060 — **[FACT] about the chip family, not about the SP**

### Evidence that supports (but doesn't prove) an RTOS, not Linux

- The APP1 image is only ~2.8 MB **[FACT]** — too small for a general-purpose OS
  with a GUI; typical of a bare-metal/RTOS firmware.
- Two independent community analyses (2022 on 2.0.1, 2026 on 5.52) both identify
  **µT-Kernel** (TRON family RTOS). https://www.reddit.com/r/SP404/comments/x2gigu/interesting_things_in_the_mkii_201_update/
  and https://www.reddit.com/r/sp404mk2/ — **[GUESS from community, two independent sources]**
- The DOOM OS patcher treats the image as little-endian and edits it at
  byte offsets with Thumb-style instruction sequences (see `03-…`) **[FACT]** —
  consistent with ARM little-endian.

## Firmware image facts and layout (as revealed by the DOOM OS patcher)

Decoded this session from the shipped `doomos-patcher.js` (see `00-…` for the
container format) **[FACT]**:

- `SP404MKII_APP1.bin` (5.52) is 2,803,536 bytes; the leading **`0x0..0x2F6A6`
  is never modified** by the patcher — presumed header/boot/early-section zone.
- Named tables in the rebuilt tail: `SCRTBL` (screens), `SYSTAB`, `SYSSTR`
  (strings), `CONTBL` (controls), `BOOTANI` (boot animation).
- An end-of-image block `SPUA` with entries `STARTUP`, `STARTUP1..5`, `ROLAND`,
  `PRODUCT`, `SBMP` plus bitmap data — a boot/branding block that must be kept
  format-consistent.
- The image appears to be composed of **multiple load segments** (edits cluster
  around offsets `0x5Cxxx`, `0x91xxx`, `0xDCxxx`, `0xE…`, `0xF…`, `0x15Fxxx`,
  `0x191xxx`, `0x1D0xxx`, `0x1F8Bxx`, `0x22Bxxx`, `0x23E8xx`, `0x24xxx`, tail).
- **[GUESS]** The stock image contains per-voice/per-pad tables: the patcher makes
  regular edits at strides `0x188` / `0xC8` / `0x190` around `0x23E8C0..0x24E000`,
  which is exactly the shape of an array of fixed-size per-pad/per-track entries.
- **[GUESS]** "APP0" is a separate stage (bootloader/initial-loader half) that the
  patcher deliberately leaves alone; only "APP1" is the main application image.
  "APP1 scatter-loaded image" per the r/sp404mk2 project **[GUESS, community]**.

## Debug / recovery interfaces

- **No public documentation** of a service port, debug UART, JTAG, or SWD on the
  MK2. No FCC filing found (the product has no radio, so likely only Part 15
  Class B / CE applies). **[FACT] nothing public found**
- **[PRACTICE]** On Cortex-M parts (if the i.MX RT theory is right) SWD/JTAG pins
  are commonly still bonded out on the PCB even when not documented; reading chip
  markings off the teardown video is the cheapest way to learn more.
- Battery-powered unit: probe any debug lines with the unit on batteries or a
  bench supply, with appropriate care (see `04-…` for risk).

## What is and isn't known to be recoverable

| Scenario | Known? | How you'd recover |
|---|---|---|
| APP1 patched badly (wrong screens, crashes) | **[FACT]** recoverable | Re-flash stock APP1 via the normal updater (SHIFT+power). This is DOOM OS's documented revert path. |
| APP1 missing/corrupt on SD | **[FACT]** recoverable | Same as above. |
| APP0 damaged or wrong | **[GUESS]** unknown | Not documented publicly; the updater itself programs APP0, but there is no public description of an APP0-level recovery (e.g. a bootloader fallback). **Never touch APP0.** |
| Boot block (`SPUA/STARTUP`) corrupted | **[GUESS]** unknown | The updater path may still rewrite it during a full update, but nobody has documented a recovery for a bricked boot block. Keep it intact. |
| Hardware damage from probing | **[GUESS]** unknown | Depends on what you probe. See `04-…`. |

**Rule of thumb:** modify only APP1, keep APP0 and the header/boot block
untouched, always keep a stock APP1 on a spare SD card, and expect to lose any
projects you didn't back up.

## Predecessors (for comparison)

The SP-404SX and SP-404 have service notes and community teardowns, e.g.
https://www.reddit.com/r/SP404/comments/1gz1hmx/bricked_sp404sx_teardown/ — useful
for understanding Roland's general board layout habits, **not** for MK2 specifics.