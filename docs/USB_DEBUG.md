# USB Serial Debug — m1n1 Proxy Not Enumerating

**Status as of 2026-03-17 — HV auto-boot approach (Option 4) implemented; first test failed (PMU timeout). Fixing Mach-O loader bugs.**

m1n1 boots and shows its boot screen on the MacBook Neo display, but does not
enumerate as a USB ACM device on the Linux host. No `/dev/ttyACM*` appears, and
`lsusb` shows no Apple device.

**Root cause: t8140 ADT uses un-indexed USB node names (`usb-drd`, `dart-usb`)
while m1n1 looks for indexed names (`usb-drd0`, `dart-usb0`). USB init fails
silently at the first ADT path lookup.**

---

## Root Cause — Confirmed via Live ioreg

m1n1's USB init is almost entirely ADT-driven. The SPMI detection path passes
correctly for t8140, but the DRD node lookup immediately fails.

### ADT Node Names: Expected vs. Actual

| m1n1 path (format string result) | t8140 ADT actual node | Match |
|---|---|---|
| `/arm-io/nub-spmi-a0/hpm0` | `nub-spmi-a0/hpm0` ✓ | PASS |
| `/arm-io/atc-phy0` | `atc-phy0@AA90000` ✓ | PASS |
| `/arm-io/usb-drd0` | `usb-drd@A280000` ✗ | **FAIL** |
| `/arm-io/dart-usb0` | `dart-usb@AF00000` ✗ | **FAIL** |
| `/arm-io/dart-usb0/mapper-usb0` | `dart-usb/mapper-usb@1` ✗ | **FAIL** |

t8140 appears to have only one USB DRD controller. The nodes are not indexed — no
`atc-phy1`, no `usb-drd1`, no `dart-usb1`.

### Why USB Init Silently Fails

```
usb_spmi_init()                          ← called (SPMI check passes)
  usb_phy_bringup(0)
    usb_drd_get_regs(0)
      adt_path_offset("/arm-io/usb-drd0")  ← NOT FOUND → returns -1
    returns -1                             ← exits here, PHY never powered
  usb_phy_bringup(1) .. (N)               ← same failure
usb_iodev_init()
  usb_iodev_bringup(0)
    usb_dart_init(0)
      adt_path_offset("/arm-io/dart-usb0/mapper-usb0")  ← NOT FOUND → returns NULL
    returns NULL                           ← exits here, DWC3 never initialized
```

No error is printed. `usb_is_initialized` is set to `true` anyway. USB controller
is never powered, never configured, never connected to DWC3. Nothing to enumerate.

### Additional: ATC PHY Compatible String

