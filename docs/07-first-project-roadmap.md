# 07 — First-project roadmap: from "hello world" to a working mod

A staged plan where every stage is independently recoverable. The design rule:
**never ship a change whose only possible outcome is a brick** — because every
APP1-level change can be undone by re-flashing stock through the updater, the only
unrecoverable thing is touching APP0 or the boot block (see `01-…`).

**Global invariants for every stage:**
- Work on a **copy** of `SP404MKII_APP1.bin` (5.52). Verify `sha256sum` equals
  `4a3d67711e14dcc97d50249a4eee7dd6df0251a2f37757cbbe2556c233730d80` before you
  start and after you finish.
- Keep a stock `SP404MKII_APP1.bin` on a spare SD card **in the same folder
  structure Roland's updater expects**, and a full backup of any projects.
- Know the recovery flow by heart: hold **SHIFT** + power on → UPDATER menu →
  install stock file. Test it once *before* you write any code
  (re-flash stock now, so the muscle memory and card are proven).
- Do not modify anything below `0x2F6A6`, and never modify APP0.
- Prefer signature-anchored hooks (find a routine by pattern, patch its offset).

---

## Stage 0 — Baseline and tooling (safe, no flashing)

**Goal:** a repeatable pipeline and a map of the device's observable behavior.

- Download Roland 5.52, unzip, verify the APP0/APP1 filenames and hashes.
- Run `04-…` Stages 0–1 triage on your own copy: `binwalk`, `ent`, `strings`,
  vector-table hunt, base-address guess, Ghidra import.
- Diff a **DOOM OS-patched** image against stock with `tools/diff_cluster.py`
  (`05-…`) and bookmark the clusters (esp. `0x2F6A6`, `0x5C380`, the
  `0x23E8C0..0x24E000` tables, and the tail) — these are your "known-good hook
  examples" from a working project.
- Black-box the updater: confirm stock re-flash works; try a *renamed* file and an
  *odd-size* file on a sacrificial device if you have one, to learn what the
  updater validates (see `open-questions.md`).

**Risk:** none (no flashing). **Recovery:** n/a.

## Stage 1 — Hello world on the display

**Goal:** draw your own text on the screen, proving you can execute code.

- Find a **display text-draw routine**: in Ghidra, pick a visible UI string →
  xref → walk the draw path. Confirm the routine by comparing with the DOOM OS
  clusters near that string (they patched the same neighborhood).
- Write a **trampoline** (`03-…`): a tiny Thumb-2 `MOVW/MOVT + BX` redirect into a
  cave (find a zero/0xFF padding region — `binwalk -E` low-entropy runs), where a
  payload calls the draw routine with your string, then `BX LR`.
- Assemble the bytes with a cross-assembler (arm-none-eabi-as or an online
  assembler), splice into a copy of the image, verify size/prefix unchanged,
  SHA-256 the result (it will *not* match DOOM OS — that's fine, you're not
  shipping it yet).
- Flash via the updater. Success = your string on screen. Re-flash stock
  afterward to confirm revert works.

