# Maintenance log

Append-only record of **physical changes to the rig** — what it *is*, so the data can be read
against it. A rebuild is a **hard boundary**: absolute signal levels do not carry across it (new
surfaces, new clearances, new preload), so the first run after any entry here is a deliberate
**re-baseline**, not a warm-up (see `CLAUDE.md`). Where a build fact should also travel *inside* the
data, stamp it into `/metadata/ground_truth` on the run's HDF5 (Pi's stamper).

---

## 2026-09-02 → boundary: bearing bushing + lock rings replaced (root cause: self-loosening nut → bearing slip)

**Status (2026-09-05): rig OPEN, work in progress.** It stays down until the new bushing + lock nut
are fitted and a **stroboscope re-test at running speed shows no slip and no nut creep**. That strobe
pass is the acceptance gate to close the rebuild and resume runs — no runs before it.

**Discovery.** With a **stroboscope** set to the shaft frequency (which freezes the rotation), the
bearing was seen **slipping on the shaft** and the retaining **nut slowly loosening itself under
drive** — a reference mark that should have been frozen instead crept.

**Root cause.** The tightening specification was **never followed** → too little preload → classic
vibration **self-loosening** of a nut on a rotating shaft (Junker effect) → loss of axial clamp →
the bearing slips on the shaft → wear of the **bushing** (the running surface). Because the spec was
never followed, the retaining ring / clamp was **probably loose across all historical runs**, not
just the recent ones — so ring/clamp state is unknown for every run before this rebuild, the three
13 h runs included.

**Planned / in progress (rig down since 2026-09-02).**
- New **bushing / bearing seat** — `<part no. — TBD Kim>`. The old one was worn by the slip.
- New **lock rings** — `<part no. — TBD Kim>`.
- Retaining nut **torqued to spec** — `<torque value — TBD Kim>` — with the lock **positively
  engaged** (not friction alone).
- As-built (record while apart): radial clearance `<TBD>`, preload `<TBD>`, ring seated: `yes`.

**Data impact.** 2026-09 is a hard boundary — **absolute levels void, re-baseline.**
Rotation-correlated / impulsive readings in historical data carry an uncharacterised mechanical
artefact (the slip). The **UL-vs-temperature finding survives** (it reproduced across two 13 h runs
with the 0 rpm floor flat in both, and ring state was shown not to move UL amplitude beyond the
~26 % run-to-run wander) but is **re-confirmed on the first post-rebuild run**.

**Prevention (now procedure, not a note).** Torque-to-spec + a positive lock, recorded here; and the
**strobe check** is in `docs/Prerun_Checklist.md` §2 — strobe the shaft at speed after any reassembly
and spot-check it on long runs. A creeping mark = slip / self-loosening, caught before it wears
anything. This is the missing procedure that caused the whole ring saga; the fix is the written
procedure, not tightening harder this once.
