# USB Serial Debug — m1n1 Proxy Not Enumerating

**Status as of 2026-03-15 — ROOT CAUSE FOUND**

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
