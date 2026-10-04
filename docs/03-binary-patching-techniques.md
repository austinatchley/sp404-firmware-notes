# 03 — Binary patching techniques (with worked examples)

The mechanics of modifying a closed binary so it keeps working. Labels:
**[FACT]** verified, **[PRACTICE]** standard technique, **[GUESS]** inference.

---

## 1. Where new code goes: code caves and free space

A closed firmware image is a fixed-size blob. To add code you either reuse bytes
that already exist ("caves", unused padding) or rebuild a region and point the
dispatch tables at it.

**Code cave** — unused bytes you can claim. On consoles/embedded targets these are
typically the zero or `0xFF`-filled padding after a function/bank boundary:

```
0x0802F6A0  <last function>  ...  ends
0x0802F700 00 00 00 00 00 00 ...  <- cave (padding)
```

**[PRACTICE]** An *in-place* hook is: overwrite a few bytes of a function entry,
put the displaced bytes + your code in the cave, and jump back. The DOOM OS
patcher's small edits at offsets like `0x2F6A6` (7- and 9-byte records) are
exactly this shape **[FACT]**.

**Two approaches when caves are insufficient:**
- **Rebuild a region** (DOOM OS rebuilds the tail `0x287A00..0x2AC750`, relocating
  stock code/tables into it rather than re-emitting them — the 51
  "copy-from-stock" records) **[FACT]**.
- **Bank/mapper tricks** from ROM hacking: if the firmware has a loader with a
  load-region table, you may be able to grow the image — but the SP updater
  appears to enforce a fixed size, so grow it only if you prove otherwise
  **[GUESS]**.

## 2. Trampolines / hooks

A **trampoline** is the tiny redirect placed at the call site; the **payload**
lives in a cave/region. The three standard idioms:

### x86 (64-bit) example — `jmp rel32` into a cave

```
; function entry at 0x401000. We clobber its first 5 bytes.
; cave at 0x401500. rel32 = 0x401500 - (0x401000 + 5) = 0x4FB
;
; at 0x401000:
E9 FB 04 00 00        jmp 0x401500

; displaced instructions (the 5 bytes we overwrote), replayed in the cave:
; original first 5 bytes: 48 8B 5B 10 51  = mov rbx,[rbx+0x10]; push rcx
401500:  51            push rcx
401501:  48 8B 5B 10   mov rbx, [rbx+0x10]
401505:  ... your hook code ...
4015xx:  E9 <rel32>    jmp 0x401005    ; back to original+5
```

Key rules **[PRACTICE]**:
- The **displaced instructions must be replayed before your code** (or before the
  jump back), and they must behave identically from the cave (see §4 relocation).
- The clobbered region must start at an **instruction boundary** and be fully
  covered by your jump (5 bytes on x86-64, 4 bytes on 32-bit x86).
- `jmp rel32` only reaches ±2 GiB — fine inside one image.

### ARM Thumb-2 example (relevant: little-endian ARM is the SP's presumed arch)

Thumb-2 has no single 5-byte absolute jump. The classic trick is
**materialize the target address in a register, then branch**:

```
; hook a function entry; redirect to payload at 0x08002880 (Thumb)
;
42 F2 80 8C    MOVW R12, #0x2880     ; low 16 bits of target
C0 F2 00 0C    MOVT R12, #0x0800     ; high 16 bits
60 47          BX   R12              ; branch (bit0 of R12=0 -> stay in Thumb)
```

Decoding `42 F2 80 8C`: `0xF242` is `MOVW` with imm4=2, `0x8C80` is
`imm3=8, Rd=12, imm8=0x80` → `R12 = 0x2880`. **[FACT]** these encodings.

**Why the DOOM OS record bytes look the way they do** — the patcher's small
records begin with `47 f6 70 21` which decodes to `MOVW R1, #0x7070`
(`0xF647` + `0x2170`), followed by bytes consistent with another
MOVW/MOVT-family instruction and a branch. That is the classic shape of
**Thumb-2 trampolines that materialize an address and jump** **[GUESS]** —
good news: it means the region around `0x2F6A6` is already a known hook idiom
you can learn from by diffing (see `05-…`).

Alternative ARM idioms when in-range: `B.W` (Thumb-2 wide branch, ±16 MB),
or `LDR PC, [PC, #-4]` with a literal pool (careful with alignment — the
literal must be 4-byte aligned relative to the PC value read).

## 3. Displaced instructions

When you overwrite N bytes, the original N bytes must execute somewhere. **[PRACTICE]**
- Replay them verbatim in the cave (works for position-independent code).
- If the original instructions are **PC-relative** (x86 RIP-relative, ARM
  `LDR Rd, [PC, #imm]`, `ADR`, `BL` to a nearby function), replaying them at a
  different address computes a **different target**. Fix by:
  - rewriting the displacement (re-assembling for the new location), or
  - fetching the original bytes from their original location at runtime, or
  - arranging for the cave to contain its own literal pool and pointing the
    displaced instruction at it.

## 4. Relocation when moving code

Moving a chunk of code/tables to a new region breaks three things **[PRACTICE]**:
1. **Absolute addresses** — any `LDR Rd, [label]`/`MOVW/MOVT` pairs or data
   pointers that name the old address must be rewritten to the new address.
   (This is why DOOM OS's container has `(offset, len, where)` records with a
   `where` that *copies from stock* — stock blobs that "move to a new place" are
   brought along, and their fixups are handled in the rebuilt tables.)
