# ARCHITECTURE.md — XNU Shim Boot Design

Last updated: 2026-03-14

## Overview

### Critical Discovery (2026-03-14)

We are developing **on** the target hardware (MacBook Neo, A18 Pro, t8140).
Scanning the running macOS 26 kernelcache revealed: **macOS on A18 Pro uses PPL,
not SPTM**. Zero `genter` instructions exist in the entire macOS kernel. SPTM is
activated by iBoot only for iOS kernelcaches; macOS continues to use PPL.

This opens two distinct boot paths:

**Path A — macOS/PPL (primary for Phase 1):**
Boot a macOS-style custom kernelcache. iBoot likely won't activate SPTM. The PPL
challenge is well-understood by Asahi Linux (M1/M2/M3). This is the lower-risk path
to a first terminal boot.

**Path B — iOS/SPTM (research path):**
Boot an iOS-style XNU kernelcache that activates SPTM. Requires the full SPTM shim
architecture. Higher difficulty, but necessary to understand the long-term A18 Pro
security model and for any future hardened Linux deployment.

---

On A18 Pro, Apple's SPTM (Secure Page Table Monitor) runs at GL2 — a **lateral**
hardware privilege domain implemented via GXF (Guarded Execution Feature). SPTM is
separate firmware loaded by iBoot before the kernel. GL2 is not "above EL2"; it is
a separate trust dimension enforced by SPRR. SPTM code pages are executable only in
GL2, so EL1 kernel exploits cannot touch page tables directly.

PPL (Page Protection Layer) — the M1/M2/M3 predecessor — also runs at GL2 but is
embedded in the XNU kernelcache itself, not separate firmware.

The XNU Shim exploits the fact that iBoot + XNU can legitimately initialize whichever
security mechanism is active (PPL or SPTM). We let that initialization complete,
intercept at the last safe moment, and pivot to Linux.

---

## Boot Chain

```
SecureROM
  └─► iBoot stage 1 (NOR flash)
        └─► iBoot stage 2 (SSD, APFS Preboot)
              └─► kernelcache (Permissive Security, non-Apple-signed)
                    ├─► [XNU startup] cpu_machine_init → SPTM init calls
                    ├─► [XNU startup] arm_init → MMU enable via SPTM
                    └─► [SHIM INTERCEPT] → Linux loader → Linux entry
```

iBoot hands off via the MachO Boot Protocol. The kernelcache we sign for Permissive
Security contains a stripped XNU + our shim object linked in.

---

## Privilege Levels on A18 Pro / M4

GXF adds a LATERAL dimension (GL0/GL1/GL2) orthogonal to the ARM EL hierarchy.
Each EL can have a corresponding GL, enforced by SPRR remapping page permissions.

```
ARM EL levels:          GXF lateral domains (SPRR-enforced):

EL3  Secure Monitor     (no GXF interaction)
EL2  Hypervisor ──────► GL2  SPTM  (page table owner, reached via genter from EL1/EL2)
EL1  OS kernel  ──────► GL1  TXM   (code signing / entitlements)
EL0  Userspace          GL0  (unused currently)
```

- `genter` (encoding: `0x00201420`) — transitions current EL into its GL counterpart
- `gexit`  (encoding: `0x00201400`) — returns from GL to the calling EL
- SPRR makes SPTM code pages executable ONLY in GL2; EL1 cannot execute them
- The OS kernel calls SPTM for every page table mutation via `genter` → GL2 → `gexit`

**Key registers (from m1n1 source / Sven Peter blog):**
- `SYS_IMP_APL_SPRR_CONFIG_EL1` (`S3_6_C15_C1_0`) — enable SPRR
- `SYS_IMP_APL_GXF_CONFIG_EL1`  (`S3_6_C15_C1_2`) — enable GXF
- `SYS_IMP_APL_GXF_ENTER_EL1`   (`S3_6_C15_C8_1`) — GL2 entry point address
- `SYS_IMP_APL_GXF_STATUS_EL1`  — GXF active status

**SPRR permission table:** 64-bit register encoding 16 4-bit nibbles, each mapping
one page table permission class to separate EL/GL access rights. SPTM sets this
table to prevent EL1 from creating writable+executable mappings in its own domain.

