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

| Generation | Chip | macOS mechanism | iOS mechanism |
|-----------|------|-----------------|---------------|
| A12–A14, M1 | iPhone XS – iPhone 13, M1 Mac | PPL (in kernelcache) | PPL |
| A15, M2+ | iPhone 13 Pro+ / M2 Mac+ | SPTM | SPTM |
| A17, A18 Pro, M3, M4 | Current iPhones / Macs | **macOS: PPL** (confirmed A18 Pro t8140) | SPTM |

> **Key finding (2026-03-14):** macOS 26 on A18 Pro (t8140) uses **PPL**, not SPTM.
> Zero `genter` instructions in the 121 MB ARM64 kernelcache. SPTM blobs ARE present
> on the SSD (extracted: `sptm.t8140.bin`) but iBoot does not load them for macOS.
> iBoot activates SPTM only for iOS-style kernelcaches. This means **Path A
> (boot macOS-style kernelcache) does NOT require SPTM interaction.** It follows
> the same PPL path as M1/M2/M3 Asahi Linux.

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

### Domains (from `sptm_common.h`, confirmed in paper Appendix A.2)

| ID | Name | Permission mask |
|----|------|----------------|
| 0  | `SPTM_DOMAIN`    | — |
| 1  | `XNU_DOMAIN`     | 0x02 |
| 2  | `TXM_DOMAIN`     | 0x04 |
| 3  | `SK_DOMAIN`      | 0x08 |
| 4  | `XNU_HIB_DOMAIN` | 0x10 |
| 5  | `MAX_DOMAINS`    | (sentinel) |

### Dispatch Table IDs (from `sptm_common.h`, confirmed in paper Appendix A.3)

| ID | Name |
|----|------|
| 0  | `SPTM_DISPATCH_TABLE_XNU_BOOTSTRAP` |
| 1  | `SPTM_DISPATCH_TABLE_TXM_BOOTSTRAP` |
| 2  | `SPTM_DISPATCH_TABLE_SK_BOOTSTRAP` |
| 3  | `SPTM_DISPATCH_TABLE_T8110_DART_XNU` |
| 4  | `SPTM_DISPATCH_TABLE_T8110_DART_SK` |
| 5  | `SPTM_DISPATCH_TABLE_SART` |
| 6  | `SPTM_DISPATCH_TABLE_NVME` |
| 7  | `SPTM_DISPATCH_TABLE_UAT` |
| 8  | `SPTM_DISPATCH_TABLE_SHART` |
| 9  | `SPTM_DISPATCH_TABLE_RESERVED` |
| 10 | `SPTM_DISPATCH_TABLE_HIB` |
| 11 | `SPTM_DISPATCH_TABLE_INVALID` |

### Endpoint IDs (from `sptm_xnu.h`, confirmed in paper Appendix A.4)

| ID | Name | Relevance to Linux boot |
|----|------|------------------------|
| 0  | `SPTM_FUNCTIONID_LOCKDOWN` | — |
| **1**  | **`SPTM_FUNCTIONID_RETYPE`** | **Claim frames for Linux (FREE→XNU_DEFAULT)** |
| **2**  | **`SPTM_FUNCTIONID_MAP_PAGE`** | **Build Linux page table entries** |
| **3**  | **`SPTM_FUNCTIONID_MAP_TABLE`** | **Install page table pages** |
| 4  | `SPTM_FUNCTIONID_UNMAP_TABLE` | — |
| 5  | `SPTM_FUNCTIONID_UPDATE_REGION` | May be needed for TTBR setup |
| 6  | `SPTM_FUNCTIONID_UPDATE_DISJOINT` | — |
| 7  | `SPTM_FUNCTIONID_UNMAP_REGION` | — |
| 8  | `SPTM_FUNCTIONID_UNMAP_DISJOINT` | — |
| 9  | `SPTM_FUNCTIONID_CONFIGURE_SHAREDREGION` | — |
| 10 | `SPTM_FUNCTIONID_NEST_REGION` | — |
| 11 | `SPTM_FUNCTIONID_UNNEST_REGION` | — |
| 12 | `SPTM_FUNCTIONID_CONFIGURE_ROOT` | May be needed for TTBR0/TTBR1 |
| 13 | `SPTM_FUNCTIONID_SWITCH_ROOT` | **Switch to Linux root page table?** |
| **14** | **`SPTM_FUNCTIONID_REGISTER_CPU`** | **Per-CPU registration — must call for each core** |
| 15 | `SPTM_FUNCTIONID_FIXUPS_COMPLETE` | — |
| 16 | `SPTM_FUNCTIONID_SIGN_USER_POINTER` | — |
| 17 | `SPTM_FUNCTIONID_AUTH_USER_POINTER` | — |
| 18 | `SPTM_FUNCTIONID_REGISTER_EXC_RETURN` | — |
| 19 | `SPTM_FUNCTIONID_CPU_ID` | Get CPU ID |
| 20 | `SPTM_FUNCTIONID_SLIDE_REGION` | KASLR slide application |
| 21 | `SPTM_FUNCTIONID_UPDATE_DISJOINT_MULTIPAGE` | — |
| 22 | `SPTM_FUNCTIONID_REG_READ` | — |
| 23 | `SPTM_FUNCTIONID_REG_WRITE` | — |
| 24–28 | `SPTM_FUNCTIONID_GUEST_*` | Hypervisor/VM guest support |
| 29 | `SPTM_FUNCTIONID_MAP_SK_DOMAIN` | — |
| 30–32 | `SPTM_FUNCTIONID_HIB_*` | Hibernation |
| 33 | `SPTM_FUNCTIONID_IOFILTER_PROTECTED_WRITE` | — |