`atc-phy0` reports compatible `atc-phy,t8130` (M3 Pro/Max silicon, reused in t8140).
This is NOT in `kboot_atc.c`'s `atc_fuses[]` table — only t6020, t8112, t6000, t8103
are listed. This is a secondary issue affecting Linux kernel boot (USB3/TB won't work
via the kernel's ATC PHY driver) but does NOT affect m1n1 proxyclient USB2.

---

## Hardware Facts Confirmed via ioreg (2026-03-15)

| Property | Value |
|---|---|
| Board | MacBook Neo, Mac17,5, A18 Pro (t8140) |
| SPMI bus | `nub-spmi-a0@F8908000` |
| HPM nodes | `hpm0@C`, `hpm1@A` (two ports, SPMI address bus) |
| ATC PHY | `atc-phy0@AA90000`, compatible `atc-phy,t8130` |
| USB DRD | `usb-drd@A280000`, compatible `usb-drd,t8140` |
| USB DART | `dart-usb@AF00000`, compatible `dart,t8110` |
| DART mapper | `mapper-usb@1` (child of dart-usb, not indexed) |
| Second USB port | No `atc-phy1`, `usb-drd1`, or `dart-usb1` found |

---

## Required Fix in m1n1 (human-authored)

The format strings in `src/usb.c` assume all Apple Silicon uses indexed node names.
t8140 breaks this. Two plausible approaches:

### Option A — Fallback to un-indexed name

In `usb_drd_get_regs()` and `usb_dart_init()`, if the indexed path (`usb-drd0`,
`dart-usb0`) fails, try the un-indexed path (`usb-drd`, `dart-usb`). This is a
minimal fix but adds a special case branch.

Pseudo-code for `usb_drd_get_regs()`:
```c
// Try indexed first (all chips prior to t8140)
snprintf(drd_path, sizeof(drd_path), "/arm-io/usb-drd%u", idx);
adt_drd_offset = adt_path_offset_trace(adt, drd_path, adt_drd_path);
// t8140 fallback: un-indexed name, only valid for idx==0
if (adt_drd_offset < 0 && idx == 0) {
    snprintf(drd_path, sizeof(drd_path), "/arm-io/usb-drd");
    adt_drd_offset = adt_path_offset_trace(adt, drd_path, adt_drd_path);
}
if (adt_drd_offset < 0)
    return -1;
```
Same pattern for `dart-usb` and `mapper-usb`.

### Option B — ADT-compatible-driven discovery

Instead of constructing paths from format strings, iterate `/arm-io` children and
match by `compatible` property (`usb-drd,t8140`, etc.). More robust but larger
change to usb.c.

### Option C — `kboot_atc.c` fix (secondary, Linux boot)

Add `atc-phy,t8130` to the `atc_fuses[]` table with `NULL` fuses, same as `t6020`:
```c
{"atc-phy,t8130", -1, NULL, 0},
```
This covers t8140 since it uses the same ATC PHY silicon as t8130/M3 Pro.

---

## Boot Setup State (as of 2026-03-15)

The stub volume setup required non-obvious steps — document for next time:

1. `bputil -nkcas` from 1TR (authenticate as stub user)
2. `csrutil disable` from 1TR
3. Unlock and mount the **Data** volume — it is FileVault-encrypted and must be
   unlocked before mounting. The system volume (`Macintosh HD`) is auto-mounted
   by 1TR but `/Users` lives on the Data volume (`disk4s5`):
   ```
   diskutil apfs unlockVolume disk4s5
   ```
   Enter your login password when prompted. Mounts at `/Volumes/Data`.
4. Run the reinstall script (handles steps 5–6 automatically):
   ```
   sh /Volumes/Data/Users/rusch/Projects/asahi_neo/scripts/reinstall_m1n1.sh
   ```
   The script will also unlock the Data volume itself if not yet mounted, so
   if you're running it cold from 1TR Terminal you can skip step 3 and just run
   the script directly once the Data volume path is accessible.
5. `kmutil configure-boot -c m1n1.bin --raw --entry-point 2048 --lowest-virtual-address 0 -v /Volumes/Linux`
6. `bless --mount /Volumes/Linux --setBoot` — **required, stub won't appear in picker without this**

Step 3 is the non-obvious one. The Data volume must be mounted explicitly; 1TR
only auto-mounts the sealed system snapshot. Without step 6, the stub volume does
not appear in the startup picker even with a valid boot object installed.

---

## Debug Log — NVMe Scratch Area

`pmgr_dump_usb_devices()` writes its full output (struct dumps + reg[] map) to
disk0 NS1 LBA 64 — a 4096-byte sector in the GPT free gap that no filesystem owns.
The log persists across reboots until the next m1n1 boot overwrites it.

**Read back from macOS (no 1TR needed):**
```sh
sudo dd if=/dev/disk0 bs=4096 skip=8 count=1 | strings
```
*(LBA 64 at 512-byte sectors = byte offset 32768 = 4096-byte block 8)*

**Read back from 1TR:**
```sh
dd if=/dev/disk0 bs=4096 skip=8 count=1 | strings
```

**Verify LBA 64 is free** (run once from macOS or 1TR):
```sh
sudo gpt show /dev/disk0
```
The first partition (`Apple_APFS_ISC`) should start at LBA 2048 or later,
leaving LBAs 34–2047 as the GPT free gap. LBA 64 sits safely inside that range.

---

## What to Check on the Linux Host

Once the m1n1 fix is applied and rebuilt, verify on the Linux box:

```bash
# After booting m1n1 (wait ~5 seconds for USB init):
lsusb | grep -i apple          # should show "Apple USB-C DFU" or similar ACM device
ls /dev/ttyACM*                # should appear
dmesg | grep -i "acm\|apple"   # should show cdc_acm binding
```

If still nothing: check `dmesg | grep usb` for connection events — even failed
ones show up as port resets, which would at least confirm physical USB connectivity.

---

## Third Root Cause — SPMI Wakeup Targeting Wrong Bus (2026-03-15)

**Status: fixed in commit c0c7338, pending boot test**

The previous build sent `spmi_send_wakeup()` to **hpm0 (addr=0xC)** on **nub-spmi-a0**
(the USB HPM bus, physical addr 0xF8908000). This is the TI SN2012xx USB-C controller —
it does NOT control ATC0_USB_AON. The HPM was already in "APP" mode at boot and the
wakeup had no effect on the stuck pmgr register.

**Root cause of the wrong target**: The comment in usb_spmi_init() said "HPM" but the
device that controls power rails (including ATC0_USB_AON) is the Dialog Semiconductor
"baku" PMU (compatible "pmu,spmi","pmu,baku") at **addr=0xE on nub-spmi0@F8714000**.
That's the system PMU bus — a completely separate SPMI controller.

**Fix in c0c7338**: Send WAKEUP to pmu-main (addr=0xE) on nub-spmi0. Also read 16 bytes
at SPMI reg 0x6000 (first ptmu-region) to see power domain control register state.

**Dialog PMU "baku" register map** (from pmu-main@E ADT ptmu-region properties):

| Region | SPMI addr range | Size |
|--------|-----------------|------|
| 0–7    | 0x6000–0x61FF   | 8×64 bytes (power domain controls?) |
| 8–11   | 0x6200–0x63FF   | 4×128 bytes |
| 12–13  | 0x6400–0x67FF   | 2×512 bytes |
| 14–15  | 0x6800–0x6FFF   | 2×1024 bytes |

ATC0_USB_AON enable bit is likely in 0x6000–0x61FF. The 0x6000 register dump printed
by the new build will tell us which region controls USB power.

Additional PMU properties found in pmu-main@E ioreg:
- `info-leg_scrpad = <00f70000>` → SPMI reg 0xf700 is the panic counter register
- `function-external_standby = <890000005779656b4553424d>` → routed via smc-pmu
  (phandle 0x89), not direct SPMI — macOS-only deep sleep interaction
- `info-pm_setting = <01f80000>` → SPMI reg 0xf801 for PM settings

**How to read the NVMe log after this boot** (same as before):
```sh
sudo dd if=/dev/disk0 bs=4096 skip=8 count=1 | strings
```

---

## Second Root Cause — ATC0_USB_AON Blocks DWC3 Clock Gate (2026-03-15)

**Status: fix applied, pending boot test**

After adding t8140 un-indexed path fallbacks (dart-usb, usb-drd), USB init finds all
the right nodes and registers but DWC3 still does not respond:

```
usb: using un-indexed dart path (t8140 compat)
usb: dart0 init: path=/arm-io/dart-usb idx=1
dart: dart /arm-io/dart-usb at 0x40af80000 is a t8110
usb: using un-indexed drd path (t8140 compat)
usb: drd regs ok: drd=0x40a280000 unk3=0x40aa84000 atc=0x40aa90000
no DWC3 core found at 0x40a280000: 00000000      ← GSNPSID reads zero
```

### Root Cause

`pmgr_set_mode_recursive()` enables a device's parents before enabling the device
itself (lines 229–238 of pmgr.c). When enabling `ATC0_USB` (the DWC3 clock gate),
it first recurses to enable parent `ATC0_USB_AON`. On t8140, `ATC0_USB_AON` requires
an SPMI HPM command before its pmgr register will accept a mode change — m1n1 does
not issue that command, so the register times out. The recursive call returns -1 and
the abort path (`return ret`) exits **before `ATC0_USB` is ever touched**.

Confirmed sequence:
```
pmgr: [0x300700000] before=0x00000100 actual=0 target=0 -> setting mode f
pmgr: timeout while trying to set mode f for device at 0x300700000: 100
```
`ATC0_USB_AON` psreg stays stuck; DWC3 clock gate `ATC0_USB` never enabled;
read from `0x40a280000 + 0xc120` (GSNPSID) returns 0x00000000.

### Fix Applied

`pmgr_power_on(int die, const char *name)` looks up a device by name and calls
`pmgr_set_mode(addr, PMGR_PS_ACTIVE)` directly — **no parent recursion**. Added to
`usb_phy_bringup()` for `idx == 0` after the standard (failing) pmgr calls:

```c
// On t8140, ATC0_USB_AON requires SPMI — recursive enable aborts before
// ATC0_USB (DWC3 clock gate) is enabled. Enable it directly.
if (idx == 0) {
    if (pmgr_power_on(0, "ATC0_USB") < 0)
        printf("usb: direct ATC0_USB enable failed\n");
    else
        printf("usb: ATC0_USB direct enable ok\n");
}
```

This works because iBoot already powered the AON domain as part of DFU/USB bringup.
The hardware is already up; only the DWC3 clock gate needed to be toggled.

### ATC0_USB_AON — Why It Stays Stuck

`ATC0_USB_AON` is an always-on power island controlled jointly by pmgr and the SPMI
HPM (nub-spmi-a0). On earlier chips (M1/M2), no HPM is involved and pmgr alone can
transition the AON domain. On t8140 (A18 Pro), the HPM must assert USB power before
the pmgr register reflects the change. m1n1 has no SPMI HPM driver. The correct
long-term fix is an SPMI HPM driver, but bypassing the stuck parent unblocks USB2
proxyclient operation without it.

---

## Fourth Root Cause — SPMI Controller Not pmgr-Enabled (2026-03-15)

**Status: fix applied in current build; pending boot test**

### All SPMI Reads Were Always Failing

Despite the Third Root Cause fix (correct SPMI bus and address), every SPMI register
read — including the mandatory SPMI device-ID register 0x00 and `pm_setting` (0xF801)
— continued to fail. Symptoms:

- `WAKEUP` to addr=0xE ACKed (bus-level response)
- All `EXT_READ` (8-bit addr) and `EXT_READL` (16-bit addr) returned fast NAK
- SPMI controller STATUS register = `0x01000100` = RX_EMPTY | TX_EMPTY (idle, correct)
- MMIO offsets 0x00–0x3C: only STATUS/CMD/REPLY at 0x00–0x08; rest zero
- Waiting 200ms post-WAKEUP made no difference
- The WAKEUP ACK was likely **synthetic** — the unclocked controller generating a
  canned reply, not a real response from the Dialog PMU on the wire

### Root Cause: SPMI Bus Controller Requires pmgr Power-On

Kernelcache RE of `AppleARMSPMI.cpp` (`AppleARMSPMIController`) found:

```
result == 0
Unable to enablePsdService, result=%08x
Panicing from IOKit spmi command
```

`enablePsdService()` is `AppleARMIO`'s pmgr power domain enable — equivalent to
`pmgr_adt_power_enable()` in m1n1. `AppleARMSPMIController::start()` calls this
before issuing any commands, and panics on failure. m1n1's `spmi_init()` only maps
the MMIO but never enables the controller via pmgr, so the SPMI bus clock was gated.
The controller appeared healthy (MMIO reads worked through the AXI fabric) but no
commands reached the SPMI wire.

### Additional Kernelcache Findings

From `AppleDialogSPMIPMU.cpp` string table, the PMU driver reads these ADT properties
from `pmu-main@E` at startup:

| ADT property | Purpose |
|---|---|
| `pmu-spmi-retry` | SPMI command retry count |
| `pmu-spmi-delay` | Mandatory inter-command delay (us) |
| `pmu-bringup` | Bringup mode flag |
| `pmu-debug` | Debug logging |
| `info-id` | PMU hardware ID |

The `pmu-spmi-delay` property means macOS applies a fixed delay between SPMI
transactions that m1n1 does not — relevant if reads start working after the pmgr
fix but produce intermittent errors.

### Fix

```c
// Must pmgr-enable the SPMI bus controller before any spmi_init() call.
// AppleARMSPMIController::start() calls enablePsdService() (= pmgr power domain
// enable) before using the bus; without it the clock is gated and all commands fail.
if (pmgr_adt_power_enable(BAKU_SPMI_NODE) < 0)
    printf("usb: pmgr enable %s failed (may be ok if already on)\n", BAKU_SPMI_NODE);
spmi_dev_t *pmu_spmi = spmi_init(BAKU_SPMI_NODE);
```

### Expected Outcome

If `pmgr_adt_power_enable("/arm-io/nub-spmi0")` succeeds, the SPMI bus clock is
ungated and EXT_READ of reg 0x00 should return the Dialog PMU's SPMI device ID.
Subsequent reads of `pm_setting` (0xF801), `leg_scrpad` (0xF700), and `ptmu[0]`
(0x6000) should also succeed, and the pmgr ATC0_USB_AON timeout may resolve as the
PMU firmware signals power-good for the USB rail.

### Fourth Root Cause Status: Hypothesis Wrong

**The pmgr clock-gate hypothesis was incorrect.** Live boot confirmed:
- All three candidate pmgr domain names (`"SPMI"`, `"SPMI0"`, `"NUB_SPMI"`) return `-1`
  on t8140 — there is no named pmgr power domain for the nub-spmi0 controller.
- The `pmgr_adt_power_enable()` call silently failed (printed "may be ok if already on")
  but SPMI reads continued to fail identically.
- The SPMI controller is fully powered by iBoot and left running. MMIO is accessible
  through the AXI fabric regardless (STATUS = `0x01000100` visible even when clock-gated
  per our earlier misread — but the real situation is the controller IS running).

The actual reason SPMI reads fail is in the **Fifth Root Cause** below.

---

## Fifth Root Cause — Dialog PMU External Standby Mode (2026-03-16)

**Status: SMC-based fix in commit 944adbd; pending boot test**

### The Decisive Clue: ret=-2 = SPMI_ERR_BUS_IO

After the Fourth Root Cause fix the boot log showed:

```
PMU pm_setting(0xF801) FAILED ret=-2
```

SPMI error code mapping (from `src/spmi.h`):
```
SPMI_ERR_UNKNOWN       = 1  → ret=-1
SPMI_ERR_BUS_IO        = 2  → ret=-2   ← THIS
SPMI_ERR_INVALID_PARAM = 3  → ret=-3
```

`ret=-2` = `SPMI_ERR_BUS_IO` means the SPMI controller sent the EXT_READL command
and received a **NACK reply frame** from the PMU slave — not a timeout, not a bus hang.
The PMU received the command, formed a response, and actively refused it. The SPMI bus
and controller are fully functional.

### Exclave Hypothesis — Ruled Out (2026-03-16)

**Question**: is nub-spmi0 protected by an Apple Exclave, making direct AP MMIO access
illegal?

**Investigation**: compared ADT properties of nub-spmi0 vs nub-spmi1:

| Property | nub-spmi0 (Dialog PMU bus) | nub-spmi1 |
|---|---|---|
| `exclave-edk-service` | not present | `"com.apple.service.XSPMIQueue_EDK"` |
| `xspmi` | not present | `<01000000>` |

**Conclusion**: nub-spmi1 is exclave-controlled (XSPMIQueue_EDK). nub-spmi0 is NOT —
it has no exclave properties at all. Direct AP SPMI writes to nub-spmi0 are legal.
The NACK is coming from PMU firmware, not from any exclave protection mechanism.

### Three Register Regions on nub-spmi0

Live boot confirmed nub-spmi0 has three MMIO regions (reg[0..2] from ADT):

| Region | Base address | STATUS read | Role |
|---|---|---|---|
| reg[0] | 0x308714000 | `0x01000100` (RX_EMPTY\|TX_EMPTY) | FIFO: STATUS/CMD/REPLY — used by spmi_init() |
| reg[1] | 0x308704000 | `0x01000000` (TX_EMPTY only) | Unknown secondary register bank |
| reg[2] | 0x308700000 | `0x00000004` | Unknown — different type/purpose |

Only reg[0] is used by m1n1's SPMI driver. The other two are informational; they do
not need to be touched to fix the NACK.

### pmgr Domain Search — All Names Miss on t8140

Attempted `pmgr_power_on(0, name)` for multiple candidate names; all return -1:

```
pmgr_power_on(0, "SPMI")     → -1
pmgr_power_on(0, "SPMI0")    → -1
pmgr_power_on(0, "NUB_SPMI") → -1
```

There is no named pmgr power domain for nub-spmi0 on t8140. The controller is
powered on by iBoot and stays on. The SPMI NACK is not a clock/power issue.

### IOPMUBootLPMCtrl — Not a Register Address

The IOKit property `IOPMUBootLPMCtrl = {"lpm1"=0,"imgIdx"=0,"lpm2"=0,...}` is a
dictionary of LPM image indices (all zero = PMU booted fresh, not from a sleep image).
It is NOT a physical register address. Unrelated to the NACK.

### Root Cause: External Standby Mode

The Dialog "baku" PMU has a post-iBoot firmware state called **external standby mode**.
In this state the PMU firmware:
- ACKs SPMI **management commands** (WAKEUP, RESET) — these use the command channel
- **NACKs all register access** (EXT_READ, EXT_READL, EXT_WRITE) — firmware refuses
  all register transactions until a specific unlock sequence is completed

macOS resolves this via the IOKit function `function-external_standby` on `pmu-main@E`.
The function specifier bytes are: `<890000005779656b4553424d>`:

```
89 00 00 00  → phandle 0x89 = smc-pmu (AppleSMCInterface node)
57 79 65 6b  → "Wyek" (ASCII)
45 53 42 4d  → "ESBM" (ASCII)
```

IOKit routes `function-external_standby` to `smc-pmu` (phandle 0x89), which is the
`AppleSMCInterface` node. `AppleSMCInterface` sends an SMC key write to the AOP/SMC
firmware telling the SMC to signal the Dialog PMU to exit external standby. The PMU
then allows register reads.

**smc-pmu node properties** (ADT, phandle 0x89):
- class: `AppleSMCInterface`
- `has-lpem-fw-scc=1`, `info-has_slpsmc=1`, `info-has_phra=1`
  (same SLPSMC coordination flags as pmu-main@E — confirms it's the same PMU's SMC proxy)

### SMC Key Hypotheses

The specifier `"Wyek" + "ESBM"` could be decoded as either:

| Hypothesis | SMC key | Value |
|---|---|---|
| A — key is ESBM, value is exit flag | `0x4553424d` ("ESBM") | `0` or `1` |
| B — key is Wyek, value encodes command | `0x5779656b` ("Wyek") | `0x4553424d` ("ESBM") |

Both are tested in commit 944adbd:

```c
smc_dev_t *smc = smc_init();
// Hypothesis A
smc_write_u32(smc, 0x4553424d, 0);   // "ESBM"=0
smc_write_u32(smc, 0x4553424d, 1);   // "ESBM"=1
// Hypothesis B
smc_write_u32(smc, 0x5779656b, 0x4553424d);  // "Wyek"="ESBM"
```

m1n1's SMC driver (`src/smc.c`) connects via `/arm-io/smc` + ASC + RTKit endpoint
0x20. `smc_init()` / `smc_write_u32()` are existing, tested infrastructure.

### What to Look for on Next Boot

```
usb: SMC init OK
usb: SMC 'ESBM'=0 ret=0           ← 0 = success
usb: SMC 'ESBM'=1 ret=X
usb: SMC 'Wyek'=0x4553424d ret=X
usb: PMU pm_setting(0xF801)=0xXX OK — external standby exited!
```

If SMC init fails outright: the ADT path for `/arm-io/smc` may differ on t8140
(possible alternative: `/arm-io/nub-gpio/smc`). Investigate ADT node name.

If SMC writes return non-zero: wrong key. Fallback: enumerate SMC keys by scanning
the SMC key table (m1n1's `smc_read_keyinfo()` can iterate).

If SMC writes return 0 but reads still fail: the unlock sequence may require a
specific order or additional keys. May need to sniff the full
`AppleDialogSPMIPMU::start()` → `AppleSMCInterface` call chain from kernelcache.

---

## Sixth Investigation — "ESBM"/"Wyek" Are Not Raw SMC Keys (2026-03-16)

**Status: SMC_RW_KEY approach in iteration 15; pending boot test**

### SMC Write Results From 944adbd

Boot of commit 944adbd confirmed SMC init works on t8140 (`/arm-io/smc` is valid).
However, all three `smc_write_u32()` calls returned **0x84 = not found**:

```
usb: SMC 'ESBM'=0   ret=0x84   ← key not in SMC firmware key table
usb: SMC 'ESBM'=1   ret=0x84
usb: SMC 'Wyek'=ESBM ret=0x84
```

This rules out both SMC key hypotheses from the Fifth Root Cause section.
"ESBM" and "Wyek" are not standard SMC key names accessible via SMC_WRITE_KEY (0x11).

### Mac Code Research — "Wyek"/"ESBM" Are callPlatformFunction Args

Cross-referencing Apple open-source confirms the mechanism:

- `AppleSMCPMU::callPlatformFunction(func, p1, p2, ...)` is the IOKit dispatch path.
- The `function-external_standby` specifier `<89 00 00 00  57 79 65 6b  45 53 42 4d>`
  decodes as: phandle=0x89, arg1="Wyek", arg2="ESBM".
- These are arguments to `callPlatformFunction` **inside AppleSMCPMU** — they identify
  which sub-function to dispatch, NOT literal SMC key names.
- `AppleSMCPMU::callPlatformFunction` then calls into the SMC IOP NUB using its own
  internal key/command mapping. The AP never sends "ESBM" or "Wyek" directly over the
  RTKit mailbox.

**Implication**: we cannot reconstruct the standby-exit command from the specifier bytes
alone. We need to find the actual SMC key that `AppleSMCPMU` dispatches.

### ADT Search for smc-pmu (phandle 0x89)

Needed to find the IOP NUB path to understand the protocol. ADT search iterations:

| Iteration | Approach | Result |
|-----------|----------|--------|
| 9 | BFS over full ADT (64-slot stack) | **Watchdog reset** — 296+ nodes, too slow |
| 10 | Scan direct /arm-io children (1 level) | Not found — smc-pmu is deeper |
| 11 | Fallback: linear blob scan, dump nodes [43]–[50] | Showed smc node, not smc-pmu |
| 12 | Scan /arm-io children + each child's children (2 levels) | Not found — 3 levels needed |
| 13 | Add `/arm-io/X/Y/Z` scan (3 levels) | **Found**: `/arm-io/smc/iop-smc-nub/smc-pmu` |

**BFS watchdog note**: the 64-slot BFS stack over the entire ADT trips the hardware
watchdog — too many nodes processed in a tight loop. Always use bounded depth with
`ADT_FOREACH_CHILD` for ADT traversal in m1n1.

### Critical Discovery: smc-pmu Has No `reg[]`

Live boot of iteration 13 printed:

```
usb: ph89 'smc'/'iop-smc-nub'/'smc-pmu'
usb: no reg
```

The `smc-pmu` node at `/arm-io/smc/iop-smc-nub/smc-pmu` **has no `reg[]` property**.
It is not an MMIO block. There is no physical register address to write.

This is expected for an IOP (I/O Processor) NUB node. The `iop-smc-nub` logical device
communicates with the SMC co-processor exclusively through the SMC RTKit firmware
mailbox (endpoint 0x20) — the AP never directly pokes SMC registers.

### SMC RTKit Protocol — SMC_RW_KEY (0x20) Identified

The SMC RTKit protocol (endpoint 0x20) has these message types, all defined in
`src/smc.c`:

```c
#define SMC_READ_KEY         0x10
#define SMC_WRITE_KEY        0x11
#define SMC_GET_KEY_BY_INDEX 0x12
#define SMC_GET_KEY_INFO     0x13
#define SMC_INITIALIZE       0x17
#define SMC_NOTIFICATION     0x18
#define SMC_RW_KEY           0x20  ← defined but NEVER used in m1n1 prior to this work
```

`SMC_RW_KEY` (0x20) is an atomic read-write command: write new value, read old value
back from shared memory. It was defined in m1n1's `smc.c` but had no corresponding
m1n1 function. This is exactly the type of command `AppleSMCPMU` would use for a
state-toggle operation like external standby exit.

### Iteration 15 Approach

Two new functions added to `src/smc.c` and `src/smc.h`:

**`smc_get_key_info(smc, key, &sz, &type, &attr)`** — issues `SMC_GET_KEY_INFO` (0x13).
SMC firmware stores key metadata in shmem: `u8 size, u32 type, u8 attributes`.
Returns 0 on success, 0x84 if key not found. Used to probe whether "ESBM"/"Wyek"
exist at all under a different command path.

**`smc_rw_key(smc, key, new_val, data_size, &old_out)`** — issues `SMC_RW_KEY` (0x20).
Atomic: writes `new_val` to shmem, sends RW_KEY message, reads back old value.

`usb_spmi_init()` in iteration 15:
1. Dumps `iop-smc-nub` ADT property names/sizes (to find any endpoint/protocol fields)
2. 5-second delay, then `smc_init()`
3. `smc_get_key_info()` for "ESBM" and "Wyek" — expect 0x84 confirming they're not keys
4. `smc_rw_key(smc, "ESBM", "Wyek", 4, &old)` — the actual standby-exit attempt
5. SPMI read of PMU 0xF801 — confirms whether standby was exited

### What to Look for on Next Boot

```
usb: iop-smc-nub props:
  <list of property names>        ← look for endpoint, protocol, service-name fields
usb: SMC probe in 5s...
usb: ESBM info: 0x84             ← expected: not a standard key
usb: Wyek info: 0x84             ← expected: not a standard key
usb: RW_KEY ESBM<-Wyek: ret=0 old=XXXXXXXX  ← ret=0 = RW_KEY accepted!
usb: PMU 0xF801 = OK (standby exited!)       ← external standby exited
```

If `RW_KEY ret=0x84` again: AppleSMCPMU uses an undocumented internal dispatch, not
a raw SMC key. Next step: enumerate the full SMC key table via `smc_get_key_by_index()`
and search for power-management or PMU-related key names.

If `RW_KEY ret=0` but PMU still NACKs: the unlock requires additional SMC keys or
a specific sequence. May need a SMC key table scan to find the actual SPMI-exit key.

### SMC Key Namespace Note

SMC keys are 4-byte big-endian ASCII identifiers. Known PMU-related key categories:
- `B` prefix: battery/power (e.g., `BCLM`, `BATS`)
- `F` prefix: fan / thermal
- `M` prefix: motion / sensor
- `S` prefix: system state (sleep, etc.)
- Power-management keys likely in `S`-prefix or a custom 4-char sequence

If key table enumeration is needed, `smc_get_key_by_index()` iterates all keys; at
~200–600 keys on Apple Silicon expect ~1 second to enumerate the full table.

---

## Seventh Investigation — SMC_RW_KEY + SPMI Direct Approaches (iterations 15–17)

**Status: all failed**

### Iteration 15: SMC_RW_KEY(ESBM ← Wyek)

`SMC_RW_KEY` (opcode 0x20) is an atomic read-modify-write: the AP writes a new value
to shared memory, sends the message, and reads back the old value. It was defined in
m1n1's `smc.c` but had no caller prior to this work. The hypothesis was that
`AppleSMCPMU::callPlatformFunction("Wyek", "ESBM")` might internally issue a RW_KEY
to an SMC virtual key.

**Result**: `SMC_RW_KEY(ESBM ← Wyek)` returned **0x84** (key not found). The "ESBM"
and "Wyek" strings do not map to any SMC key accessible via any SMC message type
(WRITE_KEY, GET_KEY_INFO, RW_KEY). They are internal identifiers within AppleSMCPMU's
dispatch table, not RTKit-level keys.

### Iterations 16–17: SPMI Register Writes + RESET

Attempted a sequence of SPMI direct writes to the Dialog PMU:
- Writes to ptmu-region 0 (0x6000–0x603F) to try enabling ATC0_USB_AON power rail
- `EXT_WRITE` to `pm_setting` (0xF801)
- SPMI RESET command to addr=0xE

All writes ACKed (the SPMI command channel is open) but subsequent reads of 0xF801
still returned NACK. The RESET (iteration 17) also returned "still in standby".

**Conclusion from iterations 15–17**: The PMU's external standby mode blocks all
register access from the SPMI side regardless of what is written. The exit signal
must come from the **SMC co-processor**, not from the AP SPMI bus. SPMI-side approaches
are exhausted. Deeper kernelcache RE is required to find the actual SMC command.

---

## Eighth Investigation — Kernelcache RE: ApplePPMSMCInterface Confirms ESBM="slpw" (2026-03-17)

**Status: led to iterations 18–20, all NACK**

### MH_FILESET Parsing Bug Found and Fixed

The mac17g kernelcache (`research/firmware/kernelcache.mac17g.bin`, 121MB arm64e) uses
`LC_FILESET_ENTRY` commands to embed kext Mach-O objects. The command type is
**0x80000035** (`0x35 | LC_REQ_DYLD`), not `0x41` as initially assumed. Initial
attempts to extract kext offsets produced garbage because they matched the wrong command.
Fixed to use `0x80000035`.

### ApplePPMSMCInterface — sendValueToSMCKey

After fixing the parser, disassembly of ApplePPMSMCInterface found:

- **`sendValueToSMCKey`** at VA `0xfffffe000a27a238` (fileoff `0x032487bc`)
- BL at fileoff `0x0324881c` dispatches to a kernel function at fileoff `0x217315c`
  via PAC-authenticated IOKit vtable dispatch (vtable[274] = offset 0x890 on
  `this->field_0x10`, the inner SMC channel object).
- At **power state `0xe0000340`** (external standby exit): writes the 4CC value
  `"slpw"` to SMC key `"ESBM"`.

### SMC Key Encoding (Critical)

The SMC shared memory region uses **little-endian byte order**. `smc_write_u32()`
does `memcpy(shmem, &value, 4)`. The correct encodings are:

| String | LE u32 value | Bytes in shmem |
|--------|-------------|----------------|
| `"ESBM"` (key) | `0x4d425345` | `E, S, B, M` |
| `"slpw"` (value) | `0x77706c73` | `s, l, p, w` |

The BE encoding `0x4553424d` for "ESBM" does NOT work — the SMC firmware stores all
keys in little-endian byte order on this hardware.

Python proxyclient inconsistency: `smc.py` uses `byteorder="big"` for write (sends BE)
but `byteorder="little"` for `get_key_by_index` (reads LE). This is a latent bug in
the Python client; the C driver's LE encoding is correct.

### Iteration 18: BE Key → 0x84

First attempt used `smc_write_u32(smc, 0x4553424d, 0x736c7077)` (BE "ESBM"):

```
usb: SMC ESBM(BE)=slpw ret=132   ← 0x84 = key not found
```

Expected — the firmware's key table only contains LE-encoded keys.

### Iteration 19: LE Key Accepted, PMU Still NACK

Switched to LE key `0x4d425345`:

```
usb: ESBM(LE) ret=0   ← key accepted!
usb: PMU post-SMC 0xF801 = NACK (standby active)
```

**Root cause of NACK**: `smc_shutdown()` was called **before** the PMU check. The PMU
check ran after `rtkit_quiesce()`, which likely re-asserted SLPSMC as part of SMC
cleanup. The write itself succeeded; the issue was the shutdown racing with the check.

Also from iteration 19 boot log:
```
function-external_standby: 89 00 00 00  57 79 65 6b  45 53 42 4d
  phandle=0x89 not found in direct /arm-io children (deeper in tree)
```

### Iteration 20: Pre-Shutdown PMU Check — Still NACK

Moved PMU check to **before** `smc_shutdown()`, with 500 ms delay. Tested both value
encodings in one boot:

| Value | Shmem bytes | Result |
|-------|-------------|--------|
| `0x736c7077` | `w, p, l, s` | NACK |
| `0x77706c73` | `s, l, p, w` = "slpw" | NACK |

Both NACK even while SMC is still alive. The ESBM write is accepted (ret=0) but does
not deassert SLPSMC within 500 ms. Possible causes remaining:
1. The PMU state machine requires a sequence of states (not a cold "slpw" write)
2. 500 ms is insufficient — PMU firmware needs more time to respond
3. ESBM affects a software flag only; a separate SPMI or hardware signal is also needed

---

## Ninth Investigation — State Machine Sequence + Extended Poll (iteration 21)

**Status: pending boot test (2026-03-17)**

### Hypothesis

macOS may drive the SMC "ESBM" key through a **power state sequence** rather than
writing "slpw" cold. Observed macOS ESBM states from kernelcache:

| State name | LE u32 value | Shmem bytes |
|------------|-------------|-------------|
| `"offw"`   | `0x7766666f` | `o, f, f, w` |
| `"rest"`   | `0x74736572` | `r, e, s, t` |
| `"slpw"`   | `0x77706c73` | `s, l, p, w` |

The Dialog PMU firmware may require seeing `offw → rest → slpw` in order before
deassigning SLPSMC. Writing "slpw" alone from a cold (never-transitioned) state
might be silently ignored by the firmware's state machine.

### Changes in Iteration 21 (`usb_spmi_init`)

1. **Recursive ADT phandle search** — `usb_adt_find_phandle()` walks the entire ADT
   tree to resolve phandle 0x89 and print the node name. Previously the 3-level
   hard-coded search found it at `/arm-io/smc/iop-smc-nub/smc-pmu`; the recursive
   search handles any depth and will confirm whether `smc_init()` is targeting the
   same SMC device.

2. **State machine sequence** — writes `offw` → `rest` → `slpw` in order, polling
   after each step (5 × 200 ms = 1 second per state, 3 seconds max).

3. **No `smc_shutdown`** — RTKit co-processor remains live throughout. If `rtkit_quiesce()`
   was re-asserting SLPSMC as cleanup, this eliminates that path entirely.

4. **Extended polling** — 5 × 200 ms checks after each write (vs. single 500 ms in
   iteration 20). Exact state transition timing visible in the log.

### What to Look for on Next Boot

```
usb: phandle 0x89 node = 'smc-pmu'   ← confirms same device found
usb: ESBM=offw ret=0
usb: NACK after offw
usb: ESBM=rest ret=0
usb: NACK after rest
usb: ESBM=slpw ret=0
usb: PMU exited standby after ESBM=slpw poll N   ← success
usb: PMU external standby EXITED
usb: ptmu[0]: XX XX XX ...
```

If all three states return NACK: the Dialog PMU firmware is likely waiting for a
separate SPMI-side signal (write to `BAKU_LPM_CTRL` at 0x8FDC) in addition to the
SMC key — possible coordination between the SMC and SPMI paths. Next step would be
writing 0x8FDC alongside the ESBM sequence.

If ret != 0 for any state: wrong SMC device, or the SMC firmware on this hardware
doesn't expose ESBM writes from the standard endpoint 0x20 path (unlikely given
iteration 19/20 results).

### Iteration 21 Result: Crashloop + ret=137

**Crashloop cause**: `usb_adt_find_phandle()` called `adt_first_child_offset()` and
`adt_next_sibling_offset()` without guards. Both are Rust functions that call `.unwrap()`:
- `adt_first_child_offset` panics when `child_count == 0` (leaf node returns `Err(NotFound)`)
- `adt_next_sibling_offset` panics when called on the last sibling

`ADT_FOREACH_CHILD` avoids both via its outer `_child_count` guard — this guard was
not replicated in the hand-written loop. Fix: `if (cnt <= 0) return -1` before calling
`adt_first_child_offset`, and `if (i < cnt - 1)` before calling `adt_next_sibling_offset`.

**ret=137 after crashloop fix**: once the ADT crash was fixed, all ESBM writes returned
137 instead of 0. Root cause: the SMC is an always-on co-processor — its RTKit endpoint
0x20 session persists across AP resets. Iteration 21 skipped `smc_shutdown()`, leaving
the endpoint open. When the AP reset (due to the ADT panic) and m1n1 booted again,
`smc_init()` attempted to re-initialize an already-open endpoint → rejected with 137.

`rtkit(smc): smc_cmd(0x1) failed: 137` appearing before the first ESBM write confirms
the failure is in the RTKit endpoint initialization, not the ESBM write itself.

**Lesson**: always call `smc_shutdown()` on every exit path, even on failure. The SMC
AON domain outlives AP reboots and retains endpoint state until `rtkit_quiesce()` closes it.

---

## Tenth Investigation — ESBM Read Diagnostic (iteration 22)

**Status: pending boot test (2026-03-17)**

### Hypothesis

After 4 iterations of ESBM writes that were accepted (ret=0) but produced no PMU
response, the key question is: does the SMC actually hold the value across reboots?
If `smc_read_u32(ESBM)` after `smc_init()` returns "slpw", the SMC retained state from
a prior boot. If it returns something else (or not-found), the state is reset at boot.

This diagnostic will also confirm:
- Whether ESBM is readable at all (0x86 = not readable would indicate a write-only key)
- What "ground state" the SMC firmware assigns to ESBM at startup

### Changes in Iteration 22

1. **smc_shutdown() restored** — always called on all exit paths (fix for ret=137).
2. **Read ESBM before writing** — `smc_read_u32(ESBM)` prints current value and ASCII
   representation. If the SMC is stateless (resets at boot), cur will be "offw" or zeros.
   If stateful, cur will be "slpw" from iteration 19/20.
3. **Write "slpw" only** — reverts to single confirmed-working write (no state machine).
4. **Read ESBM after writing** — confirms the value was actually stored in shmem.
5. **Extended poll** — 10 × 200 ms = 2 seconds.
6. **Phandle search removed** — already confirmed as `/arm-io/smc/iop-smc-nub/smc-pmu`.

### What to Look for on Next Boot

```
usb: ESBM read: ret=0 val=0x6f666677 (o,f,f,w)  ← SMC resets to "offw" at boot
usb: ESBM=slpw ret=0
usb: ESBM readback=0x77706c73 (s,l,p,w)          ← value confirmed stored
usb: PMU exited standby poll N                    ← success
```

**If `ESBM read` val is already `0x77706c73` ("slpw")**: the SMC retains state across
reboots. Writing "slpw" again is a no-op and will never trigger the transition. Need to
write "offw" first (to reset the state machine), then "slpw". Or ESBM is not the right
mechanism.

**If `ESBM read` ret=0x86** (not readable): key is write-only — the readback approach
won't work, but the write path is correct; need to look elsewhere for the standby exit.

**If `ESBM=slpw ret=0` but PMU still NACKs after 2 s**: ESBM does not directly control
SLPSMC hardware on this silicon. Need to investigate `BAKU_LPM_CTRL` (0x8FDC) or look
at the full `ApplePPMSMCInterface` initialization sequence for additional steps.

### Iteration 22 Result

```
usb: ESBM read ret=0 val=0x00000000 (????)
SMC smc_cmd[0x2] Failed: 137
usb: ESBM=slpw ret=137
usb: PMU still in standby
```

**`[0x2]` is the message sequence ID** (not the opcode) — the 3rd message sent overall
(0=INITIALIZE, 1=read, 2=write). The read succeeded; the write failed with 137.

Key findings:
- **ESBM ground state = 0x00000000** — SMC resets to null at boot; iBoot does not initialize ESBM
- **Read-before-write blocks writes** — reading ESBM causes subsequent WRITE_KEY to return 137.
  Hypothesis: firmware write-once semantics per session after a READ_KEY command.

---

## Eleventh Investigation — State Machine Without Pre-Read + Direction Reversal (iteration 23)

**Status: failed — ret=137**

### Hypothesis

Removed pre-read (which was causing 137). Reversed hypothesis: "offw" deasserts SLPSMC
(system awake), "slpw" asserts it. Tried offw→rest→slpw sequence without any pre-read.

### Result

```
usb: ESBM=offw ret=137
usb: PMU still in standby
```

WRITE_KEY returns 137 for "offw" even without a prior read. This rules out the
"read-before-write lock" as the sole cause — WRITE_KEY (0x11) is now consistently
rejected with 137 regardless of read state. Something changed since iterations 19–20
when writes returned 0.

**Root cause hypothesis**: the crashloop (iteration 21 — multiple AP resets without
`smc_shutdown`) may have caused the SMC firmware to transition to a "locked" state for
ESBM writes. The SMC firmware might enforce write permissions based on caller context or
internal state machine, and the abnormal resets corrupted that state.

---

## Twelfth Investigation — RW_KEY + SPMI LPM_CTRL Direct Write (iteration 24)

**Status: pending boot test (2026-03-17)**

### New Angles

**A) `smc_get_key_info(ESBM)`** — uses SMC_GET_KEY_INFO (0x13), not WRITE_KEY (0x11).
Key attribute byte may reveal why writes fail:
- Bit 0x10 set → key is read-only (firmware enforces; explains 137)
- Bit 0x20 set → key is write-only
- Other bits → privilege or context requirements

