---
id: 0039
title: Phono-cartridge (record-player pickup) as a bearing-ring vibration/AE sensor — inner ring, maybe outer
area: instrumentation / sensor R&D
role: hardware
status: backlog
depends_on:
branch:
pr:
---

## Purpose
Add a **phono cartridge (record-player pickup)** as a vibration / acoustic-emission sensor on the bearing,
mounted to read the **inner ring** (and maybe the **outer ring**). A phono cartridge is a cheap, very
sensitive mechanical-to-electrical transducer; in contact with a ring it could capture vibration / AE that
complements the existing UL (Kistler AE probe), AE (accelerometer) and OE ultrasound-mic channels — a
different transduction and band, close to the contact.

## The signal-conditioning question (Kim's open point)
A phono cartridge is normally fed into a **phono preamp that applies RIAA equalization** — a playback EQ
curve (large bass boost + treble cut) plus often a subsonic/rumble filter and sometimes a low-pass. That EQ
exists to undo the inverse curve cut into a vinyl groove; **on a raw measurement it just colours the
spectrum.** So for measurement:
- **Bypass / remove the RIAA equalization** and any built-in low-pass / rumble filter, so the cartridge's
  own response is what reaches the DAQ (this is the "get the RIAA amp off / the low-pass off" Kim asked
  about — correct instinct).
- Replace it with a **flat gain stage** (an instrumentation preamp, not a phono one). Cartridge output is
  small — moving-magnet ~a few mV, moving-coil sub-mV — so it needs clean flat gain to a scope-friendly
  level.
- Characterise the cartridge's own frequency response + mechanical resonance so we know what "flat" actually
  measures.

## Unknowns to settle
- **Cartridge type:** moving-magnet (MM — higher output, simpler) vs moving-coil (MC — lower output, more
  gain, more delicate). **MM is the pragmatic start.**
- **Mount / coupling to the ring:** how the stylus/body contacts the inner ring (and whether an outer-ring
  mount is feasible), contact force, and isolation from the rest of the rig's vibration.
- **Band of interest:** bearing defect frequencies + the AE band vs the cartridge's usable range and
  resonance — a cartridge is happy to ~20 kHz-ish, well below the OE ultrasound mic, so treat it as a
  low/mid-frequency vibration view, not an ultrasound one.
- **DAQ landing:** a spare scope channel (CHAN4/Temp is disabled) or alongside the others; sample rate +
  anti-alias for the chosen band.

## Why it's worth trying
Cheap, extremely sensitive, and a second independent vibration/AE view on the ring near the contact —
a useful cross-check against UL/AE and the OE mic, in a different transduction and band.

## Owner / test
- **Kim / hardware:** source a cartridge (MM to start), sort the flat preamp (RIAA bypassed), and the ring
  mount.
- **Pi / Dev:** wire it into the DAQ, capture a spin-up, and characterise the response (flat? resonance?
  what does it see that the others don't?).
