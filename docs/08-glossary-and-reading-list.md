# 08 — Glossary and reading list

## Glossary

- **APP0 / APP1** — the two firmware files Roland ships for the SP-404MK2.
  Presumed loader/updater stage (APP0) and main application image (APP1, the one
  DOOM OS patches). **[GUESS]**
- **UPDATER mode** — the SP's stock boot menu entered by holding SHIFT while
  powering on; it rewrites APP0/APP1 from the SD card and is the recovery path
  for all APP1-level problems.
- **µT-Kernel** — a TRON-family real-time OS (T-Engine Forum); the RTOS the
  community identifies in SP-404MK2 firmware. https://www.tron.org/
- **RTOS** — real-time operating system; scheduler + tasks + IPC for embedded
  targets.
- **ISR** — interrupt service routine; runs with the CPU on an interrupt stack,
  no scheduler. Bad place to block/allocate.
- **Bare metal / XIP** — running directly on the CPU with no OS (bare metal), or
  executing code in place from flash without copying to RAM (XIP).
- **Vector table** — on Cortex-M, the array at the image base: initial SP word,
  then reset/exception handler addresses (bit0 set = Thumb).
- **Scatter loading** — ARM toolchain term for an image composed of multiple
  load regions placed at different addresses by the startup code; the community
  description of APP1.
- **Trampoline / hook** — the small redirect written over a function entry that
  jumps to your payload, plus the payload itself.
- **Code cave** — unused bytes (padding) inside the image you can claim for your
  payload.
- **Displaced instructions** — the original bytes you overwrote with a
  trampoline, replayed inside the cave.
- **Stub** — a named entry point (function address) for a specific
  firmware/build; Magic Lantern's `stubs.S` concept. A "stubs table" = your
  per-version address manifest.
- **IPS / BPS** — patch/delta formats (see `03-…`). IPS is the old simple one;
  BPS is the modern, CRC-verified one.
- **`DOOMPTCH`** — Klangfeld Labs' custom patch container (see `00-…`).
- **Entropy** — a measure of byte randomness; high ≈ code/compressed, low ≈
  padding/zero/ASCII tables. `binwalk -E` plots it per block.
- **XREF / xref** — a reference (usually a code reference) to an address, e.g.
  "this string is referenced by the draw function".
- **Load address / base address** — the virtual address the image (or a region)
  runs at; required to disassemble correctly in Ghidra.
- **Version Tracking / Diaphora / radiff2** — tools that match functions across
  two binaries (stock vs patched) to find what changed and what a patched
  function "used to be".
- **Rel32 / Thumb-2 MOVW/MOVT** — x86 and ARM idioms for building branch targets
  and 32-bit addresses (see `03-…`).
- **Bootflag** — Magic Lantern's in-RAM flag that makes Canon cameras boot code
  from the SD card (a different model from firmware patching, but the same
  "trick the vendor loader" idea).
- **Write-then-rename** — atomic file save: write a temp file, flush, rename over
  the old one; the safe-save pattern DOOM OS adopted.

## Reading list (annotated)

### The project you're imitating
- DOOM OS overview: https://klangfeldlabs.com/doom-os/
- Patcher (in-browser, offline): https://klangfeldlabs.com/doom-os/patcher
- Manual: https://klangfeldlabs.com/doom-os/manual/
- Repo (patcher, checksums, changelog): https://github.com/klangfeld-labs/doom-os
- Launch post: https://klangfeldlabs.com/posts/2026-09-27-doom-os-sp404mk2
- **Read `doomos-patcher.js` end-to-end** — it's the entire public description of
  the technique (digest whitelist, `DOOMPTCH` container, offset records).

### Roland / official
- SP-404MK2 firmware updates: https://www.roland.com/global/support/by_product/sp-404mk2/updates_drivers/
- Official update procedure (SD card, SHIFT+power, APP0/APP1 OK):
  https://support.roland.com/hc/en-us/articles/4409641783579-SP-404MK2-System-Program-Version-Update
- Specs: https://www.roland.com/global/products/sp-404mk2/specifications/

### Community / hardware
- r/SP404 (modding discussions, e.g. decompilation thread):
  https://www.reddit.com/r/SP404/ and
  https://www.reddit.com/r/SP404/comments/1eryyga/decompilation_modding_efforts_for_the_404/
- r/sp404mk2 (active custom-firmware research project — i.MX RT / µT-Kernel /
  scatter-loaded APP1 claims, **unverified**): https://www.reddit.com/r/sp404mk2/
- Teardown video (board photos; no chip ID published): https://www.youtube.com/watch?v=wTqpxwjcDRg
- NXP i.MX RT1060/1064 (what the SP might be — for context):
  https://www.nxp.com/products/i.MX-RT1060
- µT-Kernel (TRON/RTOS): https://www.tron.org/

### Case-study projects
- Magic Lantern wiki (bootflags, autoexec, stubs, building):
  https://magiclantern.fandom.com/wiki/Magic_Lantern_Firmware_Wiki
- ML source layout (per-camera `stubs.S`): https://github.com/reticulatedpines/magiclantern_simplified
- Rockbox manual (three-piece model, updater-patching, uninstall):
  https://github.com/Rockbox/rockbox/blob/master/manual/getting_started/installation.tex
- Atmosphère (fusée, KIP IPS patches): https://github.com/Atmosphere-NX/Atmosphere
- OP-1 repacker (firmware modify/repack, no new features):
  https://github.com/op1hacks/op1repacker
- Volca Bass custom firmware (vendor-updater install, .wav update):
  https://github.com/mpasserini/volca-bass-custom-firmware

### Techniques
- Flips (IPS/BPS implementation): https://github.com/Sir-Walrus/Flips
- BPS spec (public domain): https://raw.githubusercontent.com/Sir-Walrus/Flips/master/bps_spec.md
- bsdiff/bspatch: https://www.daemonology.net/bsdiff/
- ROM hacking overview (patch distribution, ROM expansion):
  https://en.wikipedia.org/wiki/ROM_hacking
- NESdev wiki (hardware/assembly background): https://www.nesdev.org/

### Tooling
- Ghidra (NSA): https://github.com/NationalSecurityAgency/ghidra
- Diaphora (binary diff/function matching): https://github.com/juxingzhen/diaphora
- radare2/rizin: https://github.com/radareorg/radare2
- binwalk (signatures/entropy): https://github.com/ReFirmLabs/binwalk
- Unicorn (CPU emulation for single-function RE):
  https://www.unicorn-engine.org/
- QEMU (system emulation; limited use here): https://www.qemu.org/
- ent (entropy tool): https://www.fourmilab.ch/random/

### General RE learning
- "Reverse Engineering for Beginners" (free PDF, Dennis Yurichev):
  https://beginners.re/
- "Practical Binary Analysis" (Andriesse, No Starch) — binary formats, ELF,
  disassembly, dynamic analysis.
- LiveOverflow (firmware/exploit walkthroughs): https://liveoverflow.com/
- Magic Lantern's porting guide (the template for adding a new device to a
  patching project): https://magiclantern.fandom.com/wiki/PortingML

### Working set for this project
`binwalk`, `ent`, `strings`, `xxd`, `ghidra`, `radare2`, `unicorn`,
`tools/diff_cluster.py`, a cross-assembler (`arm-none-eabi-as`), `sha256sum`,
and this repo's docs `00`–`07` plus `open-questions.md`.