### Dispatch Table Registration

During `init_xnu_ro_data`, XNU registers dispatch tables:

```c
sptm_register_dispatch_table(0,  dispatch_entry, 2);    // XNU_BOOTSTRAP, XNU_DOMAIN
sptm_register_dispatch_table(1,  dispatch_entry, 4);    // TXM_BOOTSTRAP, TXM_DOMAIN
sptm_register_dispatch_table(2,  dispatch_entry, 8);    // SK_BOOTSTRAP,  SK_DOMAIN
sptm_register_dispatch_table(10, dispatch_entry, 0x10); // HIB,           XNU_HIB_DOMAIN
```

NVME dispatch table registers with permission 0x12 (XNU_DOMAIN | XNU_HIB_DOMAIN).

**Key insight for our shim:** Capability-based trust — no per-call XNU identity check.
Our shim (running post `init_xnu_ro_data`) calls SPTM using registered XNU domain
credentials. SPTM dispatches based on encoded domain, not caller identity.

### Calling a SPTM Function (canonical example: RETYPE)

```asm
; Call SPTM_FUNCTIONID_RETYPE (endpoint 1) as XNU_DOMAIN (id 1) on table 0 (XNU_BOOTSTRAP)
; x16 = (domain=1 << 48) | (table=0 << 32) | (endpoint=1)
movz x16, #0x1              ; endpoint_id = 1 (RETYPE)
movk x16, #0x0, lsl #32     ; table_id = 0 (XNU_BOOTSTRAP)
movk x16, #0x1, lsl #48     ; domain = 1 (XNU_DOMAIN)
; x0–x3 = arguments to sptm_retype()
.long 0x00201420             ; genter
```

### Key Function Signatures (from XNU source / paper)

```c
// Claim a physical frame for use
void sptm_retype(
    pmap_paddr_t        physical_address,
    sptm_frame_type_t   previous_type,
    sptm_frame_type_t   new_type,
    sptm_retype_params_t retype_params);

// Map a page into a page table
sptm_return_t sptm_map_page(
    pmap_paddr_t  ttep,      // page table physical addr
    vm_address_t  va,        // virtual address to map
    pt_entry_t    new_pte);  // new page table entry
```

---

## Symbol Address Map (A18 Pro t8140, iOS 18.4 / 22E240)

From paper Appendix A.1. These are virtual addresses in the SPTM binary loaded by
iBoot. Useful as Ghidra/r2 base offsets when analyzing the actual firmware blob.

### SPTM Binary (`sptm.t8140.release`)

