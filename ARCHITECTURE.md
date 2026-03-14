# ARCHITECTURE.md — XNU Shim Boot Design

Last updated: 2026-03-14

## Overview

On A18 Pro (and M4), Apple's SPTM (Secure Page Table Monitor) runs at GXF EL2 —
a privilege level above the OS kernel (EL1) but below the hypervisor (EL2 proper).
SPTM owns all page table management; the OS kernel requests mappings through it rather
than writing page tables directly. This breaks the assumption all prior Apple Silicon
Linux ports make (direct EL1 page table control).

The XNU Shim exploits the fact that iBoot + XNU can legitimately initialize SPTM.
We let them do so, intercept at the last safe moment, and pivot to Linux.

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

```
EL3     — Secure Monitor (Apple firmware, immutable)
GXF EL2 — SPTM (Guarded Execution Feature, page table owner)
EL2     — Available for hypervisor (m1n1 uses this in dev)
EL1     — OS kernel (XNU or Linux)
EL0     — Userspace
```

GXF is Apple's name for a hardware feature that inserts an additional privilege domain.
Transitions to GXF EL2 happen via `genter` / `gexit` instructions. SPTM exposes a
call table; the OS calls into it for all page table mutations.

**Implication for Linux:** Linux's `__cpu_setup` and `paging_init` paths must be patched
or wrapped to call through the SPTM interface rather than writing TTBR0/TTBR1 directly.
Alternatively, the shim can set up a thin compatibility layer that traps Linux page table
writes and forwards them to SPTM — but this is heavyweight.

**Preferred approach:** Modify Linux's ARM64 mm init to call a small SPTM shim layer
for initial mapping setup, then hand SPTM a "trusted kernel" designation so subsequent
page table ops work normally. Whether SPTM supports this trust handoff is TBD — see
docs/SPTM_FINDINGS.md.

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
Run XNU under m1n1's EL2 hypervisor. Use hypervisor hooks to intercept the
GXF→EL1 transition after SPTM init, then replace XNU's EL1 context with Linux.
Cleanest for research/debugging; not suitable for standalone boots.

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
4. Are GXF `genter`/`gexit` encodings the same on A18 Pro as M4?
5. Does A18 Pro DRAM layout differ significantly from M4?

All answers go in docs/SPTM_FINDINGS.md as discovered.
