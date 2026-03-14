#!/usr/bin/env python3
"""
diff_sptm_blobs.py — Compare SPTM firmware blobs from two IPSWs.

Compares the SPTM firmware component between two IPSWs (e.g., M4 macOS IPSW
and A18 Pro iOS IPSW) to determine whether the SPTM ABI is shared.

Requires:
  - Two IPSW files (or pre-extracted SPTM blobs)
  - Python 3.11+
  - Optional: ipsw CLI tool (https://github.com/blacktop/ipsw)

Usage:
  # Compare extracted blobs directly:
  python3 diff_sptm_blobs.py --blob1 m4_sptm.bin --blob2 a18pro_sptm.bin

  # Extract from IPSWs first (requires ipsw CLI):
  python3 diff_sptm_blobs.py --ipsw1 M4.ipsw --ipsw2 A18Pro.ipsw

Output:
  - SHA-256 hashes of both blobs
  - Byte-level diff statistics
  - Attempt to identify shared vs. divergent function preambles
  - Recommendation: "ABI likely identical", "ABI likely divergent", "unknown"

Finding "ABI identical" would confirm we can use M4 SPTM call numbers on A18 Pro.
"""

import sys
import hashlib
import argparse
import subprocess
import struct
from pathlib import Path
from typing import Optional


SPTM_BUNDLE_PATHS = [
    # Known paths inside IPSW / restore bundle — may vary by version
    "kernelcache.release.t8132",       # M4 kernelcache
    "Firmware/dfu/iBoot.d74.RELEASE.im4p",
    # Add more as discovered
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_from_ipsw(ipsw: Path, outdir: Path) -> Optional[Path]:
    """Attempt to extract SPTM blob using ipsw CLI tool."""
    try:
        result = subprocess.run(
            ["ipsw", "version"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise FileNotFoundError
    except FileNotFoundError:
        print("[diff_sptm_blobs] ipsw CLI not found.")
        print("  Install: https://github.com/blacktop/ipsw")
        print("  Or extract SPTM blob manually and use --blob1/--blob2.")
        return None

    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[diff_sptm_blobs] Extracting from {ipsw} ...")
    print("[diff_sptm_blobs] TODO: determine correct ipsw CLI command to extract SPTM")
    print("  Candidate: ipsw extract --sptm <ipsw>")
    print("  Manual alternative: unzip <ipsw> and locate SPTM in the Firmware/ hierarchy")
    return None


def diff_blobs(blob1: Path, blob2: Path) -> None:
    print(f"\n=== SPTM Blob Comparison ===")
    print(f"Blob 1: {blob1}")
    print(f"Blob 2: {blob2}")
    print()

    data1 = blob1.read_bytes()
    data2 = blob2.read_bytes()

    h1 = sha256(blob1)
    h2 = sha256(blob2)

    print(f"SHA-256 blob1: {h1}")
    print(f"SHA-256 blob2: {h2}")
    print()

    if h1 == h2:
        print("RESULT: Blobs are IDENTICAL.")
        print("  → SPTM ABI is confirmed identical between the two devices.")
        print("  → M4 call table applies directly to A18 Pro.")
        print("  → Update docs/SPTM_FINDINGS.md: 'SPTM ABI: IDENTICAL'")
        return

    print(f"Sizes: {len(data1)} vs {len(data2)} bytes")
    if len(data1) != len(data2):
        print(f"  Size delta: {len(data2) - len(data1):+d} bytes")

    # Byte-level diff
    min_len = min(len(data1), len(data2))
    diff_bytes = sum(1 for a, b in zip(data1, data2) if a != b)
    pct = diff_bytes / min_len * 100
    print(f"Differing bytes: {diff_bytes} / {min_len} ({pct:.2f}%)")
    print()

    # Heuristic: compare first 0x100 bytes (header / magic / version)
    header_diffs = sum(1 for a, b in zip(data1[:0x100], data2[:0x100]) if a != b)
    print(f"Header (first 256 bytes) differences: {header_diffs}")

    if pct < 1.0:
        print("\nHEURISTIC: < 1% difference — likely same ABI, minor version delta.")
        print("  → Manually diff at function-preamble level to confirm.")
    elif pct < 10.0:
        print("\nHEURISTIC: 1–10% difference — possible ABI evolution.")
        print("  → Disassemble both and compare call table offsets.")
    else:
        print("\nHEURISTIC: > 10% difference — significant divergence.")
        print("  → Do not assume call table compatibility. Full RE required.")

    print()
    print("Next step: load both in Ghidra / r2, diff function preambles at matching offsets.")
    print("Document findings in docs/SPTM_FINDINGS.md.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare SPTM blobs from two IPSWs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--blobs", nargs=2, metavar=("BLOB1", "BLOB2"),
                       help="Compare two pre-extracted SPTM blobs")
    group.add_argument("--ipsws", nargs=2, metavar=("IPSW1", "IPSW2"),
                       help="Extract and compare from two IPSWs (requires ipsw CLI)")

    parser.add_argument("--outdir", default="./ipsw_extract",
                        help="Directory for extracted files")
    args = parser.parse_args()

    if args.blobs:
        blob1, blob2 = Path(args.blobs[0]), Path(args.blobs[1])
        for p in (blob1, blob2):
            if not p.exists():
                print(f"[diff_sptm_blobs] File not found: {p}")
                sys.exit(1)
        diff_blobs(blob1, blob2)

    else:
        outdir = Path(args.outdir)
        ipsw1, ipsw2 = Path(args.ipsws[0]), Path(args.ipsws[1])
        blob1 = extract_from_ipsw(ipsw1, outdir / "ipsw1")
        blob2 = extract_from_ipsw(ipsw2, outdir / "ipsw2")
        if blob1 and blob2:
            diff_blobs(blob1, blob2)
        else:
            print("[diff_sptm_blobs] Extraction failed. Extract blobs manually.")
            sys.exit(1)


if __name__ == "__main__":
    main()
