#!/usr/bin/env python3
"""
Minimal backend runner der udfører en tidsstyret testsekvens og logger samples i JSONL.

Mål for "komplet sekvens":
- Følg setpoints fra JSON (rpm + temperature) over tid
- Closed-loop RPM (PI) via tachometer feedback (RP2040 SPEED?)
- Log: rpm_target/rpm_meas/hz_cmd/temp_target + omron/vfd status
- Stop korrekt (duration/stop_event + simple safety)

Bemærk:
- RS485 clients holdes åbne under hele run for at undgå open/close storms.
- RP2040 serial holdes også åben (hvis tilgængelig).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import time
import statistics
from typing import Optional, Tuple


@dataclass
class RunnerResult:
    log_path: str


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _parse_first_float(s: str) -> Optional[float]:
    if not s:
        return None
    m = _NUMBER_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _normalize_schedule(items: Any) -> List[Tuple[float, float]]:
    """Accepts [{time_sec,value},...] or [[t,v],...] or [(t,v),...] -> sorted list."""
    out: List[Tuple[float, float]] = []
    if not items:
        return out

    if isinstance(items, dict):
        # Not expected, but tolerate {"time_sec":..,"value":..}
        t = items.get("time_sec")
        v = items.get("value")
        if t is not None and v is not None:
            out.append((float(t), float(v)))
        return out

    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                t = it.get("time_sec")
                v = it.get("value")
                if t is None or v is None:
                    continue
                out.append((float(t), float(v)))
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                out.append((float(it[0]), float(it[1])))
            else:
                # ignore unknown entry
                continue

    out.sort(key=lambda x: x[0])
    return out


def _value_at(schedule: List[Tuple[float, float]], t_sec: float) -> Optional[float]:
    """Piecewise-constant: last value where time<=t_sec."""
    if not schedule:
        return None
    # Fast linear scan is fine (schedules are small), but keep it simple:
    last_v = schedule[0][1]
    for ts, v in schedule:
        if t_sec < ts:
            break
        last_v = v
    return last_v


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


class TestRunner:
    def __init__(
        self,
        *,
        rs485_lock: asyncio.Lock,
        data_dir: Path,
        discover_serial_ports: Callable[[], Dict[str, Any]],
        E5CCTool,
        RS510VFDController,
        run_id: Optional[str] = None,   # <-- NY
    ):
        self._rs485_lock = rs485_lock
        self._data_dir = data_dir
        self._discover_serial_ports = discover_serial_ports
        self._E5CCTool = E5CCTool
        self._RS510VFDController = RS510VFDController
        self._run_id = run_id           # <-- NY
        
    def _make_logfile(self, profile_name: Optional[str]) -> Path:
        # If run_id is supplied (e.g. from acquire_scope_data.py), make filename deterministic
        # so JSONL can be paired 1:1 with HDF5.
        ts = self._run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "_".join((profile_name or "run").split())
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Use a stable prefix so it's easy to recognize in a run folder
        return self._data_dir / f"telemetry_{ts}_{safe_name}.jsonl"
        
    async def run(
        self,
        cfg: Dict[str, Any],
        *,
        update_cb: Callable[[Dict[str, Any]], None],
        stop_event: asyncio.Event,
    ) -> RunnerResult:
        # --- Parse config (tolerant) ---
        profile_name = cfg.get("name") or (cfg.get("test_parameters", {}) or {}).get("test_name")
        duration_min = (
            cfg.get("duration_minutes")
            or (cfg.get("test_parameters", {}) or {}).get("duration_minutes")
            or 0
        )
        duration_sec = int(float(duration_min) * 60)

        acq = cfg.get("acquisition", {}) or {}
        interval_sec = float(acq.get("interval_sec") or 1.0)
        if interval_sec <= 0:
            interval_sec = 1.0
        samples_per_step = int(acq.get("samples_per_step") or 1)
        if samples_per_step <= 0:
            samples_per_step = 1

        tick_sec = interval_sec / float(samples_per_step)

        setpoints = cfg.get("setpoints", {}) or {}

        # Schedules (preferred)
        rpm_schedule = _normalize_schedule(setpoints.get("rpm"))
        temp_schedule = _normalize_schedule(setpoints.get("temperature"))

        # Fallback single setpoints (older profiles)
        fallback_temp_c = setpoints.get("omron_sv_c") or setpoints.get("temperature_setpoint_c")
        fallback_hz = setpoints.get("vfd_frequency_hz") or setpoints.get("frequency_hz")

        omron_unit_id = int(setpoints.get("omron_unit_id") or 2)
        vfd_slave_id = int(setpoints.get("vfd_slave_id") or 3)

        # Control params (PI)
        control = (cfg.get("control") or {}) if isinstance(cfg.get("control"), dict) else {}
        vfd_min_hz = float(control.get("vfd_min_hz", 0.0))
        vfd_max_hz = float(control.get("vfd_max_hz", 60.0))
        rpm_per_hz_guess = float(control.get("rpm_per_hz_guess", 30.0))  # feedforward initial guess
        open_loop = bool(control.get("open_loop", False))  # True: command Hz from target, ignore tacho
        kp = float(control.get("kp_hz_per_rpm", 0.002))
        ki = float(control.get("ki_hz_per_rpm_s", 0.0004))
        integrator_limit_hz = float(control.get("integrator_limit_hz", 20.0))
        rpm_deadband = float(control.get("rpm_deadband", 5.0))
        hz_min_delta = float(control.get("hz_min_delta", 0.05))  # only send if change >= this
        hz_rate_limit = float(control.get("hz_rate_limit_hz_per_s", 5.0))  # max delta per second
        max_missing_rpm_sec = float(control.get("max_missing_rpm_sec", 10.0))
        max_consecutive_modbus_errors = int(control.get("max_consecutive_modbus_errors", 10))

        log_path = self._make_logfile(profile_name)

        # --- Resolve ports once ---
        ports = self._discover_serial_ports()
        ftdi_ports = ports.get("ftdi", [])
        rs485_port = ftdi_ports[0]["device"] if ftdi_ports else None

        rp_ports = ports.get("rp2040", [])
        rp_port = rp_ports[0]["device"] if rp_ports and rp_ports[0].get("device") else None

        header = {
            "type": "run_header",
            "timestamp": _now_iso(),
            "profile_name": profile_name,
            "duration_sec": duration_sec,
            "interval_sec": interval_sec,
            "samples_per_step": samples_per_step,
            "tick_sec": tick_sec,
            "rs485_port": rs485_port,
            "rp2040_port": rp_port,
            "omron_unit_id": omron_unit_id,
            "vfd_slave_id": vfd_slave_id,
            "setpoints": setpoints,
            "control": {
                "vfd_min_hz": vfd_min_hz,
                "vfd_max_hz": vfd_max_hz,
                "rpm_per_hz_guess": rpm_per_hz_guess,
                "open_loop": open_loop,
                "kp_hz_per_rpm": kp,
                "ki_hz_per_rpm_s": ki,
                "integrator_limit_hz": integrator_limit_hz,
                "rpm_deadband": rpm_deadband,
                "hz_min_delta": hz_min_delta,
                "hz_rate_limit_hz_per_s": hz_rate_limit,
                "max_missing_rpm_sec": max_missing_rpm_sec,
                "max_consecutive_modbus_errors": max_consecutive_modbus_errors,
            },
        }
        log_path.write_text(json.dumps(header) + "\n", encoding="utf-8")

        started_at = datetime.now()
        sample_idx = 0

        # Persistent clients
        omron_tool = None
        vfd = None
        rp_ser = None

        # State for PI + setpoint sending
        last_temp_sent: Optional[float] = None
        vfd_started = False
        vfd_start_failures = 0
        # Refusing to start the drive is fatal: without it the rig sits still while
        # the schedule runs on, and the recorded data looks like a normal test.
        vfd_start_max_failures = int(control.get("vfd_start_max_failures", 5))
        integ_hz = 0.0
        last_hz_cmd: Optional[float] = None
        last_hz_sent: Optional[float] = None
        last_send_t = 0.0
        last_good_rpm_t = 0.0
        stop_reason: Optional[str] = None

        consecutive_modbus_errors = 0

        # --- Init / open connections once ---
        if rs485_port:
            async with self._rs485_lock:
                try:
                    omron_tool = self._E5CCTool(
                        port=rs485_port,
                        baudrate=9600,
                        parity="N",
                        bytesize=8,
                        stopbits=1,
                        timeout=2.0,
                        unit_id=omron_unit_id,
                        pv_address=0x2000,
                        sv_address=0x2103,
                        scale=1.0,
                        debug=False,
                    )
                except Exception:
                    omron_tool = None

                try:
                    vfd = self._RS510VFDController(
                        port=rs485_port,
                        slave_id=vfd_slave_id,
                        baudrate=9600,
                        timeout=2.0,
                        debug=False,
                    )
                    if hasattr(vfd, "connect"):
                        vfd.connect()
                except Exception:
                    vfd = None

        # RP2040 serial (tachometer)
        if rp_port:
            try:
                import serial  # local import (optional dependency in some setups)
                rp_ser = serial.Serial(rp_port, 115200, timeout=1.0)
            except Exception:
                rp_ser = None


        MAX_RPM = 50000.0   # kun til sample-filtering (behold høj)
        MIN_RPM = 0.0
        N_SAMPLES = 5

        # ---- Nye "real world" guardrails ----
        REALISTIC_MAX_RPM = 6000.0      # sæt efter dit rig (fx 6000/10000)
        REALISTIC_MIN_RPM = 0.0
        MAX_RPM_SLEW_PER_SEC = 1500.0   # max rpm-ændring pr sekund (justér)

        _last_good_rpm: Optional[float] = None
        _last_good_t: Optional[float] = None

        def _read_rpm() -> Tuple[Optional[float], Optional[str]]:
            nonlocal _last_good_rpm, _last_good_t  # <-- vigtigt (ikke global)

            if rp_ser is None:
                return _last_good_rpm, "rp2040_not_available"

            try:
                vals = []
                for _ in range(N_SAMPLES):
                    try:
                        rp_ser.reset_input_buffer()
                    except Exception:
                        pass

                    rp_ser.write(b"SPEED?\r\n")
                    time.sleep(0.07)

                    # Firmware v1.2.x can interleave an unsolicited
                    # "OK AUTOGAIN gain=N" line here. Its number parses as a
                    # plausible rpm (64 or 128), so read past it and accept
                    # only the "rpm=" field of an actual SPEED reply.
                    v = None
                    _deadline = time.monotonic() + 0.5
                    for _ in range(4):
                        if time.monotonic() > _deadline:
                            break
                        line = rp_ser.readline().decode("ascii", errors="ignore").strip()
                        if not line:
                            break
                        if "rpm=" in line:
                            v = _parse_first_float(line.split("rpm=", 1)[1])
                            break
                        if "AUTOGAIN" in line:
                            print(f"[runner] load cell gain switch: {line}", flush=True)
                        if line.startswith("ERR"):
                            print(f"[runner] SPEED? -> {line}", flush=True)
                            break
                    if v is None:
                        continue

                    v = float(v)
                    if MIN_RPM <= v <= MAX_RPM:
                        vals.append(v)

                if not vals:
                    return _last_good_rpm, "bad_speed_response:no_valid_samples"

                rpm = float(statistics.median(vals))
                now = time.time()

                # (A) Sanity range (realistisk)
                if not (REALISTIC_MIN_RPM <= rpm <= REALISTIC_MAX_RPM):
                    return _last_good_rpm, f"rpm_out_of_range:{rpm:.1f}"

                # (B) Slew-rate limit (anti-spike)
                if _last_good_rpm is not None and _last_good_t is not None:
                    dt = max(1e-3, now - _last_good_t)
                    max_change = MAX_RPM_SLEW_PER_SEC * dt
                    if abs(rpm - _last_good_rpm) > max_change:
                        return _last_good_rpm, f"rpm_slew_limited:{rpm:.1f}"

                _last_good_rpm = rpm
                _last_good_t = now
                return rpm, None

            except Exception as e:
                return _last_good_rpm, str(e)

        def _read_load() -> Optional[float]:
            """Read load cell from RP2040 via LOAD? command."""
            if rp_ser is None:
                return None
            try:
                rp_ser.reset_input_buffer()
                rp_ser.write(b"LOAD?\r\n")
                time.sleep(0.15)
                import re as _re
                # Firmware v1.2.0 emits an unsolicited "OK AUTOGAIN gain=N" line
                # whenever it switches HX711 gain. Reading exactly one line would
                # take that as the answer and drop the sample without a trace, so
                # read past it — bounded by a deadline and a line cap so a chatty
                # or wedged board cannot stall the control tick.
                deadline = time.monotonic() + 0.8
                for _ in range(4):
                    if time.monotonic() > deadline:
                        break
                    line = rp_ser.readline().decode("ascii", errors="ignore").strip()
                    if not line:
                        break
                    m = _re.search(r"mass_g=(-?[\d.]+)", line)
                    if m:
                        return float(m.group(1))
                    if line.startswith("ERR"):
                        # e.g. "ERR 21 ADC_saturation" — the load cell is railed.
                        print(f"[runner] LOAD? -> {line}", flush=True)
                        break
                    if "AUTOGAIN" in line:
                        print(f"[runner] load cell gain switch: {line}", flush=True)
            except Exception:
                pass
            return None

        # Pre-set initial temperature (if available) to first scheduled or fallback
        initial_temp = _value_at(temp_schedule, 0.0)
        if initial_temp is None and fallback_temp_c is not None:
            initial_temp = float(fallback_temp_c)

        if initial_temp is not None and omron_tool is not None:
            async with self._rs485_lock:
                try:
                    omron_tool.write_sv_c(float(initial_temp))
                    last_temp_sent = float(initial_temp)
                except Exception:
                    pass

        # If no rpm schedule, allow fallback hz
        if (not rpm_schedule) and (fallback_hz is not None) and vfd is not None:
            hz0 = _clamp(float(fallback_hz), vfd_min_hz, vfd_max_hz)
            async with self._rs485_lock:
                try:
                    vfd.set_frequency(hz0)
                    vfd.start_forward(hz0)
                    vfd_started = True
                    last_hz_cmd = hz0
                    last_hz_sent = hz0
                except Exception:
                    pass

        # --- Main loop ---
        total_steps = int(duration_sec / tick_sec) if duration_sec > 0 else 0

        while True:
            if stop_event.is_set():
                stop_reason = stop_reason or "stopped_by_user"
                break

            elapsed = (datetime.now() - started_at).total_seconds()
            if duration_sec > 0 and elapsed >= duration_sec:
                stop_reason = stop_reason or "duration_reached"
                break

            sample_idx += 1

            # Compute targets from schedules
            rpm_target = _value_at(rpm_schedule, elapsed)
            temp_target = _value_at(temp_schedule, elapsed)
            if temp_target is None and fallback_temp_c is not None:
                temp_target = float(fallback_temp_c)

            # Read tachometer RPM
            rpm_meas, rpm_err = _read_rpm()

            # Read load cell
            mass_g = _read_load()
            now_t = float(elapsed)
            if rpm_meas is not None:
                last_good_rpm_t = now_t
            elif rpm_target is not None and rpm_target > 0:
                # Only trigger tachometer-missing stop if RP2040 was present at startup.
                # If rp_ser is None (never connected), we never had RPM data — don't stop.
                # In open-loop mode we ignore the tacho entirely, so never stop on it.
                if (not open_loop) and rp_ser is not None and (now_t - last_good_rpm_t) > max_missing_rpm_sec:
                    stop_reason = f"tachometer_missing>{max_missing_rpm_sec}s"
                    break

            # Control: PI to Hz
            hz_cmd = last_hz_cmd if last_hz_cmd is not None else 0.0
            p_term = None
            i_term = None
            err = None

            if rpm_target is not None and rpm_target > 0 and vfd is not None:
                # Ensure VFD is running
                if not vfd_started:
                    # initial guess (feedforward) to get moving
                    hz_guess = _clamp(float(rpm_target) / rpm_per_hz_guess, vfd_min_hz, vfd_max_hz)
                    async with self._rs485_lock:
                        try:
                            vfd.set_frequency(hz_guess)
                            vfd.start_forward(hz_guess)
                            vfd_started = True
                            vfd_start_failures = 0
                            last_hz_cmd = hz_guess
                            last_hz_sent = hz_guess
                            hz_cmd = hz_guess
                        except Exception as e:
                            # Never swallow this. If the drive cannot be started the
                            # bearing does not turn, yet the schedule keeps advancing
                            # and telemetry still reports the *commanded* Hz, so the
                            # run looks healthy while recording a stationary rig.
                            vfd_start_failures += 1
                            print(f"[runner] vfd start failed "
                                  f"({vfd_start_failures}/{vfd_start_max_failures}): {e!r}",
                                  flush=True)
                            if vfd_start_failures >= vfd_start_max_failures:
                                stop_reason = (f"vfd_start_failed after "
                                               f"{vfd_start_failures} attempts: {e}")

                if open_loop:
                    # Open-loop: command Hz straight from the target via the rpm/Hz
                    # calibration; ignore the tacho entirely (robust when the optical
                    # sensor is unreliable). True speed is reconstructed offline from Hz.
                    hz_cmd = _clamp(float(rpm_target) / rpm_per_hz_guess, vfd_min_hz, vfd_max_hz)
                    if last_hz_cmd is not None:
                        max_d = hz_rate_limit * float(tick_sec)
                        hz_cmd = _clamp(hz_cmd, last_hz_cmd - max_d, last_hz_cmd + max_d)
                    last_hz_cmd = hz_cmd

                elif rpm_meas is not None:
                    err = float(rpm_target) - float(rpm_meas)
                    if abs(err) < rpm_deadband:
                        err = 0.0

                    # Feedforward baseline for positional PI
                    hz_ff = float(rpm_target) / rpm_per_hz_guess

                    # Integrator (units: Hz)
                    integ_hz += ki * err * float(tick_sec)
                    integ_hz = _clamp(integ_hz, -integrator_limit_hz, integrator_limit_hz)

                    p_term = kp * err
                    i_term = integ_hz

                    # Positional PI (correct): hz = ff + P + I
                    hz_cmd = hz_ff + p_term + i_term
                    hz_cmd = _clamp(hz_cmd, vfd_min_hz, vfd_max_hz)

                    # Rate limit
                    if last_hz_cmd is not None:
                        max_d = hz_rate_limit * float(tick_sec)
                        hz_cmd = _clamp(hz_cmd, last_hz_cmd - max_d, last_hz_cmd + max_d)

                    last_hz_cmd = hz_cmd

            else:
                # No rpm target -> optionally stop motor
                if vfd_started and vfd is not None:
                    async with self._rs485_lock:
                        try:
                            vfd.stop()
                        except Exception:
                            pass
                    vfd_started = False
                last_hz_cmd = 0.0

            # Send new Omron SV only when it changes meaningfully
            if (temp_target is not None) and (omron_tool is not None):
                if last_temp_sent is None or abs(float(temp_target) - float(last_temp_sent)) >= 0.1:
                    async with self._rs485_lock:
                        try:
                            omron_tool.write_sv_c(float(temp_target))
                            last_temp_sent = float(temp_target)
                        except Exception:
                            pass

            # Send Hz only when it changes enough (and motor is started)
            if vfd is not None and vfd_started and last_hz_cmd is not None:
                should_send = False
                if last_hz_sent is None:
                    should_send = True
                elif abs(float(last_hz_cmd) - float(last_hz_sent)) >= hz_min_delta:
                    should_send = True
                elif (now_t - last_send_t) >= 1.0:
                    # periodic refresh
                    should_send = True

                if should_send:
                    async with self._rs485_lock:
                        try:
                            vfd.set_frequency(float(last_hz_cmd))
                            last_hz_sent = float(last_hz_cmd)
                            last_send_t = now_t
                            consecutive_modbus_errors = 0
                        except Exception:
                            consecutive_modbus_errors += 1

            # Read Omron PV/SV + VFD status for logging
            rec: Dict[str, Any] = {
                "type": "sample",
                "idx": sample_idx,
                "timestamp": _now_iso(),
                "elapsed_sec": float(elapsed),
                "rpm_target": rpm_target,
                "rpm_meas": rpm_meas,
                "rpm_read_error": rpm_err,
                "vfd_cmd_hz": last_hz_cmd,
                "pi": {"err": err, "p": p_term, "i": i_term},
                "temp_target": temp_target,
                "mass_g": mass_g,
            }

            if rs485_port:
                async with self._rs485_lock:
                    # Omron read PV/SV
                    if omron_tool is None:
                        # Hardware port was found but Omron never initialised — not a comm error
                        rec["omron_error"] = "not_initialized"
                    else:
                        try:
                            rec["omron_pv_c"] = omron_tool.read_pv_c()
                            rec["omron_sv_c"] = omron_tool.read_sv_c()
                            consecutive_modbus_errors = 0
                        except Exception as e:
                            rec["omron_error"] = str(e)
                            consecutive_modbus_errors += 1

                    # VFD status
                    if vfd is None:
                        # Hardware port was found but VFD never initialised — not a comm error
                        rec["vfd_error"] = "not_initialized"
                    else:
                        try:
                            st = vfd.get_status()
                            rec["vfd_frequency_cmd_hz"] = getattr(
                                st, "frequency_cmd_hz", getattr(st, "frequency_command_hz", None)
                            )
                            rc = getattr(st, "run_command", None)
                            rec["vfd_run_command"] = rc.name if rc else None
                            rec["vfd_fault_code"] = getattr(st, "fault_code", None)
                            rec["vfd_is_running"] = getattr(st, "is_running", None)

                            # Safety: VFD fault
                            fault = rec.get("vfd_fault_code")
                            if fault not in (None, 0, "0"):
                                stop_reason = f"vfd_fault:{fault}"
                        except Exception as e:
                            rec["vfd_error"] = str(e)
                            consecutive_modbus_errors += 1

            # Safety: too many REAL comm errors (not counting "not_initialized")
            if consecutive_modbus_errors >= max_consecutive_modbus_errors:
                stop_reason = stop_reason or f"modbus_errors>={max_consecutive_modbus_errors}"

            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

            update_cb(
                {
                    "elapsed_sec":    float(elapsed),
                    "current_step":   sample_idx,
                    "total_steps":    total_steps,
                    "log_path":       str(log_path),
                    "stop_reason":    stop_reason,
                    "rpm_target":     rec.get("rpm_target"),
                    "rpm_meas":       rec.get("rpm_meas"),
                    "temp_target":    rec.get("temp_target"),
                    "omron_pv_c":     rec.get("omron_pv_c"),
                    "omron_sv_c":     rec.get("omron_sv_c"),
                    "vfd_cmd_hz":     rec.get("vfd_cmd_hz"),
                    "vfd_is_running": rec.get("vfd_is_running"),
                    "mass_g":         rec.get("mass_g"),
                }
            )

            if stop_reason:
                break

            await asyncio.sleep(tick_sec)

        # --- Stop VFD on end (default True) ---
        stop_on_end = bool((cfg.get("setpoints", {}) or {}).get("vfd_stop_on_end", True))
        if stop_on_end and rs485_port and vfd is not None:
            async with self._rs485_lock:
                try:
                    vfd.stop()
                except Exception:
                    pass

        # Write footer
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "run_end", "ts": _now_iso(), "reason": stop_reason}) + "\n")

        # --- Cleanup ---
        if rp_ser is not None:
            try:
                rp_ser.close()
            except Exception:
                pass

        if rs485_port:
            async with self._rs485_lock:
                try:
                    if omron_tool is not None:
                        omron_tool.close()
                except Exception:
                    pass
                try:
                    if vfd is not None and hasattr(vfd, "disconnect"):
                        vfd.disconnect()
                except Exception:
                    pass

        return RunnerResult(log_path=str(log_path))
