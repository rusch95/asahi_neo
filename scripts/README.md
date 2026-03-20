# scripts — Testing & Analysis Scripts

All scripts should be runnable from a development machine connected to the target
hardware via USB-C serial (m1n1 tethered boot), or offline against extracted files.

## Planned Scripts

### SPTM Reverse Engineering

**extract_sptm_calls.py**
Extract the SPTM call table from an XNU kernelcache image.
Usage: `python3 extract_sptm_calls.py <kernelcache.img>`
Output: JSON mapping call numbers to names/signatures (best-effort from symbols)

**diff_sptm_blobs.py**
Compare SPTM firmware blobs from two IPSWs (e.g., M4 vs A18 Pro).
Usage: `python3 diff_sptm_blobs.py <m4.ipsw> <a18pro.ipsw>`
Output: structural diff, identifies shared vs divergent functions

### m1n1 Proxyclient Extensions

**probe_sptm.py**
Run over m1n1 hypervisor to log all SPTM (`genter`) calls during XNU boot.
Usage: `python3 probe_sptm.py` (requires m1n1 USB serial on /dev/cu.usbmodem*)
Output: timestamped log of call numbers and arguments

**dump_adt.py**
Dump the Apple Device Tree from live hardware and save as both ADT binary and
converted FDT (for inspection with `fdtdump`).
Usage: `python3 dump_adt.py`
Output: `adt.bin`, `adt.fdt`

**probe_registers.py**
Dump key system registers (GXF, SPTM, AIC) at a specified boot phase.
Usage: `python3 probe_registers.py --phase post-sptm-init`

### Linux Payload Tools

**pack_linux_payload.sh**
Packages a Linux Image + initramfs + DTB into the format expected by the shim.
Usage: `./pack_linux_payload.sh <Image.gz> <initramfs.cpio.gz> <device.dtb>`
Output: `linux_payload.bin` ready to write to Preboot partition

**verify_dtb.sh**
Runs `fdtdump` and basic sanity checks on a device tree blob.
Usage: `./verify_dtb.sh <device.dtb>`

### Build & Flash Helpers

**reinstall_m1n1.sh**
Install m1n1 (with optional XNU kernelcache payload) into the Linux stub volume.

| Mode | Environment | What it does |
|------|-------------|-------------|
| `(default)` | macOS or 1TR | Fast update — overwrites existing boot object on Preboot. No bputil/kmutil. |
| `--create-stub` | **macOS** | Creates a simple Linux APFS partition. One-time. |
| `--setup` | **macOS 1TR** | Runs `kmutil configure-boot --raw` + `bless`. Requires `csrutil disable` and `bputil -nkcas` to have been run first. |

First-time install workflow:
```
# 1. From macOS — create the Linux partition
sudo sh reinstall_m1n1.sh --create-stub

# 2. Reboot to macOS 1TR (hold power → Options → Terminal)
csrutil disable
bputil -nkcas
#   (select Linux when prompted, enter macOS credentials)

# 3. Install m1n1 (still in 1TR)
diskutil apfs unlockVolume disk4s5
sh /Volumes/Data/Users/rusch/Projects/asahi_neo/scripts/reinstall_m1n1.sh --setup

# 4. Hold power → select macOS to restore normal boot
# 5. Subsequent m1n1 updates from macOS (no 1TR needed):
sudo sh reinstall_m1n1.sh
```

Notes on Apple Silicon boot security (learned the hard way):
- `bputil -nkcas` and `kmutil configure-boot --raw` both run from **macOS 1TR**
  (hold power → Options → Terminal). This is the simplest approach and was
  confirmed working on A18 Pro / macOS 26.
- The stub is a simple APFS volume in its own container. No volume group, no
  recovery OS image, no IPSW-derived files needed for the simple approach.
- `bless --mount /Volumes/Linux --setBoot` makes the stub appear in the boot picker.
- If the LocalPolicy gets corrupted (e.g. from deleting boot objects), the fix is
  to delete the stub entirely and recreate from scratch. Attempting to repair a
  broken LocalPolicy leads to "code pairing (17)" errors that cannot be resolved
  without a full recreate.
- The Asahi installer's approach (volume groups, paired recovery, step2.sh) is more
  complex and designed for M1/M2. On A18 Pro / macOS 26, the recovery pairing
  mechanism doesn't work correctly with the standard Asahi tooling — the machine
  always enters the macOS recovery instead of the stub's paired recovery.

**build_kernelcache.sh**
Builds the custom XNU+shim kernelcache and signs it for Permissive Security.
(Stub — implementation after shim is written)

**flash_preboot.sh**
Writes the Linux payload to the correct offset in the Preboot APFS partition.
(Stub — dangerous, will require explicit confirmation prompt)

## Dependencies

- Python 3.11+
- m1n1 proxyclient: `pip install -e path/to/m1n1/python`
- `dtc` (device tree compiler): `brew install dtc`
- `jtool2` or `joker` for kernelcache analysis
- `radare2` or `Ghidra` for SPTM blob disassembly

## Safety Notes

Scripts that write to hardware (`flash_preboot.sh`) will:
1. Print the exact bytes and target partition before writing
2. Require typing `CONFIRM` to proceed
3. Never touch the macOS container

Never run `flash_preboot.sh` without first confirming partition layout with `dump_adt.py`.