2. **PC-relative references** — literal pools must move with their referrers or
   the ±4 KB (LDR literal) / ±1 KB (Thumb `LDR Rd,[PC,#imm]`) range is exceeded.
3. **Branch ranges** — a long-range call from the new region to old code may
   exceed the direct branch range; use an absolute jump via register.

## 5. Fixing checksums and headers

Images that carry an internal integrity field must be re-validated after editing:
- **[PRACTICE]** Magic Lantern's `assemble_fw` inserts its payload into an empty
  `.fir` and **recomputes the firmware checksum** so Canon's loader accepts it.
  https://magiclantern.fandom.com/wiki/Build_instructions
- **[PRACTICE]** IPS has an optional truncate record (from Flips): after `EOF`, a
  3-byte length sets the output size — useful when the updater checks exact size.
  https://github.com/Sir-Walrus/Flips/blob/master/libips.cpp
- **The SP case:** the DOOM OS patcher performs **no internal checksum fix** — it
  verifies the *result* externally by SHA-256. Two inferences **[GUESS]**:
  (a) the updater does not checksum APP1 content (or checks a header region the
  patcher leaves untouched), and (b) it enforces the file size
  (patched output is exactly the stock size). Verify both yourself by experiment
  (see `open-questions.md`).

## 6. Signature-based hook location

Hard offsets break when a firmware updates. The robust pattern is
**find the hook point by byte pattern, then compute the offset** **[PRACTICE]**:
- **Pattern scan**: search for a distinctive instruction byte sequence that
  identifies the function you want (e.g. the `MOVW/MOVT` pair above, or a
  function prologue). Tooling: `radare2 /c <pattern>` (a.k.a. `aap`), Ghidra
  `Search Memory → String`, or a small script.
- **Relative search** (ROM-hacking jargon): search for "what changes around the
  string I care about" — find the string you want to affect, then look a fixed
  distance away for the dispatch table entry that references it.
- **Anchoring**: Magic Lantern *names* functions via stubs discovered with a
  signature finder, then stores them as per-version offsets. Same idea: build a
  "stubs" table per firmware version. https://magiclantern.fandom.com/wiki/PortingML

The DOOM OS patcher inverts this: it whitelists one exact stock SHA-256 and uses
**precomputed offsets** — simple, but fragile (a new Roland release = new table)
**[FACT]**. For your own project, prefer signature-anchored patches so you can
ride out minor firmware changes.

## 7. Delta formats for distribution

You will never ship the whole modified binary if you can avoid it; ship a delta
and let the user's machine apply it to the stock file they downloaded.

### IPS (simplest)
```
"PATCH"
0F A0 00         24-bit offset 0x000FA0 (big-endian)
00 03            16-bit length 3
41 42 43         bytes 'ABC'
45 4F 46         "EOF" terminator
```
length==0 means "RLE: 16-bit run length, 1 data byte". https://github.com/Sir-Walrus/Flips/blob/master/libips.cpp

### BPS (modern, LZ-ish, CRC-verified)
`"BPS1"` + varint source size + varint target size + varint metadata length +
metadata + action stream + CRC32(source) + CRC32(target) + CRC32(patch).
Actions are a signed-varint `data` where the low 2 bits select the command and
`data >> 2` is `length-1`; the value is XORed with an input/output offset
accumulator. Commands: `0=SourceRead` (copy from input), `1=TargetRead`
(byte in the patch), `2=SourceCopy` (back-reference in input), `3=TargetCopy`
(back-reference in output). Full spec (public domain):
https://raw.githubusercontent.com/Sir-Walrus/Flips/master/bps_spec.md
**[FACT]** format; a byte-exact mini-example is left as an exercise — the spec
is short and precise.

### bsdiff / xdelta
`bsdiff` (https://www.daemonology.net/bsdiff/) produces deltas from suffix-sorted
arrays and is O(n) to apply; `xdelta3` (http://xdman.sourceforge.net/ or the
`xdelta` package) implements VCDIFF. These are **lossless binary diff** formats,
good for whole-file deltas, but less expressive than a patch that *relocates*
bytes the way the DOOM OS container does.

### The DOOM OS `DOOMPTCH` container — a real example **[FACT]**
```
'DOOMPTCH'  u16 format(1)  u16 count
entry(96): label[16] srcSha[32] dstSha[32]
           u32 dstSize u32 recCount u32 recsAt u32 dataAt
record(12): u32 outOffset  u32 len  u32 where
            where==0xFFFFFFFF -> len bytes inline in the patch
            else              -> copy len bytes from stock at 'where'
```
It is IPS-with-relocation: edits by absolute offset, stock bytes referenced by
position (never carried), digest-verified in/out. This is a good template for
your own patcher (see `07-…`).

## 8. Safety checklist before you flash anything

1. Keep APP0 and the image header/boot block untouched (see `01-…`).
2. Keep a stock APP1 on a spare SD card; know the SHIFT+power updater flow cold.
3. Verify your output against a known-good SHA-256 before installing.
4. Test on a project/device you can afford to lose.
5. Prefer **signature-anchored** hook locations over hard offsets.
6. If your hook executes code, remember cache coherency and stack limits
   (`06-…`).