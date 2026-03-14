#!/usr/bin/env python3
"""
extract_sptm_calls.py — Extract SPTM call sites from XNU kernelcache.

Requires:
  - An extracted kernelcache (decompressed Mach-O)
  - Python 3.11+
  - Optional: lief (pip install lief) for Mach-O parsing

Usage:
  python3 extract_sptm_calls.py <kernelcache.macho> [--json output.json] [--raw]

Strategy:
  1. Scan for genter (0x00201420) in the __TEXT segment
  2. Walk back from each site looking for the x16 setup sequence:
       MOVZ x16, #endpoint_id         (bits 31:0  of dispatch descriptor)
       MOVK x16, #table_id,  LSL #32  (bits 39:32)
       MOVK x16, #domain_id, LSL #48  (bits 55:48)
  3. Decode and print domain, table, endpoint for each genter site

Call ABI (Steffin/Classen arXiv:2510.09272):
  x16 = sptm_dispatch_target_t:
    bits[55:48] = domain        (1=XNU, 2=TXM, 3=SK, 4=HIB)
    bits[39:32] = dispatch_table_id
    bits[31:0]  = endpoint_id
  x0–x7 = arguments; x0 = return value

genter = 0x00201420  (m1n1 src/gxf_asm.S, confirmed)
gexit  = 0x00201400
"""

import sys
import json
import struct
import argparse
from pathlib import Path
from typing import Optional

GENTER_ENCODING = 0x00201420
GEXIT_ENCODING  = 0x00201400
LOOKBACK_INSNS  = 24  # search window in instructions

# Known domains
SPTM_DOMAINS: dict[int, str] = {
    0: "SPTM_DOMAIN",
    1: "XNU_DOMAIN",
    2: "TXM_DOMAIN",
    3: "SK_DOMAIN",
    4: "XNU_HIB_DOMAIN",
}

# Dispatch Table IDs (from sptm_common.h, paper Appendix A.3)
SPTM_TABLES: dict[int, str] = {
    0:  "XNU_BOOTSTRAP",
    1:  "TXM_BOOTSTRAP",
    2:  "SK_BOOTSTRAP",
    3:  "T8110_DART_XNU",
    4:  "T8110_DART_SK",
    5:  "SART",
    6:  "NVME",
    7:  "UAT",
    8:  "SHART",
    9:  "RESERVED",
    10: "HIB",
    11: "INVALID",
}

# Endpoint IDs (from sptm_xnu.h, paper Appendix A.4)
SPTM_ENDPOINTS: dict[int, str] = {
    0:  "LOCKDOWN",
    1:  "RETYPE",           # sptm_retype() — claim frames
    2:  "MAP_PAGE",          # sptm_map_page() — build PTEs
    3:  "MAP_TABLE",
    4:  "UNMAP_TABLE",
    5:  "UPDATE_REGION",
    6:  "UPDATE_DISJOINT",
    7:  "UNMAP_REGION",
    8:  "UNMAP_DISJOINT",
    9:  "CONFIGURE_SHAREDREGION",
    10: "NEST_REGION",
    11: "UNNEST_REGION",
    12: "CONFIGURE_ROOT",
    13: "SWITCH_ROOT",
    14: "REGISTER_CPU",
    15: "FIXUPS_COMPLETE",
    16: "SIGN_USER_POINTER",
    17: "AUTH_USER_POINTER",
    18: "REGISTER_EXC_RETURN",
    19: "CPU_ID",
    20: "SLIDE_REGION",
    21: "UPDATE_DISJOINT_MULTIPAGE",
    22: "REG_READ",
    23: "REG_WRITE",
    24: "GUEST_VA_TO_IPA",
    25: "GUEST_STAGE1_TLBOP",
    26: "GUEST_STAGE2_TLBOP",
    27: "GUEST_DISPATCH",
    28: "GUEST_EXIT",
    29: "MAP_SK_DOMAIN",
    30: "HIB_BEGIN",
    31: "HIB_VERIFY_HASH_NON_WIRED",
    32: "HIB_FINALIZE_NON_WIRED",
    33: "IOFILTER_PROTECTED_WRITE",
}


# ---------------------------------------------------------------------------
# ARM64 instruction decode helpers for x16 (register number 16 = 0b10000)
# ---------------------------------------------------------------------------

def _imm16(insn: int) -> int:
    return (insn >> 5) & 0xFFFF

def is_movz_x16(insn: int) -> bool:
    # MOVZ x16, #imm  (hw=00, LSL#0)
    # sf=1 opc=10 100 hw=00 imm16 Rd=10000
    return (insn & 0xFFE0001F) == 0xD2800010

def is_movk_x16_lsl0(insn: int) -> bool:
    return (insn & 0xFFE0001F) == 0xF2800010

def is_movk_x16_lsl16(insn: int) -> bool:
    return (insn & 0xFFE0001F) == 0xF2A00010

def is_movk_x16_lsl32(insn: int) -> bool:
    # table_id lives at bits[39:32]
    return (insn & 0xFFE0001F) == 0xF2C00010

def is_movk_x16_lsl48(insn: int) -> bool:
    # domain lives at bits[55:48]
    return (insn & 0xFFE0001F) == 0xF2E00010


