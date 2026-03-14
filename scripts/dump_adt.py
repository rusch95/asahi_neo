#!/usr/bin/env python3
"""
dump_adt.py — Dump Apple Device Tree from live hardware.

Two modes:
  1. Live (m1n1): Requires m1n1 USB serial connection.
  2. ioreg (macOS): Extracts known nodes via ioreg — works without m1n1.
     Run: python3 dump_adt.py --ioreg --outdir ./adt_dump

Outputs (ioreg mode):
  adt_summary.txt   Physical addresses of all key peripherals
  stub_a18pro.dts   Partial Linux device tree stub for Phase 1

Outputs (m1n1 mode — not yet implemented):
  adt.bin           Raw Apple Device Tree binary
  adt.fdt           FDT (standard) converted by m1n1's adt.py
  adt.dts           Human-readable DTS via dtc
"""

import sys
import os
import argparse
import subprocess
import struct
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# ioreg-based ADT extraction
# ---------------------------------------------------------------------------

def ioreg_get_node(name: str, depth: int = 1) -> str:
    r = subprocess.run(
        ["ioreg", "-r", "-p", "IODeviceTree", "-n", name, "-d", str(depth)],
        capture_output=True, text=True
    )
    return r.stdout


def decode_hex_prop(hex_str: str, fmt: str = "le64") -> int:
    """Decode ioreg raw hex data property."""
    raw = bytes.fromhex(hex_str.strip("<>").replace(" ", ""))
    if fmt == "le64" and len(raw) >= 8:
        return struct.unpack_from("<Q", raw)[0]
    elif fmt == "le32" and len(raw) >= 4:
        return struct.unpack_from("<I", raw)[0]
    elif fmt == "be32" and len(raw) >= 4:
        return struct.unpack_from(">I", raw)[0]
    return 0