**B) `smc_rw_key(ESBM, "offw", 4, &old)`** — uses SMC_RW_KEY (0x20), the atomic
write+readback command. Different firmware code path than WRITE_KEY (0x11). The "Wyek"
callPlatformFunction in AppleSMCPMU might specifically use RW_KEY internally rather than
a plain write. Returns old value so we can see what the firmware had before.

**C) SPMI write to `BAKU_LPM_CTRL` (0x8FDC = 0x00)** — bypasses SMC entirely. SPMI
EXT_WRITE ACKs even in external standby. Writing 0x00 to the LPM control register may
clear whatever bit is keeping the PMU in standby.

### What to Look for

```
usb: ESBM info ret=0 sz=4 type=... attr=0xXX   ← attr bits reveal write restrictions
usb: ESBM RW_KEY=offw ret=0 old=0x00000000     ← RW_KEY succeeds where WRITE_KEY fails
usb: LPM_CTRL=0x00 wr=0                         ← SPMI write ACKed
usb: PMU exited standby poll N                  ← success
```

If `attr & 0x10` (read-only): ESBM is read-only from the AP side; macOS uses a
privileged channel we don't have access to. Need a completely different approach.

If RW_KEY ret=0 but PMU still NACK: writing ESBM via any command is accepted but not
sufficient alone. The SPMI LPM_CTRL write (path C) is the remaining hope.