**Risks & recovery:**
- Wrong draw routine / wrong arg → blank screen or crash → **re-flash stock**.
- Payload runs but draws garbage → wrong call signature → re-flash stock, adjust.
- Cave overlaps real data (caves aren't guaranteed) → weird corruption → re-flash
  stock, pick a different cave.
- **The one thing to avoid:** assuming the display controller is directly
  accessible. Go through the draw path.

## Stage 2 — Input hook

**Goal:** respond to your own pad/key combo.

- Locate the input dispatch: µT-Kernel task reading pads/encoder, or a
  key-event queue. Anchor by signature (`04-…` §6). The DOOM OS `CONTBL`
  (control table) suggests a named control-dispatch table **[GUESS, from named
  tables]** — find it and its handler dispatch.
- Hook the dispatch: on a chosen event, call your Stage 1 draw, then fall through
  to the stock handler (or swallow the event).

**Risks & recovery:**
- Swallowing a needed event → buttons stop working → re-flash stock (or patch the
  swallow to be key-specific).
- Hook in the wrong context (ISR vs task) → hangs → re-flash stock.
- Event codes are per-firmware → version fragility; keep a stubs/consts table
  (`02-…` lesson).

## Stage 3 — Your own screen

**Goal:** a full custom screen (not just an overlay).

- Understand the screen system: DOOM OS's rebuilt tail *registers* new screens via
  a table whose header lists `SCRTBL` (screen table), `SYSTAB`, `SYSSTR`,
  `CONTBL`, `BOOTANI` **[FACT]**. In the stock image, find the screen-dispatch
  (each screen ID → init/handle/redraw functions).
- Two approaches **[PRACTICE]**: (a) *reuse* an existing screen slot you don't
  care about (simpler), or (b) *register* a new slot (needs the table format +
  free entry space — what DOOM OS did). Do (a) first.
- Render your own content, wire a "back/exit" combo, ensure state is clean on
  entry/exit (no leaked locks, no half-set mode).

**Risks & recovery:**
- Screen state machine confusion → frozen UI, updater still reachable via
  SHIFT+power → re-flash stock.
- Memory for your buffers from wrong pool → heap corruption → re-flash stock;
  use the OS allocator (`06-…`).
- Leaving an audio/lock held on exit → device misbehaves later → re-flash stock.

## Stage 4 — Read pattern data

**Goal:** display live pattern/step data (read-only).

- Use the DOOM OS diff to find the **per-voice/per-step tables** (regular-stride
  edits `0x188/0xC8/0x190` at `0x23E8C0..0x24E000`) **[FACT, inferred]**; these are
  probably the same structures your screen wants to read.
- Cross-check against the sequencer: find the playhead/transport state, confirm
  your read is coherent (lock or stopped-state guard, `06-…` §2).
- Render: for the playing pattern, show steps/pads on your Stage 3 screen.

**Risks & recovery:** read-only → low. Wrong structure interpretation just shows
garbage. No flash risk. (Still test on a throwaway project.)

## Stage 5 — Write pattern data

**Goal:** edit steps from your screen (mute, note on/off), saved safely.

- Mutate pattern state under the sequencer's lock or when stopped
  (`06-…` §2). Re-render from your snapshot.
- Persistence: **write-new-then-rename** like DOOM OS's "Safer saving"
  **[FACT]** — write a new file, commit, then remove the old. Or reuse the
  vendor's save path.
- Backup your projects before any write-path testing; test save/reload/rename
  on a sacrificial project.

**Risks & recovery:**
- Corrupted pattern data on disk → restore backup, re-flash stock to clear
  any in-RAM state.
- Lockup during save → re-flash stock; projects may be at risk if your save path
  is bad → that's why backups and the atomic-rename discipline exist.
- Undo semantics: DOOM OS offers 12-step undo **[FACT]**; if you implement undo,
  snapshot before mutations.

## Stage 6 — Distribution (only when you're stable)

- Build a **patcher, not a binary** (legal + `00-…`, `03-…`): a `DOOMPTCH`-style
  container (stock SHA-256 in, `(offset,len,where)` records out) applied by a
  script or browser page; or IPS/BPS for pure byte edits.
- Publish: patcher JS + `checksums.txt` + README, no firmware.
- Per-version policy: one stubs/consts table per firmware; refuse unknown digests
  with a clear message (DOOM OS's model **[FACT]**).

## Overall risk map

| Stage | Flashing risk | Data risk | Rollback |
|---|---|---|---|
| 0 | none | none | — |
| 1 | medium (screen/blank) | none | re-flash stock |
| 2 | medium (hang) | none | re-flash stock |
| 3 | medium (UI freeze) | none | re-flash stock |
| 4 | low | none | — |
| 5 | low | **medium** (user data) | backup restore + re-flash |
| 6 | n/a | n/a | ship a revert path (re-flash stock) |

**Golden rule:** the moment a flash seems unrecoverable (updater won't come up,
display dead even in updater), stop, verify you haven't touched APP0, and
re-check the basics before doing anything heroic. On this device the
documented and proven recovery path is stock re-flash — rely on it.