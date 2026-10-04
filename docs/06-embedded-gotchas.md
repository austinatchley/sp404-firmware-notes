# 06 — Embedded gotchas for in-firmware code

The difference between "works in Ghidra" and "works on the device". Labels:
**[PRACTICE]** standard embedded practice, **[FACT]** verified, **[GUESS]**
inference about the SP specifically.

## 1. Execution contexts: you are a guest in someone else's scheduler

The SP runs a vendor RTOS (community-identified as µT-Kernel, a TRON-family
kernel, https://www.tron.org/ — **[GUESS, community]**). Your hooked code executes
in one of several contexts, and context determines almost everything you may do:

| Context | Runs | What it may touch | What it must NOT do |
|---|---|---|---|
| Task (sequencer, UI) | cooperative/preemptive task | own task data, IPC, filesystem, display | block on a long lock, sleep inside audio |
| Audio/ISR context | high-priority interrupt or audio task | DSP buffers, ring buffers, audio flags | allocate, lock, do filesystem I/O, call slow syscalls |
| Boot/init path | before the scheduler is up | hardware init registers | assume the RTOS is running |

**[GUESS]** On this class of device the audio path is an ISR or a high-priority
task at sample rate (48 kHz); a hook that does a `printf`-style loop inside it
will glitch audio at best and livelock at worst.

**Rules **[PRACTICE]**:*
- Identify the context your hook runs in *before* writing it. If a function is
  called from both the UI task and the audio task, either hook only the UI entry
  or make your code context-safe (atomic flags, no blocking).
- Keep ISR/audio hooks to O(1) work: set a flag, push to a small lock-free ring,
  let a task do the heavy lifting.
- Don't call RTOS APIs you haven't verified are safe from that context. If you
  see `tk_dly_tsk` (µT-Kernel delay) anywhere near your hook, you're in task
  context.

## 2. Concurrency with the sequencer engine

DOOM OS reads/writes *live pattern data* from its own screens while the sequencer
is playing **[FACT]** (that's the whole product). The danger pattern:
- You read a pattern structure, the sequencer advances mid-read → torn state.
- You write a note, the sequencer reads it before your write completes.

**Mitigations [PRACTICE]:**
- Find the sequencer's **critical section / lock** (or its "engine is stopped"
  flag) and do pattern mutations under it, or only when transport is stopped.
- Observe how DOOM OS does it by diffing (see `05-…`): the regular-stride table
  edits around `0x23E8C0..0x24E000` are per-voice/per-step state **[FACT, inferred
  from record pattern]** — learn which lock surrounds them from the surrounding
  stock code.
- Copy-on-write for anything you render (render from a snapshot, mutate a shadow
  copy).

## 3. Stack and heap limits

- **Stack:** embedded stacks are small (a few KB per task is typical). Your hook
  adds frames to whatever stack it runs on. Don't allocate big buffers on the
  stack; keep recursion out.
- **Heap:** use the OS's own allocator (Magic Lantern's lesson:
  allocate with Canon's pool wrappers, not a private arena — `02-…`). If the SP is
  an i.MX RT-class chip, RAM is ~1 MB total and shared between everything
  **[GUESS, community chip theory]**; be frugal.
- **Fragmentation:** if you allocate often (e.g. per-screen), allocate once at
  init and reuse buffers.

## 4. Cache coherency (self-modifying code)

If the chip is a Cortex-M7 (per the community theory **[GUESS]**), it has a
Harvard architecture with separate I-cache and D-cache, and the firmware likely
runs XIP from external QSPI flash. Two failure modes:

1. **You patch a flash-resident function** (your trampoline writes the flash
   image, which the CPU then executes from cache): the I-cache may still hold the
   old instructions. On Cortex-M7 the standard fix is to invalidate the
   instruction cache (`SCB->ICIALLU` / `__DSB(); __ISB();`) after self-modifying
   code, or use `__clear_cache()` on GCC/Clang **[PRACTICE]**.
   - **Practical implication:** DOOM OS's trampolines are small and pre-built;
   if you generate code at runtime instead, you own the cache flush.
2. **DMA vs cache** (SD reads, codec data): if the vendor's file/driver code uses
   DMA into buffers you also touch from the CPU, use cacheable-vs-DMA carefully —
   Magic Lantern's `alloc_dma_memory` exists precisely for this.
   https://magiclantern.fandom.com/wiki/Extending_Magic_Lantern

**The safest design [PRACTICE]:** don't write executable code at runtime at all.
Splice your payload into the *image* at build/patch time (like DOOM OS does) and
let the device boot from the modified flash; the cache is coherent because the
data never changes while the CPU runs. Save runtime codegen for a later stage.

## 5. Filesystem safety

The SP reads/writes projects on internal storage and SD. The classic embedded
corruption vector is a power cut mid-write leaving a half-written file. This is
exactly what DOOM OS hardened: "Safer saving: a pattern is written to a new file
first, and the old file is only removed once the new one is complete"
**[FACT]** (https://github.com/klangfeld-labs/doom-os).

**Rules [PRACTICE]:**
- **write-new-then-rename** (atomic replace) instead of overwrite-in-place.
- **fsync/commit before rename**; delete the old file *after* the new one is
  fully durable.
- Never trust that a "close" in a foreign codebase flushes; if you use the
  vendor's own file API, confirm its write/close semantics.
- If your code writes pattern/project data, write through the **vendor's save
  path** if you can find it (diff for it), so you inherit its locking and flush
  behavior.

## 6. Flash endurance and the updater

- Each re-flash rewrites the APP1 region. NOR/QSPI flash endurance is typically
  ~100k erase cycles; do not treat the device as a dev board you reflash
  thousands of times without thought. Batch experiments: flash once, run many
  tests, then flash again **[PRACTICE]**.
- The updater presumably erases and rewrites whole regions, so partial writes
  are only a risk if *you* patch an image that passes the updater but faults at
  boot — that's a boot-loop, not a wear problem. Recovery is always
  "re-flash stock" (see `01-…`) **[FACT]**.

## 7. Timing and the display

- Display draws happen on a refresh loop; drawing from a random task can tear or
  fight the refresh. Hook the **screen table / draw path** (DOOM OS's `SCRTBL`)
  and render through it rather than poking the display controller directly
  **[GUESS, informed by the named tables]**.
- Long operations (filesystem, formatting) must not run in the draw or audio
  path; defer them to a work task.

## 8. Debugging without a debugger

- No known debug port (see `01-…`) **[FACT]**. Your debug channels: the display
  (draw debug text), USB (host-side sniffing), and the *brick-and-recover* loop
  (flash a suspect build, observe, re-flash stock). Budget for slow iteration.
- Add a "panic renderer" early: a function that draws a string + number and is
  called from your hook's failure paths, so a fault in your code produces a
  readable screen instead of a mystery freeze.

## Checklist before flashing any hook

- [ ] Runs in the intended context; no blocking/alloc/lock in ISR/audio path
- [ ] Cache handling done if codegen is runtime (or: avoid runtime codegen)
- [ ] Allocates from the OS pool, not private arenas, and bounded
- [ ] Filesystem writes are write-then-rename with commit-before-rename
- [ ] Stock APP1 on a spare SD card; full project backup taken
- [ ] Output SHA-256 verified against expectation before install