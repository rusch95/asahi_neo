#!/usr/bin/env python3
"""
probe_sptm.py — Log SPTM (genter) calls during XNU boot via m1n1 hypervisor.

Requires:
  - m1n1 running on target hardware with USB serial connected
  - m1n1 proxyclient installed: pip install -e path/to/m1n1/python
  - XNU (or custom kernelcache) as the guest OS

Usage:
  python3 probe_sptm.py [--device /dev/cu.usbmodemXXXX] [--output sptm_log.json]

What it does:
  Sets a hypervisor hook on the `genter` instruction entry point in GXF.
  Each time GXF EL2 is entered (i.e., every SPTM call), we record:
    - Timestamp (relative to boot)
    - x0 (call number)
    - x1-x3 (first three arguments)
    - EL1 return address (tells us which XNU function made the call)
  Output is a JSON log for offline analysis.

NOTE: This is a stub. Implementation requires understanding of m1n1's HV API
and the specific GXF entry point address on target hardware. See:
  - m1n1/python/m1n1/hv/ for hypervisor API
  - ARCHITECTURE.md Option C for context
"""

import sys
import json
import argparse
from datetime import datetime

# TODO: replace with actual m1n1 proxyclient imports once available
# from m1n1.setup import *
# from m1n1.hv import HV

SPTM_LOG_VERSION = 1

# Known SPTM call numbers (UNVERIFIED — placeholder until extract_sptm_calls.py runs)
# Format: call_number -> (name, arg_description)
SPTM_CALL_NAMES: dict[int, tuple[str, str]] = {
    # These are guesses based on XNU source review. DO NOT TRUST.
    0x00: ("SPTM_BOOTSTRAP",    "x1=ttbr0, x2=ttbr1, x3=flags"),
    0x01: ("SPTM_CPU_INIT",     "x1=cpu_id, x2=stack, x3=flags"),
    0x10: ("SPTM_MAP_PAGE",     "x1=va, x2=pa, x3=prot"),
    0x11: ("SPTM_UNMAP_PAGE",   "x1=va, x2=asid, x3=flags"),
    0x12: ("SPTM_CHANGE_PERM",  "x1=va, x2=new_prot, x3=flags"),
    # Add entries as extract_sptm_calls.py reveals them
}


def decode_call(x0: int, x1: int, x2: int, x3: int) -> dict:
    name, arg_desc = SPTM_CALL_NAMES.get(x0, (f"UNKNOWN_0x{x0:04x}", ""))
    return {
        "call_number": x0,
        "name": name,
        "arg_description": arg_desc,
        "x1": f"0x{x1:016x}",
        "x2": f"0x{x2:016x}",
        "x3": f"0x{x3:016x}",
    }


def run_probe(device: str, output_path: str) -> None:
    print(f"[probe_sptm] Connecting to {device} ...")
    print("[probe_sptm] ERROR: m1n1 proxyclient not yet integrated.")
    print("[probe_sptm] TODO: implement HV hook on GXF entry vector.")
    print()
    print("Manual steps until this script is complete:")
    print("  1. Connect USB-C serial to target hardware")
    print("  2. Boot into m1n1 hypervisor mode")
    print("  3. Use m1n1 proxyclient to load XNU as guest")
    print("  4. Add a trap on the GXF entry vector (address TBD from ADT)")
    print("  5. Log x0-x3 at each genter call")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Log SPTM calls via m1n1 hypervisor")
    parser.add_argument("--device", default=None,
                        help="USB serial device (auto-detect if omitted)")
    parser.add_argument("--output", default=f"sptm_log_{datetime.now():%Y%m%d_%H%M%S}.json",
                        help="Output JSON log file")
    args = parser.parse_args()

    device = args.device or "/dev/cu.usbmodem001"  # adjust as needed
    run_probe(device, args.output)


if __name__ == "__main__":
    main()
