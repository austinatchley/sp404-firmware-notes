# AGENTS.md — SP-404MK2 custom-firmware project

Research notes and tooling for building a DOOM OS-style custom firmware for the
Roland SP-404MK2. Docs live in `docs/` (start with `docs/00-overview.md`).
All content uses a confidence legend: **[FACT]** verified/cited, **[PRACTICE]**
common in comparable projects, **[GUESS]** inference.

## Ground rules (treat as mandatory)

- Work from public info only. Never download, host, or distribute Roland
  firmware or any copyrighted binary. Only describe workflows that operate on
  files the user obtains themselves.
- Modify only `SP404MKII_APP1.bin` (5.52). **Never touch APP0 or the image
  header/boot block (`0x0..0x2F6A6`).** Always keep a stock APP1 on a spare SD.
- Every claim stays labeled; never present inference as fact.
- Recovery rule: any APP1-level breakage is fixed by re-flashing stock via the
  updater (hold SHIFT + power on). Keep APP0 intact.

## Verified facts from this session (key numbers)

- Stock 5.52 `SP404MKII_APP1.bin` SHA-256:
  `4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80`
- DOOM OS-patched output: 2,803,536 bytes, SHA-256
  `79525d514784bbdcc70cb9c05b5fb987500e99ddf02aa4ceeb875bf9070fa26d`
- Patcher container `DOOMPTCH`: `'DOOMPTCH'` + u16 format(1) + u16 count, then
  96-byte entries (label[16], srcSha[32], dstSha[32], u32 dstSize, u32 recCount,
  u32 recsAt, u32 dataAt); records `(u32 outOffset, u32 len, u32 where)` where
  `where==0xFFFFFFFF` = inline bytes, else copy from stock at `where`.
- DOOM OS 5.52 diff shape: nothing below `0x2F6A6`; small Thumb-2 trampolines at
  `0x2F6A6`/`0x5C380` (bytes like `47 f6 70 21` = `MOVW R1,#0x7070`); regular
  stride edits `0x188/0xC8/0x190` at `0x23E8C0..0x24E000` (per-voice tables);
  rebuilt tail `0x287A00..0x2AC750` with tables `SCRTBL/SYSTAB/SYSSTR/CONTBL/
  BOOTANI` and an end-of-image `SPUA/STARTUP/SBMP` boot block.
- SoC/OS NOT publicly confirmed. Community (unverified) says NXP i.MX
  RT1060/62 (Cortex-M7) + µT-Kernel. Never state otherwise without labeling it.

## Tooling

- `docs/tools/diff_cluster.py` — stdlib-only alignment-aware binary diff.
  Usage: `python3 docs/tools/diff_cluster.py stock.bin patched.bin --block 16
  --gap 4 [--json out.json]`. Classifies changed blocks as `moved` (bytes exist
  elsewhere in stock = relocated) vs `novel` (new code/data) and clusters them.
  Read the full interpretation in `docs/05-diffing-guide.md`.
- No build/lint/test commands exist for this repo (docs + one script).
  Validate with `python3 -m py_compile docs/tools/diff_cluster.py`.

## Where to look

- `docs/00-overview.md` — what the project is, DOOM OS case, legal note, doc map
- `docs/01-…` — hardware/firmware facts, unknowns, recoverability table
- `docs/02-…` — case studies (Magic Lantern, Rockbox, Atmosphère, ROM hacks)
- `docs/03-…` — patching techniques with worked examples
- `docs/04-…` — RE workflow (triage → Ghidra → Unicorn)
- `docs/05-…` — stock-vs-patched diffing guide
- `docs/06-…` — embedded gotchas (contexts, cache, filesystem, flash wear)
- `docs/07-…` — staged first-project roadmap with per-stage recovery
- `docs/open-questions.md` — unknowns + cheapest experiments to resolve each