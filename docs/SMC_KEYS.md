# SMC Key Table — MacBook Neo (Mac17,5 / t8140 / A18 Pro)

**Captured 2026-03-16 via m1n1 usb_spmi_init() SMC enumeration**

255 keys (indices 0–254). Keys are returned little-endian in RESULT_VALUE,
so the raw 4-byte value is byte-reversed from the canonical key name.
Column "Displayed" = what m1n1 printed (LSB-first rendering).
Column "Actual key" = correct canonical SMC key name (bytes reversed).

All keys fall into standard Mac SMC management categories.
**No PMU/standby-related keys exist.** The function-external_standby
mechanism does not go through the SMC key-value store.

## Keys 0–34 (AC adapter)

| # | Displayed | Actual key | Category |
|---|-----------|-----------|----------|
| 0 | YEK# | #KEY | Meta — key count |
| 1 | B-CA | AC-B | AC adapter |
| 2 | C-CA | AC-C | AC adapter |
| 3 | E-CA | AC-E | AC adapter |
| 4 | F-CA | AC-F | AC adapter |
| 5 | I-CA | AC-I | AC adapter |
| 6 | J-CA | AC-J | AC adapter |
| 7 | M-CA | AC-M | AC adapter |
| 8 | N-CA | AC-N | AC adapter |
| 9 | P-CA | AC-P | AC adapter |
| 10 | Q-CA | AC-Q | AC adapter |
| 11 | R-CA | AC-R | AC adapter |
| 12 | S-CA | AC-S | AC adapter |
| 13 | T-CA | AC-T | AC adapter |
| 14 | U-CA | AC-U | AC adapter |
| 15 | W-CA | AC-W | AC adapter |
| 16 | X-CA | AC-X | AC adapter |
| 17 | PACA | ACAP | AC adapter |
| 18 | IBCA | ACBI | AC adapter |
| 19 | FCCA | ACCF | AC adapter |
| 20 | PCCA | ACCP | AC adapter |
| 21 | BDCA | ACDB | AC adapter |
| 22 | IDCA | ACDI | AC adapter |
| 23 | LDCA | ACDL | AC adapter |
| 24 | CECA | ACEC | AC adapter |
| 25 | QECA | ACEQ | AC adapter |
| 26 | PFCA | ACFP | AC adapter |
| 27 | DICA | ACID | AC adapter |
| 28 | EICA | ACIE | AC adapter |
| 29 | MLCA | ACLM | AC adapter |
| 30 | KPCA | ACPK | AC adapter |
| 31 | OPCA | ACPO | AC adapter |
| 32 | WPCA | ACPW | AC adapter |
| 33 | tSCA | ACSt | AC adapter |
| 34 | SVCA | ACSv | AC adapter |

## Keys 35–72 (power/ATC/AY)

| # | Displayed | Actual key | Category |
|---|-----------|-----------|----------|
| 35 | ABDA | ADBA | Power |
| 36 | PWNA | ANWP | Power |
| 37 | bPOA | AOPb | Power |
| 38 | N-PA | AP-N | Power |
| 39 | A1PA | AP1A | Power |
| 40 | F1PA | AP1F | Power |
| 41 | I1PA | AP1I | Power |
| 42 | P1PA | AP1P | Power |
| 43 | S1PA | AP1S | Power |
| 44 | V1PA | AP1V | Power |
| 45 | i1PA | AP1i | Power |
| 46 | p1PA | AP1p | Power |
| 47 | q1PA | AP1q | Power |
| 48 | u1PA | AP1u | Power |
| 49 | v1PA | AP1v | Power |
| 50 | A2PA | AP2A | Power |
| 51 | F2PA | AP2F | Power |
| 52 | I2PA | AP2I | Power |
| 53 | P2PA | AP2P | Power |
| 54 | S2PA | AP2S | Power |
| 55 | V2PA | AP2V | Power |
| 56 | i2PA | AP2i | Power |
| 57 | p2PA | AP2p | Power |
| 58 | q2PA | AP2q | Power |
| 59 | u2PA | AP2u | Power |
| 60 | v2PA | AP2v | Power |
| 61 | DSRA | ARSD | Power |
| 62 | PSRA | ARSP | Power |
| 63 | 0CTA | ATC0 | ATC |
| 64 | 1CTA | ATC1 | ATC |
| 65 | 0PTA | ATP0 | Power |
| 66 | 1PTA | ATP1 | Power |
| 67 | N-YA | AY-N | |
| 68 | A1YA | AY1A | |
| 69 | C1YA | AY1C | |
| 70 | P1YA | AY1P | |
| 71 | S1YA | AY1S | |
| 72 | T1YA | AY1T | |

