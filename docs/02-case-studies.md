# 02 — Case studies: comparable firmware-extension projects

How other projects patch closed vendor firmware, structure hooks and stubs, keep
per-version support, and distribute safely. Each section ends with the lessons
that transfer to a custom SP-404MK2 firmware. **[FACT]** = verified during
research (linked); **[PRACTICE]** = documented practice; **[GUESS]** = synthesis.

---

## 1. Magic Lantern (Canon EOS DSLRs)

Magic Lantern (ML) is the closest spiritual sibling to DOOM OS: it layers a large
feature set (RAW video, overlays, scripting) on top of Canon's DryOS without
modifying the camera's ROM.

**How it loads — a card-based exploit, not a ROM patch:**
- "Each time you start your camera, Magic Lantern is loaded from your memory
  card. Our only modification was to enable the ability to run software from the
  memory card." https://magiclantern.fandom.com/wiki/Magic_Lantern_Firmware_Wiki
- The trigger is a **bootflag in camera RAM**: `BOOTDISK @ 0xF8000004` — if `-1`,
  the camera loads and runs `AUTOEXEC.BIN` from a bootable card; a `FIRMWARE` flag
  at `0xF8000000` gates card acceptance. On DIGIC 5/6 the flags live elsewhere
  (`0xF8000024` / `0xFC040000`) and a wrong bootflag config can brick the boot
  path. https://magiclantern.fandom.com/wiki/Bootflags
- `autoexec.bin` is a tiny shim: linked at `0x800000`, sets CPSR to supervisor
  mode, sets a stack, relocates the real ML blob above DryOS BSS, then **patches a
  few branch instructions in Canon's own `cstart()`** and installs a
  **task-dispatch hook at a function pointer** so ML can disable/re-purpose Canon
  tasks. https://magiclantern.fandom.com/wiki/Autoexec and
  https://magiclantern.fandom.com/wiki/DryOS_boot_process

Key insight: ML modifies vendor code **in RAM at boot**, so uninstall is "clear
the bootflag / format the card". The SP equivalent is different — DOOM OS patches
the on-disk APP1 image — but the *hook-point thinking* transfers directly.

**Stubs — the per-version address table:**
- Each camera+firmware is its own platform dir: `platform/100D.101/`,
  `platform/1100D.105/`, `platform/50D.109/`, each with `stubs.S`, `consts.h`,
  `features.h`, a Makefile, and a `ML-SETUP.FIR`.
  https://github.com/reticulatedpines/magiclantern_simplified/tree/dev/platform
  (canonical repo: magiclantern.fm; the git mirror used for source-level claims)
- `stubs.S` maps named DryOS functions to ROM addresses, e.g.
  `NSTUB(0xFF0C1BD0, cstart)`, `NSTUB(0xFF1433EC, call)`, `NSTUB(0xFF0D5F70, gui_main_task)`.
  https://raw.githubusercontent.com/reticulatedpines/magiclantern_simplified/dev/platform/100D.101/stubs.S
- The macro makes the ROM image "look like a library": the stub `.o` exports
  symbols at fixed addresses. https://magiclantern.fandom.com/wiki/Build_instructions

**Hooks:**
- **Event procs are called by name** through the `call()` stub:
  `call("MovieStart")`, `call("FA_StartLiveView")`.
  https://magiclantern.fandom.com/wiki/Extending_Magic_Lantern
- **GUI/key hooks** override Canon's task: `TASK_OVERRIDE(gui_main_task, my_gui_main_task)`;
  key codes arrive as `BGMT_PRESS_LEFT` / `BGMT_UNPRESS_RIGHT`, and GUI event IDs
  are mapped per camera. https://magiclantern.fandom.com/wiki/GUI_Events
- **Memory**: allocate through Canon's own pools wrapped by ML (`alloc_dma_memory`,
  `malloc`, `malloc_dma`) — "allocate buffers with alloc_dma_memory … to avoid
  getting corrupt data". https://magiclantern.fandom.com/wiki/Extending_Magic_Lantern

**Build system:** cross-compile ELF → `objcopy` to `magiclantern.bin` → inlined
into the `reboot.c` shim with `.incbin` → shim linked at `0x800000` →
`assemble_fw` inserts it into a legitimate empty `.fir` **at offset 0x120 and
fixes the checksum** (this "signed update" trick is what gets the camera to accept
the bootflag-setting payload). Modules are per-directory with per-platform
include/hide lists. https://magiclantern.fandom.com/wiki/Build_instructions

