#!/usr/bin/env python3
"""
dump_adt.py — Dump Apple Device Tree from live hardware via m1n1.

Requires:
  - m1n1 running on target hardware with USB serial connected
  - m1n1 proxyclient: pip install -e path/to/m1n1/python
  - dtc (device tree compiler): brew install dtc

Usage:
  python3 dump_adt.py [--device /dev/cu.usbmodemXXXX] [--outdir ./adt_dump]

Outputs:
  adt.bin       Raw Apple Device Tree binary
  adt.fdt       FDT (standard) converted by m1n1's adt.py
  adt.dts       Human-readable DTS (via dtc)
  chip_id.txt   Chip identifier string (e.g., "t8132,0" for M4)
  memory.txt    DRAM regions parsed from ADT

This is essential for building the A18 Pro device tree for Linux.
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path


def find_serial_device() -> str:
    """Auto-detect m1n1 USB serial device on macOS."""
    import glob
    candidates = glob.glob("/dev/cu.usbmodem*")
    if not candidates:
        raise RuntimeError("No USB serial device found. Is m1n1 connected?")
    if len(candidates) > 1:
        print(f"[dump_adt] Multiple devices found: {candidates}")
        print(f"[dump_adt] Using first: {candidates[0]}")
    return candidates[0]


def dump_adt(device: str, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[dump_adt] Connecting to {device} ...")
    print("[dump_adt] ERROR: m1n1 proxyclient not yet integrated.")
    print()
    print("Manual steps until this script is complete:")
    print()
    print("  # In m1n1 proxyclient Python session:")
    print("  from m1n1.setup import *")
    print("  from m1n1.adt import load_adt")
    print("  import struct")
    print()
    print("  adt_data = u.get_adt()            # fetch raw ADT bytes")
    print("  open('adt.bin', 'wb').write(adt_data)")
    print()
    print("  adt = load_adt(adt_data)")
    print("  print(adt['/']['compatible'])     # reveals chip ID")
    print()
    print("  # Convert to FDT:")
    print("  # m1n1 does ADT→FDT conversion during normal boot.")
    print("  # For manual conversion, see m1n1/python/m1n1/adt.py")
    print()
    print("  # Key nodes to inspect for A18 Pro bringup:")
    print("  for node in adt: print(node._path)")


def parse_memory(adt_bin: Path) -> None:
    """Parse DRAM regions from saved ADT binary. Stub."""
    print(f"[parse_memory] Parsing {adt_bin} ...")
    print("[parse_memory] TODO: implement ADT binary parser")
    print("  Look for /chosen/dram-base and /memory nodes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump ADT from live hardware")
    parser.add_argument("--device", default=None)
    parser.add_argument("--outdir", default="./adt_dump")
    parser.add_argument("--parse-saved", metavar="ADT_BIN",
                        help="Parse a previously saved adt.bin (offline mode)")
    args = parser.parse_args()

    outdir = Path(args.outdir)

    if args.parse_saved:
        parse_memory(Path(args.parse_saved))
        return

    try:
        device = args.device or find_serial_device()
    except RuntimeError as e:
        print(f"[dump_adt] {e}")
        sys.exit(1)

    dump_adt(device, outdir)


if __name__ == "__main__":
    main()