If LPM_CTRL write ACKs and PMU exits standby: SPMI-side override works independently
of SLPSMC. The SMC key path was a red herring.

### Iteration 24 Result

```
usb: ESBM info ret=0 sz=4 type=0x5f786568 attr=0xd4
usb: ESBM RW_KEY=offw ret=0 old=0x00000000
usb: LPM_CTRL=0x00 wr=0
usb: NACK (2s)
usb: PMU still in standby
```

**Key findings:**
- `smc_get_key_info(ESBM)` succeeded: sz=4, type="hex_" (0x5f786568 LE), attr=0xd4
  (bits 7,6,4,2 = readable + writable). ESBM IS writable.
- `smc_rw_key(ESBM, "offw")` returned 0 (success), old=0x00000000 (null/cold boot).
  RW_KEY (0x20) bypasses the 137 error from WRITE_KEY (0x11).
- LPM_CTRL 1-byte write ACKed but PMU still NACKs all reads after 2 seconds.
- Both SMC and SPMI writes accepted, but single "offw" write alone is insufficient.

---

## Thirteenth Investigation — Kernelcache RE: 3-Step ESBM Sequence (iteration 25)

**Status: pending boot test (2026-03-17)**

### Critical Kernelcache Finding

Disassembly of `AppleDialogSPMIPMU`'s `SystemPowerStateChange` handler
(kext `com.apple.driver.AppleSPMIPMU`, __TEXT at fileoff 0x656c80) found
three contiguous log strings at fileoff 0x64bb20:

