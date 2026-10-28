# Run 20261028_125638 — Modbus-driven temperature sweep (2026-10-28), the RS485-ON twin of 20261028_114027

Purpose (Kim): the same test as the manual-drive run, but with RS485 plugged back into the VFD and the runner
driving it, to see whether the RS485 bus induces noise. **Compare against `20261028_114027`**
(`docs/RUN_20261028_MANUAL_SWEEP.md`).

## Where the data is
| | |
|---|---|
| Azure account / container | `csfbst001` / `eceherning` |
| Blob | `20261028_125638/scope_20261028_125638.h5` |
| Size / content-MD5 | 235,975,031 B / `e7e9f098b72d…` (verified by `py/tools/upload_to_azure.py`) |
| Sidecars (same prefix) | `telemetry_20261028_125638_Modbus_temp_sweep_40-100.jsonl`, `acquire_scope.log`, `heater_guard.log`, `upload.log` |
| Pi (not in git, `py/data/*` is ignored) | `py/data/runs/20261028_125638/` |

## What was run
`react/public/config/Modbus_TempSweep_53min.json` (`make_manual_temp_sweep.py --auto`): **identical schedule,
acquisition block and 50 Hz limit to `Manual_TempSweep_53min.json`** - only `control.manual_drive` is false, so
`test_runner.py` writes the drive (open loop, `rpm = 59.5 x Hz`, tacho read as a cross-check). 12:56:38-13:49:43
local. Result: 264 sweeps, 0 skipped, 11 OE captures, 0 VFD / 0 Omron comm errors, full schedule completed.
Scope exactly as on the front panel (UL 0.4 V, AE 4.0 V, SP 16 V, 0.1 s, 500 k points/channel @ 5 MS/s,
scope FFT off). Median tach deviation from the commanded speed -0.7 % (slip).

## Differences from the manual run (read before comparing)
- **Frequency is exact here** (written by the runner); in the manual run the operator hit +-1 %, worst +4 %.
  `telem_vfd_cmd_hz` is now the commanded Hz; step changes land on the schedule, not +-5-15 s.
- **The runner polls the VFD every tick**, so the RS485 bus is active during the whole run (that is the point).
  Tick is ~5 s rather than 4 s.
- **Started at PV 45 C** (oil cooled from 100 C after the earlier run), vs 44 C for the manual run: same.
  Bearing had run once more (the manual run) - a one-way run-in effect cannot be separated from the bus effect
  with n=1 each; ideally repeat in the other order.
- Heater switched on by hand before the run and off by the guard at the end (verified OFF 13:53:00; PV 80 -> 78 C
  while falling).
- Drive source parameters had to be restored first: Kim had set the drive to manual operation (**00-02 = 0,
  00-05 = 1**); with those, `0x2523` ignored `0x2502`. Written back over Modbus with Kim's OK to **00-02 = 2,
  00-05 = 5** (00-07 = 0 unchanged); `0x2523` then followed `0x2502` (2000/3500/0) and a 20 Hz test spin read
  1180.6 rpm on the tach. **After taking RS485 off the drive and putting it back, re-check these.**
