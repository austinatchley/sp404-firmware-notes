# 00 — Overview

Learning notes for building a custom-firmware project for the **Roland SP-404MK2**
(the MK2; if you meant another SP-404 model, most of this still applies but the
firmware and update details do not). The reference project is **DOOM OS** by
Klangfeld Labs. These notes are research materials: verified facts are cited,
everything else is labeled.

**Confidence legend used throughout:**
- **[FACT]** — verified from a primary source during research (linked).
- **[PRACTICE]** — common, documented practice in comparable projects.
- **[GUESS]** — my inference, not verified. Treat as a hypothesis to test.

---

## What "a custom OS for the SP-404MK2" means

The SP-404MK2 is a closed sampler: Roland publishes no OS source, no SDK, and no
hardware documentation beyond the user manual. A "custom OS" project does not
rebuild the device from scratch — it *modifies Roland's own firmware image* and
loads it through the device's stock updater. In DOOM OS's own words it is
"a heavily modified version of the original 5.52 firmware" that keeps everything
stock working and adds new screens, a pattern grid, a mixer, and so on.

The attack surface is therefore one binary: **`SP404MKII_APP1.bin`**, the file the
SP's stock updater installs. If you can edit that file and still have the updater
accept it, you control everything the OS controls: display, pads, knobs, the
sequencer, the file system.

## The DOOM OS case, as documented

