# VPS heater-safety watchdog (ticket 0034)

Independent always-running daemon on the **MQTT-broker VPS** (`185.81.165.190`) that
guarantees the oil heater (Shelly Pro 4PM **channel 0**) is OFF whenever no live, healthy
run legitimately wants heat. It is deliberately independent of the rig Pi: the broker is
local (`localhost:1883`), so a frozen / dead / rebooting Pi cannot stop the watchdog from
cutting the relay. Motivated by the 2026-08-26 incident where a Pi freeze left the heater
regulating at 100 °C for 2 h 16 min unattended (tickets 0033 / 0004).

## Fail-safe principle
The **absence** of a positive "a run is alive and heating" signal is what triggers
heater-off. A frozen Pi publishes no heartbeat → heater is cut, not left on. Clean test-end
is the same rule: the heartbeat stops → heater off.

## Heartbeat contract (rig Pi → VPS)   ⚠ Pi side must be implemented before arming
```
topic:   testrig/run/heartbeat          (NOT retained)
payload: {"run_id": "<id>", "heating": true, "ts": <unix_seconds>, "host": "pi"}
cadence: every ~30 s while a heated run is active AND wants heat
```
A heartbeat counts as "heat wanted" only when fresh (`age < stale_sec`, default 180 s) and
`heating == true`. Stop publishing at run-end; the watchdog then backs up the on-Pi guard.

## State / control (matches `py/shelly_control.py`)
- Command OFF: publish to `<device>/rpc` → `Switch.Set {"id":0,"on":false}`.
- Read state: `Switch.GetStatus` reply on `<src>/rpc`, plus `<device>/status/switch:0` and
  `<device>/events/rpc` (`NotifyStatus`). This Shelly keeps **no retained channel state**, so
  the rule is *"heat not wanted AND heater ON or not-confirmed-OFF → send OFF"*. The only true
  confirmation the relay opened is falling bearing/oil temperature.

## Files
| file | role |
|---|---|
| `watchdog.py` | the daemon (stdlib + vendored paho-mqtt) |
| `config.example.json` | copy to `config.json` on the VPS; `armed:false` = observe-only |
| `heater-watchdog.service` | systemd unit (runs as `claude-win`, `Restart=always`) |
| `install_root.sh` | installs/updates the service — run as root |

## Deploy (on the VPS, as `claude-win`)
```
mkdir -p ~/heater-watchdog/logs
# upload watchdog.py, config.example.json -> config.json, heater-watchdog.service, install_root.sh
# vendor paho without pip/venv (both need root here):
python3 -m zipfile -e paho_mqtt-2.1.0-py3-none-any.whl vendor/
PYTHONPATH=vendor python3 watchdog.py --once --config config.json   # smoke test
sudo bash install_root.sh                                           # persistent service
```

## Arming
Ships **observe-only** (`armed:false`): it logs the decision and publishes
`testrig/watchdog/status` every cycle but **never actuates the relay**. The on-Pi guard
remains primary until then. Arm only **after** the Pi heartbeat publisher is live and verified
(otherwise the watchdog would cut the heater on every run):
```
# in config.json set "armed": true
sudo systemctl restart heater-watchdog
```

## Operate
```
journalctl -u heater-watchdog -f                       # live log
mosquitto_sub -h localhost -u mqttuser -P 3711 -t testrig/watchdog/status   # current verdict
touch ~/heater-watchdog/MAINTENANCE                    # override: allow heater on for bench work
rm    ~/heater-watchdog/MAINTENANCE                    # end maintenance
```

## Acceptance evidence (2026-10-29, live relay)
| case | input | decision | relay |
|---|---|---|---|
| A | fresh heartbeat | `run-alive` | untouched |
| B | no heartbeat, heater OFF | `off-confirmed` | untouched |
| C | no heartbeat, heater ON, **armed:false** | `would-cut` (log only) | **stays ON** |
| D | no heartbeat, heater ON, **armed:true** | `INTERVENTION → Switch.Set OFF` | **→ OFF, 0 W** |

## Limitations / scope
- The VPS cannot reach the Omron (RS485 is on the Pi), so driving the Omron **SV down** on a
  clean end stays a Pi-side responsibility. The relay cut here is the hard physical backstop and
  de-energises the heater regardless of the Omron SV.
- Optional Pi power-cycle via Shelly ch3 (ticket 0033) is **disabled** (`pi_cycle_enabled:false`);
  heater-off is the safety-critical core and never gated on rebooting the Pi.
