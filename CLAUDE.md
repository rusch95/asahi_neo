# CLAUDE.md — asahi_neo

This project is an experimental feasibility study for booting Linux on Apple hardware
featuring the A18 Pro chip (architecturally close to M4) via an XNU Shim approach.
It is **not** affiliated with the Asahi Linux project. GenAI is not to be used for
writing patches intended for upstreaming — this is exploratory research only.

## Navigation

- **PLAN.md** — Current action items, milestones, and known blockers. Check here first.
- **ARCHITECTURE.md** — High-level design of the XNU shim boot path and memory layout.
- **docs/SPTM_FINDINGS.md** — Running log of everything learned about SPTM/GXF.
- **docs/ASAHI_REFERENCE.md** — Distilled notes from Asahi Linux docs relevant to this effort.
- **docs/GRAPHICS.md** — Notes on graphics paths: framebuffer → software → AGX hardware.
- **xnu_shim/** — The shim implementation (stub code, build scripts, notes).
- **scripts/** — Testing, extraction, and analysis scripts.
- **research/** — Papers, reverse-engineering notes, binary dumps and annotations.

## Governing Principles

1. **Document everything.** If you discover something about the architecture — even a dead end —
   write it down in the relevant doc before moving on. The docs are the project.

2. **Defer to docs.** Before writing code, check ARCHITECTURE.md and SPTM_FINDINGS.md.
   Don't re-derive what's already been established.

3. **Test scripts first.** Prefer small, targeted scripts that can be run from a tethered
   boot or hypervisor context before writing permanent shim code.

4. **No GenAI patches.** Scripts and analysis tools are fine. Kernel/bootloader patches
   intended for any upstream must be human-authored and reviewed.

5. **Respect the Asahi social contract.** Never alter macOS security settings.
   All work happens in isolated APFS containers under Permissive Security.

## Key References

- Asahi Linux docs: https://asahilinux.org/docs/
- m1n1 hypervisor guide: see docs/sw/m1n1-hypervisor.md in AsahiLinux/docs
- Steffin/Classen paper on SPTM (see research/)
- IntegralPilot M3 DOOM patch (see docs/GRAPHICS.md for context)
- AsahiLinux/linux kernel tree for M4 bringup reference