Sources: the DOOM OS page (https://klangfeldlabs.com/doom-os/), the patcher page
(https://klangfeldlabs.com/doom-os/patcher), the launch post
(https://klangfeldlabs.com/posts/2026-09-27-doom-os-sp404mk2), and the repo
(https://github.com/klangfeld-labs/doom-os).

Verified facts **[FACT]**:

- v0.6-alpha, build 0C34, for firmware 5.52, released 2026-09-28.
- Distribution is a **browser-based patcher** (JS in the repo, `doomos-patcher.js`).
  The user downloads Roland's official 5.52 update, unzips it, and drops
  `SP404MKII_APP1.bin` onto the patcher page. Nothing is uploaded; the page works
  offline from `file://`.
- The patcher accepts only the official 5.52 file: it computes SHA-256 and matches
  against a whitelist (`4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80`).
  The patched result must hash to `79525d514784bbdcc70cb9c05b5fb987500e99ddf02aa4ceeb875bf9070fa26d`
  (both in `checksums.txt` and baked into the JS).
- Install uses the **stock updater**: copy the patched file to the root of an SD
  card, insert it, hold **SHIFT** and power on, wait for the UPDATER menu, press
  the VALUE knob / ENTER. (The DOOM OS page says VALUE knob; Roland's support
  article says ENTER — same flow, https://support.roland.com/hc/en-us/articles/4409641783579)
- Reverting is the same procedure with the unpatched Roland file. "To go back to
  the original firmware, just run the updater with the original Roland firmware."
- The repo contains **no readable OS source** — only the patcher, `checksums.txt`,
  `index.html`, docs, manual, assets, changelog.

The patcher's container format (decoded from the shipped JS this session) **[FACT]**:

```
'DOOMPTCH'  u16 format(=1)  u16 entry_count
per entry (96 bytes):  label[16]  srcSha[32]  dstSha[32]
                       u32 dstSize  u32 recCount  u32 recsAt  u32 dataAt
records: (u32 outOffset, u32 len, u32 where)   where==0xFFFFFFFF -> inline bytes,
                                               else copy from stock at 'where'
```

For 5.52: `dstSize = 0x2AC750 = 2,803,536`, **283 records** (232 inline + 51
copy-from-stock). The result is a fixed-size image: the leading region
`0x0..0x2F6A6` is never touched, ~a hundred surgical edits are scattered through
the middle, and the **tail `0x287A00..0x2AC750` is fully rebuilt** — it contains
named tables (`SCRTBL` screen table, `SYSTAB`, `SYSSTR` system strings, `CONTBL`
control table, `BOOTANI` boot animation), the DOOM OS code/data blobs, and a
boot/branding block at the very end (`SPUA`/`STARTUP…`/`ROLAND`/`PRODUCT`/`SBMP`
plus bitmap data).

### What this implies about Roland's firmware — labeled inference

- **[GUESS]** The image is a fixed-size container with multiple load regions.
  Nothing before `0x2F6A6` may be touched (header / boot metadata / earlier
  sections), and the file must be exactly 2,803,536 bytes, so the updater
  validates at least the file size and likely some header region in the untouched
  prefix.
- **[GUESS]** The updater does **not** cryptographically sign or strongly
  checksum APP1 content, or the edits would fail. (Weak-checksum inference is
  directly supported: a heavily edited tail installs and boots.)
- **[GUESS]** The end-of-image `SPUA/STARTUP/SBMP` block is parsed by the boot or
  update path; the patcher rebuilds it in place, so it must be size/format
  consistent. Leave it alone in your own experiments.

### Why "a custom OS" and "the firmware updater" coexist

The SP has a low-level update path (the SHIFT+power "UPDATER" menu) that rewrites
APP0/APP1 regardless of what the running OS does. That path is your **safety net**:
any APP1-level breakage can be undone by re-flashing stock. This is exactly how
DOOM OS guarantees recoverability ("re-flash stock firmware reverts it").

## Why this is hard

1. **No hardware docs.** The SoC and RTOS are not officially documented (see
   `01-…facts.md`). Everything is community-inferred.
2. **No symbols.** You work from a raw binary with strings and guesses.
3. **No debug port known.** No public JTAG/SWD/UART story; recovery is via the
   stock updater, not a debugger.
4. **Real-time audio.** The sequencer and DSP run on tight timing; a bad hook
   causes glitches or freezes, not just a crash you can read.
5. **Per-version fragility.** Every firmware release shifts addresses. DOOM OS is
   pinned to exactly 5.52.

## Legal / terms-of-use note (not legal advice)

These notes describe interoperability and personal-device research on hardware you
own. A few things to be aware of:

- Roland's firmware is copyrighted binary code. Projects like DOOM OS therefore
  ship **patches, not firmware**: the user downloads the official update from
  Roland and the patcher produces the modified file locally, so no copyrighted
  binary is redistributed. The DOOM OS container even carries stock bytes by
  *reference* ("copy from offset 0x…"), not inline. This is the same distribution
  model ROM hackers standardized (IPS/BPS patches, see `03-…`) and Rockbox uses
  ("for legal reasons we cannot distribute the bootloader directly, we have to
  patch the iriver firmware", https://github.com/Rockbox/rockbox manual).
- Modifying firmware voids the warranty and may violate Roland's terms of use
  for the update files. DOOM OS ships a disclaimer to that effect
  (https://klangfeldlabs.com/doom-os/).
- Do not redistribute Roland firmware you have downloaded. Do all experiments on
  files you obtained yourself for your own device.
- Different jurisdictions treat firmware modification and circumvention
  differently (e.g. DMCA §1201 in the US, EULA/ToS clauses in shrink-wrap
  agreements). This document is not legal advice; if it matters commercially,
  ask a lawyer who does IP/security work.

## Map of the rest of these notes

| File | What it covers |
|---|---|
| `01-sp404-hardware-and-firmware-facts.md` | Verified hardware/firmware facts, unknowns, sources |
| `02-case-studies.md` | Magic Lantern, Rockbox, Atmosphère, ROM hacks, music-hardware mods; transferable lessons |
| `03-binary-patching-techniques.md` | Code caves, trampolines, displaced instructions, checksum fixes, delta formats — with worked examples |
| `04-reverse-engineering-workflow.md` | Triage → architecture ID → Ghidra → dynamic analysis |
| `05-diffing-guide.md` | Stock-vs-patched analysis; how to read `tools/diff_cluster.py` output |
| `06-embedded-gotchas.md` | RTOS contexts, cache coherency, filesystem safety, flash endurance |
| `07-first-project-roadmap.md` | Staged "hello world" plan with risk + recovery per stage |
| `08-glossary-and-reading-list.md` | Terms and annotated links |
| `open-questions.md` | What is still unknown and the cheapest experiment to resolve each |