| Symbol | Address |
|--------|---------|
| `gxf_setup_early` | `0xfffffff02708b8e8` |
| `gxf_setup_late` | `0xfffffff02708b918` |
| `gxf_entry_point` | `0xfffffff02708053c` |
| `init_xnu_ro_data` | `0xfffffff0270987b4` |
| `IOMMU_bootstrap` | `0xfffffff0270be298` |
| `genter_dispatch_entry` | `0xfffffff0270bf3f8` |
| `synchronous_exception_handler_from_lower` | `0xfffffff027081e38` |
| `retype_frames` | `0xfffffff0270b4118` |
| `retype` | `0xfffffff0270c4ad8` |
| `map_page` | `0xfffffff0270c51d4` |
| `PAPT_permission_update` | `0xfffffff0270b2a38` |
| `sptm_dispatch` | `0xfffffff0270bf268` |
| `XNU_BOOTSTRAP_TABLE` | `0xfffffff0270186d8` |
| `TXM_BOOTSTRAP_TABLE` | `0xfffffff027018980` |
| `AllowedCallerDomains` | `0xfffffff027019100` |
| `CORE_DISPATCH_STRUCTURE_POINTER` | `0xfffffff027079500` |

### XNU (kernelcache for iPhone 16 / A18 Pro)

| Symbol | Address |
|--------|---------|
| `GENTER_main_gate` | `0xfffffff00ab3510c` |
| `sptm_retype` | `0xfffffff0088ebc0c` |
| `sptm_map_page` | `0xfffffff0088ebc24` |
| `txm_kernel_call` | `0xfffffff0088eb384` |
| `sk_enter` | `0xfffffff0088eb330` |

### Secure Kernel (SK binary)

| Symbol | Address |
|--------|---------|
| `main_sptm_gate` | `0xffffff8000001784` |
| `register_dispatch_table` | `0xffffff8000004340` |

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

## Critical Finding: macOS on A18 Pro Uses PPL, Not SPTM

**Discovered 2026-03-14 by scanning the running system's kernelcache.**

Hardware: MacBook Neo, chip-id 0x8140 (t8140 = A18 Pro), macOS 26.3.2 (Tahoe).

Scan of `/System/Library/KernelCollections/BootKernelExtensions.kc`:
- `genter` (0x00201420): **0 occurrences**
- `SPTM`/`sptm_retype`/`gxf_setup` strings: **not found**
- `_ppl` functions (e.g. `pmap_in_ppl`, `pmap_claim_reserved_ppl_page`): **present**

**Conclusion:** macOS on A18 Pro (even macOS 26 / Tahoe) still uses **PPL** (Page
Protection Layer), the same mechanism as M1/M2/M3. SPTM is only activated on this
hardware when booting iOS. The SPTM firmware blob (`sptm.t8140.release.im4p`) is
present in the Preboot partition but is NOT loaded by the macOS boot chain.

**Implication:** iBoot chooses the security mechanism based on the OS being booted,
not just the hardware. The A18 Pro hardware supports SPTM, but macOS uses PPL.

**Impact on this project — two boot paths now in scope:**

| Path | Mechanism | Difficulty | Relevance |
|------|-----------|-----------|-----------|
| **Path A: macOS/PPL** | PPL (same as M1-M3 Asahi) | Lower | More directly follows Asahi M3 work |
| **Path B: iOS/SPTM** | SPTM via genter | Higher | Requires iOS-style XNU shim |

**Path A is now the primary path for Phase 1 (boot to terminal).** If iBoot doesn't
activate SPTM for our macOS-style custom kernelcache, we face the PPL challenge that
Asahi has already largely solved for M1-M3.

**Open question:** Will iBoot activate SPTM when booting our custom non-Apple kernelcache
under Permissive Security? Needs empirical testing. If iBoot always activates SPTM on
A18 Pro hardware regardless of what's being booted, Path A is not viable.

## PPL Opcode Encodings on A18 Pro macOS — **CONFIRMED 2026-03-14**

The running macOS ARM64 kernelcache (`kernelcache.release.mac17g`, extracted from
Preboot im4p at `research/firmware/kernelcache.mac17g.bin`, 121 MB, MH_FILESET arm64e)
was disassembled to find the PPL enter/exit mechanism.

> **Note:** `/System/Library/KernelCollections/BootKernelExtensions.kc` is **x86_64**
> (Rosetta/Intel compatibility binary, cpu type 0x01000007). The actual A18 Pro ARM64
> kernelcache is in the Preboot volume as an im4p-wrapped Mach-O. Always use the Preboot
> kernelcache for A18 Pro analysis.

### PPL Instruction Encodings (HINT family, A18 Pro macOS 26.3.2)

