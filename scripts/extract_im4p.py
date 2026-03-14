#!/usr/bin/env python3
"""
extract_im4p.py — Extract raw payload from Apple IM4P firmware blobs.

IM4P is a DER/ASN1 wrapper:
  SEQUENCE {
    IA5String "IM4P"
    IA5String <type>  (e.g. "sptm")
    IA5String <desc>
    OCTET STRING <payload>  (lzfse or lzss compressed, or raw)
    [OCTET STRING <keybag>] (optional, for encrypted blobs)
  }

Usage:
  python3 extract_im4p.py <file.im4p> [--out <output.bin>]
"""

import sys
import struct
import argparse
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal DER parser (no external deps)
# ---------------------------------------------------------------------------

def _read_length(data: bytes, pos: int) -> tuple[int, int]:
    """Return (length, new_pos)."""
    b = data[pos]
    pos += 1
    if b < 0x80:
        return b, pos
    n = b & 0x7F
    length = int.from_bytes(data[pos:pos+n], 'big')
    return length, pos + n

def _read_tlv(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """Return (tag, value_bytes, new_pos)."""
    tag = data[pos]; pos += 1
    length, pos = _read_length(data, pos)
    value = data[pos:pos+length]
    return tag, value, pos + length

def parse_im4p(data: bytes) -> dict:
    """Return dict with keys: type, description, payload."""
    tag, seq_data, _ = _read_tlv(data, 0)
    assert tag == 0x30, f"Expected SEQUENCE (0x30), got 0x{tag:02x}"

    pos = 0
    fields = []
    while pos < len(seq_data):
        tag, val, pos = _read_tlv(seq_data, pos)
        fields.append((tag, val))

    assert fields[0][1] == b"IM4P", f"Not an IM4P file (got {fields[0][1]})"

    return {
        "type":        fields[1][1].decode("ascii"),
        "description": fields[2][1].decode("ascii") if len(fields) > 2 else "",
        "payload":     fields[3][1] if len(fields) > 3 else b"",
        "keybag":      fields[4][1] if len(fields) > 4 else None,
    }


# ---------------------------------------------------------------------------
# Decompression
# ---------------------------------------------------------------------------

LZFSE_MAGIC = b"bvx2"
LZVN_MAGIC  = b"bvx1"
RAW_MAGIC   = b"bvx-"

def decompress_payload(payload: bytes) -> bytes:
    """Detect compression and decompress."""

    # Check for lzss header used in older im4p (magic 0x636f6d70 = 'comp')
    if payload[:4] == b"comp":
        raise NotImplementedError("lzss 'comp' header not yet supported — use img4tool")

    # Find lzfse/lzvn block (may have a small prefix)
    for offset in range(0, min(32, len(payload))):
        chunk = payload[offset:offset+4]
        if chunk in (LZFSE_MAGIC, LZVN_MAGIC, RAW_MAGIC):
            compressed = payload[offset:]
            print(f"  Found {chunk.decode()} at offset +{offset}")

            # Use system lzfse tool if available
            try:
                result = subprocess.run(
                    ["lzfse", "-decode"],
                    input=compressed, capture_output=True, check=True
                )
                return result.stdout
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass

            # Fall back to pyliblzfse
            try:
                import liblzfse
                return liblzfse.decompress(compressed)
            except ImportError:
                pass

            raise RuntimeError(
                "Cannot decompress: install lzfse CLI (brew install lzfse) "
                "or pyliblzfse (pip install pyliblzfse)"
            )

    # May already be raw Mach-O
    if payload[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        print("  Payload is raw Mach-O (uncompressed)")
        return payload

    # Try lzfse anyway from offset 0
    try:
        result = subprocess.run(
            ["lzfse", "-decode"],
            input=payload, capture_output=True, check=True
        )
        return result.stdout
    except Exception:
        pass

    print(f"  WARNING: unknown payload format, first 8 bytes: {payload[:8].hex()}")
    print("  Saving raw payload (may be encrypted or unknown compression)")
    return payload


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract payload from IM4P blob")
    parser.add_argument("im4p", help="Input .im4p file")
    parser.add_argument("--out", default=None, help="Output file (default: <name>.bin)")
    parser.add_argument("--raw", action="store_true", help="Skip decompression, save raw payload")
    args = parser.parse_args()

    src = Path(args.im4p)
    out = Path(args.out) if args.out else src.with_suffix(".bin")

    print(f"[extract_im4p] Reading {src} ({src.stat().st_size:,} bytes)")
    data = src.read_bytes()

    info = parse_im4p(data)
    print(f"[extract_im4p] Type: {info['type']}  Desc: {info['description']!r}")
    print(f"[extract_im4p] Payload size: {len(info['payload']):,} bytes")
    print(f"[extract_im4p] Keybag: {'yes (encrypted)' if info['keybag'] else 'no'}")

    if info['keybag']:
        print("[extract_im4p] WARNING: blob appears encrypted — cannot decompress without keys")
        print("  The Preboot partition blobs are usually unencrypted. Try anyway...")

    if args.raw:
        payload = info['payload']
        print("[extract_im4p] Saving raw (undecompressed) payload")
    else:
        print("[extract_im4p] Decompressing...")
        payload = decompress_payload(info['payload'])

    out.write_bytes(payload)
    print(f"[extract_im4p] Saved {len(payload):,} bytes → {out}")

    # Quick sanity check
    if payload[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        print("[extract_im4p] Output is a valid Mach-O binary")
    elif payload[:4] == b"\x7fELF":
        print("[extract_im4p] Output is an ELF binary")
    else:
        print(f"[extract_im4p] Output magic: {payload[:8].hex()} (not Mach-O — may need further processing)")


if __name__ == "__main__":
    main()
