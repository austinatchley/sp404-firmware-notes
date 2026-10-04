# 04 — Reverse-engineering workflow for an unknown embedded image

A practical, tool-by-tool path from a raw `.bin` to "I can patch a function".
Assumes you have a legitimate copy of `SP404MKII_APP1.bin` (5.52) that you
downloaded from Roland yourself. **[PRACTICE]** = standard RE technique,
**[GUESS]** = inference about the SP specifically.

**Tool prerequisites (all free):** `file`, `binwalk`, `ent` (from `ent` package),
`strings`, `xxd`, Python 3, **Ghidra**, optionally `radare2`/`rizin`, `Unicorn`,
`QEMU`, `diff_cluster.py` (in `tools/`).

---

## Stage 0 — Triage (10 minutes, zero risk)

```bash
file SP404MKII_APP1.bin
xxd -g1 -l 256 SP404MKII_APP1.bin        # look at the first 256 bytes
binwalk SP404MKII_APP1.bin               # signature scan for embedded filesystems
binwalk -E SP404MKII_APP1.bin            # per-block entropy graph
strings -n 8 -t x SP404MKII_APP1.bin | head -100   # ASCII strings w/ offsets
sha256sum SP404MKII_APP1.bin             # should equal 4a3d6771... if it's 5.52
```

Read the results like this:
- **First bytes** — the DOOM OS patcher never touches `0x0..0x2F6A6`, so this
  region is your header/boot metadata. Note its shape (ASCII tag? size fields?).
  The end of the file should contain the `SPUA/STARTUP/SBMP` block and `DOOMOS`/
  `DOOM OS` strings only in the patched image; the *stock* image will have its own
  branded end block (see `05-…` to diff them).
- **Entropy** — mostly-random code sections (~7–8 bits/byte) vs. low-entropy
  padding (zeros, `0xFF`) and table zones. `binwalk -E` shows this per 1 KiB block.
  Low-entropy runs are candidate code caves and alignment padding.
