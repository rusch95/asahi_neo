# ASAHI_REFERENCE.md — Distilled Asahi Linux Notes

Last updated: 2026-03-14

This document captures findings from the Asahi Linux project that are directly
relevant to the asahi_neo effort. It is a reference, not a copy — link to upstream
docs rather than duplicating them. Asahi Linux docs: https://asahilinux.org/docs/

---

## Boot Chain Summary

From Asahi's pc-boot-differences.md and linux-bringup.md:

```
SecureROM (ROM, immutable)
  └─► iBoot stage 1 (NOR flash)
        └─► iBoot stage 2 (SSD, APFS Preboot partition)
              └─► kernelcache (from APFS container)
```

- iBoot cannot boot from external storage; it always reads from the SSD APFS container.
- Linux is installed as a "shell macOS" — a valid APFS container with iBoot stubs +
  a non-Apple-signed kernelcache (m1n1) enrolled under Permissive Security.
- Enrollment in Permissive Security requires physical access and 1TR (One True Recovery).
- This **never** touches the macOS container's security settings.

**m1n1** sits at the kernelcache slot and handles:
- ADT → FDT device tree conversion
- CPU bring-up and SMP spinup
- Chainloading U-Boot → GRUB → Linux, or directly loading Linux
- Optional: hypervisor mode for debugging

---

## Permissive Security — How to Enroll and Install m1n1

This is the procedure for Phase 1 tethered boot. Requires physical access.
**The macOS container is never touched — work in a separate APFS container.**

### Step 1 — Create a macOS stub container (if not already done)

In macOS: Disk Utility → your internal SSD → Partition → add a new partition.
Or use `diskutil apfs addVolume disk0 "APFS" "Linux" -role B` from Terminal.
Leave at least 2 GB; the stub only needs a few MB but spare space is needed for Phase 2+.

### Step 2 — Install macOS stub into the container

The container must look like a valid macOS install to iBoot. Asahi's installer
creates a stub automatically; for the manual/expert path:
```bash
# From recoveryOS or a second Mac booted with target disk mode
# Asahi's "expert install" script handles this:
curl https://alx.sh | sh   # NOT recommended for unsupported chips
# Instead: use the manual APFS stub creation from Asahi docs
```
For A18 Pro (unsupported), follow the Asahi "expert install" path from their wiki
to create the stub without relying on the installer's chip checks.

### Step 3 — Enable Permissive Security (1TR)

1. Boot into 1TR: hold power button → "Loading startup options" → Options
2. Open Terminal from Utilities menu
3. Identify the stub volume: `diskutil list`
4. `csrutil disable --volume /Volumes/<stub>` — disables SIP for that container only
5. `bputil -a --volume /Volumes/<stub>` — sets BootPolicy to Permissive
6. Reboot into macOS normally

### Step 4 — Install m1n1 as the boot object

```bash
# From macOS (not recoveryOS), with the stub volume mounted:
kmutil configure-boot -v /Volumes/<stub> \
    --custom-boot-object /path/to/m1n1.bin \
    --raw-payload
```

This replaces the kernelcache slot with m1n1. On next boot selecting that volume,
iBoot loads m1n1 directly. m1n1 waits ~5 s for a USB proxyclient connection.

> **⚠️ Caveats for A18 Pro (macOS 26):** The exact `kmutil` flags may differ.
> Verify the command against the Asahi installer source for your iBoot version
> (13822.81.10). If `--raw-payload` is rejected, try without it; m1n1.macho may
> be needed instead of m1n1.bin for signed payload paths.

### Step 5 — Tethered boot via proxyclient

On the Linux host machine:
```bash
pip install pyserial
# USB-C cable plugged in BEFORE powering on the MacBook Neo
# Select the m1n1 volume at startup
export M1N1PROXY=/dev/ttyACM0   # or ttyUSB0 — check dmesg
cd /path/to/m1n1/proxyclient
python3 tools/linux.py \
    /path/to/Image \
    /path/to/stub_a18pro.dtb \
    [/path/to/initramfs.cpio.gz]
```

The proxyclient will push the kernel, DTB, and optional initramfs over USB.
First expected output on UART: `[    0.000000] Booting Linux on physical CPU 0x0`

---

## m1n1 Hypervisor — Development Workflow