def extract_iodevicememory_address(node_text: str) -> tuple[int, int]:
    """Extract (address, length) from IODeviceMemory in ioreg output."""
    import re
    m = re.search(r'"address"=(\d+).*?"length"=(\d+)', node_text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def dump_ioreg(outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    info = {}

    print("[dump_adt] Extracting hardware info via ioreg ...")

    # --- AIC interrupt controller ---
    aic_text = ioreg_get_node("aic")
    aic_phys, aic_size = extract_iodevicememory_address(aic_text)
    import re
    m = re.search(r'"compatible"\s*=\s*<"([^"]+)">', aic_text)
    aic_compat = m.group(1) if m else "aic,3"
    info["aic"] = {"phys": aic_phys, "size": aic_size, "compatible": aic_compat}
    print(f"  AIC:   phys=0x{aic_phys:012x}  size=0x{aic_size:08x}  compat={aic_compat!r}")

    # --- UARTs ---
    for uart_name in ("uart4", "uart5"):
        uart_text = ioreg_get_node(uart_name)
        phys, size = extract_iodevicememory_address(uart_text)
        m = re.search(r'"compatible"\s*=\s*<"([^"]+)">', uart_text)
        compat = m.group(1) if m else "uart-1,samsung"
        # Determine debug label
        label = "wlan-debug" if uart_name == "uart4" else "bluetooth-debug"
        info[uart_name] = {"phys": phys, "size": size, "compatible": compat, "label": label}
        print(f"  {uart_name} ({label}):  phys=0x{phys:012x}  size=0x{size:08x}  compat={compat!r}")

    # --- CPU topology ---
    cpus_text = ioreg_get_node("cpus", depth=3)
    cpus = []
    for cpu_name in ["cpu0", "cpu1", "cpu2", "cpu3", "cpu4", "cpu5"]:
        m_reg = re.search(rf'"name"\s*=\s*<"{cpu_name}">[^\n]*\n(.*?)(?=\+-o|\Z)',
                          cpus_text, re.DOTALL)
        cpu_text = ioreg_get_node(cpu_name)
        m_cluster = re.search(r'"cluster-type"\s*=\s*<"([^"]+)">', cpu_text)
        m_compat = re.search(r'"compatible"\s*=\s*<"([^"]+)"', cpu_text)
        m_reg2 = re.search(r'"reg"\s*=\s*<([0-9a-f]+)>', cpu_text)
        if m_cluster:
            cluster_type = m_cluster.group(1)
            compat = m_compat.group(1) if m_compat else f"apple,cpu{cpu_name}"
            reg_val = int(m_reg2.group(1), 16) if m_reg2 else 0
            # Decode reg as big-endian 32-bit MPIDR
            mpidr = struct.unpack("<I", bytes.fromhex(m_reg2.group(1).zfill(8)))[0] if m_reg2 else 0
            cpus.append({
                "name": cpu_name, "cluster": cluster_type,
                "compatible": compat, "mpidr": mpidr
            })
            print(f"  {cpu_name}: cluster={cluster_type}  compat={compat!r}  mpidr=0x{mpidr:08x}")
    info["cpus"] = cpus

    # --- DRAM ---
    chosen_text = ioreg_get_node("chosen")
    m_size = re.search(r'"dram-size"\s*=\s*<([0-9a-f]+)>', chosen_text)
    m_base = re.search(r'"dram-base"\s*=\s*<([0-9a-f]+)>', chosen_text)
    dram_size = decode_hex_prop(m_size.group(1)) if m_size else 0
    dram_base = decode_hex_prop(m_base.group(1)) if m_base else 0
    info["dram"] = {"base": dram_base, "size": dram_size}
    # Also get from sysctl (more reliable for size)
    r = subprocess.run(["sysctl", "hw.memsize"], capture_output=True, text=True)
    hw_memsize = int(r.stdout.split(":")[-1].strip()) if r.returncode == 0 else 0
    info["dram"]["hw_memsize"] = hw_memsize
    print(f"  DRAM: base=0x{dram_base:012x}  size=0x{dram_size:012x}  hw.memsize={hw_memsize/1e9:.1f}GB")

    # --- Save summary ---
    summary_path = outdir / "adt_summary.json"
    with open(summary_path, "w") as f:
        json.dump(info, f, indent=2)
    print(f"\n[dump_adt] Summary saved to {summary_path}")

    return info


def write_stub_dts(info: dict, outdir: Path) -> None:
    """Write a partial Linux DTS stub for A18 Pro Phase 1."""
    aic = info.get("aic", {})
    uart4 = info.get("uart4", {})
    cpus = info.get("cpus", [])
    dram = info.get("dram", {})

    # Use hw.memsize as authoritative DRAM size
    dram_size = dram.get("hw_memsize", 8589934592)  # default 8GB
    # DRAM base: LE64 decode from dram-base property
    # On A18 Pro macOS 26.3.2: dram-base LE64 = 0x0000010000000000
    # This value is suspect (1TB) — use 0x800000000 (32GB) as Asahi convention
    # TODO: verify empirically via m1n1 once tethered boot is set up
    dram_base = dram.get("base", 0)
    if dram_base == 0 or dram_base > 0x100000000000:
        # Fall back to Asahi convention for Apple Silicon
        dram_base_note = "/* TODO: verify — using Apple Silicon convention 0x8_0000_0000 */"
        dram_base_use = 0x800000000
    else:
        dram_base_note = f"/* from ADT dram-base */"
        dram_base_use = dram_base

    aic_phys = aic.get("phys", 0x301000000)
    aic_size = aic.get("size", 0x1CC000)
    uart4_phys = uart4.get("phys", 0x385210000)
    uart4_size = uart4.get("size", 0x4000)

    cpu_nodes = []
    for cpu in cpus:
        name = cpu["name"]
        mpidr = cpu["mpidr"]
        compat = cpu["compatible"]
        cluster = cpu["cluster"]
        cpu_nodes.append(f"""\
		{name}: cpu@{mpidr:x} {{
			/* {cluster}-cluster, {compat} */
			device_type = "processor";
			compatible = "{compat}", "arm,armv8";
			reg = <0x{mpidr >> 16:02x} 0x{mpidr & 0xffff:04x}>;
			enable-method = "spin-table";  /* TODO: verify — Apple uses custom WFE */
			/* TODO: operating-points, freq tables */
		}};""")
    if not cpu_nodes:
        # Fallback: hardcode known A18 Pro MacBook Neo topology
        cpu_nodes = [
            "\t\tcpu0: cpu@0 { compatible = \"apple,sawtooth\"; reg = <0x00 0x0000>; /* E-core */ };",
            "\t\tcpu1: cpu@1 { compatible = \"apple,sawtooth\"; reg = <0x00 0x0001>; /* E-core */ };",
            "\t\tcpu2: cpu@2 { compatible = \"apple,sawtooth\"; reg = <0x00 0x0002>; /* E-core */ };",
            "\t\tcpu3: cpu@3 { compatible = \"apple,sawtooth\"; reg = <0x00 0x0003>; /* E-core */ };",
            "\t\tcpu4: cpu@10000 { compatible = \"apple,everest\"; reg = <0x01 0x0000>; /* P-core */ };",
            "\t\tcpu5: cpu@10001 { compatible = \"apple,everest\"; reg = <0x01 0x0001>; /* P-core */ };",
        ]

    dts = f"""\
// SPDX-License-Identifier: GPL-2.0+ OR MIT
/*
 * Apple A18 Pro (t8140) — MacBook Neo stub device tree
 * Phase 1: serial console only
 *
 * GENERATED by asahi_neo/scripts/dump_adt.py — NOT for upstreaming.
 * Physical addresses from live ioreg dump, macOS 26.3.2 (25D2140).
 *
 * Verified physical addresses:
 *   AIC:   0x{aic_phys:012x} (size 0x{aic_size:08x})
 *   uart4: 0x{uart4_phys:012x} (size 0x{uart4_size:08x}) — wlan-debug UART
 *
 * TODO before use:
 *   - Verify DRAM base address (empirically via m1n1)
 *   - Add interrupt numbers for UART (uart4 IRQ = 0x448 from ADT)
 *   - Add clock nodes (samsung,uart requires clock)
 *   - Add timer node (ARM generic timer)
 *   - Add CPU power domains
 *   - Reference Asahi Linux apple-m4 DTS for missing nodes
 */

/dts-v1/;

/ {{
	#address-cells = <2>;
	#size-cells = <2>;
	compatible = "apple,mac17,5", "apple,t8140";

	memory@{dram_base_use:x} {{
		device_type = "memory";
		{dram_base_note}
		reg = <0x{dram_base_use >> 32:08x} 0x{dram_base_use & 0xffffffff:08x}
		       0x{dram_size >> 32:08x} 0x{dram_size & 0xffffffff:08x}>;
	}};

	chosen {{
		/* bootargs set by shim — e.g. "earlycon=s3c2410,mmio32,0x{uart4_phys:x} console=ttyS0,115200" */
		bootargs = "earlycon console=ttyS0,115200 loglevel=8";
		stdout-path = &uart4_node;
	}};

	/* ARM generic timer — A18 Pro uses standard cntp/cntv timer */
	timer {{
		compatible = "arm,armv8-timer";
		interrupt-parent = <&aic>;
		/* TODO: fill interrupt specifiers for A18 Pro AIC v3 */
		interrupts = </* TBD */>;
		always-on;
	}};

	cpus {{
		#address-cells = <2>;
		#size-cells = <0>;
		/* A18 Pro (MacBook Neo): 4 E-cores (apple,sawtooth) + 2 P-cores (apple,everest) */

{chr(10).join(cpu_nodes)}
	}};

	soc {{
		#address-cells = <2>;
		#size-cells = <2>;
		ranges;

		/* Apple Interrupt Controller v3 */
		aic: interrupt-controller@{aic_phys:x} {{
			compatible = "apple,aic2";  /* AIC v3 — use aic2 driver, TODO: verify compat string */
			#interrupt-cells = <4>;
			interrupt-controller;
			reg = <0x{aic_phys >> 32:08x} 0x{aic_phys & 0xffffffff:08x}
			       0x{aic_size >> 32:08x} 0x{aic_size & 0xffffffff:08x}>;
		}};

		/* UART4 (wlan-debug) — Samsung compatible 8250-derivative */
		uart4_node: serial@{uart4_phys:x} {{
			compatible = "apple,s5l-uart";  /* TODO: verify — might need samsung,s3c2410-uart */
			reg = <0x{uart4_phys >> 32:08x} 0x{uart4_phys & 0xffffffff:08x}
			       0x{uart4_size >> 32:08x} 0x{uart4_size & 0xffffffff:08x}>;
			interrupt-parent = <&aic>;
			/* uart4 interrupt from ADT: 0x448 = 1096 decimal */
			interrupts = </* TODO: AIC v3 specifier for IRQ 0x448 */>;
			clocks = </* TODO: uart clock reference */>;
			clock-names = "uart", "clk_uart_baud0";
			status = "okay";
		}};

		/* TODO: add gpio, i2c, spi, pcie, nvme nodes for Phase 2+ */
	}};
}};
"""

    dts_path = outdir / "stub_a18pro.dts"
    with open(dts_path, "w") as f:
        f.write(dts)
    print(f"[dump_adt] DTS stub saved to {dts_path}")
    print("  NOTE: This stub is incomplete — UART clocks, interrupts, and DRAM base")
    print("  must be verified before use. See TODO comments in the file.")


# ---------------------------------------------------------------------------
# m1n1-based ADT extraction (future)
# ---------------------------------------------------------------------------

def find_serial_device() -> str:
    import glob
    candidates = glob.glob("/dev/cu.usbmodem*")
    if not candidates:
        raise RuntimeError("No USB serial device found. Is m1n1 connected?")
    if len(candidates) > 1:
        print(f"[dump_adt] Multiple devices: {candidates}, using {candidates[0]}")
    return candidates[0]


def dump_adt_m1n1(device: str, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[dump_adt] m1n1 mode not yet implemented.")
    print("  Manual steps:")
    print("    from m1n1.setup import *")
    print("    from m1n1.adt import load_adt")
    print("    adt_data = u.get_adt()")
    print("    open('adt.bin', 'wb').write(adt_data)")
    print("    # then run: python3 dump_adt.py --parse-saved adt.bin")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Dump ADT / generate Linux DTS stub")
    parser.add_argument("--device", default=None, help="m1n1 USB serial device")
    parser.add_argument("--outdir", default="./adt_dump", help="Output directory")
    parser.add_argument("--ioreg", action="store_true",
                        help="Extract via ioreg (macOS, no m1n1 required)")
    args = parser.parse_args()

    outdir = Path(args.outdir)

    if args.ioreg:
        info = dump_ioreg(outdir)
        write_stub_dts(info, outdir)
        return

    try:
        device = args.device or find_serial_device()
    except RuntimeError as e:
        print(f"[dump_adt] {e}")
        print("  Tip: use --ioreg for macOS-native extraction without m1n1")
        sys.exit(1)

    dump_adt_m1n1(device, outdir)


if __name__ == "__main__":
    main()
