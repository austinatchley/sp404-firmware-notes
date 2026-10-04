# Open questions — what is still unknown, and the cheapest way to resolve each

Ranked roughly by "cheap to answer" first. Each has the cheapest experiment that
would resolve it, ordered within an entry from lowest to highest cost. Do the
offline ones first — everything here labeled *offline* carries zero flash risk.

## 1. What SoC is actually inside? (cheapest to start, hard to finish)

Nothing is confirmed: the leading community claim is **NXP i.MX RT1060/62
(Cortex-M7)**, an older theory is **Roland custom BMC silicon**; both unverified
(https://www.reddit.com/r/sp404mk2/, https://www.reddit.com/r/SP404/comments/1eryyga/).

- **Offline, cheapest:** read the chip markings in the teardown video frame by
  frame (https://www.youtube.com/watch?v=wTqpxwjcDRG). If the NXP logo or part
  number is legible, that's near-conclusive. Cost: one hour.
- **Offline:** look for the silicon's debug-tool strings in the firmware (e.g.
  the Cortex-M7's cache/MPU init code, or a ROM-based serial number routine).
- **Offline:** entropy/layout comparison against a *known* Cortex-M7 firmware of
  similar shape.
- **Hardware:** probe likely SWD/JTAG pads (see Q4). Unconfirmed risk.

## 2. Is the OS µT-Kernel, and which version?

Two independent community analyses say µT-Kernel; not verified.

- **Offline:** search the image for µT-Kernel syscall dispatch (the
  `tk_` service-call numbers are documented at https://www.tron.org/); if you can
  map a handful of syscall vectors to their numbers, that's strong evidence.
- **Offline:** look for the RTOS's own strings/version and its task-control-block
  layout, then check the block stride against the documented µT-Kernel TCB.

## 3. What is APP0, and does the updater validate APP1?

We know: APP0 + APP1 both flash, DOOM OS only patches APP1, the patcher keeps
`0x0..0x2F6A6` untouched and enforces exact output size **[FACT]**.

- **Offline, cheapest:** `binwalk -E` + `strings` on APP0 vs APP1. If APP0 is
  small/has UPDATER/loader strings, the split is confirmed as loader/app.
- **Offline:** diff two firmware versions (e.g. 5.52 vs an older one you can
  obtain) with `tools/diff_cluster.py`. The regions that change *between official
  versions* reveal what the updater cares about: if only APP1 content changes and
  sizes stay fixed, size+prefix validation is likely all there is.
- **Black-box (low risk):** feed the updater (a) a stock APP1 renamed to APP0,
  (b) an APP1 with one bit flipped, (c) an APP1 truncated by 1 byte, (d) an APP1
  with extra bytes. Record which are accepted/rejected. This directly maps the
  updater's validation envelope. Do on a sacrificial unit with a full backup.
- **Inference already in hand:** the patched tail (with heavy edits and a rebuilt
  end block) installs and boots, so there is **no strong signature/checksum over
  APP1 content** **[GUESS, strongly supported]**.

## 4. Is there a debug port (SWD/JTAG/UART)?

No public documentation of one.

- **Cheapest:** inspect the teardown video for unpopulated test pads / a header
  footprint; compare with the SP-404SX board (https://www.reddit.com/r/SP404/comments/1gz1hmx/bricked_sp404sx_teardown/).
- **Offline:** if the chip is confirmed to be an i.MX RT family, the datasheet
  defines where SWD pins are *expected* on the board — but confirming they're
  wired to pads needs eyes on the PCB.
- **Hardware (higher risk):** with a sacrificial unit on a bench supply, try
  touching SWD/JTAG pins with an ST-Link/J-Link and see if the core halts. Only
  do this after Q1/Q2 are answered; a wrong probe on a live board can cause
  shorts (see risk table in `04-…`).

## 5. The correct load address / image base for Ghidra

Not public. The community says APP1 is "scatter-loaded" **[GUESS, community]**.

- **Offline, cheapest:** find the vector table (Cortex-M) or entry table; try
  candidate bases (`0x00000000`, `0x08000000`, `0x60000000`) and check which one
  makes string xrefs resolve (Stage 1 of `04-…`).
- **Offline:** locate a scatter/load-region table (address+size pairs near the
  image start) and read the actual RAM/flash base from it.
- **Offline:** use the DOOM OS diff: the tail is *moved* stock content plus new
  blobs; if any new blob contains a pointer to a RAM address, that leaks the
  runtime layout.

## 6. Where do the pattern/step data structures live?

DOOM OS edits an array at `0x23E8C0..0x24E000` with strides
`0x188/0xC8/0x190` **[FACT, inferred]**, and there is a screen table `SCRTBL`
and control table `CONTBL` **[FACT]**.

- **Offline, cheapest:** in the patched image, diff those stride regions and read
  the semantics from the values DOOM OS wrote (they encode steps/velocity/length
  — the manual explains what they are). Then confirm in stock by finding the
  sequencer code that reads them.
- **Offline:** Version Tracking/Diaphora stock-vs-patched over the mid-region
  bands to name the functions that consume the tables.

## 7. How does the screen system dispatch, and can new screens be registered?

- **Offline:** reverse the stock `SCRTBL`-style table: each entry is a screen ID
  → handlers. Find the dispatch loop (probably a µT-Kernel task) by xref-ing the
  table.
- **Offline:** study how DOOM OS *extends* it (their tail registers new screens).
  The register function (or table append) is in the new code, identifiable by the
  `SCRTBL` header string.
- **Experiment (Stage 3 of `07-…`):** reuse an existing screen slot first.

## 8. What does the end-of-image `SPUA/STARTUP/SBMP` block actually do?

Present in stock and rebuilt by DOOM OS **[FACT]**; presumably parsed at boot or
by the updater.

- **Offline, cheapest:** compare the stock end block vs DOOM OS's rebuilt one —
  field-by-field (`tools/diff_cluster.py --block 4` over the tail). Fields that
  change (branding strings, bitmap) vs fields that stay (magic, sizes) reveal the
  schema.
- **Black-box:** flash a test image with a *mutated* end block on a sacrificial
  unit and observe (does the SP still boot? does the updater still run?). Keep
  stock at hand. Do this only when you're comfortable with re-flash recovery.

## 9. Does any cache/MPU setup constrain runtime codegen?

If Cortex-M7, yes by architecture; but how the firmware configures caches/MPU is
unknown.

- **Offline:** find the MPU/cache init in stock (search for `SCB`/`ICIALLU`
  register constants) and note whether regions are marked cacheable/executable.
- **Experiment:** only relevant if you plan runtime codegen; the 
  pre-spliced-image approach (DOOM OS's) sidesteps it entirely.

## 10. Sustainability of the approach across Roland firmware releases

DOOM OS is pinned to 5.52; the next Roland release may shift every address.

- **Cheapest:** diff the *next* official firmware against 5.52 (the updater lets
  you downgrade). The size of the changed regions tells you how much re-RE work a
  new version costs, and whether signature-anchored hooks would survive.

## Suggested order of attack

1. Offline: hash/verify, triage (`04-…`), find the vector table + base (Q5).
2. Offline: diff stock vs DOOM OS-patched (Q6, Q8), map clusters to structures.
3. Offline: µT-Kernel syscall identification (Q2) to anchor code analysis.
4. Black-box updater validation tests on a sacrificial unit (Q3).
5. Hardware probing (Q1/Q4) only after everything above, with full precautions.