```
%s:%d %s() 'slpw' result=%s
%s:%d %s() 'rest' result=%s
%s:%d %s() 'offw' result=%s
```

macOS writes **all three ESBM values in sequence** during a power state change:
1. `"slpw"` (0x77706c73) — initiate wake from sleep
2. `"rest"` (0x74736572) — intermediate state
3. `"offw"` (0x7766666f) — fully awake, standby bus off

Prior iterations (18–24) only wrote ONE value. This is why the PMU never exited
standby — the state machine requires the full transition sequence.

### Second Finding: LPM_CTRL is a 4-Byte Register

Disassembly of the LPM ctrl write function at VA 0xfffffe000a443558 shows:

```asm
str wzr, [sp, 0x2c]           ; init 4-byte buffer to 0
ldrh w1, [x0, 0xa4]           ; w1 = BAKU_LPM_CTRL_BASE (0x8FDC)
...
mov w3, 4                      ; size = 4 bytes
blraa x8, x17                  ; writeReg(self, reg, data_ptr, 4)
```

The function builds a 4-byte value from its parameters:
- Byte 0: always 0
- Byte 1: param7 (LPM image index)
- Byte 2: param6 (control byte)
- Byte 3: bitfield of enabled LPM domains (bits 0-4)

When all `IOPMUBootLPMCtrl` values are 0 (fresh boot), the 4-byte write is
0x00000000 — same value but the SPMI EXT_WRITEL opcode differs (0x33 for 4 bytes
vs 0x30 for 1 byte). PMU firmware may reject the wrong size.

