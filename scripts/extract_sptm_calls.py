#!/usr/bin/env python3
"""
extract_sptm_calls.py — Extract SPTM call table from XNU kernelcache.

Requires:
  - An extracted kernelcache (decompressed Mach-O)
  - Python 3.11+
  - Optional: lief (pip install lief) for Mach-O parsing
  - Optional: capstone (pip install capstone) for disassembly

Usage:
  python3 extract_sptm_calls.py <kernelcache.macho> [--json output.json]

Strategy:
  1. Locate the SPTM call dispatch stub in XNU (searches for genter instruction
     patterns: hint #0xc0 or the specific encoding for genter on A16+)
  2. Walk backward from each genter call site to find the call number loaded in x0
  3. Cross-reference with exported symbol names if kcgen symbols are present
  4. Output: JSON map of call_number → {name, call_sites, inferred_args}

genter encoding:
  On A16 Pro / M3 / M4 / A18 Pro:
  genter = HINT #0xC0 = 0xd503409f  (to be verified — may vary by microarch)
  gexit  = HINT #0xC1 = 0xd503411f  (to be verified)

NOTE: This script is a research stub. The genter opcode and call convention
must be confirmed against actual hardware before trusting output.
"""

import sys
import json
import struct
import argparse
from pathlib import Path
from typing import Optional

# ARM64 instruction encodings (little-endian)
# VERIFY THESE against Apple hardware before trusting.
# Reference: Steffin/Classen paper, m1n1 source (hv/hv_vm.c)
GENTER_ENCODING = 0xD503409F  # HINT #0xC0 — UNVERIFIED
GEXIT_ENCODING  = 0xD503411F  # HINT #0xC1 — UNVERIFIED

# How many instructions to look back from a genter to find x0 load
LOOKBACK_INSNS = 16


def find_genter_sites(data: bytes, base_addr: int) -> list[int]:
    """Return list of virtual addresses where genter appears."""
    sites = []
    insn_bytes = struct.pack("<I", GENTER_ENCODING)
    offset = 0
    while True:
        idx = data.find(insn_bytes, offset)
        if idx == -1:
            break
        # Align check: must be 4-byte aligned
        if idx % 4 == 0:
            sites.append(base_addr + idx)
        offset = idx + 1
    return sites


def extract_x0_from_lookback(data: bytes, site_offset: int) -> Optional[int]:
    """
    Walk back from a genter site to find what was loaded into x0.
    Simple pattern: look for MOV x0, #imm or MOVZ x0, #imm in the preceding
    LOOKBACK_INSNS instructions.

    Returns the immediate value if found, None otherwise.
    """
    start = max(0, site_offset - LOOKBACK_INSNS * 4)
    window = data[start:site_offset]

    for i in range(len(window) - 4, -1, -4):
        insn = struct.unpack_from("<I", window, i)[0]

        # MOVZ x0, #imm (sf=1, opc=10, hw=00): 0xD280_0000 | (imm16 << 5)
        # Mask: 0xFFE0_001F == 0xD280_0000 for x0
        if (insn & 0xFFE0001F) == 0xD2800000:
            imm16 = (insn >> 5) & 0xFFFF
            return imm16

        # MOV x0, #imm alias (ORR x0, xzr, #imm) — less common for small ints
        # Skip for now

    return None


def load_raw_binary(path: Path) -> tuple[bytes, int]:
    """Load a raw binary (no Mach-O parsing). Base address assumed 0."""
    data = path.read_bytes()
    print(f"[extract_sptm_calls] Loaded {len(data)} bytes from {path}")
    print("[extract_sptm_calls] WARNING: no Mach-O parsing — base address = 0x0")
    print("  For accurate virtual addresses, provide a decompressed + rebased kernelcache.")
    return data, 0x0


def load_macho(path: Path) -> tuple[bytes, int]:
    """
    Attempt to parse Mach-O and extract the __TEXT segment.
    Falls back to raw binary if lief is not available.
    """
    try:
        import lief
        binary = lief.parse(str(path))
        if binary is None:
            raise ValueError("lief could not parse file")
        text = binary.get_segment("__TEXT")
        if text is None:
            raise ValueError("no __TEXT segment")
        data = bytes(text.content)
        base = text.virtual_address
        print(f"[extract_sptm_calls] Mach-O __TEXT: base=0x{base:016x}, size={len(data)}")
        return data, base
    except ImportError:
        print("[extract_sptm_calls] lief not available — falling back to raw binary mode")
        return load_raw_binary(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract SPTM call table from XNU kernelcache"
    )
    parser.add_argument("kernelcache", help="Path to decompressed Mach-O kernelcache")
    parser.add_argument("--json", default=None, help="Write results to JSON file")
    parser.add_argument("--raw", action="store_true",
                        help="Treat input as raw binary (skip Mach-O parsing)")
    args = parser.parse_args()

    path = Path(args.kernelcache)
    if not path.exists():
        print(f"[extract_sptm_calls] File not found: {path}")
        sys.exit(1)

    if args.raw:
        data, base = load_raw_binary(path)
    else:
        data, base = load_macho(path)

    print(f"\n[extract_sptm_calls] Scanning for genter (0x{GENTER_ENCODING:08X}) ...")
    sites = find_genter_sites(data, base)
    print(f"[extract_sptm_calls] Found {len(sites)} genter site(s)")

    results = []
    seen_calls: dict[int, list[int]] = {}

    for addr in sites:
        offset = addr - base
        call_num = extract_x0_from_lookback(data, offset)
        entry = {
            "site_va": f"0x{addr:016x}",
            "call_number": call_num,
            "call_number_hex": f"0x{call_num:04x}" if call_num is not None else None,
        }
        results.append(entry)
        if call_num is not None:
            seen_calls.setdefault(call_num, []).append(addr)

    # Summary
    print(f"\n=== SPTM Call Summary ===")
    print(f"Total genter sites : {len(sites)}")
    print(f"Unique call numbers: {len(seen_calls)}")
    print()
    for num in sorted(seen_calls):
        addrs = seen_calls[num]
        print(f"  0x{num:04x}  ({len(addrs)} site(s)): {[f'0x{a:x}' for a in addrs]}")

    print()
    print("NOTE: Call number extraction is heuristic. Verify with Ghidra/r2 disassembly.")
    print("      Update docs/SPTM_FINDINGS.md with confirmed call numbers.")

    if args.json:
        out = {
            "version": 1,
            "source": str(path),
            "genter_encoding": f"0x{GENTER_ENCODING:08X}",
            "warning": "UNVERIFIED — heuristic extraction only",
            "sites": results,
            "unique_calls": {
                f"0x{k:04x}": [f"0x{a:016x}" for a in v]
                for k, v in sorted(seen_calls.items())
            },
        }
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"[extract_sptm_calls] Results written to {args.json}")


if __name__ == "__main__":
    main()
