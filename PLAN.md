# PLAN.md — Action Items

Last updated: 2026-03-15

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
- [x] Disassemble PPL enter/exit mechanism in macOS A18 Pro XNU — **FOUND 2026-03-14**
      HINT #0x1b (0xD503237F) = PPL enter, HINT #0x1f (0xD50323FF) = PPL exit,
      HINT #0x22 (0xD503245F) = pmap_in_ppl check. All verified in 121MB ARM64 kernelcache.
      NOTE: BootKernelExtensions.kc is x86_64; real ARM64 KC is in Preboot im4p.
- [x] Identify earliest safe intercept point post-PPL-init (Path A) — IOPlatformExpert::start()
      is post-PPL-init; this is the Option A hook target. Confirmed via SPTM findings.
- [ ] If pursuing Path B: identify SPTM init sequence in iOS XNU (requires iOS kernelcache)
- [ ] Determine minimum kexts required for PPL to complete init (Path A)

### 0.2b Local Hardware Analysis (NEW — we are on target hardware)
- [x] Confirmed chip: A18 Pro, t8140, board Mac17,5
- [x] Confirmed iBoot: 13822.81.10
- [x] Extracted SPTM blobs: sptm.t8140.bin (1.1MB) and sptm.t8132.bin (M4, 1.1MB)
- [x] Diff result: 27.4% byte difference — cannot assume identical ABI
- [x] genter found in SPTM binary at 0x9f8d4 (1 site — SPTM's own init/self-call)
- [x] ARM64 kernelcache extracted: Preboot im4p → research/firmware/kernelcache.mac17g.bin
      (121MB MH_FILESET arm64e). BootKernelExtensions.kc is x86_64 — do NOT use it for A18 Pro analysis.
- [x] PPL opcodes confirmed in ARM64 KC: HINT#0x1b=enter, HINT#0x1f=exit, HINT#0x22=check
- [x] Dump ADT via ioreg — **DONE 2026-03-14** → research/adt_dump/adt_summary.json
      AIC=0x301000000, uart4=0x385210000 (wlan-debug), uart5=0x385214000 (bt-debug)
      CPU: 4×E-core (sawtooth, mpidr 0–3) + 2×P-core (everest, mpidr 0x100–0x101)
      DRAM: 8GB, ADT dram-base=0x10000000000 — SUSPECT, needs m1n1 verification
- [x] Generate stub Linux DTS → research/adt_dump/stub_a18pro.dts
      Addresses confirmed; UART IRQ, clock nodes, DRAM base are TODOs
- [x] PPL enter/exit opcodes found — HINT#0x1b/HINT#0x1f (see SPTM_FINDINGS.md)
      "Explore PPL call mechanism" task is now complete.
- [ ] Run r2/Ghidra structural diff on t8140 vs t8132 SPTM binaries
- [ ] Determine iBoot behavior: does it activate SPTM for non-iOS Permissive boot?
- [ ] Investigate DRAM base — verify 0x10000000000 via m1n1 once tethered boot is set up
- [ ] Resolve UART compatible string: "apple,s5l-uart" vs "samsung,s3c2410-uart" for Linux driver

### 0.3 m1n1 / Toolchain Setup
- [x] Build m1n1 from source targeting M4 (closest available proxy for A18 Pro)
      → build/m1n1.bin and build/m1n1.macho at /Users/rusch/Projects/m1n1/build/
- [x] Diagnosed USB not enumerating — ROOT CAUSE FOUND 2026-03-15
      t8140 ADT uses un-indexed node names (`usb-drd`, `dart-usb`, `mapper-usb`)
      while m1n1 uses indexed format strings (`usb-drd%u` → `usb-drd0`).
      `usb_drd_get_regs()` fails at first ADT lookup, USB PHY never powered.
      See docs/USB_DEBUG.md for full analysis and fix options.
      Secondary: `atc-phy0` reports compatible `atc-phy,t8130` — not in kboot_atc.c
      fuse table. Affects Linux boot USB3/TB only, not m1n1 proxyclient.
- [x] Patched m1n1 src/usb.c — fallback to un-indexed ADT node names (`usb-drd`,
      `dart-usb`, `mapper-usb`) when indexed lookup fails at idx==0. 2026-03-15
- [x] Patched m1n1 src/kboot_atc.c — added `atc-phy,t8130` (no fuses) to fuse table.
- [x] Rebuilt m1n1 — build/m1n1.bin @ 2026-03-15 09:19, 1.0MB (USB node name fix)
- [x] First boot: dart found ✓, but pmgr_init() failed — t8140 uses `pmgr1,t8140`
      which has no `ps-regs` property. USB PHY never powered. 2026-03-15
- [x] Patched pmgr.c — pmgr1 mode: psreg_idx indexes reg[] directly, no ps-regs table.
- [x] Rebuilt m1n1 — build/m1n1.bin @ 2026-03-15 (pmgr1 + USB node fix)
- [x] Second root cause found 2026-03-15: ATC0_USB_AON pmgr register times out because
      it requires SPMI HPM interaction that m1n1 does not issue. pmgr_set_mode_recursive()
      aborts on parent failure, so ATC0_USB (DWC3 clock gate) is never enabled.
      Confirmed via live boot: GSNPSID reads 0x00000000 at drd=0x40a280000.
      Fix: call pmgr_power_on(0, "ATC0_USB") directly after standard pmgr calls —
      bypasses parent recursion, writes ATC0_USB psreg immediately. iBoot already
      powered AON; only DWC3 clock gate needed toggling. See docs/USB_DEBUG.md.
- [x] Rebuilt m1n1 — build/m1n1.bin @ 2026-03-15 18:54 (commit 30caac3)
- [x] Third root cause found 2026-03-15: SPMI wakeup was targeting the wrong bus.
      Sent WAKEUP to hpm0/addr=0xC on nub-spmi-a0 (USB HPM = TI SN2012xx, USB-C ctrl).
      ATC0_USB_AON is controlled by the Dialog PMU "baku" at addr=0xE on nub-spmi0.
      Fixed in commit c0c7338: targets nub-spmi0/0xE. Also dumps SPMI 0x6000-0x600F
      (Dialog PMU power domain region 0) to screen for analysis.
      Dialog PMU power rail registers confirmed at SPMI 0x6000-0x6FFF (16 ptmu-regions).
- [x] Rebuilt m1n1 — build/m1n1.bin @ 2026-03-15 (commit c0c7338)
- [x] Reverse-engineered AppleDialogSPMIPMU kext from mac17g kernelcache (2026-03-15)
      Complete Dialog baku PMU register map documented in src/baku_pmu.h:
        BAKU_PM_SETTING=0xF801, BAKU_LEG_SCRPAD=0xF700, BAKU_SCRPAD_BASE=0x8000
        BAKU_LPM_CTRL_BASE=0x8FDC (SLPSMC is ENABLED on mac17g)
        BAKU_PTMU_BASE=0x6000 (16 regions 0x6000-0x6FFF — PMU fw managed)
      Key finding: ATC0_USB_AON power control is inside 0x6000-0x6FFF, managed by
      PMU firmware. OS cannot directly write these regs; firmware unlocks them after
      its own init. iBoot runs PMU fw before handoff, so SPMI WAKEUP should be enough.
      usb_spmi_init() now probes 0xF801, 0xF700, 0x8FDC, and 0x6000 to diagnose
      which stage the PMU is at when m1n1 runs.
- [x] Rebuilt m1n1 — build/m1n1.bin @ 2026-03-15 (baku_pmu.h + diagnostic probes)
- [x] SPMI diagnostic: all reads fail (EXT_READ + EXT_READL), both before and after WAKEUP.
      WAKEUP appeared to ACK but was synthetic — bus clock was gated.
      SPMI ctrl STATUS = 0x01000100 (RX_EMPTY|TX_EMPTY = idle, MMIO accessible via AXI
      fabric even when clock-gated). Controller base confirmed at 0x308714000 from ADT.
- [x] Root cause found: AppleARMSPMIController::start() calls enablePsdService()
      (= pmgr power domain enable) before using the bus. m1n1's spmi_init() skips this.
      Found via kernelcache RE of AppleARMSPMI.cpp: panic string
      "Unable to enablePsdService, result=%08x" proves it's mandatory.
      Also found: pmu-spmi-delay and pmu-spmi-retry ADT props for inter-command timing.
- [x] Fix applied: pmgr_adt_power_enable(BAKU_SPMI_NODE) before spmi_init() in usb.c.
      Docs updated in docs/USB_DEBUG.md (Fourth Root Cause section).
- [ ] **NEXT: Flash and boot — check for:**
        "spmi0 +00: ..." MMIO dump line — confirm STATUS is same (0x01000100)
        "PMU EXT_READ reg00=XX ok" — SPMI reads now working
        "PMU 0xf801(pm_setting)=XX" → PMU alive
        "PMU 0x6000(ptmu[0]) ok@Xms" → PMU firmware accessible
        Absence of pmgr ATC0_USB_AON timeout → USB rail enabled by PMU
        "USB0 registered" → tethered boot working
- [ ] Confirm tethered boot works over USB-C UART on target hardware
- [x] Set up ARM64 cross-compilation toolchain (clang + lld) — brew llvm + lld installed
- [ ] Set up Python proxyclient environment for m1n1 scripting
- [ ] Implement scripts/probe_sptm.py using m1n1's existing gl2_call() / gxf hooks
      (m1n1 has native GXF support in src/gxf.c — we can set GXF_ENTER_EL1 to our
      logging stub before loading XNU as guest, intercept every genter call)
- [ ] Install ipsw CLI tool (https://github.com/blacktop/ipsw) for IPSW extraction

### 0.4 Linux Kernel Baseline
- [x] Identify which AsahiLinux/linux branch has the most M4 progress
      → AsahiLinux/linux `asahi` branch (March 2026); no M4/t8132 DTS yet
- [x] Build a minimal ARM64 kernel with CONFIG_APPLE_MACHINE, no AGX, serial console only
      → arch/arm64/boot/Image (7.0 MB, 16K pages) at /Users/rusch/Projects/linux-asahi/
      → macOS build required shims: .host_include/{elf.h,byteswap.h,gethostuuid.h,sys/_types/_uuid_t.h},
        .build_tools/sed → gsed, per-file HOSTCFLAGS_file2alias.o += -D_UUID_T in scripts/mod/Makefile
      → Build cmd: PATH=".build_tools:llvm/bin:bison/bin:$PATH" gmake ARCH=arm64 LLVM=1 HOSTCFLAGS="-I.host_include" Image
- [ ] Confirm it boots under m1n1 hypervisor on M4 hardware (as a sanity check)

---

## Phase 1: Goal 1 — Boot to Terminal

- [ ] Write minimal XNU stub (xnu_shim/stub/) that links against kernelcache
- [ ] Implement shim intercept point post-SPTM-init
- [ ] Implement Linux ELF loader within shim
- [ ] Map Linux kernel image via SPTM calls (read-only + executable pages)
- [ ] Set up Linux boot args struct (FDT / device tree pointer)
- [~] Write minimal A18 Pro device tree (DT) — stub created at research/adt_dump/stub_a18pro.dts
      Still needs: DRAM base verification, UART IRQ specifier, clock nodes
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
