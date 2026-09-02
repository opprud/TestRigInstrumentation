# 0044 — Drop redundant h5 time axis (Azure cost) + prepare two thicker oils

Opened: 2026-09-02 (Kim, two input notes via windows-Claude)

## Note 1 — drop the scope time axis in h5

Kim: "Kan vi droppe time-stamp fra scopet i h5? Det sparer en masse plads i Azure."

**Finding:** the per-channel `time` dataset is a pure arithmetic ramp,
`t = (arange(n) - x_reference) * x_increment + x_origin`, computed in `_raw_to_tv()` from
three preamble values that are ALREADY stored as channel attrs (`x_increment`, `x_origin`,
`x_reference`, plus `sample_rate`, `points_reported`). It carries zero information.
Dropping it is lossless by construction. The OE/scope alignment lives in
`sweep.attrs["tick"]` and is untouched.

**Change (this ticket):**
- `acquire_scope_data.py`: new store flag `time_axis` (default `true` = old behaviour);
  when `false` the `time` dataset is not written.
- `plot_waveform.py::load_waveform`: transparent fallback — reconstructs t from attrs
  when the dataset is absent (the only reader in the repo that touched it).
- `py/config.json`: `store.time_axis: false` (active on next run start; the running
  acquisition keeps its old in-memory config).

**Expected saving:** time is float64, same length as voltage → ~50% of sweep payload
uncompressed; with gzip-4 the realized saving is somewhat less (ramp compresses) —
Pi: please measure old-vs-new file size over one comparable run and note it here.

**Acceptance:** one run with the flag off → file readable via `plot_waveform.py` and
`inspect_hdf5.py`, Azure upload intact, measured size delta recorded.

## Note 2 — two new, thicker oils

Kim: "Vi skal til at køre med 2 andre olier der er lidt tykkere. Det skal skrives ind i
vores dokumentation."

Documented in `docs/Lubricant_Plan.md` (new): current oil baseline (Keratech 22),
placeholder spec table for Oil B / Oil C (names, ISO VG / viscosity, batch — awaiting
specs from Kim/Morten), and the per-oil run procedure (clone config profile, update
`lubricant` section, per-oil `output_file` naming). Fill the TBDs when the oils are
chosen; the `lubricant` config block already flows into the h5, so runs are
self-describing once the section is updated.

## Status

- [x] Code + config + docs committed (windows)
- [ ] Pi: apply after the current 13h run finishes (do NOT restart mid-run)
- [ ] Pi: size measurement old-vs-new
- [x] Oil names from Kim 2/9: **Foodlube 22** (same VG as baseline -> chemistry axis) +
      **Foodlube 150** (~7x viscosity -> film-thickness axis) — table updated
- [ ] Kim/Morten: datasheet details (exact product line, cSt@40C, flash point, batch)