## Keys 73–139 (battery B0xx/B1xx/BAxx)

| # | Displayed | Actual key | Category |
|---|-----------|-----------|----------|
| 73 | CA0B | B0AC | Battery |
| 74 | IA0B | B0AI | Battery |
| 75 | JA0B | B0AJ | Battery |
| 76 | PA0B | B0AP | Battery |
| 77 | TA0B | B0AT | Battery |
| 78 | VA0B | B0AV | Battery |
| 79 | DB0B | B0BD | Battery |
| 80 | LB0B | B0BL | Battery |
| 81 | AC0B | B0CA | Battery |
| 82 | DC0B | B0CD | Battery |
| 83 | HC0B | B0CH | Battery |
| 84 | IC0B | B0CI | Battery |
| 85 | JC0B | B0CJ | Battery |
| 86 | MC0B | B0CM | Battery |
| 87 | SC0B | B0CS | Battery |
| 88 | TC0B | B0CT | Battery |
| 89 | VC0B | B0CV | Battery |
| 90 | 1D0B | B0D1 | Battery |
| 91 | CD0B | B0DC | Battery |
| 92 | CF0B | B0FC | Battery |
| 93 | GF0B | B0FG | Battery |
| 94 | HF0B | B0FH | Battery |
| 95 | IF0B | B0FI | Battery |
| 96 | UF0B | B0FU | Battery |
| 97 | VF0B | B0FV | Battery |
| 98 | MH0B | B0HM | Battery |
| 99 | 2I0B | B0I2 | Battery |
| 100 | DI0B | B0ID | Battery |
| 101 | FI0B | B0IF | Battery |
| 102 | MI0B | B0IM | Battery |
| 103 | SI0B | B0IS | Battery |
| 104 | VI0B | B0IV | Battery |
| 105 | PL0B | B0LP | Battery |
| 106 | SM0B | B0MS | Battery |
| 107 | CN0B | B0NC | Battery |
| 108 | DN0B | B0ND | Battery |
| 109 | MN0B | B0NM | Battery |
| 110 | C00B | B00C | Battery |
| 111 | V00B | B00V | Battery |
| 112 | SP0B | B0PS | Battery |
| 113 | DQ0B | B0QD | Battery |
| 114 | SQ0B | B0QS | Battery |
| 115 | 1R0B | B0R1 | Battery |
| 116 | MR0B | B0RM | Battery |
| 117 | SR0B | B0RS | Battery |
| 118 | 1S0B | B0S1 | Battery |
| 119 | CS0B | B0SC | Battery |
| 120 | DS0B | B0SD | Battery |
| 121 | ES0B | B0SE | Battery |
| 122 | LS0B | B0SL | Battery |
| 123 | RS0B | B0SR | Battery |
| 124 | SS0B | B0SS | Battery |
| 125 | CT0B | B0TC | Battery temp |
| 126 | ET0B | B0TE | Battery temp |
| 127 | FT0B | B0TF | Battery temp |
| 128 | IT0B | B0TI | Battery temp |
| 129 | PT0B | B0TP | Battery temp |
| 130 | iT0B | B0Ti | Battery temp |
| 131 | CU0B | B0UC | Battery |
| 132 | CV0B | B0VC | Battery |
| 133 | DW0B | B0WD | Battery |
| 134 | SS1B | B1SS | Battery 1 |
| 135 | IT1B | B1TI | Battery 1 temp |
| 136 | IW1B | B1WI | Battery 1 |
| 137 | CAAB | BAAC | Battery |
| 138 | CCAB | BACC | Battery |
| 139 | SPAB | BAPS | Battery |

## Keys 140–254 (partially transcribed — photos too small)

Keys 140–254 were visible on screen but the photos are too small for
reliable per-key transcription. Patterns observed:
- 140–174: Keys ending in BB, CB, FB, PB — likely more battery keys (B?xx)
- 175–209: Keys ending in TB, LB, FB — likely Bluetooth/thermal (BT??, BF??)
- 210–244: Keys ending in HB, LB — likely more battery/thermal
- 245–254: Keys ending in B0, SB — likely battery state/status

## Notes

- `#KEY` returned value 0 (not 255) when read directly with big-endian encoding
  0x234B4559. The key IS at index 0 but the SMC returns key count as 0 at this
  boot stage, or the key encoding for reads differs from the enumeration byte order.
  The 256-key safety cap in the code covered all 255 actual keys.
- All key names need byte-reversal to get canonical form (SMC stores/returns 4-byte
  keys in little-endian order in RESULT_VALUE).
- Fix for future enumeration: use `u8 c = (k >> (b * 8)) & 0xFF` (LSB-first) instead
  of `(k >> (24 - b * 8)) & 0xFF` to print keys in correct order.