Our code was writing only 1 byte (0x00). Fixed to 4 bytes.

### Changes in Iteration 25

1. **ESBM 3-step sequence**: writes slpw → rest → offw via RW_KEY (0x20) with
   100ms delay between each transition. Logs ret and old value for each step.

2. **4-byte LPM_CTRL write**: writes `u32 0x00000000` instead of `u8 0x00`.
   Uses `spmi_ext_write_long(..., 4)` instead of `spmi_ext_write_long(..., 1)`.

3. **SPMI WAKEUP after ESBM**: sends `spmi_send_wakeup(addr=0xE)` with 200ms
   delay after the ESBM sequence. Prior iters tried WAKEUP alone (ACKed but no
   effect) — this is the first test with WAKEUP combined with a successful ESBM
   sequence.

### What to Look for on Next Boot

```
usb: ESBM RW_KEY=slpw ret=0 old=0x00000000   ← first write: null → slpw
usb: ESBM RW_KEY=rest ret=0 old=0x77706c73   ← second: slpw → rest
usb: ESBM RW_KEY=offw ret=0 old=0x74736572   ← third: rest → offw
usb: LPM_CTRL=0x00(4B) wr=0                  ← 4-byte write ACKed
usb: SPMI WAKEUP ret=0                       ← WAKEUP command ACKed
usb: PMU exited standby poll N               ← SUCCESS
```

