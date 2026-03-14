# GRAPHICS.md — Graphics Bringup Notes

Last updated: 2026-03-14

Three progressive goals. Each section documents what we know and what needs work.

---

## Goal 2: Software Framebuffer (SimpleDRM / efifb)

### Approach

iBoot initializes a linear framebuffer before handing off to the kernel. The address
and dimensions are passed via the MachO Boot Protocol (or ADT). m1n1 converts this
into a standard `simple-framebuffer` FDT node.

Steps:
1. Ensure m1n1 (or our shim) creates a `simple-framebuffer` node in the FDT with:
   - `reg` = physical address + size
   - `width`, `height`, `stride`, `format` (typically `x8r8g8b8` or `a8r8g8b8`)
2. Enable `CONFIG_DRM_SIMPLEDRM=y` in kernel config
3. Linux will bind `simpledrm` to the node and expose `/dev/dri/card0`

**No GPU firmware needed. No DCP driver needed.**

This is the expected path for Phase 1.5 → Phase 2.

### A18 Pro Display Controller

Apple's display subsystem uses DCP (Display Coprocessor) for compositing on M-series.
On iPhone-lineage chips (A-series), it may differ — verify via ADT dump.
For software framebuffer, we bypass DCP entirely and use the iBoot-initialized buffer.
The display may not refresh or handle resolution changes without DCP, but it will show
a static framebuffer at boot resolution.

---

## Goal 3: Hardware GPU (AGX)

### Background: IntegralPilot M3 DOOM Patch

The IntegralPilot patch demonstrated running DOOM (and presumably other OpenGL apps)
on M3 hardware before the full Asahi AGX driver was upstreamed for M3.

**Key insight (to be verified):** The patch likely:
1. Bypassed the normal RTKit GPU firmware bring-up sequence
2. Used a pre-initialized GPU state left by macOS / iBoot
3. Submitted minimal GPU command buffers directly, bypassing the full DRM/KMS stack

OR alternatively, it used an early development version of the asahi-drm driver with
M3 firmware tables added. The exact mechanism needs to be confirmed by reading the
patch itself.

**TODO:** Obtain and analyze the IntegralPilot patch. Add findings here.
Source: likely available on GitHub or the Asahi Linux community Discord/Matrix.

### AGX on A18 Pro

AGX generation on A18 Pro: likely G18 (same as M4). Evidence:
- A18 Pro and M4 launched in the same product cycle (2024)
- Both advertised as "same GPU class" in Apple marketing

If the AGX firmware and register layout are identical to M4, the M4 AGX work in
AsahiLinux/linux should apply with:
- New `compatible` string for A18 Pro
- Possibly new firmware extraction from A18 Pro IPSW
- Updated firmware version entry in the driver

### AGX Driver Architecture Summary

From Asahi agx-driver-notes.md:
- GPU has its own coprocessor (RTKit) running Apple firmware
- Driver submits command buffers to firmware queues
- Two render queues per logical queue: vertex + fragment (can run concurrently)
- Explicit dependency barriers between submissions
- UAPI inspired by Intel Xe: Files → VMs → Binds → Queues

**Not yet implemented in Asahi AGX (as of 2026-03):**
- VM bind/unbind subranges
- Performance counters
- Blit commands
- Compute preemption
- M2 Pro/Max support (structural hints that M4/A18 Pro also absent)

### Path to Hardware GPU on A18 Pro

1. Confirm AGX generation (G18 assumed)
2. Extract AGX firmware from A18 Pro IPSW
3. Add A18 Pro entries to asahi-drm firmware table
4. Test basic render with M4-targeting driver on A18 Pro hardware
5. Debug any register offset differences via hypervisor tracing

IntegralPilot approach may shortcut steps 3-5 if the technique generalizes.

---

## Display Output Without DCP

If DCP bring-up is required for hardware display output (possible on A18 Pro), we may
need to either:
- Write a minimal DCP init sequence (complex — DCP has its own firmware)
- Use HDMI/DP output via a USB-C dock (which may use a different path)
- Accept display-over-UART as the "terminal" for Phase 1

For Phase 1, UART output is sufficient. Display is Phase 2+.
