---
id: 0019
title: Can the OE sensor be reset over BLE instead of by hand? — investigated, answer is no
area: ble
role: dev
status: review
assignee: pi-claude
branch: ticket/0019-oe-remote-reset
depends_on: 0001
pr:
---

## The question
Kim asked on 2026-08-19, with the sensor wedged and nobody at the rig: can we send a reset over
BLE so that nobody has to press the button? It is the right question — the sensor sits on fixed
power, not on USB and not on the Shelly, so a physical reset means a trip to the rig, and a
wedged sensor otherwise blocks every run that needs it.

## Answer: no, not with anything available to us
Two independent reasons, and the second is the one that matters.

**1. No reset command exists.** The protocol has exactly five commands:

| Code | Command |
|---|---|
| 0x01 | UPDATE_FIRMWARE |
| 0x20 | CONFIG_READ |
| 0x21 | CONFIG_WRITE |
| 0x30 | SAMPLE_SENSORS |
| 0x40 | SLEEP |

A search of the whole BearingBrain tree for reset / reboot / restart / watchdog finds one hit: a
comment in `upload_signature_data()` saying *"device restarts when correct signature is
received"*. That restart is the tail of a **signed firmware update** — the device reboots only
after verifying a cryptographic signature over a firmware image we just uploaded. It is not a
reset primitive, and a wrong signature is rejected by design.

**2. Even a reset command would not reach the part that is broken.** Every command travels over
the UART characteristic (`…0254`) and is handled by the device application — which is precisely
what has stopped. Measured on 2026-08-19:

- All 6 readable GATT characteristics answer instantly → the BLE stack is alive
- `start_notify` accepted on both the UART and firmware characteristics, CCCD written
- A hand-framed `CONFIG_READ` write **accepted with response**
- **0 frames** returned in the following 40 s, link up throughout

A write being "accepted" only means the BLE stack acknowledged it at link level. It says nothing
about anyone reading it. The mechanism that would execute a reset is the mechanism that is down,
so no command sent that way can work — a reset command would land in the same dead parser as
everything else.

## The one avenue that could work, and why it is not ours to take
The firmware characteristic (`…0255`, handle 774) is served **below** the application, which is
why it still accepts writes and subscriptions. A genuine signed firmware install would reboot the
device without the application's cooperation.

That needs a real firmware image **and its valid signature from BearingBrain**. Attempting it
without one risks leaving the sensor in a bootloader state — still unreachable, but now also not
running its application, and still with nobody able to touch it. That trades a problem we can fix
with a button press for one we might not be able to fix at all. **Ask BearingBrain** whether they
expose a supported remote reset (or a signed no-op image) before anyone tries this.

## What to do instead, for now
Press the button. The recovery watcher polls every 10 minutes and reports the moment a config
read succeeds, so no one has to sit and retry.

## Worth watching
The device ran fine after Kim's power cycle this morning and wedged again around 11:40. If it
wedges again after the next reset, that is a pattern in the sensor's own firmware rather than an
accident, and it belongs upstream with BearingBrain — a sensor that needs a manual reset at
unpredictable intervals cannot be part of a 13-hour unattended run.
