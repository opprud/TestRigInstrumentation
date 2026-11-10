"""Log load cell (mass_g) and Omron PV every N s after a run ends (cool-down curve).
Usage: cooldown_load_log.py <out.csv> [period_s=30] [duration_min=360]
Run only when no run holds the RP2040 / RS485 ports."""
import sys, time, re, glob, datetime, subprocess
from pymodbus.client import ModbusSerialClient

out = sys.argv[1]
period = float(sys.argv[2]) if len(sys.argv) > 2 else 30
dur = float(sys.argv[3]) if len(sys.argv) > 3 else 360
t_end = time.time() + dur * 60
with open(out, "a", buffering=1) as f:
    f.write("ts,mass_g,omron_pv_c\n")
    while time.time() < t_end:
        t0 = time.time()
        m = ""
        try:
            r = subprocess.run([sys.executable, "util_tool.py", "--port", "/dev/ttyACM0", "load"],
                               capture_output=True, text=True, timeout=20).stdout
            mm = re.search(r"mass_g:\s*(-?[\d.]+)", r)
            m = mm.group(1) if mm else ""
        except Exception:
            pass
        pv = ""
        try:
            c = ModbusSerialClient(glob.glob("/dev/ttyUSB*")[0], baudrate=9600, parity="N",
                                   stopbits=1, bytesize=8, timeout=2)
            if c.connect():
                rr = c.read_holding_registers(0x2000, count=1, device_id=2)
                pv = rr.registers[0] if hasattr(rr, "registers") else ""
            c.close()
        except Exception:
            pass
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')},{m},{pv}\n")
        time.sleep(max(1, period - (time.time() - t0)))
