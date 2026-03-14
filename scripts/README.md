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