- **Strings** — the community found UI strings referencing ZENOLOGY, Fantom-X,
  sample WAVs and a hidden high-score system in firmware 2.0.1
  (https://www.reddit.com/r/SP404/comments/x2gigu/interesting_things_in_the_mkii_201_update/)
  **[GUESS]** similar branding strings exist in 5.52 and are great anchors.

**Architecture ID checklist** (this is where you confirm the community's
Cortex-M7 / µT-Kernel theory for yourself):
- **Endianness:** the DOOM OS patcher reads its *container* little-endian and the
  image decodes as little-endian ARM **[FACT]**. Confirm independently: halfword
  pairs like `42 F2` / `C0 F2` (MOVW/MOVT) and Thumb-2 `0xFxxx` first-halfwords
  are only sensible in little-endian ARM.
- **Vector table (Cortex-M):** at the image (or a load region's) base, word 0 is
  the initial SP (a RAM address like `0x2000xxxx`/`0x2020xxxx`), word 1 is the
  reset handler with bit0 set (Thumb). If you find a `0x2000xxxx`-looking word
  followed by an odd code address near an image region boundary, you have a
  vector table.
- **RTOS tell-tales:** search for `tk_`, `µT-Kernel`, `T-Kernel`, `T-Kernel/OS`,
  `task`, `sem_` style strings. µT-Kernel is a TRON-family RTOS
  (https://www.tron.org/) — the community identifies it as the OS
  **[GUESS, community]**.
- **Bootloader vs app:** APP0 is presumed the loader/updater stage and APP1 the
  main image **[GUESS]**. Don't RE APP0 for your first project; APP1 is the
  surface you patch.

## Stage 1 — Recover the load address and image structure

Ghidra needs to know where the image lives in memory. For a raw, non-ELF image
there is no authoritative answer; you *derive* one:

1. **Look for a vector table / entry table.** For Cortex-M, if the image begins
   with `(SP_value, reset_vector)` you can set base = file offset of that table
   and the reset vector gives you the first code address.
2. **Find the load-region / scatter table.** The community describes APP1 as a
   "scatter-loaded image" **[GUESS, community]**; DOOM OS's edit bands imply
   multiple load segments **[FACT, inferred from record offsets]**. A scatter
   table is usually a small array of `(load_address, size)` or
   `(load_addr, exec_addr, size)` pairs near the start of the image. Hunt for
   pairs of little-endian words where one is a plausible RAM/flash address
   (`0x20000000..0x20100000` SRAM, `0x60000000`/`0x70000000`-ish XIP flash for
   i.MX RT) and the other a plausible size.
3. **Corroborate with a code anchor.** Find a string, look for its 32-bit
   address in the code (literal pool) via a search for the byte-swapped address;
   if the file offset of the string minus the literal value is constant across
   several strings, that constant is your base offset.

**Typical guesses for a Cortex-M XIP image:** load at the flash base the SoC
maps (`0x00000000` alias, or `0x60000000` for i.MX RT flexSPI). If Ghidra shows
garbage after you pick a base, try the others; consistent string xrefs are the
smell test. **[PRACTICE]** (Do not burn time perfecting this — strings + a
plausible base is enough to start.)

## Stage 2 — Ghidra setup

1. `ghidraRun` → File → New Project → File → Import File → select
   `SP404MKII_APP1.bin`.
2. In the import dialog, Language: try **ARM:LE:32:v7** (or the Cortex-M variant
   if offered — Cortex-M7 if the community theory holds), **little-endian**,
   base address = your Stage 1 guess.
3. Leave "Options" default; Analyze → Auto Analyze.
4. **First pass:** Window → Strings. Click any string you recognize → right-click →
   References → Show References To. Landing on code means your base is right.
5. **Make it useful:**
   - `G` (goto) any scatter-table addresses to split the image into regions
     (right-click → Code, or use "Add to Program" as a data region).
   - Window → Memory Map: add labels for region boundaries (`load0`, `tail`, ...).
   - Mark the `SPUA/STARTUP/SBMP` end block and the named tables
     (`SCRTBL`, `SYSTAB`, `SYSSTR`, `CONTBL`, `BOOTANI`) — these are in the
     *patched* image at `0x287A00+` **[FACT]**; in the stock image they live at
     different offsets, which is exactly what you'll diff for.
6. **Struct recovery:** from a string xref, walk the function; when you see
   `LDR R0, [R1, #off]` repeated with the same base, define a struct on that
   base in the Listing → Data Type Manager → create → apply. µT-Kernel code uses
   the `tk_` API; recognize calls by their syscall numbers via the µT-Kernel
   reference (https://www.tron.org/) to name kernel entry points **[PRACTICE]**.

**Diffing is your biggest shortcut** (see `05-…`): instead of finding things by
hand, diff stock vs. DOOM OS-patched, and every cluster that shows "moved"
content pointing into the rebuilt tail tells you which stock table got relocated
and where the hook entry points are.

## Stage 3 — Dynamic analysis (no debug port required)

No public JTAG/SWD/UART on the SP **[FACT, nothing found]**. You still have three
non-invasive dynamic avenues:

### a) Emulate single functions with Unicorn
For a small Cortex-M (if confirmed), you can emulate *individual functions* you've
identified, supplying input state, and observe outputs — no need to boot the
device. Sketch:

```python
from unicorn import *
from unicorn.arm_const import *

BASE = 0x60000000
mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)          # or MCLASS
mu.mem_map(BASE, 0x400000)
data = open("SP404MKII_APP1.bin","rb").read()
mu.mem_write(BASE, data[:0x400000])          # map the image
mu.reg_write(UC_ARM_REG_SP, 0x20008000)
mu.reg_write(UC_ARM_REG_R0, arg0)
# hook code fetch to log executed addresses:
def hook(uc, addr, size, user):
    if addr == TARGET_PRINT_ADDR:  # some function we named
        buf = uc.mem_read(BUF_ADDR, 64); print(buf)
mu.hook_add(UC_HOOK_CODE, hook)
mu.emu_start(FUNC_ADDR, STOP_ADDR, count=100000)
```
Readouts: how many instructions until crash, which functions are called, what
memory is touched. **[PRACTICE]** This is the standard "no debug port" technique.

### b) Boot the whole image under QEMU — low odds, try cheaply
`qemu-system-arm -machine mps2-an385 -cpu cortex-m7` can boot bare Cortex-M code
with semihosting, but the SP's peripherals (display, pads, codec, QSPI flash)
have no QEMU model, so a full boot will wedge at the first peripheral access. Use
QEMU only to sanity-check early vector-table/entry code, or emulate a *skeleton*
that stubs peripheral registers to MMIO reads. **[GUESS]** this will mostly not
pay off; Unicorn is the better first bet.

### c) On-device logging via the thing you can see
Your only output devices are the **display** and **USB**:
- **Display logging:** hook the text-drawing function (find it via a string you
  can draw, or the screen table) and render debug values. This *is* the hello
  world of `07-…`.
- **USB logging:** sniff the USB device on the host with
  `sudo modprobe usbmon && sudo tcpdump -i usbmon0 -w sp.pcap` then inspect in
  Wireshark; or hook the USB-request handler in firmware to log internally.
  **[PRACTICE]**

### d) Behavioral/black-box probing
The SP exposes MIDI and a USB drive. Before you touch bytes, learn the observable
state machine: what sysex does it answer, what does the SD-card drive look like
mid-boot, does firmware update work with files of odd sizes/names? All of this
is cheap, safe, and informs what the updater actually validates
(see `open-questions.md`).

## Stage 4 — Putting it together for your first patch

1. Choose a **display string** as your anchor (a screen title you can see).
2. In Ghidra, find its xref; that's the draw call path.
3. `diff_cluster.py stock patched --json` on a DOOM OS image to see which offsets
   near that path were edited (their clusters are your "known hook" examples).
4. Design your trampoline (§3), assemble the bytes, patch a *copy*, verify size
   and header integrity, then flash via the stock updater with a full backup.

## Risk table for the workflow

| Activity | Risk | Notes |
|---|---|---|
| Reading/hashing/strings/binwalk | none | do as much of this as possible |
| Ghidra/Unicorn analysis | none | all offline |
| USB sniffing, black-box probing | very low | read-only |
| On-device display logging | low–medium | first on-device step; revert = re-flash stock |
| First patched APP1 flash | medium | always keep stock file + backup projects |
| Probing physical pins for SWD/UART | high | unproven on this board; battery-powered; do last, with a bench supply and a sacrificial unit |