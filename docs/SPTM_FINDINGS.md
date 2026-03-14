# SPTM_FINDINGS.md — Secure Page Table Monitor Research Log

Last updated: 2026-03-14

This is a living document. Every finding — including dead ends — gets recorded here.
Do not clean up "wrong" entries; mark them INVALIDATED and note why.

---

## Background: What is SPTM?

SPTM (Secure Page Table Monitor) is Apple's firmware component introduced with **A15 / M2**
(replacing PPL from A12–A14 / M1). It is a **separate firmware component loaded by iBoot**
— not part of the XNU kernelcache. It runs at GL2 (Guarded Level 2) via GXF hardware
enforcement (SPRR registers). SPTM is the sole authority on physical memory frame typing
and all page table mutations.

| Generation | Chip | Mechanism |
|-----------|------|-----------|
| A12–A14, M1 | iPhone XS – iPhone 13, M1 Mac | PPL (embedded in XNU kernelcache) |
| A15, M2+ | iPhone 13 Pro+ / M2 Mac+ | SPTM (separate iBoot-loaded firmware) |
| A17, A18, M3, M4 | Current | SPTM (confirmed; paper targets A18 Pro t8140 + M4) |

**Primary reference:** Steffin & Classen — "Modern iOS Security Features: A Deep Dive
into SPTM, TXM, and Exclaves", arXiv:2510.09272 (Oct 2025).
PDF: research/papers/steffin_classen_sptm_2025.pdf

---

## GXF — Guarded Execution Feature

GXF adds LATERAL privilege domains (GL0/GL1/GL2) orthogonal to the ARM EL hierarchy,
enforced by SPRR (Shadow Permission Remapping Register). GL levels have separate memory
permissions; SPTM code is marked `r-x` only in GL2 and inaccessible from EL1.

### Confirmed Instruction Encodings

Source: m1n1 `src/gxf_asm.S`. Stable across A16/M3/M4/A18 Pro. **VERIFIED.**

| Instruction | Encoding | Direction |
|-------------|----------|-----------|
| `genter` | `0x00201420` | Current EL → GL counterpart |
| `gexit` | `0x00201400` | GL → back to calling EL |

> **⚠️ INVALIDATED:** Earlier speculation that these are HINT NOPs (`0xD503409F` /
> `0xD503411F`) was wrong. They are custom Apple encodings; they UNDEFINED-fault on
> hardware without GXF. Do not use HINT encodings in any shim code.

### System Registers (Confirmed)

| Name | Encoding | Purpose |
|------|----------|---------|
| `SYS_IMP_APL_SPRR_CONFIG_EL1` | `S3_6_C15_C1_0` | Enable SPRR (bit 1) |
| `SYS_IMP_APL_GXF_CONFIG_EL1`  | `S3_6_C15_C1_2` | Enable GXF |
| `SYS_IMP_APL_GXF_ENTER_EL1`   | `S3_6_C15_C8_1` | GL entry point address |
| `SYS_IMP_APL_GXF_STATUS_EL1`  | (encoding TBD)  | GXF active status |
| `SYS_IMP_APL_SPRR_PERM_EL0`   | `S3_6_C15_C1_5` | SPRR permission table EL0 |
| `SYS_IMP_APL_SPRR_PERM_EL1`   | `S3_6_C15_C1_6` | SPRR permission table EL1 |

### GL Domains

| Level | Domain | Purpose |
|-------|--------|---------|
| GL2 | SPTM | Page table management, frame retyping |
| GL1 | SK (Secure Kernel, seL4-derived) / TXM | Code signing, Exclaves |
| GL0 | TXM (Trusted Execution Monitor) | Entitlements, code directory validation |

---

## SPTM Call ABI — **CRITICAL: x16 based dispatch, not x0**

> **⚠️ INVALIDATED:** All earlier speculation that `x0` holds the call number was
> wrong. SPTM uses `x16` as the dispatch descriptor. `x0–x7` are arguments only.

### Dispatch Descriptor (x16)

