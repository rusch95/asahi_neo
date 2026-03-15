# USB Serial Debug — m1n1 Proxy Not Enumerating

**Status as of 2026-03-15**

m1n1 boots and shows its boot screen on the MacBook Neo display, but does not
enumerate as a USB ACM device on the Linux host. No `/dev/ttyACM*` appears, and
`lsusb` shows no Apple device.

---

## What We Know

| Fact | Value |
|------|-------|
| m1n1 commit | `46fc983` (HEAD of AsahiLinux/m1n1 main) |
| Board | MacBook Neo, j700ap, A18 Pro (t8140), Mac17,5 |
| m1n1 boot screen | Visible on display — iBoot framebuffer working |
| USB device on Linux | Not appearing at all in `lsusb` |
| Cable | Confirmed data cable (same cable enumerates iPhone fine) |
| Port tried | Left USB-C port (USB 3, 10 Gbps) |
| Linux host | `/dev/ttyACM*` never appears |

---

## Most Likely Cause

**t8140 USB controller not initialized by m1n1.**

m1n1 has no official t8140 support — it was built targeting M4 as the closest
proxy. The USB controller on t8140 likely has a different base address or
initialization sequence. The display output is from iBoot's framebuffer and
does not confirm m1n1's USB stack is working.

---

## What to Check on the Mac Side

### 1. Find the USB controller address in the ADT

The ADT dump has the USB controller addresses. Compare against what m1n1 expects:

```bash
# In m1n1 source, look for USB controller initialization:
grep -r "usb\|dwc\|xhci\|typec" /Users/rusch/Projects/m1n1/src/ -i -l
```

Key file to check: `src/usb.c` or similar. Find what base address m1n1 uses
for the USB controller and compare to the ADT dump at
`research/adt_dump/adt_summary.json`.

### 2. Check ADT for USB nodes

```bash
python3 -c "
import json
adt = json.load(open('research/adt_dump/adt_summary.json'))
for k,v in adt.items():
    if 'usb' in k.lower() or 'atc' in k.lower() or 'dwc' in k.lower():
        print(k, v)
"
```

Look for nodes with `atc` (Apple Thunderbolt Controller), `usb-drd`, or `dwc3`.

### 3. Check m1n1 boot log

If there's any UART output from m1n1 (requires a working serial connection —
chicken-and-egg problem), look for USB init errors. Alternatively, check if
m1n1 logs to the framebuffer on boot failure.

### 4. Check m1n1 t8140 USB support

```bash
grep -r "t8140\|j700\|a18\|0x8140" /Users/rusch/Projects/m1n1/src/ -i
grep -r "usb_init\|usb_setup" /Users/rusch/Projects/m1n1/src/
```

If t8140 is not in m1n1's USB device table, USB will silently fail to init.

---

## Possible Fixes

### Option A — Patch m1n1 USB init for t8140

If the USB controller address for t8140 differs from M4, add t8140 to m1n1's
USB device table with the correct address from the ADT. Rebuild and reinstall.

Reinstall command (confirmed for macOS 26 / iBoot 13822.81.10):
```bash
kmutil configure-boot -c build/m1n1.bin \
    --raw --entry-point 2048 --lowest-virtual-address 0 \
    -v /Volumes/<stub>
```
Then re-run `bless --mount /Volumes/<stub> --setBoot`.

### Option B — Use m1n1 UART instead of USB

If the USB controller can't be fixed quickly, m1n1 also exposes a UART debug
interface. On Apple Silicon this is typically on one of the debug UART pads.
Not practical without hardware modification.

### Option C — Boot Linux directly without proxyclient

If USB proxy is not achievable, use iBoot + m1n1 in chainload mode to boot
Linux directly from a pre-baked payload stored on the APFS container, instead
of loading over USB. This loses the interactive debug loop but gets Linux booting.

---

## Boot Setup State (as of 2026-03-15)

The stub volume setup required non-obvious steps — document for next time:

1. `bputil -nkcas` from 1TR (authenticate as stub user)
2. `csrutil disable` from 1TR
3. `kmutil configure-boot -c m1n1.bin --raw --entry-point 2048 --lowest-virtual-address 0 -v /Volumes/<stub>` from 1TR (requires Macintosh HD mounted)
4. `bless --mount /Volumes/<stub> --setBoot` from 1TR — **required, stub won't appear in picker without this**

Step 4 is the non-obvious one. Without `bless`, the stub volume does not appear
in the startup picker even with a valid boot object installed.
