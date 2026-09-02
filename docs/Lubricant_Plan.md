# Lubricant plan — ForeverBearing test series

Status: 2026-09-02 — Kim's note: the rig will move to **two additional, slightly
thicker oils**. This document is the single place that tracks which oils run on the
rig, their specs, and how a run is tagged with its oil.

## Oils

| # | Product | Manufacturer | Base | Viscosity (ISO VG / cSt@40C) | Flash point | Batch | Status |
|---|---------|--------------|------|------------------------------|-------------|-------|--------|
| A | Keratech 22 | Kerax | Paraffin oil | 22 (assumed from name — confirm) | 185 C | N/A | Baseline, applied 2026-03-16, all runs to date |
| B | Foodlube 22 | ROCOL (Foodlube series — confirm) | Food-grade (NSF H1 class — confirm on datasheet) | VG 22 (per name) | TBD (datasheet) | TBD | Chosen 2026-09-02 (Kim) |
| C | Foodlube 150 | ROCOL (Foodlube series — confirm) | Food-grade (NSF H1 class — confirm on datasheet) | VG 150 (per name) | TBD (datasheet) | TBD | Chosen 2026-09-02 (Kim) |

Note the design this pair gives us — better than "two thicker oils":
- **Foodlube 22 vs Keratech 22 = same viscosity grade, different chemistry** — a clean
  chemistry/additive comparison at constant film thickness.
- **Foodlube 150 vs Foodlube 22 = same chemistry family, ~7x viscosity** — a clean
  viscosity comparison (VG 150 is a big step, not "slightly" thicker).
Working hypothesis unchanged: higher viscosity -> thicker film -> later transition out
of full-film lubrication (see `docs/OE_sensor.md`: the OE mic tracks the lubrication
regime — the VG 150 runs should shift the temperature at which asperity noise rises;
the Foodlube 22 runs tell us whether chemistry alone moves it at all).
Still needed from the datasheets/cans: exact product names (Hi-Power line?), cSt@40C,
flash point, batch numbers.

## How a run is tagged with its oil

The `lubricant` block in `py/config.json` (or the run's profile JSON) is written into
the HDF5 of every run — the data is self-describing. Per oil change:

1. Clone the current profile (pattern: `KaretTest_Oil1.json` -> per-oil profile in
   `react/public/config/`).
2. Update the `lubricant` section: `product_name`, `manufacturer`, `base_oil`,
   viscosity fields, `quantity_applied_ml`, `application_method`,
   `application_date`, `batch_number`, `notes`.
3. Update `store.output_file` so the filename carries the oil
   (e.g. `data/oilB_<product>.hdf5`) — keep `timestamped: true`.
4. Note the change in `TEAM/BUS.md` before the first run on the new oil, and record
   which bearing (new vs. carried over) the oil change happened on — oil comparisons
   are only clean on comparable bearings.

## Open items

- [ ] Oil B spec + batch (Kim/Morten)
- [ ] Oil C spec + batch (Kim/Morten)
- [ ] Decide bearing strategy per oil (new bearing per oil?) — affects comparability
- [ ] First-run checklist per oil: quantity, application method identical to baseline