From m1n1-hypervisor.md (https://raw.githubusercontent.com/AsahiLinux/docs/main/docs/sw/):

- m1n1 runs at EL2 and presents a USB serial interface
- Python proxyclient connects over USB-C serial at 115200 baud
- Can load kernel payloads, dump registers, intercept exceptions
- Can run XNU as a guest (for SPTM observation via Option C in ARCHITECTURE.md)
- Key tools: `python/m1n1/fw/`, `proxyclient/tools/`

**Built:** `build/m1n1.bin` (1.0 MB) at `/Users/rusch/Projects/m1n1/build/` — 2026-03-14

**Proxyclient setup (Linux host):**
```bash
pip install pyserial
# Plug USB-C cable before booting MacBook Neo
# MacBook Neo enumerates as /dev/ttyACM0 (Linux) when m1n1 is running
export M1N1PROXY=/dev/ttyACM0
python3 proxyclient/tools/linux.py Image stub_a18pro.dtb [initramfs.cpio.gz]
```

**For asahi_neo:** This is our primary research and debugging environment.
We should extend the proxyclient with SPTM call logging hooks (scripts/probe_sptm.py).

---

## ADT — Apple Device Tree

Apple firmware passes its own device tree format (ADT) rather than standard FDT.
m1n1 converts ADT → FDT for Linux. Key properties:

- ADT nodes include register addresses, interrupt numbers, DMA channels
- `compatible` strings follow Apple's own scheme (e.g., `apple,t8103-uart`)
- m1n1's `python/m1n1/adt.py` parses ADT live from hardware

**A18 Pro (MacBook Neo) ADT confirmed — 2026-03-14:**
Chip: `t8140`, board: `Mac17,5`. Key physical addresses (from live ioreg dump):

| Node | Physical address | Size | Notes |
|------|-----------------|------|-------|
| AIC | `0x301000000` | `0x1CC000` | compatible `aic,3` |
| uart4 (wlan-debug) | `0x385210000` | `0x4000` | use for earlycon |
| uart5 (bt-debug) | `0x385214000` | `0x4000` | backup |
| DRAM base | `0x10000000000` | 8 GB | **SUSPECT — verify via m1n1** |

CPU topology: 4× E-core `apple,sawtooth` (MPIDR 0–3) + 2× P-core `apple,everest`
(MPIDR 0x100–0x101). Stub DTS: `research/adt_dump/stub_a18pro.dts`.

Once tethered boot is working, verify DRAM base with:
```python
# via m1n1 proxyclient
from m1n1.setup import *
adt = load_adt(u.get_adt())
print(hex(adt["/chosen"]["dram-base"]))
print(hex(adt["/chosen"]["dram-size"]))
```

---

## Linux Bringup Notes

### macOS host build (confirmed 2026-03-14)

macOS lacks `elf.h`, `byteswap.h`, and has `uuid_t` / `sed` incompatibilities.
Required shims in `linux-asahi/.host_include/`:

| File | Purpose |
|------|---------|
| `elf.h` | Standalone ELF types (no Linux UAPI dependency) |
| `byteswap.h` | Wraps `OSByteOrder.h` → `bswap_16/32/64` |
| `gethostuuid.h` | Empty stub (prevents uuid_t conflict) |
| `sys/_types/_uuid_t.h` | Suppresses macOS flat-array `uuid_t` |

Also needed: `scripts/mod/Makefile` line `HOSTCFLAGS_file2alias.o += -D_UUID_T`,
`.build_tools/sed` symlink → `gsed` (from `brew install gnu-sed`),
`brew install make bison lld`.

**Build command:**
```bash
PATH=".build_tools:$(brew --prefix llvm)/bin:$(brew --prefix bison)/bin:$PATH" \
gmake ARCH=arm64 LLVM=1 HOSTCFLAGS="-I.host_include" -j$(sysctl -n hw.ncpu) Image
```
Output: `arch/arm64/boot/Image` (7.0 MB, 16K pages). Kernel tree: `AsahiLinux/linux asahi` branch.

### Minimal config for first boot

From linux-bringup.md:
- `CONFIG_ARCH_APPLE=y`
- `CONFIG_SERIAL_SAMSUNG=y` — driver for `apple,s5l-uart` compatible string
- `CONFIG_EARLYCON=y` — DT-driven, no address needed in bootargs
- Disable everything else — no AGX, no DCP, no USB host

**UART details (A18 Pro):** `compatible = "apple,s5l-uart"`, earlycon driver
`s3c2410` (via `OF_EARLYCON_DECLARE`). Clock: 24 MHz fixed oscillator.
`reg-io-width = <4>`. bootargs: `"earlycon console=ttyS0,115200 loglevel=8"`.

USB cables/hubs must be connected **before** boot — the USB PHY setup happens in
m1n1/iBoot and is not redone by Linux.

**Don't mix DTBs from different kernel versions.** Use the DTB generated by the
kernel you're booting (i.e., `stub_a18pro.dtb` compiled by `dtc` from our stub).

---

## Asahi Feature Support by Chip Generation

| Feature | M1 | M2 | M3 | M4 | A18 Pro |
|---------|----|----|----|----|---------|
| Linux boots | ✓ | ✓ | ✓ | WIP | Goal of this project |
| SPTM present | No | No | Yes (A16-gen) | Yes | Yes |
| m1n1 support | ✓ | ✓ | ✓ | Partial | No |
| AGX driver | ✓ | ✓ | ✓ | WIP | No |
| DCP (display) | ✓ | ✓ | WIP | No | No |
| NVMe | ✓ | ✓ | ✓ | WIP | No |

Sources: Asahi Linux blog posts and feature-support docs. Status as of 2026-03-14.
Verify against upstream before acting on this table.

---

## AGX GPU Driver Notes (from agx-driver-notes.md)

The Asahi AGX driver (asahi-drm) uses:
- DRM/KMS framework
- A custom UAPI inspired by Intel Xe
- RTKit firmware running on the GPU coprocessor

The GPU firmware is chip-specific and must be extracted from the IPSW. For A18 Pro
the firmware identifier and version need to be determined. The driver has a firmware
version table; a new chip requires adding an entry.

AGX generations: G13 (M1), G14 (M2), G15/16 (M3), G18 (M4 / likely A18 Pro).

**IntegralPilot M3 DOOM context:** See docs/GRAPHICS.md for how that patch got
hardware graphics without the full Asahi AGX driver being upstreamed on M3.

---

## Key Asahi Repositories

| Repo | Purpose |
|------|---------|
| AsahiLinux/linux | Linux kernel with Apple Silicon patches |
| AsahiLinux/m1n1 | Stage 2 bootloader / hypervisor |
| AsahiLinux/docs | Documentation (what this file summarizes) |
| AsahiLinux/PKGBUILDs | Distro packaging |
| AsahiLinux/asahi-installer | Installer for end users |

For asahi_neo, the most relevant is `AsahiLinux/linux` (M4 branch) and `AsahiLinux/m1n1`.
