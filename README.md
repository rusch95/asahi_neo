# asahi_neo

Experimental feasibility study: booting Linux on MacBook Neo (A18 Pro) via an XNU Shim.

> **Status: Pre-boot research phase.** Nothing runs yet. See PLAN.md.

## The Problem

The A18 Pro (and M4) introduced SPTM — Secure Page Table Monitor — which runs at a
higher privilege level (GXF EL2) than the OS kernel. Unlike M1/M2/M3 where m1n1 can
directly chainload Linux, on A18 Pro/M4 the page table infrastructure is owned by SPTM
and must be initialized by XNU before anything else can run. You cannot bypass it.

## The Approach: XNU Shim

```
iBoot (Permissive Security)
    └─► minimal XNU stub
            └─► SPTM initialization (via normal XNU startup path)
                    └─► XNU Shim intercepts control
                            └─► maps Linux kernel into SPTM-managed memory
                                    └─► transfers execution to Linux entry point
```

The shim rides inside a stripped-down XNU kernelcache. XNU does just enough to satisfy
SPTM's init requirements, then the shim hijacks the remaining startup path to hand off
to Linux. Linux must be compiled with awareness that page tables are SPTM-owned.

## Goals

| # | Goal | Status |
|---|------|--------|
| 1 | Boot to UART terminal | Research |
| 2 | Boot to software framebuffer | Not started |
| 3 | Hardware GPU via AGX | Not started |

## Hardware Target

- MacBook Neo with A18 Pro SoC
- Reference: M4 MacBook Pro (same SPTM generation, similar fabric)
- Development via tethered USB/UART using m1n1 hypervisor where possible

## Non-Goals

- This is not an Asahi Linux port. It does not produce upstreamable patches.
- No jailbreaking. No altering macOS Full Security containers.
- No support promises.

## Getting Started

See PLAN.md for immediate next steps and CLAUDE.md for project conventions.
