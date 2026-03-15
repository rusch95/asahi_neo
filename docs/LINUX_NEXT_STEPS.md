# Linux Host: Next Steps After First m1n1 Boot

**Status as of 2026-03-14**: m1n1 (46fc983) boots successfully on A18 Pro (t8140,
MacBook Neo, j700ap). Confirmed EL2, RAM base 0x10000000000, AIC v3 @ 0x301000000,
DT compatible `apple,j700`. Machine is sitting in `Running proxy...` waiting for
USB serial connection.

---

## What You Have (on the macOS side)

| Artifact | Path |
|---|---|
| m1n1 source + proxyclient | `/Users/rusch/Projects/m1n1/` |
| Linux kernel (Image, 7 MB) | `/Users/rusch/Projects/linux-asahi/arch/arm64/boot/Image` |
| Stub DTB | `/Users/rusch/Projects/asahi_neo/research/adt_dump/stub_a18pro.dtb` |
| Stub DTS | `/Users/rusch/Projects/asahi_neo/research/adt_dump/stub_a18pro.dts` |

Transfer these to the Linux host before connecting the USB cable.

---

## Step 0: Transfer Files to Linux Host

```bash
# From Linux host (replace MAC_IP):
scp -r rusch@MAC_IP:/Users/rusch/Projects/m1n1/proxyclient ~/m1n1-proxyclient
scp rusch@MAC_IP:/Users/rusch/Projects/linux-asahi/arch/arm64/boot/Image ~/Image
scp rusch@MAC_IP:/Users/rusch/Projects/asahi_neo/research/adt_dump/stub_a18pro.dtb ~/
```

---

## Step 1: Install Proxyclient Dependencies

```bash
pip3 install pyserial construct
```

The proxyclient also needs `parted` and a few other tools for disk ops — not needed
for kernel loading.

---

## Step 2: Connect and Open a Shell

Connect USB-C from the Mac (A18 Pro) to the Linux host. The Mac appears as a USB
serial ACM device:

```bash
ls /dev/ttyACM*   # should show /dev/ttyACM0
```

Open an interactive m1n1 shell:

```bash
cd ~/m1n1-proxyclient
M1N1PROXY=/dev/ttyACM0 python3 tools/shell.py
```

You get a Python REPL with full access to the hardware via `u` (utils) and `p`
(proxy) objects.

---

## Step 3: First Things to Do in the Shell

### 3a. Dump the full ADT

The ADT (Apple Device Tree) from iBoot contains all peripheral addresses,
interrupt numbers, and power domain info for t8140. This is the primary source of
truth for writing DTS nodes.

```python
# In shell.py:
adt_data = u.iface.readmem(u.ba.devtree, 0x100000)   # 1 MB should be enough
open("/tmp/adt_a18pro.bin", "wb").write(adt_data)

# Or use the built-in:
import adt
tree = adt.load(u.iface, u.base)
# Walk it:
for node in tree:
    print(node.name, getattr(node, "compatible", ""))
```

Parse the saved binary on the Linux host:
```bash
cd ~/m1n1-proxyclient
python3 tools/adt.py /tmp/adt_a18pro.bin > adt_dump.txt
```

Key things to extract from ADT:
- All `uart*` node addresses and IRQ numbers
- `arm-io` base and `arm-io/pmgr` (power manager) structure
- `aic` interrupt controller full register map
- `cpu*` nodes for correct CPU topology
- `mcc` node (MCC = Memory Channel Controller — currently unsupported, causes warning)
- `iop-*` nodes for coprocessors

### 3b. Verify UART4 address

```python
# Read UART4 ULCON register (offset 0) — should be 0x03 (8N1)
val = p.read32(0x385210000)
print(hex(val))
```

### 3c. Check SCTLR_EL2 and CPU state

```python
print(hex(u.mrs("SCTLR_EL2")))
print(hex(u.mrs("ID_AA64MMFR0_EL1")))   # memory model features
print(hex(u.mrs("MIDR_EL1")))            # CPU revision
```

### 3d. Dump pmgr ps-regs (investigate the boot warning)

```python
# pmgr complained about missing ps-regs — find the pmgr node in ADT and dump
# whatever address it expects
# Look for "pmgr" in ADT, find its reg property
```

---

## Step 4: Boot the Linux Kernel

Use `tools/linux.py` to load and boot Linux directly. This is the tethered boot path
— no persistence, runs entirely over USB.

```bash
cd ~/m1n1-proxyclient
M1N1PROXY=/dev/ttyACM0 python3 tools/linux.py \
    -b "earlycon=s3c2410,mmio32,0x385210000 console=ttyS0,115200 loglevel=8" \
    ~/Image ~/stub_a18pro.dtb
```

