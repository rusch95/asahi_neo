# PLAN.md — Action Items

Last updated: 2026-03-14

## CRITICAL FINDING (2026-03-14)

Developing **on** the target hardware (MacBook Neo, A18 Pro, t8140, macOS 26.3.2).
macOS on A18 Pro uses **PPL**, not SPTM — zero genter instructions in the macOS kernel.
SPTM blobs extracted locally. Two paths in scope:

- **Path A (PPL):** Boot macOS-style kernelcache → iBoot won't activate SPTM →
  follows existing Asahi M3 path. **Primary path for Phase 1.**
- **Path B (SPTM):** Boot iOS-style kernelcache → iBoot activates SPTM → full shim.
  Research path, harder.

Key open question: does iBoot activate SPTM for our custom Permissive Security
kernelcache regardless of OS type? Must verify empirically.

---

## Current Focus: Phase 0 — Research & Environment

---

## Phase 0: Research & Environment Setup

### 0.1 SPTM / GXF Reverse Engineering
- [x] Locate Steffin/Classen paper: arXiv 2510.09272 — downloaded to research/papers/
- [x] Read Steffin/Classen paper in full — key findings in docs/SPTM_FINDINGS.md
- [x] Document GXF privilege model (GL0/GL1/GL2 lateral domains, SPRR, genter/gexit)
- [x] Confirm genter=0x00201420, gexit=0x00201400 from m1n1 gxf_asm.S — VERIFIED
- [x] Confirm SPRR/GXF register names from m1n1 source
- [x] Document SPTM call ABI: x16 dispatch descriptor (domain/table/endpoint), NOT x0
- [x] Document SPTM initialization sequence: gxf_setup_early → gxf_setup_late → init_xnu_ro_data
- [x] Document frame retyping model (63 types, transition rules)
- [x] Confirm: no SPTM watchdog/heartbeat — safe to hand off to Linux post-init
- [x] Confirm: SPTM is capability-based — no per-call cryptographic XNU identity check
- [ ] Read Proteas SPTM notes: https://proteas.github.io/ios/2023/06/09/some-quick-and-discrete-notes-on-sptm.html
- [ ] Read Dataflow Forensics SPTM series: https://www.df-f.com/blog/sptm4
- [ ] Extract SPTM firmware blob from M4 IPSW (use `ipsw` CLI tool)
- [ ] Run scripts/extract_sptm_calls.py against M4 kernelcache to map endpoint IDs
- [ ] Determine minimum XNU SPTM call sequence before safe intercept (empirical, via probe)
- [ ] Check AsahiLinux/linux M4 branch for any SPTM-related kernel patches

### 0.2 XNU Kernelcache Analysis
- [x] Kernelcache located at /System/Library/KernelCollections/BootKernelExtensions.kc (64MB)
- [x] Confirmed: macOS A18 Pro kernel uses PPL, not SPTM (0 genter instructions)
- [x] PPL functions confirmed: pmap_in_ppl, pmap_claim_reserved_ppl_page etc.
- [ ] Disassemble PPL enter/exit mechanism in macOS A18 Pro XNU (what replaces HINT #0x10?)
- [ ] Identify earliest safe intercept point post-PPL-init (Path A)
- [ ] If pursuing Path B: identify SPTM init sequence in iOS XNU (requires iOS kernelcache)
- [ ] Determine minimum kexts required for PPL to complete init (Path A)

### 0.2b Local Hardware Analysis (NEW — we are on target hardware)
- [x] Confirmed chip: A18 Pro, t8140, board Mac17,5
- [x] Confirmed iBoot: 13822.81.10
- [x] Extracted SPTM blobs: sptm.t8140.bin (1.1MB) and sptm.t8132.bin (M4, 1.1MB)
- [x] Diff result: 27.4% byte difference — cannot assume identical ABI
- [x] genter found in SPTM binary at 0x9f8d4 (1 site — SPTM's own init/self-call)
- [ ] Dump ADT via ioreg and convert to FDT (script: dump_adt.py — adapt for macOS ioreg)
- [ ] Run r2/Ghidra structural diff on t8140 vs t8132 SPTM binaries
- [ ] Determine iBoot behavior: does it activate SPTM for non-iOS Permissive boot?
- [ ] Explore PPL call mechanism in macOS A18 Pro — find PPL enter/exit opcodes

### 0.3 m1n1 / Toolchain Setup
- [ ] Build m1n1 from source targeting M4 (closest available proxy for A18 Pro)
- [ ] Confirm tethered boot works over USB-C UART on target hardware
- [ ] Set up ARM64 cross-compilation toolchain (clang + lld)
- [ ] Set up Python proxyclient environment for m1n1 scripting
- [ ] Implement scripts/probe_sptm.py using m1n1's existing gl2_call() / gxf hooks
      (m1n1 has native GXF support in src/gxf.c — we can set GXF_ENTER_EL1 to our
      logging stub before loading XNU as guest, intercept every genter call)
- [ ] Install ipsw CLI tool (https://github.com/blacktop/ipsw) for IPSW extraction

### 0.4 Linux Kernel Baseline
- [ ] Identify which AsahiLinux/linux branch has the most M4 progress
- [ ] Build a minimal ARM64 kernel with CONFIG_APPLE_MACHINE, no AGX, serial console only
- [ ] Confirm it boots under m1n1 hypervisor on M4 hardware (as a sanity check)

---

## Phase 1: Goal 1 — Boot to Terminal

- [ ] Write minimal XNU stub (xnu_shim/stub/) that links against kernelcache
- [ ] Implement shim intercept point post-SPTM-init
- [ ] Implement Linux ELF loader within shim
- [ ] Map Linux kernel image via SPTM calls (read-only + executable pages)
- [ ] Set up Linux boot args struct (FDT / device tree pointer)
- [ ] Write minimal A18 Pro device tree (DT) — serial UART only
- [ ] Transfer execution to Linux `__primary_switch`
- [ ] Milestone: `[    0.000000] Booting Linux on physical CPU 0x0` on UART

### Known Blockers
- SPTM call ABI on A18 Pro not yet documented — depends on 0.1
- Device tree for A18 Pro entirely missing — must be built from scratch using ADT dumps

---

## Phase 2: Goal 2 — Software Framebuffer

- [ ] Identify display controller / DCP registers on A18 Pro (diff against M4 ADT)
- [ ] Add SimpleDRM / efifb node to device tree pointing at iBoot-initialized framebuffer
- [ ] Enable CONFIG_DRM_SIMPLEDRM in kernel config
- [ ] Milestone: Linux boots to console on display (no GPU driver required)

---

## Phase 3: Goal 3 — Hardware GPU (AGX)

- [ ] Study IntegralPilot M3 DOOM patch — understand what AGX init they did outside normal driver path
- [ ] Diff A18 Pro AGX firmware against M4 AGX firmware
- [ ] Check AGX UABI stability between M4 and A18 Pro (tile size, register offsets)
- [ ] Attempt to load asahi-drm with M4 firmware tables on A18 Pro
- [ ] Milestone: glxgears or equivalent running

---

## Parking Lot (Deferred)

- NVMe driver bringup (needed for persistent storage, not needed for goal 1)
- WiFi / BT bringup
- USB host mode
- Power management (cpufreq, idle)
- Upstreaming anything