If all three RW_KEY writes return 0 but PMU still NACKs: the ESBM writes may be
accepted by the SMC but not forwarded to the PMU's SLPSMC pin. The callPlatformFunction
dispatch in `AppleSMCPMU` may use an internal mechanism beyond simple key writes.
Next step: enumerate SMC notifications (opcode 0x18) or investigate whether the
"Wyek" dispatch requires a specific SMC endpoint or sub-command.

If any RW_KEY write returns non-zero (e.g. 137): the SMC firmware may enforce a
single RW_KEY per session. Try shutting down and reinitializing SMC between writes,
or use only the first value that succeeded.

---

## Option 4: HV Auto-Boot XNU for PMU Init (2026-03-17)

### Concept

Since all bare-metal approaches to exit PMU standby have failed (SPMI direct,
SMC key writes, ESBM sequences), we try a fundamentally different approach:
boot macOS's own XNU kernel as a guest under m1n1's hypervisor, let XNU's IOKit
initialize the PMU normally, detect the wakeup from EL2, then tear down the HV
and proceed with USB init.

### Implementation: `src/hv_autoboot.c`

Three new components in the m1n1 fork:

**1. Mach-O MH_FILESET payload detection (`payload.c`)**

The concatenated payload (`m1n1.bin + kernelcache.mac17g.bin`) is detected by
checking for `0xFEEDFACF` (MH_MAGIC_64) magic. The payload scanner stores a
pointer to the raw kernelcache and computes its size from LC_SEGMENT_64 fileoff/filesize.

**2. Mach-O parser + entry point finder (`hv_autoboot.c`)**

Parses the MH_FILESET kernelcache:
- Walks LC_SEGMENT_64 to find vmin/vmax (VA range)
- Allocates a 2MB-aligned buffer and copies segments at `(vmaddr - vmin)` offsets
- For MH_FILESET: scans LC_FILESET_ENTRY for an entry containing "kernel",
  then parses the sub-Mach-O for LC_UNIXTHREAD to extract the entry PC
