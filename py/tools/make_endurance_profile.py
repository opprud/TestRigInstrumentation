"""
Endurance-campaign profiles (bus 2026-11-09): base 13 h profile Keratech22.json with a 30 C speed sweep
added in front, the scope frozen for the whole matrix, and per-run metadata.

    py/.venv/bin/python tools/make_endurance_profile.py            # writes all 9 + 9 slip-ring twins

Matrix: 3 lubricants x 3 clamp loads (14 / 60 / 150 kg).  Twin = same profile, slip-ring probe lifted and
bias PSU off (slip_ring "lifted", bias_v 0.0); SP stays on as a noise reference.
Frozen scope (Kim, 2026-11-09): scope FFT OFF (500 k pts @ 5 MS/s at 0.1 s), SP 3.0 V / offset 1.0 (1 V bias; was 9.0/2.0 for the 5 V excitation)
UL 0.4 V, AE 5.0 V. Bias 1 V is set by hand on the PSU - it is logged here, not controlled.
"""
import copy, json
from pathlib import Path

CFG = Path(__file__).resolve().parents[2] / "react" / "public" / "config"
SHIFT = 3660        # the 30 C block is the base profile's first level verbatim (100 rpm steps, 60 s, 0->3000->0), only at 30 C
START_TEMP_C = 30

LUBRICANTS = {
    # Oil chemistry from manufacturer Technical Data Sheets (Kim supplied 2026-11-20).
    # flash_point_c is NOT on the ROCOL Foodlube TDS (SDS only) -> left FILL IN for those two.
    "keratech22": {"product_name": "Keratech 22", "manufacturer": "Kerax Ltd", "base_oil": "Highly refined white mineral oil (paraffinic)",
                   "base_fluid": "Mineral (white oil)", "additives": "None (plain white oil)", "viscosity_cSt": 22,
                   "viscosity_cSt_100C": None, "viscosity_index": None, "flash_point_c": 185},
    "foodlube_h1_power_22": {"product_name": "Foodlube H1 Power 22", "manufacturer": "ROCOL (ITW Ltd)", "base_oil": "Polyalphaolefin (PAO), synthetic",
                             "base_fluid": "PAO synthetic", "additives": "Antioxidant + anti-wear + Low-Carry-Over (LCO) anti-foam; NSF H1 reg 122180, ISO 21469, FDA 21 CFR 178.3570", "viscosity_cSt": 22,
                             "viscosity_cSt_100C": 4.8, "viscosity_index": 147,
                             "flash_point_c": ">150 (Foodlube Hi-Power Range SDS, Chemwatch 2015 - only published figure; current grade value TBC from ROCOL)", "autoignition_c": None},
    "foodlube_high_torq_150": {"product_name": "Foodlube High Torq 150", "manufacturer": "ROCOL (ITW Ltd)", "base_oil": "Polyalphaolefin (PAO), synthetic gear oil",
                               "base_fluid": "PAO synthetic", "additives": "SUPS start-up film + EP (FZG load stage 12) + anti-wear + anti-corrosion; NSF H1 reg 121604/122073/122072/122071, ISO 21469, PFAS-free", "viscosity_cSt": 150,
                               "viscosity_cSt_100C": 17.7, "viscosity_index": 130,
                               "flash_point_c": ">250 (ROCOL/ITW SDS v1.1, 2025-06-20)", "autoignition_c": ">270"},
}
MEASURED_KG = {14: 14.53}          # load cell reading when the clamp was set (2026-11-09, mounted, tare of 2026-09-23)
CLAMP_KG = {14: "measured on the load cell", 60: "measured on the load cell",
            150: "ESTIMATE from clamp turns, +/-30 % (above the cell's ~74 kg ceiling)"}

SCOPE = {"UL": {"timebase_range": 0.1, "volt_range": 0.4, "volt_offset": 0.0, "coupling": "DC"},
         "AE": {"timebase_range": 0.1, "volt_range": 5.0, "volt_offset": 0.0, "coupling": "DC"},
         "SP": {"timebase_range": 0.1, "volt_range": 3.0, "volt_offset": 1.0, "coupling": "DC"}}   # slip ring on a 1 V bias: ~0.4-1.5 V, 56-63 levels at speed


def build(lub_key, kg, twin):
    base = json.loads((CFG / "Keratech22.json").read_text())
    d = copy.deepcopy(base)
    sp = base["setpoints"]
    rpm = [dict(p) for p in sp["rpm"] if p["time_sec"] < SHIFT]      # base level 1, verbatim
    temp = [{"time_sec": 0, "value": START_TEMP_C}, {"time_sec": SHIFT - 1, "value": START_TEMP_C}]
    d["setpoints"] = {"rpm": rpm + [{"time_sec": p["time_sec"] + SHIFT, "value": p["value"]} for p in sp["rpm"]],
                      "temperature": temp + [{"time_sec": p["time_sec"] + SHIFT, "value": p["value"]} for p in sp["temperature"]]}
    end_sec = d["setpoints"]["rpm"][-1]["time_sec"]
    d["duration_minutes"] = end_sec // 60 + 1
    lub = LUBRICANTS[lub_key]
    tag = f"{lub_key}_{kg}kg" + ("_sliptwin" if twin else "")
    d["name"] = f"Endurance {tag}"
    d["description"] = (f"Lubricant endurance matrix: {lub['product_name']}, clamp {kg} kg, SKF SYJ25 hybrid B02. "
                        f"A 30 C speed sweep (the base profile\'s first level verbatim: 100 rpm steps of 60 s, 0-3000-0, {SHIFT} s) precedes the existing 13 h Keratech22 profile, "
                        f"which is shifted by {SHIFT} s. Scope frozen across the matrix: FFT off, 500 k pts @ 5 MS/s, "
                        f"UL 0.4 V, AE 5.0 V, SP 3.0 V / offset 1.0. "
                        + ("SLIP-RING TWIN: probe lifted, bias PSU off." if twin else "Slip ring connected, bias 1.0 V set on the PSU."))
    d["scope_channels"] = copy.deepcopy(SCOPE)
    d["scope_fft"] = {"enabled": False, "save": False}
    d["bearing"] = {**base.get("bearing", {}), "model": "SYJ25 hybrid B02",
                    "material": "Hybrid, 1 steel ball (B02)", "notes": "Endurance matrix specimen (Kim, 2026-11-09)"}
    d["oil"] = {"viscosity_at_40C_cSt": lub["viscosity_cSt"], "viscosity_at_100C_cSt": lub.get("viscosity_cSt_100C") or 0}
    # The profile's blocks are MERGED over config.json's, so every key config.json carries for the Keratech 22 run
    # that would be wrong here is overridden explicitly (nothing stale may survive into another lubricant's file).
    # Oil chemistry (base_oil, base_fluid, additives, viscosity_index, flash_point_c) comes from the LUBRICANTS
    # entry above (manufacturer TDS). Only the per-run physical fields stay FILL IN: set them at run time.
    d["lubricant"] = {k: v for k, v in lub.items() if k != "viscosity_cSt"} | {
        "viscosity_cSt_40C": lub["viscosity_cSt"], "nlgi_grade": "N/A",
        "quantity_applied_ml": "FILL IN", "application_method": "Manual application", "application_date": "FILL IN",
        "batch_number": "FILL IN", "notes": "Oil chemistry from manufacturer TDS (2026-11-20). Per-run FILL IN: quantity_applied_ml, application_date, batch_number."}
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