| Instruction | Encoding | imm7 | Count in __TEXT_EXEC | Purpose |
|-------------|----------|------|----------------------|---------|
| `HINT #0x1b` | `0xD503237F` | 27 | **142,080** | **PPL function entry guard** — every PPL function starts with this |
| `HINT #0x1f` | `0xD50323FF` | 31 | **32,833** | **PPL exit** — appears immediately before `RET` |
| `HINT #0x22` | `0xD503245F` | 34 | **88,770** | **PPL context check** — `pmap_in_ppl` begins with this |
| `HINT #0x24` | `0xD503249F` | 36 | 15,673 | Unknown — appears in exception handler context |

### Evidence

**`pmap_in_ppl` at `0xfffffe0008a7bfb4`:**
```asm
pmap_in_ppl:
    HINT #0x22       ; 0xD503245F — if in PPL, trap returns W0=1; else fall through
    MOV W0, #0       ; 0x52800000 — not in PPL
    RET              ; 0xD65F03C0
```

**Typical PPL function (e.g., `pmap_claim_reserved_ppl_page` at `0xfffffe0008a7c700`):**
```asm
<ppl_function>:
    HINT #0x1b       ; 0xD503237F — PPL enter: switch to GL1 if called from EL1
    ...function body...
    HINT #0x1f       ; 0xD50323FF — PPL exit: return to EL1
    RET              ; 0xD65F03C0
```

The HINT #0x1f + RET sequence was verified across hundreds of PPL functions.

### Comparison: PPL (macOS A18 Pro) vs SPTM (iOS A18 Pro)

| Aspect | PPL on macOS A18 Pro | SPTM on iOS A18 Pro |
|--------|---------------------|---------------------|
| Entry to protected domain | `HINT #0x1b` | `genter` (0x00201420) |
| Exit from protected domain | `HINT #0x1f` | `gexit` (0x00201400) |
| Context check | `HINT #0x22` | (no direct equivalent — GXF_STATUS reg) |
| Domain level | GL1 | GL2 |
| Location | Embedded in XNU kernelcache | Separate iBoot-loaded firmware |
| Shim path | Path A (primary) | Path B (research) |

### Implication for Path A (macOS/PPL boot)

For our shim to intercept after PPL init and hand off to Linux, it must:
1. Be linked into the macOS-style kernelcache (iBoot won't activate SPTM for this)
2. Let `gxf_setup_early` / `gxf_setup_late` and PPL initialization run normally
3. Intercept at `IOPlatformExpert::start()` — by this point PPL is fully initialized
4. Load Linux, set up FDT, transfer control

Unlike SPTM (Path B), PPL does not require explicit frame retyping calls from our
shim. The PPL is simpler: it restricts page table modifications to GL1 code only.
After we hand off to Linux, Linux will run at EL1 and won't need to interact with
PPL (since SPTM is not active, there's no watchdog; PPL will remain initialized
but Linux won't call into it).

**Key open question:** Does Linux need to be aware of PPL (i.e., will PPL's SPRR
settings prevent Linux from setting up its own page tables)? Linux at EL1 cannot
call into GL1, so it cannot modify page tables through the PPL gate. The Asahi Linux
project must have solved this for M1/M2/M3 — investigate their pmap solution.

---

## A18 Pro vs M4 SPTM Blob Status

| Feature | Status | Notes |
|---------|--------|-------|
| SPTM blobs extracted | **DONE** | sptm.t8140.bin (1.1MB), sptm.t8132.bin (1.1MB) |
| GXF encodings | CONFIRMED | 0x00201420/0x00201400 in t8140 binary |
| Blob diff (t8140 vs t8132) | **DONE** | 27% byte diff — significant divergence |
| ABI compatibility | UNKNOWN | 27% diff means do not assume identical call numbers |
| macOS boot chain uses SPTM | **NO** | PPL only; SPTM only for iOS boot |
| Physical memory layout | TBD | ADT dump required |

### Blob Diff Analysis (t8140 vs t8132)

Sizes: t8140=1,114,144 bytes, t8132=1,130,528 bytes (+16,384 byte delta).
SHA-256 differ. Byte-level diff: **27.4%**. Header (first 256 bytes): 3 bytes differ.

The 3-byte header difference suggests same binary format; the 27% body diff likely
reflects chip-specific register offsets, hardware initialization sequences, and
possibly new/modified SPTM functions for A18 Pro vs M4. **Cannot assume call ABI
is identical.** Need Ghidra structural diff to determine if call table layout matches.

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