```
sptm_dispatch_target_t (64-bit value placed in x16 before genter):

  bits [55:48]  domain (who is calling)
  bits [39:32]  dispatch_table_id (which table)
  bits [31:0]   endpoint_id (which function within the table)
```

Standard AArch64 calling convention: `x0–x7` = arguments, `x0` = return value.

### Domains

| ID | Name | Permission mask |
|----|------|----------------|
| 0  | `SPTM_DOMAIN`    | — |
| 1  | `XNU_DOMAIN`     | 0x2 |
| 2  | `TXM_DOMAIN`     | 0x4 |
| 3  | `SK_DOMAIN`      | 0x8 |
| 4  | `XNU_HIB_DOMAIN` | 0x10 |

### Dispatch Table Registration

During `init_xnu_ro_data`, XNU registers its dispatch tables with SPTM:

```c
sptm_register_dispatch_table(0,  dispatch_entry, 2);   // XNU_BOOTSTRAP,  XNU_DOMAIN
sptm_register_dispatch_table(1,  dispatch_entry, 4);   // TXM_BOOTSTRAP,  TXM_DOMAIN
sptm_register_dispatch_table(2,  dispatch_entry, 8);   // SK_BOOTSTRAP,   SK_DOMAIN
sptm_register_dispatch_table(10, dispatch_entry, 0x10);// HIB,            XNU_HIB_DOMAIN
```

**Key insight for our shim:** SPTM's trust model is capability-based — the dispatch
table registration is the trust grant. There is **no documented cryptographic identity
check** at call time. Whoever registers a dispatch table during the early boot window
controls that domain. Our shim can register its own dispatch tables if it runs during
or after `init_xnu_ro_data`.

### Key SPTM Call Functions (from paper)

```c
// Retype a physical frame
void sptm_retype(
    pmap_paddr_t        physical_address,
    sptm_frame_type_t   previous_type,
    sptm_frame_type_t   new_type,
    sptm_retype_params_t retype_params);

// Map a page into a page table
sptm_return_t sptm_map_page(
    pmap_paddr_t  ttep,     // page table physical addr
    vm_address_t  va,       // virtual address to map
    pt_entry_t    new_pte); // new page table entry

// Update SPRR permissions (via PAPT)
void sptm_update_disp_perm(...);
```

### Calling Example (XNU → endpoint 0xf)

```asm
movk x16, #<domain_encoded>, LSL #48
movk x16, #<table_id>,       LSL #32
movk x16, #0xf               ; endpoint_id = 0xf
.long 0x00201420             ; genter
```

---

## Frame Retyping — Memory Ownership Model

SPTM maintains a **Frame Table (FT)** with one entry per 16KB page frame, tracking
frame type. No code can use a physical frame as a page table unless SPTM has retyped
it. This is the core security guarantee.

### Frame Types (63 total, Appendix A.23 of paper)

| Type | Description |
|------|-------------|
| `FREE` | Unallocated |
| `HARDWARE` | MMIO — locked, no transitions out |
| `MONITOR_DEFAULT` | SPTM's own memory — locked |
| `XNU_DEFAULT` | Normal XNU kernel data |
| `XNU_ROZONE` | XNU read-only zone (cannot downgrade) |
| `XNU_STACK` | Kernel stack |
| `XNU_IOMMU` | IOMMU-mapped memory |
| `XNU_PAGE_TABLE` | XNU page table pages |
| `XNU_SHARED_RO` | Shared RO between domains |
| `TXM_DEFAULT` | TXM writable memory |
| `TXM_PAGE_TABLE` | TXM page tables |
| `SK_DEFAULT` | Secure Kernel memory |
| `SK_PAGE_TABLE` | SK page tables |
| `EXCLAVE_DEFAULT` | Exclave memory |
| `EXCLAVE_CODE` | Exclave executable code (requires TXM sig validation) |
| `EXCLAVE_STACK` | Exclave stack |
| `SPTM_BOOTSTRAP_PAGETABLE` | SPTM page tables used during init |

### Key Transition Rules

