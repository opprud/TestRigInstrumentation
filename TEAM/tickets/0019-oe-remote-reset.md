---
id: 0019
title: Remote reset of the OE sensor over BLE — no reset command, but OTA is a real recovery path
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

## Correction after reading the whole OTA implementation
Kim pointed at the OTA code, and it changes the answer materially. The first version of this
ticket treated the firmware path as a theoretical curiosity. It is not — it is a working remote
recovery path that we are one artefact short of being able to use.

**The OTA path never touches the application's UART parser.** Firmware blocks are written
straight to the firmware characteristic with a leading opcode byte 1; the signature goes as
opcode 2. `UPDATE_FIRMWARE_CMD` (0x01) appears in the code *only as a reply code*, never as
something we send — so nothing about starting or driving an update requires the application to
be alive. That is the same layer we measured still answering: GATT reads instant, CCCD writes
accepted on the firmware characteristic too.

So the honest statement is not "the sensor cannot be reset remotely". It is:

> **No reset *command* exists — but a successful signed firmware install reboots the device, and
> that path runs below the wedged application. With a signed image from BearingBrain we could
> recover this sensor over the air without anyone driving to the rig.**

There are exactly two opcodes on that characteristic, 1 (data) and 2 (install + signature).
Neither is a reset primitive; the reboot is a side effect of signature verification succeeding.

**Untested:** whether the bootloader-side handler is actually still running. We subscribed to the
firmware characteristic and saw no traffic, but we never wrote to it, so its silence proves
nothing either way.

## Why it is still not ours to take unilaterally
The firmware characteristic (`…0255`, handle 774) is served **below** the application, which is
why it still accepts writes and subscriptions. A genuine signed firmware install would reboot the
device without the application's cooperation.

It needs a real firmware image **and its valid signature**. Only BearingBrain can produce that
pair; a wrong signature is rejected by design, which is the point of signing.

The risk of experimenting instead is asymmetric. Writing unsigned blocks to a device **nobody can
physically reach today** could park it in a state where it is not running its application *and*
not recoverable by the button — trading a problem a finger solves for one that may have no
solution. The sensor is already useless until someone visits it, so there is nothing to buy by
rushing.

**The ask for BearingBrain is now concrete:** a signed image (the current firmware re-signed is
enough — we want the reboot, not new features), or confirmation that a supported remote-reset
opcode exists on the firmware characteristic that we have not found. If they supply either, the
OE sensor stops being able to block an unattended run by hanging.

## What to do instead, for now
Press the button. The recovery watcher polls every 10 minutes and reports the moment a config
read succeeds, so no one has to sit and retry.

## Worth watching
The device ran fine after Kim's power cycle this morning and wedged again around 11:40. If it
wedges again after the next reset, that is a pattern in the sensor's own firmware rather than an
accident, and it belongs upstream with BearingBrain — a sensor that needs a manual reset at
unpredictable intervals cannot be part of a 13-hour unattended run.