def extract_x16_dispatch(data: bytes, site_offset: int) -> dict:
    """
    Walk backward from a genter site, accumulating x16 build-up instructions.
    Returns a dict with decoded dispatch fields (or None where not found).
    """
    start = max(0, site_offset - LOOKBACK_INSNS * 4)
    window = data[start:site_offset]

    endpoint_id: Optional[int] = None
    table_id:    Optional[int] = None
    domain_id:   Optional[int] = None

    # Walk backward; stop accumulating a field once we've seen it
    for i in range(len(window) - 4, -1, -4):
        insn = struct.unpack_from("<I", window, i)[0]

        if endpoint_id is None and (is_movz_x16(insn) or is_movk_x16_lsl0(insn)):
            endpoint_id = _imm16(insn)

        if table_id is None and is_movk_x16_lsl32(insn):
            table_id = _imm16(insn)

        if domain_id is None and is_movk_x16_lsl48(insn):
            domain_id = _imm16(insn)

        if endpoint_id is not None and table_id is not None and domain_id is not None:
            break

    return {
        "domain_id":   domain_id,
        "domain_name": SPTM_DOMAINS.get(domain_id, f"UNKNOWN({domain_id})") if domain_id is not None else None,
        "table_id":    table_id,
        "table_name":  SPTM_TABLES.get(table_id, f"TABLE_{table_id}") if table_id is not None else None,
        "endpoint_id": endpoint_id,
    }


# ---------------------------------------------------------------------------
# Binary loading
# ---------------------------------------------------------------------------

def load_raw_binary(path: Path) -> tuple[bytes, int]:
    data = path.read_bytes()
    print(f"[extract_sptm_calls] Loaded {len(data):,} bytes (raw binary, base=0x0)")
    print("  WARNING: provide a decompressed + rebased kernelcache for accurate VAs.")
    return data, 0x0


def load_macho(path: Path) -> tuple[bytes, int]:
    try:
        import lief
        binary = lief.parse(str(path))
        if binary is None:
            raise ValueError("lief parse failed")
        text = binary.get_segment("__TEXT")
        if text is None:
            raise ValueError("no __TEXT segment")
        data = bytes(text.content)
        base = text.virtual_address
        print(f"[extract_sptm_calls] __TEXT: base=0x{base:016x}, size={len(data):,}")
        return data, base
    except ImportError:
        print("[extract_sptm_calls] lief not installed — falling back to raw binary")
        print("  pip install lief")
        return load_raw_binary(path)


def find_genter_sites(data: bytes, base_addr: int) -> list[int]:
    sites = []
    needle = struct.pack("<I", GENTER_ENCODING)
    offset = 0
    while True:
        idx = data.find(needle, offset)
        if idx == -1:
            break
        if idx % 4 == 0:
            sites.append(base_addr + idx)
        offset = idx + 1
    return sites


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SPTM call sites from kernelcache")
    parser.add_argument("kernelcache", help="Decompressed Mach-O kernelcache path")
    parser.add_argument("--json", default=None, metavar="OUTPUT", help="Write JSON results")
    parser.add_argument("--raw", action="store_true", help="Skip Mach-O parsing")
    args = parser.parse_args()

    path = Path(args.kernelcache)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    data, base = load_raw_binary(path) if args.raw else load_macho(path)

    print(f"\nScanning for genter (0x{GENTER_ENCODING:08X}) ...")
    sites = find_genter_sites(data, base)
    print(f"Found {len(sites)} genter site(s)\n")

    results = []
    # Group by (domain, table, endpoint)
    call_groups: dict[tuple, list[int]] = {}

    for addr in sites:
        offset = addr - base
        dispatch = extract_x16_dispatch(data, offset)
        entry = {
            "site_va": f"0x{addr:016x}",
            **dispatch,
        }
        results.append(entry)
        key = (dispatch["domain_id"], dispatch["table_id"], dispatch["endpoint_id"])
        call_groups.setdefault(key, []).append(addr)

    # Print summary
    print("=== SPTM Dispatch Site Summary ===")
    print(f"{'Domain':<20} {'Table':<18} {'EP':>4}  {'Function':<32}  {'#':>4}  First VA")
    print("-" * 95)
    for (dom, tbl, ep), addrs in sorted(call_groups.items()):
        dom_s = SPTM_DOMAINS.get(dom, f"?({dom})") if dom is not None else "?"
        tbl_s = SPTM_TABLES.get(tbl, f"TABLE_{tbl}") if tbl is not None else "?"
        ep_s  = f"{ep}" if ep is not None else "?"
        fn_s  = SPTM_ENDPOINTS.get(ep, "UNKNOWN") if ep is not None else "?"
        va_s  = f"0x{addrs[0]:x}" if addrs else "?"
        print(f"{dom_s:<20} {tbl_s:<18} {ep_s:>4}  {fn_s:<32}  {len(addrs):>4}  {va_s}")

    print()
    print("NOTE: x16 extraction is heuristic. Verify with r2 / Ghidra disassembly.")
    print("      Add confirmed endpoint names to docs/SPTM_FINDINGS.md.")

    if args.json:
        out = {
            "version": 2,
            "source": str(path),
            "genter_encoding": f"0x{GENTER_ENCODING:08X}",
            "abi_reference": "arXiv:2510.09272 (Steffin/Classen)",
            "note": "Heuristic x16 decode — verify manually",
            "sites": results,
        }
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"Results written to {args.json}")


if __name__ == "__main__":
    main()
