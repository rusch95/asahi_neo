# research — Papers, Notes, Binaries

This directory holds reference material that informs the project but isn't code.

## To Obtain

- [ ] **steffin_classen_sptm.pdf** — The Steffin/Classen paper on SPTM.
      Search: "Apple SPTM Secure Page Table Monitor" in academic paper search.
      Once obtained: read fully, annotate key findings into docs/SPTM_FINDINGS.md.

- [ ] **m4_kernelcache/** — Extracted M4 XNU kernelcache from macOS 15.x IPSW.
      Extract via: `ipsw` tool or manual APFS extraction.
      Use: disassemble SPTM call sites in XNU to map call table.

- [ ] **a18pro_kernelcache/** — Same, for A18 Pro from iOS 18.x IPSW.
      Use: compare SPTM ABI against M4.

- [ ] **integralPilot_doom_patch/** — The IntegralPilot M3 DOOM patch.
      Find: Asahi Linux community (Matrix/Discord/GitHub).
      Use: understand hardware graphics shortcut for Phase 3.

## File Organization

```
research/
├── README.md
├── papers/              PDFs of academic / conference papers
├── kernelcaches/        Extracted + partially annotated kernelcache binaries
│   ├── m4/
│   └── a18pro/
├── ipsw_notes/          Notes from IPSW extraction (versions, file hashes)
└── ghidra_projects/     Ghidra project exports for SPTM analysis
```

## Notes Convention

For each binary analyzed, create a `.notes.md` file alongside it:
```
kernelcaches/m4/sptm_blob.notes.md
```
with: extraction method, version string, key findings, open questions.