- Falls back to `__TEXT_EXEC` vmaddr → `__TEXT` vmaddr → vmin

**3. Standalone HV mode (`hv_autoboot.c` + `hv_exc.c`)**

- Calls `hv_init()` to set up stage-2 page tables
- Identity-maps all RAM and MMIO via `hv_map_hw()`
- Constructs `boot_args` from iBoot's original, patching:
  - `phys_base` = address of loaded image buffer
  - `virt_base` = vmin (lowest segment vmaddr)
  - `top_of_kernel_data` = end of image
- Sets HCR_EL2 for minimal trapping (API|APK|TEA|E2H|RW|VM)
- Boots XNU at EL1 via `hv_start(entry, {boot_args, 0, 0, 0})`
- From EL2 timer FIQ tick (1000 Hz), polls SPMI `BAKU_PM_SETTING` every 100th
  tick (~10 Hz). When register read ACKs (ret==0), PMU has exited standby.
- `hv_exc_proxy()` patched: in autoboot mode, logs exceptions and returns
  instead of entering `uartproxy_run()` (which blocks forever without USB).
- 60-second timeout; bails after 50 trapped exceptions.
- After HV exit: restores HCR, flushes TLBs, returns 0 (success) or -1 (timeout).

Flow in `payload_run()`:
```
payload_run() → detects MH_FILESET → hv_autoboot_xnu()
  → parse_macho() → hv_init() → hv_map_hw() → hv_start()
  → [XNU runs at EL1, IOKit starts, PMU driver runs]
  → [tick polls SPMI → PMU ACKs → hv_exit_cpu()]
  → restore HCR → return -1 to run_actions()
  → usb_init() → PMU awake → USB works
```

### First Test (2026-03-17): FAILED

Boot log (from display):
```
HV autoboot: FAILED ??? PMU did not exit standby
HV auto-boot failed (ret=-1) ??? falling through to proxy
No valid payload found
```

The HV ran for the full timeout but XNU never woke the PMU. Likely XNU crashed
immediately due to bugs in the initial implementation:

1. **virt_base was wrong**: set to iBoot's original `cur_boot_args.virt_base`
   instead of `vmin` (the lowest Mach-O segment vmaddr). This corrupts
   XNU's `slide = phys_base - virt_base` computation, causing all VA→PA
   translations to be wrong. XNU's MMU setup would triple-fault immediately.

2. **Entry point not found**: MH_FILESET kernelcaches don't have LC_UNIXTHREAD
   at the top level. The entry point is inside the `com.apple.kernel` sub-Mach-O
   (reached via LC_FILESET_ENTRY). Without this, we fell back to vmin — almost
   certainly wrong.

3. **Exception handler hung**: `hv_exc_proxy()` calls `uartproxy_run()` which
   spins forever waiting for USB proxy commands. If XNU faulted (due to bugs 1-2),
   the sync exception handler would enter this infinite loop. The EL2 timer FIQ
   might still fire, but `hv_exit_cpu()` sets `hv_should_exit` which is only
   checked in `hv_maybe_exit()` — not inside the proxy loop. The HV effectively
   deadlocks until the watchdog fires.

### Fixes Applied (iteration 26)

1. **virt_base = vmin**: `parse_macho()` now outputs `vmin` and the caller sets
   `ba->virt_base = vmin`. This makes `slide = (u64)image - vmin`, so
   `vmaddr + slide = image + (vmaddr - vmin)`, matching our segment layout.

2. **LC_FILESET_ENTRY parsing**: `find_entry_point()` scans for LC_FILESET_ENTRY
   with entry_id containing "kernel", then parses the sub-Mach-O for LC_UNIXTHREAD.
   Fallback chain: LC_UNIXTHREAD → `__TEXT_EXEC` vmaddr → fileset vmaddr →
   top-level `__TEXT` → vmin.

3. **Autoboot exception handling**: `hv_exc_proxy()` now checks
   `hv_autoboot_is_active()` and calls `hv_autoboot_exc()` instead of the proxy
   loop. `hv_autoboot_exc()` logs the first 5 exceptions (EC, ESR, ELR, FAR) and
   bails after 50 total. This prevents deadlocks and provides diagnostics.

4. **Timeout extended to 60s**: XNU IOKit matching takes time; 30s may be too short.

5. **Diagnostic output**: prints Mach-O filetype/ncmds, segment count/VA range,
   fileset entry names, entry point source, boot_args values (phys_base, virt_base,
   top_of_kdata, mem_size, devtree), MMIO mapping ranges, exception details.

6. **Extended MMIO mapping**: added 0x100000000-0x200000000 in addition to
   0x200000000-0x700000000.

### Build & Install

```bash
# Build m1n1
cd /Users/rusch/Projects/m1n1 && make -j$(nproc)

# Create concat payload
cat build/m1n1.bin \
    /Users/rusch/Projects/asahi_neo/research/firmware/kernelcache.mac17g.bin \
    > build/m1n1-xnu-payload.bin

# Install (from 1TR):
sh /Volumes/Data/Users/rusch/Projects/asahi_neo/scripts/reinstall_m1n1.sh
# (script auto-concatenates if kernelcache exists)
```

### What to Look for on Next Boot (iteration 26)

```
HV autoboot: Mach-O filetype=12 ncmds=...       ← filetype 12 = MH_FILESET ✓
HV autoboot: N segments, VA range 0x...          ← should be ~121MB range
HV autoboot: found fileset entry '..kernel..' at fileoff=0x...
HV autoboot: entry point from kernel LC_UNIXTHREAD: 0x...  ← real entry point
HV autoboot: phys_entry=0x... (virt=0x..., slide=0x...)
HV autoboot: boot_args at 0x...
  phys_base=0x... virt_base=0x...                ← virt_base should match VA range start
HV autoboot: launching XNU guest at phys 0x... (timeout 60s)
```

If XNU starts but crashes:
```
HV autoboot: guest exc #1 type=... ec=0x... esr=0x...
  elr=0x... far=0x...
```
→ EC=0x25 (data abort) with FAR in unmapped region: MMIO mapping gap
→ EC=0x24 (data abort from EL0) or EC=0x21 (instruction abort): wrong entry point
→ EC=0x18 (MSR/MRS trap): system register access trapped by HCR/HACR
→ No exceptions but timeout: XNU may be running but PMU init takes a different path

If PMU wakes:
```
HV autoboot: PMU exited standby! (pm_setting=0x...)
HV autoboot: SUCCESS — PMU is awake, proceeding to USB init
```

### Open Questions

1. **Does XNU's arm_init survive our boot_args?** We construct boot_args with
   `phys_base` pointing to heap memory, not the canonical iBoot load address.
   XNU's early code may validate boot_args fields beyond what we've patched.

2. **Is the ADT still valid?** We pass iBoot's original ADT (device tree), but
   XNU may check consistency between ADT memory-map entries and boot_args.
   The `Kernel_mach__header` entry in `/chosen/memory-map` still points to
   iBoot's original kernel address, not our relocated image.

3. **Will XNU reach IOKit?** XNU must pass arm_init → ml_static_mfree →
   kernel_bootstrap → bsd_init → IOKit matching → AppleDialogSPMIPMU::start().
   Any crash before IOKit means the PMU never wakes.

4. **Timer FIQ delivery**: With VHE (HCR_E2H=1), the physical timer (CNTP) is
   EL2's timer and the virtual timer (CNTV) is the guest's. XNU expects FIQ-based
   timer delivery via AIC. Our HCR config should allow this, but if XNU's timer
   setup conflicts with m1n1's tick, we may get double-fires or missed ticks.
