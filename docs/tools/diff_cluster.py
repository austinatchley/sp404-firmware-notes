#!/usr/bin/env python3
"""diff_cluster.py - alignment-aware binary diff clustering.

Compares two firmware images (e.g. stock vs. DOOM OS-patched) at fixed
block granularity and clusters the differences into human-readable regions.

What it tells you, and how to read it:

* IDENTICAL blocks   - unchanged regions (usually the vast majority of a
                       vendor image; the DOOM OS patcher leaves 0x0..0x2F6A6
                       completely untouched).
* SUBSTITUTION blocks - a block at the same offset differs from stock. This
                        is an in-place edit (a hook, a patched table entry).
* MOVED blocks        - a block that differs at its current offset but is
                        byte-identical to a block somewhere else in the
                        stock image. This is a *relocated* region (code or
                        table copied to a new home), not new code.
* NOVEL blocks        - a block that differs at its offset and does not
                        exist anywhere in the stock image. This is new
                        content: injected code, new strings, new data.

Clusters are formed by merging changed blocks that are within --gap blocks
of each other, so one logical edit region becomes one cluster even if it
contains small islands of unchanged bytes.

Output modes:
  text   (default) human-readable report
  --json writes a machine-readable report for downstream tooling
  --blocks  prints every changed block, one per line

Example:
  python3 diff_cluster.py stock.bin patched.bin --block 16 --gap 4
  python3 diff_cluster.py stock.bin patched.bin --json out.json

Written for the SP-404MK2 custom-firmware learning notes. Standard library
only. Run on any two binaries, not just the SP.
"""

import argparse
import hashlib
import json
import os
import sys


def read_block(data, off, size):
    return data[off : off + size]


def block_hash(block):
    return hashlib.sha256(block).digest()


def classify_blocks(old, new, bsize):
    """Return per-block classifications: (changed, n_old_blocks, n_new_blocks).

    Blocks at the same offset that differ are 'moved' (the bytes exist
    elsewhere in the stock image, i.e. relocated) or 'novel' (new content).
    Any new-image blocks beyond the stock length are always 'novel'.
    """
    n_old = len(old) // bsize
    n_new = len(new) // bsize

    # Hash every stock block and index by digest for O(1) moved-detection.
    stock_hashes = {}
    for i in range(n_old):
        stock_hashes.setdefault(block_hash(old[i * bsize : (i + 1) * bsize]), []).append(i)

    changed = []
    for i in range(n_old):
        o = read_block(old, i * bsize, bsize)
        h = read_block(new, i * bsize, bsize)
        if o == h:
            continue
        kind = "moved" if block_hash(h) in stock_hashes else "novel"
        changed.append((i, kind))
    for i in range(n_old, n_new):
        changed.append((i, "novel"))
    return changed, n_old, n_new


def cluster_changed(changed, bsize, gap):
    """Merge changed blocks that are within `gap` blocks of each other."""
    clusters = []
    for idx, kind in changed:
        if clusters and idx - clusters[-1]["end_block"] <= gap:
            c = clusters[-1]
            c["end_block"] = idx
            c["counts"][kind] = c["counts"].get(kind, 0) + 1
        else:
            clusters.append(
                {
                    "start_block": idx,
                    "end_block": idx,
                    "counts": {kind: 1},
                }
            )
    for c in clusters:
        c["start"] = c["start_block"] * bsize
        c["end"] = (c["end_block"] + 1) * bsize
        c["length"] = c["end"] - c["start"]
    return clusters


def fmt_hex(v):
    return f"0x{v:08X}"


def render_cluster(c, bsize, old, new):
    total = sum(c["counts"].values())
    moved = c["counts"].get("moved", 0)
    novel = c["counts"].get("novel", 0)
    kinds = " ".join(f"{k}={v}" for k, v in sorted(c["counts"].items()))
    sim = (total - novel) / total if total else 0.0
    head = (
        f"[{fmt_hex(c['start'])} - {fmt_hex(c['end'])}]  "
        f"len {c['length']:>8}  blocks {total:>4}  {kinds}  sim {sim:.2f}"
    )
    yield head
    # Show the first few changed bytes of the cluster in both images.
    shown = 0
    for b in range(c["start_block"], c["end_block"] + 1):
        o = read_block(old, b * bsize, bsize)
        h = read_block(new, b * bsize, bsize)
        if o == h or shown >= 4:
            continue
        shown += 1
        yield f"    @ {fmt_hex(b * bsize)}"
        yield f"      stock   : {o.hex(' ')}"
        yield f"      patched : {h.hex(' ')}"


def main():
    ap = argparse.ArgumentParser(description="alignment-aware binary diff clustering")
    ap.add_argument("old", help="stock firmware image")
    ap.add_argument("new", help="patched firmware image")
    ap.add_argument("--block", type=int, default=16, help="block size in bytes (default 16)")
    ap.add_argument("--gap", type=int, default=4, help="merge changed blocks within this many blocks (default 4)")
    ap.add_argument("--json", metavar="FILE", help="also write a JSON report to FILE")
    ap.add_argument("--blocks", action="store_true", help="print every changed block")
    args = ap.parse_args()

    with open(args.old, "rb") as f:
        old = f.read()
    with open(args.new, "rb") as f:
        new = f.read()

    bsize = args.block
    if bsize < 1 or bsize % 2:
        ap.error("--block must be a positive even number of bytes")

    changed, n_old_blocks, n_new_blocks = classify_blocks(old, new, bsize)
    clusters = cluster_changed(changed, bsize, args.gap)

    total_changed = len(changed)
    total_moved = sum(1 for _, k in changed if k == "moved")
    total_novel = total_changed - total_moved
    pct = 100.0 * total_changed / n_old_blocks if n_old_blocks else 0.0

    out = []
    out.append(f"old : {args.old}  ({len(old)} bytes)")
    out.append(f"new : {args.new}  ({len(new)} bytes)")
    out.append(f"size delta: {len(new) - len(old):+d} bytes")
    out.append(
        f"blocks: {n_old_blocks} stock / {n_new_blocks} patched of {bsize} bytes, "
        f"{total_changed} changed ({pct:.2f}%), "
        f"{total_moved} moved, {total_novel} novel"
    )
    out.append(f"clusters: {len(clusters)}")
    out.append("")
    out.append("legend: moved = bytes that exist elsewhere in stock (relocated),")
    out.append("        novel = bytes that appear nowhere in stock (new code/data),")
    out.append("        sim = fraction of cluster blocks that are not novel")
    out.append("")

    for i, c in enumerate(clusters, 1):
        out.append(f"--- cluster {i} ---")
        out.extend(render_cluster(c, bsize, old, new))
        out.append("")

    if args.blocks:
        out.append("--- changed blocks ---")
        for idx, kind in changed:
            out.append(f"{fmt_hex(idx * bsize)}  {kind}")

    text = "\n".join(out)
    print(text)

    if args.json:
        report = {
            "old": {"path": args.old, "size": len(old)},
            "new": {"path": args.new, "size": len(new)},
            "block_size": bsize,
            "gap_blocks": args.gap,
            "total_blocks": n_old_blocks,
            "changed_blocks": total_changed,
            "moved_blocks": total_moved,
            "novel_blocks": total_novel,
            "size_delta": len(new) - len(old),
            "clusters": [
                {
                    "start": c["start"],
                    "end": c["end"],
                    "length": c["length"],
                    "start_hex": fmt_hex(c["start"]),
                    "end_hex": fmt_hex(c["end"]),
                    "counts": c["counts"],
                }
                for c in clusters
            ],
        }
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"json report written to {args.json}")


if __name__ == "__main__":
    main()