# SPTM_FINDINGS.md — Secure Page Table Monitor Research Log

Last updated: 2026-03-14

This is a living document. Every finding — including dead ends — gets recorded here.
Do not clean up "wrong" entries; mark them INVALIDATED and note why.

---

## Background: What is SPTM?

SPTM (Secure Page Table Monitor) is Apple's firmware component introduced with the
A16 Bionic (iPhone 14 Pro) and carried forward into M3, M4, and A18 Pro. It runs
at GXF EL2 — a hardware-enforced privilege level above the OS kernel, implemented
via Apple's Guarded Execution Feature (GXF).

**Primary function:** SPTM owns all page table management for the OS kernel. The kernel
cannot write page table entries directly; it must request mappings through SPTM's
call interface. This prevents kernel exploits from remapping arbitrary memory.

**Key reference:** Steffin/Classen paper (see research/steffin_classen_sptm.pdf when
obtained). This is the primary external reverse-engineering analysis of SPTM.

---

## GXF — Guarded Execution Feature

GXF adds two new privilege levels to ARM64:

- **GXF EL2** (Guarded EL2): Where SPTM runs. Activated via `genter` instruction.
- **GXF EL1** (Guarded EL1): Unused by Apple currently; reserved.

Transitions:
- Normal EL1 → GXF EL2: `genter` (only from EL1 or EL2 with appropriate GXFCONFIG)
- GXF EL2 → EL1: `gexit`

The `genter` and `gexit` instructions are encoded as `HINT` NOPs on hardware that
doesn't support GXF, so they're safe to include in code that may run on older chips.

**GXF system registers** (partial, from public XNU source + Asahi research):
- `GXFCONFIG_EL1`: Controls GXF behavior from EL1
- `GXFCONFIG_EL2`: Controls GXF behavior from EL2
- `GXFSCTLR_EL1`: GXF state control (analogous to SCTLR_EL1)

**Key question:** Are these register encodings identical on A18 Pro vs M4?
Status: UNKNOWN — needs verification via m1n1 hypervisor register dump.

---

## SPTM Call Interface

SPTM exposes a call table that XNU invokes via `genter`. The call ABI is:
- `x0` = call number / function selector
- `x1`–`x7` = arguments
- Return values in `x0`–`x3`

**Known call categories (from XNU source analysis and Asahi research):**

| Category | Purpose | Status |
|----------|---------|--------|
| `SPTM_MAP_PAGE` | Map a physical page into a virtual address | Suspected |
| `SPTM_UNMAP_PAGE` | Remove a mapping | Suspected |
| `SPTM_CHANGE_PERM` | Change page permissions | Suspected |
| `SPTM_BOOTSTRAP` | Early boot page table setup | Suspected |
| `SPTM_CPU_INIT` | Per-CPU initialization | Suspected |

**Status: all entries above are UNVERIFIED.** Call numbers, argument order, and
exact semantics must be extracted from XNU kernelcache disassembly.

**TODO:** Run scripts/extract_sptm_calls.py against M4 kernelcache to get real call table.

---

## SPTM Initialization Sequence (XNU side)

From XNU open-source (xnu-10000+ series, approximate — exact version TBD):

```
arm_init()
  └─► sptm_cpu_early_init()        # very early, before MMU
        └─► genter → SPTM bootstrap call
  └─► [MMU enable via SPTM mapping calls]
  └─► sptm_cpu_init()              # per-CPU init
  └─► ... rest of arm_init
```

**Critical constraint:** We must not intercept before `sptm_cpu_init()` completes on
at least the boot CPU. Intercepting too early will leave SPTM in a partially initialized
state and any subsequent `genter` will fault.

The earliest safe intercept point is TBD — needs empirical testing via Option C
(m1n1 hypervisor) in ARCHITECTURE.md.

---

## Linux / SPTM Compatibility Challenge

Linux's `__cpu_setup` (arch/arm64/mm/proc.S) and `paging_init()` assume:
1. The kernel can write directly to page tables
2. TTBR0_EL1 / TTBR1_EL1 can be set freely

On SPTM hardware, assumption 1 is false. SPTM may trap or panic if EL1 writes
a page table entry it hasn't been told about.

**Possible mitigations (ranked by invasiveness):**

1. **SPTM "trusted kernel" mode:** If SPTM can be told "this new kernel is trusted,
   allow its page table writes," then Linux could work unmodified. Existence of this
   mode is UNKNOWN.

2. **Shim trampolines:** Replace Linux's page table write macros with calls through
   the SPTM interface. Requires patching `arch/arm64/include/asm/pgtable.h` and
   related low-level code. Significant effort but surgically contained.

3. **Identity-mapped handoff:** Shim sets up a full Linux identity map via SPTM
   calls before handing off. Linux starts with a pre-built page table that it only
   needs to extend (not rebuild). May avoid most conflicts during early boot.
   **This is the leading candidate for Phase 1.**

---

## A18 Pro vs M4 Differences (Known)

| Feature | M4 | A18 Pro | Delta |
|---------|-----|---------|-------|
| CPU cores | 4P + 6E | 2P + 4E | Fewer cores |
| GPU (AGX gen) | G18P | G18? | Likely same gen |
| SPTM version | unknown | unknown | Assume same until proven different |
| GXF support | Yes | Yes | Same |
| DRAM controller | LPDDR5X | LPDDR5X | Same |
| Memory aperture | TBD | TBD | Verify via ADT |
| Neural Engine | 38 TOPS | 35 TOPS | Minor variant |

**Primary assumption:** A18 Pro and M4 share the same SPTM firmware version and
call ABI. This is plausible given they launched in the same product cycle.
If false, this changes the project significantly.

**TODO:** Compare SPTM firmware blobs from M4 IPSW and A18 Pro IPSW. If SHA matches
or if disassembly is structurally identical, assumption holds.

---

## Papers & References

- **Steffin/Classen SPTM paper** — Primary reference. Obtain and add to research/.
  Document key findings here as sections are read.
- **Apple Platform Security Guide** — https://support.apple.com/guide/security/
- **XNU source** (open source components) — https://github.com/apple-oss-distributions/xnu
- **Asahi Linux SPRR/GXF notes** — check AsahiLinux/docs platform/subsystems.md
- **m1n1 SPRR support** — see m1n1 source, hv/hv_vm.c for GXF handling in hypervisor

---

## Dead Ends & Invalidated Approaches

*(None yet — add here as experiments fail)*