If the serial console needs a custom initramfs (to avoid rootfs panic):
```bash
M1N1PROXY=/dev/ttyACM0 python3 tools/linux.py \
    -b "earlycon=s3c2410,mmio32,0x385210000 console=ttyS0,115200 loglevel=8" \
    ~/Image ~/stub_a18pro.dtb ~/initramfs.cpio.gz
```

A minimal initramfs can be built with busybox. For early bringup, the kernel
panicking on rootfs mount is fine — you want to see how far the boot log gets.

Serial console output from the Mac will appear in the proxyclient terminal.

---

## Step 5: What to Expect / Debug

### Likely first failures

| Symptom | Likely cause | Fix |
|---|---|---|
| No earlycon output | UART4 address wrong or clock not running | Try different UART node from ADT dump |
| Kernel hangs at timer init | AIC v3 interrupt specifier wrong | Check ADT aic node, compare to M4 DTS |
| Kernel panics at GIC probe | Wrong interrupt controller compat | Verify `apple,aic2` vs `apple,aic3` in asahi kernel |
| `Synchronous Exception` at EL1 | MMU/page table issue | Check DRAM region in DTS, 16K page config |

### Known issues in current stub DTS

1. **AIC interrupt specifier for uart4** — format is `<AIC_IRQ die irq flags>`.
   IRQ 0x448 (1096 dec) from ADT. Die is 0 for die 0 (single-die view).
   Need to verify whether AIC v3 on t8140 uses 1 or 2 dies in the DT view
   (m1n1 reports "1/2 dies").

2. **ARM generic timer interrupts** — `timer` node has empty `interrupts`.
   For AIC v3, the timer IRQs are FIQ-based, not routed through AIC.
   The `arm,armv8-timer` node on Apple Silicon typically has no `interrupts`
   property — the FIQ wiring is handled by m1n1/hypervisor context.
   Remove the `interrupts` line and the `interrupt-parent` from the timer node.

3. **CPU enable-method** — `spin-table` is wrong. Apple Silicon CPUs use a custom
   WFE-based method. In the Asahi kernel this is handled by `apple,cluster-cpus`
   and the PMGR. For initial single-CPU boot, comment out cpu1–cpu5 entirely.

4. **MCC (mcc,t8140)** — Causes a warning but does not prevent booting. The memory
   channel controller is not yet modelled for t8140.

---

## Step 6: DTS Iteration Loop

For each boot attempt, the iteration cycle is:

1. Edit `stub_a18pro.dts` on Linux (or macOS and rsync)
2. `dtc -I dts -O dtb stub_a18pro.dts -o stub_a18pro.dtb`
3. Re-run `tools/linux.py` — no need to reboot the Mac between attempts,
   m1n1 proxy stays running until you reboot

This is much faster than flashing — the tethered proxy loop lets you iterate in
seconds.

---

## Step 7: Once Serial Console Works

Once `earlycon` output appears, priorities are:

1. **Get a full dmesg** — see what drivers probe successfully
2. **Check AIC probing** — `apple,aic2` driver must bind for interrupts to work
3. **Add missing DTS nodes from ADT dump** — uart (full), gpio, i2c, nvme
4. **Attempt multi-CPU bring-up** — use proxyclient to poke PMGR power domains first

---

## Key Confirmed Facts (do not re-derive)

| Fact | Value | Source |
|---|---|---|
| DRAM base | `0x10000000000` | m1n1 boot screen 2026-03-14 |
| AIC base | `0x301000000` | m1n1 boot screen + ADT |
| AIC version | 3 (1/2 dies) | m1n1 boot screen |
| DT compatible | `apple,j700`, `apple,t8140` | m1n1 boot screen |
| Chip ID | `0x8140` | m1n1 boot screen |
| macOS FW | `26.3 / iBoot-13822.81.10` | m1n1 boot screen |
| Display | 2408×1506, already init by iBoot | m1n1 boot screen |
| EL level | EL2 | m1n1 boot screen |
| m1n1 commit | `46fc983` | built on macOS, at HEAD of main |

---

## m1n1.bin: Do Not Rebuild

The current `m1n1.bin` at `46fc983` is HEAD of AsahiLinux/m1n1 main and boots
correctly. Do not rebuild unless you have a specific fix to apply. The MCC and
cpufreq warnings are expected — they reflect missing t8140 support in m1n1, not
build problems.

If you do rebuild, the macOS build command is:
```bash
# On macOS, in /Users/rusch/Projects/m1n1/:
make ARCH=aarch64-linux-gnu- RELEASE=1
# Then re-run kmutil configure-boot to update the installed boot object
```
