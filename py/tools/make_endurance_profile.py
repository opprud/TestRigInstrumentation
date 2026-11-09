"""
Endurance-campaign profiles (bus 2026-11-09): base 13 h profile Keratech22.json with a 30 C speed sweep
added in front, the scope frozen for the whole matrix, and per-run metadata.

    py/.venv/bin/python tools/make_endurance_profile.py            # writes all 9 + 9 slip-ring twins

Matrix: 3 lubricants x 3 clamp loads (14 / 60 / 150 kg).  Twin = same profile, slip-ring probe lifted and
bias PSU off (slip_ring "lifted", bias_v 0.0); SP stays on as a noise reference.
Frozen scope (Kim, 2026-11-09): scope FFT OFF (500 k pts @ 5 MS/s at 0.1 s), SP 9.0 V / offset 2.0 as in the
live profiles, UL 0.4 V, AE 5.0 V. Bias 1 V is set by hand on the PSU - it is logged here, not controlled.
"""
import copy, json
from pathlib import Path

CFG = Path(__file__).resolve().parents[2] / "react" / "public" / "config"
SWEEP_RPM = [0, 600, 1200, 1800, 2400, 3000, 2400, 1800, 1200, 600, 0]     # 1 min per step
SHIFT = 60 * len(SWEEP_RPM)                                                   # 660 s
START_TEMP_C = 30

LUBRICANTS = {
    "keratech22": {"product_name": "Keratech 22", "manufacturer": "Kerax", "base_oil": "Parafin Oil",
                   "additives": "None", "viscosity_cSt": 22},
    "foodlube_h1_power_22": {"product_name": "Foodlube H1 Power 22", "manufacturer": "Foodlube",
                             "base_oil": "FILL IN (different base oil from Keratech 22)",
                             "additives": "FILL IN", "viscosity_cSt": 22},
    "foodlube_high_torq_150": {"product_name": "Foodlube High Torq 150", "manufacturer": "Foodlube",
                               "base_oil": "FILL IN", "additives": "FILL IN", "viscosity_cSt": 150},
}
MEASURED_KG = {14: 14.53}          # load cell reading when the clamp was set (2026-11-09, mounted, tare of 2026-09-23)
CLAMP_KG = {14: "measured on the load cell", 60: "measured on the load cell",
            150: "ESTIMATE from clamp turns, +/-30 % (above the cell's ~74 kg ceiling)"}

SCOPE = {"UL": {"timebase_range": 0.1, "volt_range": 0.4, "volt_offset": 0.0, "coupling": "DC"},
         "AE": {"timebase_range": 0.1, "volt_range": 5.0, "volt_offset": 0.0, "coupling": "DC"},
         "SP": {"timebase_range": 0.1, "volt_range": 9.0, "volt_offset": 2.0, "coupling": "DC"}}


def build(lub_key, kg, twin):
    base = json.loads((CFG / "Keratech22.json").read_text())
    d = copy.deepcopy(base)
    sp = base["setpoints"]
    rpm = [{"time_sec": i * 60 + o, "value": v} for i, v in enumerate(SWEEP_RPM) for o in (0, 59)]
    rpm[-1] = {"time_sec": SHIFT - 1, "value": 0}
    temp = [{"time_sec": 0, "value": START_TEMP_C}, {"time_sec": SHIFT - 1, "value": START_TEMP_C}]
    d["setpoints"] = {"rpm": rpm + [{"time_sec": p["time_sec"] + SHIFT, "value": p["value"]} for p in sp["rpm"]],
                      "temperature": temp + [{"time_sec": p["time_sec"] + SHIFT, "value": p["value"]} for p in sp["temperature"]]}
    end_sec = d["setpoints"]["rpm"][-1]["time_sec"]
    d["duration_minutes"] = end_sec // 60 + 1
    lub = LUBRICANTS[lub_key]
    tag = f"{lub_key}_{kg}kg" + ("_sliptwin" if twin else "")
    d["name"] = f"Endurance {tag}"
    d["description"] = (f"Lubricant endurance matrix: {lub['product_name']}, clamp {kg} kg, SKF SYJ25 hybrid B02. "
                        f"A 30 C speed sweep (0-3000-0 rpm, 1 min/step, {SHIFT} s) precedes the existing 13 h Keratech22 profile, "
                        f"which is shifted by {SHIFT} s. Scope frozen across the matrix: FFT off, 500 k pts @ 5 MS/s, "
                        f"UL 0.4 V, AE 5.0 V, SP 9.0 V / offset 2.0. "
                        + ("SLIP-RING TWIN: probe lifted, bias PSU off." if twin else "Slip ring connected, bias 1.0 V set on the PSU."))
    d["scope_channels"] = copy.deepcopy(SCOPE)
    d["scope_fft"] = {"enabled": False, "save": False}
    d["bearing"] = {**base.get("bearing", {}), "model": "SYJ25 hybrid B02",
                    "material": "Hybrid, 1 steel ball (B02)", "notes": "Endurance matrix specimen (Kim, 2026-11-09)"}
    d["oil"] = {"viscosity_at_40C_cSt": lub["viscosity_cSt"], "viscosity_at_100C_cSt": 0}
    # The profile's blocks are MERGED over config.json's, so every key config.json carries for the Keratech 22 run
    # that would be wrong here is overridden explicitly (nothing stale may survive into another lubricant's file).
    d["lubricant"] = {k: v for k, v in lub.items() if k != "viscosity_cSt"} | {
        "viscosity_cSt_40C": lub["viscosity_cSt"], "nlgi_grade": "N/A", "flash_point_c": "FILL IN",
        "quantity_applied_ml": "FILL IN", "application_method": "Manual application", "application_date": "FILL IN",
        "batch_number": "FILL IN", "notes": "Lubricant endurance matrix 2026-11; fill in the FILL IN fields before the run."}
    d["test_parameters"] = {"duration_minutes": d["duration_minutes"], "clamp_load_kg": kg,
                            "clamp_load_basis": CLAMP_KG[kg], "start_temp_c": START_TEMP_C,
                            "bias_v": 0.0 if twin else 1.0, "slip_ring": "lifted" if twin else "connected",
                            "campaign": "lubricant-endurance-2026-11", "test_name": tag,
                            "notes": "Lubricant endurance matrix, SKF SYJ25 hybrid B02, scope frozen (FFT off).",
                            "expected_load_g": kg * 1000, "clamp_load_kg_estimated": float(kg) if kg > 74 else "",
                            "clamp_load_uncertainty_pct": 30.0 if kg > 74 else 5.0,
                            "clamp_load_method": ("Set by counting clamp turns above the load cell's 74 kg ceiling; NOT measured, "
                                                  "treat as 150 +/- 40 kg (see CLAUDE.md, clamp load of 2026-09-23)." if kg > 74
                                                  else "Set by reading the load cell."),
                            "target_rpm": "", "target_temperature_c": ""}
    if kg in MEASURED_KG:
        d["test_parameters"]["clamp_load_kg_measured"] = MEASURED_KG[kg]
    return tag, d


def main():
    for lub in LUBRICANTS:
        for kg in CLAMP_KG:
            for twin in (False, True):
                tag, d = build(lub, kg, twin)
                (CFG / f"Endurance_{tag}.json").write_text(json.dumps(d, indent=2) + "\n")
                print(f"Endurance_{tag}.json  {d['duration_minutes']} min")


if __name__ == "__main__":
    main()
