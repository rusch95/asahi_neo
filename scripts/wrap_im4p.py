#!/usr/bin/env python3
"""
wrap_im4p.py — Wrap a raw binary in an IM4P (im4p) container.

Usage: python3 wrap_im4p.py <input.bin> <output.im4p> [type]

The output is a DER-encoded ASN.1 structure:
  SEQUENCE {
    IA5String "IM4P"
    IA5String <type>      (default: "rkrn" = raw kernel)
    IA5String ""          (description, empty)
    OCTET STRING <data>   (the raw binary payload)
  }

This is the format that kmutil configure-boot --raw creates, and that
iBoot expects on the Preboot partition.
"""

import sys
import struct


def der_len(length):
    """Encode a DER length field."""
    if length < 0x80:
        return bytes([length])
    elif length < 0x100:
        return bytes([0x81, length])
    elif length < 0x10000:
        return bytes([0x82]) + struct.pack(">H", length)
    elif length < 0x1000000:
        return bytes([0x83]) + struct.pack(">I", length)[1:]
    else:
        return bytes([0x84]) + struct.pack(">I", length)


def ia5string(s):
    """Encode an IA5String."""
    data = s.encode("ascii")
    return b"\x16" + der_len(len(data)) + data


def octet_string(data):
    """Encode an OCTET STRING."""
    return b"\x04" + der_len(len(data)) + data


def sequence(items):
    """Encode a SEQUENCE."""
    body = b"".join(items)
    return b"\x30" + der_len(len(body)) + body


def wrap_im4p(raw_data, payload_type="rkrn"):
    """Wrap raw binary data in an IM4P container."""
    return sequence([
        ia5string("IM4P"),
        ia5string(payload_type),
        ia5string(""),
        octet_string(raw_data),
    ])


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.bin> <output.im4p> [type]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    payload_type = sys.argv[3] if len(sys.argv) > 3 else "rkrn"

    with open(input_path, "rb") as f:
        raw_data = f.read()

    print(f"Input: {input_path} ({len(raw_data)} bytes, {len(raw_data) >> 20} MB)")

    im4p = wrap_im4p(raw_data, payload_type)

    with open(output_path, "wb") as f:
        f.write(im4p)

    print(f"Output: {output_path} ({len(im4p)} bytes, {len(im4p) >> 20} MB)")
    print(f"  type={payload_type}, overhead={len(im4p) - len(raw_data)} bytes")


if __name__ == "__main__":
    main()