- `FREE ↔ XNU_DEFAULT` — always allowed
- `XNU_DEFAULT → XNU_PAGE_TABLE` — allowed (page table promotion)
- `XNU_PAGE_TABLE → XNU_DEFAULT` — allowed only if zero live mappings remain
- `XNU_ROZONE → XNU_DEFAULT` — **NOT allowed** (once RO zone, always RO)
- Cross-domain (e.g., `XNU_DEFAULT → TXM_DEFAULT`) — must go via `FREE` first
- `HARDWARE`, `MONITOR_DEFAULT` — locked, no exit transitions
- `FREE → EXCLAVE_CODE` — requires TXM code signature validation

### Implication for Linux Boot

To load Linux, our shim must:
1. Call `sptm_retype(linux_phys, FREE, XNU_DEFAULT, ...)` for each Linux page
2. Call `sptm_retype(pt_phys, FREE → XNU_PAGE_TABLE, ...)` for Linux page table pages
3. Call `sptm_map_page(ttep, va, pte)` to build Linux's address space
4. Transfer execution — SPTM does NOT have a watchdog/heartbeat (see below)

There is no `LINUX_CODE` frame type. Linux pages must be typed as `XNU_DEFAULT` or
similar — which means SPTM will allow EL1 to both write and execute them. This may
be acceptable for our feasibility goal (not hardened, just booting).

---

## SPTM Initialization Sequence (from paper, XNU side)

```
iBoot → loads SPTM firmware, enters GL2, runs SPTM self-init, returns
iBoot → jumps to XNU entry

XNU arm_init():
  └─► gxf_setup_early()
        msr GXF_CONFIG_EL1, #1        ; enable GXF
        msr GXF_PABENTRY_EL1, <addr>  ; physical abort handler
        genter                        ; first GL1 entry (basic probe)
        gexit
  └─► [basic memory setup]
  └─► gxf_setup_late()
        msr GXF_PABENTRY_EL1, <addr>
        msr GXF_ENTRY_EL1, <addr>     ; main GL1 entry vector
        msr VBAR_GL1, <addr>          ; GL1 vector table
        msr GXF_CONFIG_EL1, 0x2f      ; full GXF config
  └─► init_xnu_ro_data()
        sptm_register_dispatch_table(0, ..., 2)   ; XNU domain registration
        sptm_register_dispatch_table(1, ..., 4)   ; TXM domain
        sptm_register_dispatch_table(2, ..., 8)   ; SK domain
        sptm_register_dispatch_table(10, ..., 0x10) ; HIB domain
  └─► [SPTM now fully initialized with all domain tables]
  └─► [XNU continues — builds page tables via sptm_map_page]
```

**Earliest safe shim intercept:** After `init_xnu_ro_data()` completes.
Option A (IOPlatformExpert hook) is well past this point — safe.

---

## Watchdog / Heartbeat

**None documented.** A full search of the paper found no SPTM watchdog or heartbeat
mechanism. After SPTM init, SPTM is passive — it responds to calls but does not
proactively check whether XNU is still alive. This is highly favorable for our shim:
after we transfer control to Linux, SPTM will not kill EL1.

---

## Non-XNU Kernel Compatibility Assessment

From the paper's analysis of SPTM's trust model:

**SPTM does NOT appear to have runtime per-call identity verification.** The security
model is:
1. iBoot loads SPTM and XNU in a verified chain (Secure Boot)
2. XNU registers dispatch tables during `init_xnu_ro_data`
3. After registration, any code that executes `genter` with the correct `x16` encoding
   gets service — SPTM dispatches based on the encoded domain, not caller identity

