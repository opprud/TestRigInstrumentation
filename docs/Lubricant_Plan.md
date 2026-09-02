# Lubricant plan — ForeverBearing test series

Status: 2026-09-02 — Kim's note: the rig will move to **two additional, slightly
thicker oils**. This document is the single place that tracks which oils run on the
rig, their specs, and how a run is tagged with its oil.

## Oils

| # | Product | Manufacturer | Base | Viscosity (ISO VG / cSt@40C) | Flash point | Batch | Status |
|---|---------|--------------|------|------------------------------|-------------|-------|--------|
| A | Keratech 22 | Kerax | Paraffin oil | 22 (assumed from name — confirm) | 185 C | N/A | Baseline, applied 2026-03-16, all runs to date |
| B | TBD | TBD | TBD | TBD — "slightly thicker" than A | TBD | TBD | Planned |
| C | TBD | TBD | TBD | TBD — "slightly thicker" than A | TBD | TBD | Planned |

Fill B and C when Kim/Morten choose the products (name, manufacturer, viscosity grade,
flash point, batch number). "Slightly thicker" = the working hypothesis is a higher
viscosity film -> later transition out of full-film lubrication (see
`docs/OE_sensor.md`: the OE mic tracks the lubrication regime — thicker oil should
shift the temperature at which asperity noise rises).

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
