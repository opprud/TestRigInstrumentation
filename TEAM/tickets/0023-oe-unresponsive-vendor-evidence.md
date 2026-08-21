---
id: 0023
title: WITHDRAWN — "unresponsive OE sensor" was a bad probe, not a fault. One real vendor defect remains.
area: ble
role: dev
status: withdrawn
assignee: pi-claude
branch: ticket/0023-oe-unresponsive-vendor-evidence
depends_on: 0001
pr:
---

## Withdrawn, and why
This ticket was an evidence package arguing that sensor **OE00031204100074** had stopped
responding and needed vendor intervention. **The sensor was healthy the whole time.** Nothing here
should be sent to BearingBrain except the single defect in the last section.

**The error was mine and it was basic.** I used `read_config` as the liveness probe — 60+ probes
over 24 hours, each dutifully reported as "advertising, still not answering" — and concluded the
application was wedged. But `read_config` times out on this firmware **by design**. The project's
own history said so, in commit `912121b` (2026-04-20, "removed read config"):

> *Skip config read to avoid the 45 s overhead and to keep sampling viable when config read would
> time out.*

Everything I presented as evidence of a fault was a healthy device: GATT answering instantly,
writes accepted, the LED tracking connection state. It answered every question except the one I
kept asking. `sample(mask=0x18)` returns in **19 s** with 74,752 + 74,153 samples of real mic data.

**Cost:** a day and a half of diagnosis, a wasted trip to the rig for Kim, a reset and a power
cycle that were never needed, and firmware-channel pokes at a device that was fine. The lesson is
narrow and worth keeping: **a probe has to be something the target actually implements, and that
is checkable before building a day of conclusions on it.**

Also withdrawn on the way: the advertisement was never abnormal (it matches the vendor readme's
own example exactly), and the red LED at ~1 Hz means awake and waiting for a BLE connection.

## The one thing that is real, and does belong with BearingBrain
Confirmed against their pristine tree at `/home/aau/projects/BearingBrain/BearingBrainGWEmulator 1`,
whose `oe_protocol.py`, `utils.py`, `run_sampler.py` and `ble_debug_scan.py` are **byte-identical**
to our copies:

> In `oe_device.py`, `connect()` has its `start_notify(UART_CHAR_UUID, …)` line **commented out**.
> The only active subscription in the whole tree is on the *firmware* characteristic inside
> `connect_ota()`. Since `oe_protocol` never calls `read_gatt_char`, nothing can reach
> `notification_handler` → `OeProtocol.push()`, so **`run_sampler.py` as shipped cannot parse any
> device reply on any platform.**

We enable that line, which is why capture works here at all. That is a genuine bug in the
emulator, independent of everything above.

## Two questions still worth asking them
1. **Do the mics on this unit sample at 100 kHz or 80 kHz?** Their `pdm_mic_config.json` for this
   exact serial says `100000`; the readme says the custom PDM firmware runs the PDM mic
   *"upto 80KHz"*. We stamp 100 kHz into every capture — if it is really 80 kHz, every frequency
   in the analysis is 25 % out. This is the one that can quietly corrupt results.
2. Is the device's self-sleep configurable? It sleeps on its own and stops advertising, which cost
   4 of 6 captures until we widened the scan window (ticket 0024).
