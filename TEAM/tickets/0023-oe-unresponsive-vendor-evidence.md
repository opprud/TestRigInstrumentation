---
id: 0023
title: OE sensor stopped responding — evidence package for BearingBrain
area: ble
role: dev
status: open
assignee: pi-claude
branch: ticket/0023-oe-unresponsive-vendor-evidence
depends_on: 0001, 0019
pr:
---

## Summary for the vendor
Sensor **OE00031204100074** captured mic data normally on 2026-08-19 at 11:35, 11:44 and 11:52,
and has answered **no protocol command since ~12:17 that day**. It is awake and connectable; it
simply never replies. Neither the reset button nor a power cycle restores it.

**BearingBrain's own `run_sampler.py` fails identically to our integration**, so this is not
something we built on top: `read_config` times out, `sample` times out after 120 s, and the saved
JSON comes back with `device_configs: {}`.

## What is confirmed working on the device
Measured with raw GATT, bypassing the OE protocol entirely:

- Advertises normally as `OE00031204100074` (RSSI ≈ −68 dBm), matching the readme's example
  exactly, including the cached name `Packet` and the empty `0xFFFF` manufacturer field.
- Connects on demand; the link stays up for minutes.
- **All 6 readable GATT characteristics answer instantly** — Database Hash, Client/Server
  Supported Features, Central Address Resolution, Appearance, Device Name.
- `start_notify` accepted on **both** the UART and firmware characteristics; CCCD written.
- A hand-framed `CONFIG_READ` write is **accepted with response** at ATT level.
- **The red LED changes cadence when we connect and disconnect** — so the application is running
  and tracking connection state. This is not a crashed or browned-out device.

## What does not work
**Zero notifications, ever.** Across 60+ probes over more than a day, and five minutes of
sustained polling on one held connection, not one frame has arrived on either characteristic.

## What has been ruled out, with evidence
| Suspicion | How it was ruled out |
|---|---|
| Our integration | The vendor's own `run_sampler.py` fails identically; our sampler is not in that path |
| Our edits to `oe_device.py` | The three successful captures on 08-19 ran **with** those edits already committed (08-18 12:08) |
| The removed 3 s "Windows BLE stack" delay | Temporarily restored; identical timeout |
| Stale BlueZ bond or attribute cache | No bond and no cache exist on disk for this address |
| Wrong characteristic | `…0255` is the firmware/DFU channel; the harness uses `…0254`, and both were subscribed |
| An abnormal advertisement | It matches the vendor readme's own example output exactly |
| Red LED as a fault indication | It means awake and waiting for a BLE connection |
| A wake-window we kept missing | Five minutes of continuous polling on a held connection: silent |
| Firmware-channel opcodes | Bogus signature (opcode 2) and opcodes 0x00/0x03 all accepted, all silent |

## A defect in the shipped code, independent of the above
Confirmed against the **pristine vendor tree** (`/home/aau/projects/BearingBrain/
BearingBrainGWEmulator 1`), whose `oe_protocol.py`, `utils.py`, `run_sampler.py` and
`ble_debug_scan.py` are byte-identical to our copies:

> In `oe_device.py`, `connect()` has its `start_notify(UART_CHAR_UUID, …)` line **commented out**.
> The only active subscription in the whole tree is on the *firmware* characteristic inside
> `connect_ota()`. Since `oe_protocol` never calls `read_gatt_char`, nothing can ever reach
> `notification_handler` → `OeProtocol.push()`, so **`run_sampler.py` as shipped cannot parse any
> device reply on any platform.**

We enable that line, which is why capture worked here at all. Worth flagging to BearingBrain as a
bug in the emulator regardless of the hardware question — and it means anyone else running their
`run_sampler.py` unmodified will see exactly the timeouts we are seeing now, for a different
reason. **Do not let that coincidence muddy the report:** our copy has the fix, and still gets
nothing.

## Questions for BearingBrain
1. What state is the sensor in — awake, connectable, GATT serving, application tracking the link,
   yet answering no protocol command? What recovers it, given the button and power cycle do not?
2. Is there a supported remote reset? A signed firmware install reboots the device over a path
   that runs below the application (ticket 0019) — would they supply a signed image, even the
   current firmware re-signed, purely for the reboot?
3. **Do the mics on this unit sample at 100 kHz or 80 kHz?** Their `pdm_mic_config.json` for this
   exact serial says 100000, while the readme says the custom PDM firmware runs the PDM mic
   "upto 80KHz". A 100 kHz label on 80 kHz data puts every frequency 25 % out.

## Reference material now available
The full vendor tree is at `/home/aau/projects/BearingBrain/BearingBrainGWEmulator 1` and holds
four modules we never had — `ble_service.py`, `device_handler.py`, `interface.py`, `main.py` —
plus `gateway-service-device-configs` and `gateway-service-measurement-creator`. `device_handler.py`
shows the production flow: connect → `read_all_configs` → handle configs → sample. We fail at the
first step, so the ordering is not what is wrong. **That path is outside the repo and can vanish;
worth importing the missing pieces.**