**SPTM call ABI (from Steffin/Classen paper):** Calls use the `genter` instruction
with `x16` holding a packed dispatch descriptor (domain | table_id | endpoint_id).
`x0–x7` are arguments. Key calls our shim must make:
- `sptm_retype(phys, FREE, XNU_DEFAULT, ...)` — claim Linux pages
- `sptm_retype(phys, FREE, XNU_PAGE_TABLE, ...)` — claim page table pages
- `sptm_map_page(ttep, va, pte)` — build Linux address space

**No SPTM watchdog:** After handoff, SPTM is passive. Linux won't be killed.

**Capability model:** SPTM has no per-call XNU identity check. Whoever registers
dispatch tables during `init_xnu_ro_data` controls those domains. Our shim runs
after this window — we call SPTM using XNU domain credentials already registered.
See docs/SPTM_FINDINGS.md for full ABI details.

---

## Memory Layout at Shim Intercept

```
Physical address space (approximate, to be verified via ADT dump):

0x0_0000_0000  — I/O / peripheral registers (ARM topology)
0x0_8000_0000  — DRAM start (typical on A18 Pro; verify)
  [iBoot data]
  [XNU kernelcache + shim]  ← we are here at intercept
  [SPTM region]             ← mapped and owned by SPTM, do not touch
  [Linux kernel image]      ← loaded here by shim
  [Linux initramfs]
  [Device tree blob]
0x2_0000_0000  — DRAM end (estimate; actual size from ADT memory node)
```

Exact addresses must be extracted from a live ADT dump via m1n1 proxyclient.

---

## Shim Intercept Strategy

**Option A — Entry hook (preferred for Phase 1):**
Link shim into kernelcache as a kext. Override `IOPlatformExpert::start()` or an
equivalent early-userspace hook. By this point SPTM is fully initialized. Shim
reads a "linux payload" from a known offset in the Preboot partition, maps it
via SPTM calls, and jumps.

**Option B — XNU startup patch:**
Patch `arm_init()` directly. Higher risk of breaking SPTM init sequence.
Reserve for if Option A proves too late in the boot (e.g., SPTM needs kernel
cooperation after this point).

**Option C — m1n1 hypervisor mediation:**
Run XNU under m1n1's EL2 hypervisor. m1n1 has native GXF support (`src/gxf.c`,
`src/gxf_asm.S`) and can call into GL2 itself via `gl2_call()`. Use hypervisor
hooks to log all `genter` calls during XNU boot (maps call sequence), then intercept
the GL2→EL1 `gexit` after SPTM init completes and replace XNU's EL1 context with
Linux. Cleanest for research/debugging; not suitable for standalone boots.

---

## Linux Entry Requirements

Linux ARM64 expects on entry to `__primary_switch` (or the new `primary_entry`):
- CPU in EL1 (or EL2 if HCR_EL2.E2H set)
- MMU off (or SPTM-managed identity map)
- x0 = physical address of FDT
- x21 = physical address of kernel text (for KASLR)
- All other cores in WFE spin loop

On SPTM hardware, "MMU off" is complicated — SPTM may require the MMU to remain
configured through it. This is the primary open question. See docs/SPTM_FINDINGS.md.

---

## Device Tree Strategy

We build a minimal FDT from scratch using:
1. ADT → FDT conversion (m1n1 does this for M-series; extend for A18 Pro)
2. Add only nodes needed for Phase 1: serial UART, interrupt controller (AIC), timer
3. Grow the DT incrementally as more drivers are brought up

Reference: AsahiLinux/linux arch/arm64/boot/dts/apple/ for M4 DT as a template.

---

## Open Questions

1. Can SPTM accept a "handoff" to a non-XNU kernel, or does it enforce XNU identity?
2. What is the minimum SPTM call sequence XNU must complete before we can intercept?
3. Does SPTM have a watchdog that kills EL1 if certain heartbeat calls stop?
4. ~~Are GXF `genter`/`gexit` encodings the same on A18 Pro as M4?~~
   **ANSWERED:** Yes. `genter=0x00201420`, `gexit=0x00201400` — confirmed from m1n1
   source (`gxf_asm.S`) and Sven Peter's public reverse-engineering. Encodings are
   stable across A16/M3/M4/A18 Pro generations.
5. Does A18 Pro DRAM layout differ significantly from M4?
6. Does SPTM on A18 Pro use the same call ABI as M4? (Assume yes; verify via blob diff)
7. Can our shim call `genter` after XNU's SPTM init to request new GL2 mappings for Linux?

All answers go in docs/SPTM_FINDINGS.md as discovered.
