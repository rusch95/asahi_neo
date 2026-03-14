# PLAN.md — Action Items

Last updated: 2026-03-14

## Current Focus: Phase 0 — Research & Environment

---

## Phase 0: Research & Environment Setup

### 0.1 SPTM / GXF Reverse Engineering
- [ ] Read Steffin/Classen paper in full; annotate key findings into docs/SPTM_FINDINGS.md
- [ ] Extract SPTM firmware blob from A18 Pro / M4 iBoot chain
- [ ] Map SPTM call table: identify init, map, unmap, perm-change entry points
- [ ] Document GXF EL2 privilege model — what the OS kernel can/cannot do to page tables
- [ ] Determine SPTM state machine: what XNU must call before SPTM is "ready"
- [ ] Check whether M4 Asahi work has already reversed any of this (see AsahiLinux/linux M4 branch)

### 0.2 XNU Kernelcache Analysis
- [ ] Pull M4 / A18 Pro XNU kernelcache from recoveryOS or IPSW
- [ ] Identify the exact SPTM init call sequence in XNU startup (osfmk/arm/cpu.c et al.)
- [ ] Find the earliest point after SPTM init where we can safely intercept control
- [ ] Determine minimum kexts / startup extensions required for SPTM to succeed

### 0.3 m1n1 / Toolchain Setup
- [ ] Build m1n1 from source targeting M4 (closest available proxy for A18 Pro)
- [ ] Confirm tethered boot works over USB-C UART on target hardware
- [ ] Set up ARM64 cross-compilation toolchain (clang + lld)
- [ ] Set up Python proxyclient environment for m1n1 scripting
- [ ] Write scripts/probe_sptm.py — use m1n1 hypervisor to observe SPTM calls during XNU boot

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
