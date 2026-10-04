# 05 — Diffing stock vs. patched firmware

The single most effective RE technique for this project: take the stock 5.52
image and a DOOM OS-patched image and diff them. Every cluster of changes is a
hand-drawn map of "these are the hook points, and this is where new code lives."
You get this for free because DOOM OS ships both digests and the patcher
(https://github.com/klangfeld-labs/doom-os/blob/main/checksums.txt).

**Read this guide with `tools/diff_cluster.py` open.** Run it:

```bash
python3 docs/tools/diff_cluster.py stock.bin patched.bin --block 16 --gap 4
python3 docs/tools/diff_cluster.py stock.bin patched.bin --json out.json
```

## The taxonomy: three kinds of change

The script classifies every 16-byte block that differs between the two images:

| Class | Meaning | Typical cause |
|---|---|---|
| `moved` | block is different *here* but byte-identical *somewhere in stock* | a relocated stock routine/table; an insertion that shifted everything after it |
| `novel` | block exists nowhere in stock | genuinely new code/data (the DOOM OS blobs, new strings, trampolines) |
| unchanged | same bytes at same offset | everything you can safely ignore |

Clusters merge changed blocks that are within `--gap` blocks of each other, so
one logical edit region = one cluster even if it has islands of unchanged bytes
inside it.

## Reading the output (worked example)

On synthetic data (a substitution, a novel blob, a *relocated* stock region, and
an appended tail) the tool reports five clusters:

```
--- cluster 4 ---
[0x0002C000 - 0x0002C040]  len       64  blocks    4  moved=4  sim 1.00
    @ 0x0002C000
      stock   : 81 eb 9d f7 56 b1 54 8c f2 81 d8 b3 32 a0 fb 79
      patched : 9b 73 86 f9 d8 50 14 4c d1 12 2d 04 d7 e6 11 12
```

- `moved=4`, `sim 1.00` → these 64 bytes are **stock code copied to a new
  address**. The bytes at `0x2C000` are identical to stock bytes located
  elsewhere (you can find where with `--blocks` + a lookup, or by matching the
  hex). This is what a relocated routine looks like — exactly the DOOM OS
  copy-from-stock records.
- `novel=3`, `sim 0.00` (cluster 2, `0x5000`) → **brand-new content** with no
  stock counterpart: injected code, new strings, new tables.
- The appended tail (`cluster 5`, stock side empty) → an **insertion**; note the
  whole file after an insertion point shows up as `moved` because every block is
  still found in stock, just one slot earlier.
- A `novel` block *surrounded by* unchanged blocks (cluster 1, `0x1000`) is an
  **in-place edit** — the classic tiny trampoline/table patch.

**Reading rule of thumb:**
1. Novel clusters → new code/data. On the DOOM OS image these are the tail blobs
   (`0x287A00+`) and the small trampolines at places like `0x2F6A6`.
2. `moved` clusters → relocated stock content. If a stock table you care about
   disappears from its old offset and shows up `moved` in the tail, you've found
   where DOOM OS re-homed it.
3. Long `unchanged` stretches → the parts of the vendor image you can rely on.

## What the real DOOM OS diff looks like

Decoded from the shipped patcher (see `00-…`), the 5.52 diff is **[FACT]**:

- **No edits below `0x2F6A6`** (header/boot zone untouched).
- Small edits clustered at `0x5C380` (7/9-byte Thumb-2 records at irregular
  strides) — trampoline-style patches.
- Regular-stride edits at `0x23E8C0..0x24E000` with strides `0x188/0xC8/0x190` —
  an **array of fixed-size entries** (per-pad/per-track tables).
- A fully **rebuilt tail `0x287A00..0x2AC750`** containing new code, new strings
  (`DOOM OS`, `DOOMOS`), the named tables, and the end-of-image
  `SPUA/STARTUP/SBMP` block.

Your own `diff_cluster.py` run on the real files should reproduce this shape.
If it shows anything *different* (edits below `0x2F6A6`, or a changed size),
the image isn't the 5.52 pair — stop and re-check your files.

## Alignment-aware deltas

- Use a **block size that is a power of two and ≥4 bytes** (`--block 16` is a good
  default): it tolerates unaligned single-byte edits while still catching
  word-level patterns. `--block 4` for fine detail, `--block 256` for a coarse
  "where is the tail" overview.
- The `--gap` parameter sets how far apart two change sites can be and still merge.
  Default `4` blocks (64 bytes) is good; raise it to merge a whole table region.
- Because the classifier indexes *all* stock blocks by hash, "insertion" and
  "relocation" are detected automatically regardless of alignment — that's the
  alignment-aware property. A naive line-based diff would report the entire file
  after an insertion as changed.

## Function matching (finding "what is this new code, really")

Clusters tell you *where*; these tools tell you *what function the patched region
corresponds to* in stock — i.e. which routine DOOM OS hooked:

- **Ghidra Version Tracking** (Tools → Version Tracking): import the same image as
  stock and patched, auto-match functions, focus on the "changed" matches near
  your clusters. https://github.com/NationalSecurityAgency/ghidra
- **Diaphora** (IDA/Ghidra diff plugin, https://github.com/juxingzhen/diaphora):
  matches functions by graph/bytes/mnemonics; great for "the function at
  `0x1234` in stock became the function at `0x2A600` in patched".
- **radare2**: `r2 -2c 'aaa; s 0x...; pdf' stock.bin` and `radiff2 -C -A stock.bin
  patched.bin` gives a similarity-per-function diff from the command line.
  https://github.com/radareorg/radare2

**Practical workflow:**
1. `diff_cluster.py` → list of interesting offsets.
2. Load both images in Ghidra (same base address).
3. Version Tracking over the region `0x0..0x2F6A6` + the middle bands (the parts
   of the image that are still stock-ish).
4. For each "changed" matched function, look at *its* callers — the caller that
   jumps into the tail is the hook site.
5. Diaphora over the tail region to name the relocated stock functions.

## Reusable script notes

`tools/diff_cluster.py` is stdlib-only (hashlib, argparse, json). Options:
`--block`, `--gap`, `--json FILE`, `--blocks`. JSON output includes per-cluster
`start/end/length` (hex and decimal), block counts, and the moved/novel
breakdown — feed it to a script that turns cluster offsets into Ghidra bookmarks
or a patch-container generator.

Limitations: it does not do sub-block (byte) precision reporting (the block is the
unit), and "moved" detection is exact-bytes-only — a relocated block that was also
modified reads as `novel`. That's fine for triage; function matchers cover the
"moved *and* modified" case.