**For our shim:** This means if our shim runs after `init_xnu_ro_data` (which has
registered XNU's dispatch tables), we can make SPTM calls using the XNU domain
descriptor and SPTM will serve us — there is no "is this really XNU" check.

**Remaining uncertainty:** Whether iBoot enforces XNU identity *before* dispatch
table registration (i.e., is the window between iBoot handoff and `init_xnu_ro_data`
protected in a way that locks out our shim?). The paper does not address this.
Empirical testing via Option C (hypervisor) required.

---

## SPTM Physical Memory Layout

- **SPTM binary:** loaded by iBoot into physical memory before XNU starts
- **SPTM virtual addresses:** `~0xfffffff027080000` (from paper disassembly)
- **Frame Table (FT):** contiguous, 1 FTE per 16KB frame, typed `MONITOR_DEFAULT`
- **PAPT (Physical Aperture Table):** phys→virt mapping, also `MONITOR_DEFAULT`
- **GL2 stack:** separate `MONITOR_DEFAULT` region per CPU
- **Shared XNU↔SPTM buffers:** typed `XNU_SHARED_RO` or similar

The Frame Table covers all RAM. Its physical location is determined by iBoot's memory
map and is revealed via ADT dump (`/chosen/` memory-map node).

---

## TXM and Exclaves (Brief)

**TXM (Trusted Execution Monitor):** Runs at GL0. Validates code signatures before
SPTM permits `EXCLAVE_CODE` frame typing. XNU calls TXM through SPTM dispatch.
The `txm_call_t` struct carries a selector (`TXMKernelSelector_t`) and result buffer.

**Exclaves:** Isolated resource groupings managed by SK (seL4-derived Secure Kernel
at GL1). Use Tightbeam IPC. Irrelevant to Phase 1 boot goal.

For Linux booting, TXM is irrelevant — we don't need code signing for our pages
(we type them `XNU_DEFAULT`, not `EXCLAVE_CODE`).

---

## A18 Pro vs M4 Status

| Feature | Status | Notes |
|---------|--------|-------|
| SPTM generation | Same | Both A18 Pro era; paper confirmed M4 tested |
| GXF encodings | CONFIRMED SAME | 0x00201420 / 0x00201400 stable |
| Frame type table | Assumed same | Verify via blob diff |
| Call ABI (x16 dispatch) | Assumed same | Verify via kernelcache diff |
| Physical memory layout | TBD | ADT dump required |

---

## Papers & References

| Reference | Status |
|-----------|--------|
| Steffin/Classen arXiv 2510.09272 | **Downloaded** — research/papers/steffin_classen_sptm_2025.pdf |
| Sven Peter SPRR/GXF blog (2021) | **Read** — https://blog.svenpeter.dev/posts/m1_sprr_gxf/ |
| m1n1 GXF source (gxf.c / gxf_asm.S) | **Read** — call convention confirmed |
| Proteas SPTM notes (2023) | Unread — https://proteas.github.io/ios/2023/06/09/some-quick-and-discrete-notes-on-sptm.html |
| Dataflow Forensics SPTM series | Unread — https://www.df-f.com/blog/sptm4 |
| Apple Platform Security Guide | Reference — https://support.apple.com/guide/security/ |

---

## Dead Ends & Invalidated Approaches

- **INVALIDATED:** `genter`/`gexit` as HINT NOPs (`0xD503409F`/`0xD503411F`). Real encodings
  are `0x00201420`/`0x00201400` from m1n1 source. Updated in `scripts/extract_sptm_calls.py`.

- **INVALIDATED:** `x0` holds the SPTM call number. Real dispatch uses `x16` with a packed
  domain/table/endpoint descriptor. `x0–x7` are arguments. Updated in `extract_sptm_calls.py`
  — the script now needs to scan for MOVK x16 patterns, not MOVZ x0.

- **INVALIDATED:** `GXFCONFIG_EL1` / `GXFSCTLR_EL1` as register names. Correct names:
  `SYS_IMP_APL_GXF_CONFIG_EL1` and `SYS_IMP_APL_SPRR_CONFIG_EL1`.

- **INVALIDATED:** "GXF EL2" as privilege level descriptor. Correct: GL2 (lateral domain).

- **INVALIDATED:** SPTM introduced with A16. Correct: A15 / M2 (paper confirms binary for
  A18 Pro t8140; states PPL on A12–A14/M1, SPTM on A15/M2+).