**Distribution:** a zip of SD-card files (`AUTOEXEC.BIN` + `ML/` + config); no
camera flash is modified. `make 550D` / `make 60D` etc. are the per-target builds.

### Lessons for the SP-404MK2
- **[PRACTICE]** Version-pin everything: one platform dir per firmware. DOOM OS
  does exactly this (one entry, "5.52").
- **[PRACTICE]** Hook by *name/semantic* (screen IDs, event names) where possible,
  and encode the resolved addresses in a stubs table. A "stubs.S" equivalent for
  the SP would list e.g. `SCRTBL` screen handlers, the pad-scan task, the
  display-draw function.
- **[PRACTICE]** When you need heap, allocate from the OS's own allocator, not a
  private arena, or you fight fragmentation and memory protection.
- **[PRACTICE]** A task-level hook (`TASK_OVERRIDE`-style) is gentler than
  patching inside an ISR: ML hijacks the GUI task's dispatch rather than
  individual interrupt handlers.

---

## 2. Rockbox (portable media players)

**Three-piece model:** (1) the factory player bootloader (in flash, untouched),
(2) the **Rockbox bootloader** ("directly replaces the player firmware in the boot
sequence", provides a **dual-boot menu**), (3) the Rockbox build in `.rockbox/` on
the drive. https://github.com/Rockbox/rockbox/blob/master/manual/getting_started/installation.tex

**Bootloader delivery exploits the vendor updater:**
- iPod: `ipodpatcher` writes the bootloader via raw disk access.
- iriver H100/H300, MPIO, Sansa Fuze+: **the user supplies the vendor firmware and
  Rockbox patches it**: "for legal reasons we cannot distribute the bootloader
  directly. Instead, we have to patch the iriver firmware with the Rockbox
  bootloader," then flash it via the vendor's own Firmware Upgrade procedure.
  https://github.com/Rockbox/rockbox/blob/master/manual/getting_started/installation.tex
- Uninstall: delete `.rockbox` (dual-boot falls back to stock) or re-flash an
  unpatched firmware.

### Lessons for the SP-404MK2
- **[PRACTICE]** The **dual-boot / updater-patching** model is the proven safe path
  and it's exactly what DOOM OS does: the stock updater installs your modified
  APP1, and re-flashing stock removes it.
- **[PRACTICE]** The legal pattern ("user supplies vendor file, you supply the
  patch/tool") is industry standard (see legal notes in `00-…`).

---

## 3. Atmosphère / Luma3DS (console CFW) — IPS-patching signed boot payloads

Atmosphère (Nintendo Switch) launches via Fusée, which loads Nintendo's signed
boot modules (package1/package2) and **patches them in RAM at load time** rather
than re-signing — nobody outside Nintendo can re-sign modified bytes, so you patch
what the loader decrypts and validates.
- "responsible for … injecting/patching system modules"
  https://github.com/Atmosphere-NX/Atmosphere/blob/master/docs/components/fusee.md
- KIP modules (signed system modules) are byte-patched from **IPS files** the user
  drops into `/atmosphere/kip_patches/`; the loader bounds-checks patches
  ("fatal error when using invalid IPS patches that go out of bounds").
  https://raw.githubusercontent.com/Atmosphere-NX/Atmosphere/master/docs/changelog.md
  and https://raw.githubusercontent.com/Atmosphere-NX/Atmosphere/master/atmosphere.mk

### Lessons for the SP-404MK2
- **[PRACTICE]** When you can't re-sign, **patch bytes at load/parse time and keep
  the container valid** (size, headers). This is precisely the DOOM OS strategy:
  fixed-size output, untouched header zone, exact rebuilt tail.
- **[PRACTICE]** **Validate your own patches** (Atmosphère bounds-checks IPS; DOOM
  OS SHA-256-checks the result) — fail loud rather than ship a corrupt image.

---

## 4. ROM hacking: code caves and IPS/BPS deltas

- **Distribution norm:** "The generally accepted way … is by making an unofficial
  patch (in IPS format or others) that can be applied to the unmodified ROM …
  The main purpose … is to avoid the legal aspects of distributing entire ROM
  images; the patch records only what has changed."
  https://en.wikipedia.org/wiki/ROM_hacking
- **IPS** is the simple 25-year-old format: `'PATCH'` + (24-bit offset, 16-bit
  length, data) records + `'EOF'` terminator; size==0 means RLE.
  https://github.com/Sir-Walrus/Flips/blob/master/libips.cpp
- **BPS** (byuu, public domain) is the modern replacement: `'BPS1'`, varints,
  SourceRead/TargetRead/SourceCopy/TargetCopy commands, CRC32 footer.
  https://raw.githubusercontent.com/Sir-Walrus/Flips/master/bps_spec.md
- **Code caves** (placing code in unused/padding bytes of a bank) is standard ROM
  hacking practice, but note: no single canonical citable guide exists — treat it
  as community jargon backed by the constraint that expanding a ROM may be
  impossible when banks are full or the mapper forbids it.
  https://en.wikipedia.org/wiki/ROM_hacking (ROM expansion section)

### Lessons for the SP-404MK2
- **[PRACTICE]** Distribute **deltas/patchers, never vendor binaries**. DOOM OS's
  `DOOMPTCH` container is a custom IPS (inline bytes + copy-from-stock records) —
  understand `03-…` before building your own.
- **[PRACTICE]** A fixed-size image means you have two places to put new code:
  **existing free/cave space** inside the image, or **a rebuilt region** like
  DOOM OS's tail. Copy-from-stock records (51 of them) show they relocated stock
  code/tables into the tail rather than re-emitting them.

---

## 5. Music-hardware custom firmware (credible examples)

- **OP-1 (Teenage Engineering) — `op1hacks/op1repacker`** (MIT): "unpacking,
  modifying and repacking firmware for the OP-1"; ships *mods* that enable hidden
  engines, tweak defaults, swap graphics. It explicitly **cannot add new
  features** — "only changes to what's already in the firmware are possible" —
  and warns of warranty-void/brick risk. Users supply the stock `.op1` file.
  https://github.com/op1hacks/op1repacker ; research docs:
  https://github.com/op1hacks/docs
- **Korg Volca Bass — `mpasserini/volca-bass-custom-firmware`**: bugfix firmware on
  top of official 1.02, **installed via Korg's standard update procedure**, and
  distributed as a `.wav` (Korg ships updates as audio files); explicitly
  downgradable. https://github.com/mpasserini/volca-bass-custom-firmware
- **Korg Volca Sample — "Pajen" firmware mod** (community, referenced widely).
  **Korg Volca Drum — `hj-oja/vdcf`** "A custom firmware for volca drum".
  https://github.com/hj-oja/vdcf
- Curated index of TE mods: https://github.com/bnjreece/awesome-te
- Novation/Elektron: **nothing credible found** in this research pass.

### Lessons for the SP-404MK2
- **[FACT]** Multiple music-gear projects install custom firmware **through the
  vendor's own update path** (Volca .wav, SP SD updater) and are therefore
  downgradable — the standard "recoverability by design".
- **[FACT]** A pure binary-mod project like op1repacker is limited to existing
  behavior; **adding whole new features** (like DOOM OS's sequencer) requires the
  full "rebuild a region + hook into dispatch tables" approach, which is a
  strictly harder problem. Budget accordingly (see `07-…`).

---

## 6. Cross-cutting lessons (the transferable checklist)

1. **Per-version support is non-negotiable.** Every project keys code to exact
   vendor builds (ML `platform/CAMERA.FW`, Rockbox model/v1-v2 splits, Atmosphere
   per-firmware, op1repacker "tested on firmware 235"). Plan a stubs/address table
   per firmware and a build that regenerates it. **[PRACTICE]**
2. **Anchor hooks to signatures/names where possible, offsets where necessary.**
   ML discovers named functions then encodes them as offsets; Atmosphere validates
   patch bounds; ROM hacking uses *relative search* to find code independent of
   version. DOOM OS's SHA-256 whitelist + offset table is the same philosophy.
   **[PRACTICE]**
3. **Distribute deltas, not vendor binaries** (IPS/BPS/DOOMPTCH, Rockbox patching
   user-supplied files, Atmosphère IPS, op1repacker). **[PRACTICE]**
4. **Design recovery in from day one**: ML = clear bootflag; Rockbox = dual-boot +
   uninstall; Volca/DOOM OS = re-flash stock via the vendor updater. A bad
   bootflag can brick the boot path in ML — treat anything below the updater
   (APP0, boot block) as off-limits on the SP. **[PRACTICE]**
5. **Keep vendor functionality intact.** ML runs alongside DryOS; Rockbox keeps a
   dual-boot; op1repacker only modifies existing behavior; DOOM OS's README says
   "DOOM OS doesn't remove or replace anything." Extend, don't fork. **[PRACTICE]**