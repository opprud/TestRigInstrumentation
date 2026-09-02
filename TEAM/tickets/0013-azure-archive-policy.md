---
id: 0013
title: Azure archive policy — upload only valid, analysis-worthy tests to the real container
area: ops
role: dev
status: done
assignee: unassigned
depends_on: 0010, 0011
branch:
pr:
---

## Goal
Send only **valid, analysis-worthy test runs** to the shared Azure archive container that other team
members analyse — and **not** the small stability/rehearsal runs. Use the real container (from Kim's
`eceherning_connection.json`), with its secret kept out of git.

## Why
Kim provided the real destination (account `csfbst001`, a container-scoped **Admin** SAS). Going
forward only runs others can benefit from analysing should be archived there; the small runs we do
just to confirm stability must not clutter the archive. Ties into 0010 (old container value was
dead) and 0011 (get the uploader into the repo, no secrets).

## Open decisions (Kim to confirm)
- **Container name:** the connection string gives the account + a container-scoped SAS but not the
  container *name*. **CONFIRMED: `eceherning`** (Kim, 2026-08-19).
- **Keep/skip gate:** how is a run marked "valid, archive it" vs "small stability run, skip"?
  - (recommended) explicit **opt-in flag** — archive only if flagged; default skip. A valid *short*
    test still gets kept if flagged; stability runs never leak in.
  - or a duration/size threshold (risk: a valid short run is under it).
  - or a manual post-run "promote this run to the archive" action.

## Design
- **Secret handling:** the SAS / connection string lives in a **gitignored** config (e.g.
  `py/azure_connection.json` or an env var); only the **container name** goes in committed config.
  The uploader reads both. **Never commit the SAS** — it is Admin-scoped and valid until 2126;
  treat as highly sensitive and regenerate if exposed.
- The upload path (0011's `azure_upload_guard.py`) checks the keep/skip gate before uploading and
  targets the configured container.

## Acceptance
- A flagged valid run uploads to the real container; a stability run does not.
- No secret in git; container name in committed config; uploader reads the SAS from a gitignored file.

## Owner / test
- **Dev:** wire container + gate + secret handling. **Test:** a flagged run and an unflagged run →
  only the flagged one lands in the archive.

## Destination validated (2026-08-19)
`eceherning` on `csfbst001` proven end-to-end: `scope_20260818_135505.h5` uploaded (37,747,161,391 B) and **byte-for-byte verified**; container SAS works for write/read/delete (only `get_container_properties()` 403s, expected for a container-SAS). Remaining for 0013: the keep/skip gate + wiring the container + the gitignored secret into the uploader (0011).

## Additions from the first real prune (2026-08-27)
The prune of the three 13 h `.h5`s (114 GB freed) surfaced two cheap uploader changes — **decision
(windows, 2026-08-27): do both.**
1. **Archive the sidecar files with the `.h5`.** The uploader sends only the `.h5`, so the telemetry JSONL
   and `acquire_scope.log` are the *only* copy of the per-tick record and the failure log — a folder-wide
   prune would destroy them (12 MB across the three runs = noise). Interim safeguard now in place: each
   pruned folder holds an **`ARCHIVED.txt`** (account / container / blob, byte count, verification method,
   why JSONL+log were kept), so an empty-looking folder explains itself instead of reading as data loss.
2. **Set `content_settings.content_md5` on every upload.** Chunked block-blob uploads set no content-MD5,
   so integrity can only be checked today by exact-size + sampled-range SHA-256 (offset 0 / midpoint / last
   4 MB) or a full re-download. One argument on the upload call makes every future verification a free exact
   checksum — it would have made this prune a checksum comparison instead of a sampling argument. Kim's
   uploader-touch to schedule.

---
## Done 2026-09-02 (windows) — implemented in py/tools/upload_to_azure.py

All three parts landed and tested:
1. **Sidecars.** Every non-`.h5` file in the run folder (telemetry JSONL, `acquire_scope.log`,
   `GROUND_TRUTH.txt`, config) now uploads beside the `.h5` under the same `<run>/` prefix. This is
   the fix for the 2026-08-29 loss — telemetry can no longer be lost to a folder prune — and it
   **supersedes the interim `ARCHIVED.txt` safeguard**: the sidecars are in Azure now, not merely
   noted. `--no-sidecars` opts out; a non-sidecar-sized file (>256 MB) is skipped loudly.
2. **content_md5.** Computed in a pre-upload read pass and stored on the blob, so every future
   verification is a free exact checksum instead of size + sampled SHA. `--no-md5` skips the extra
   read pass on slow media. (Blobs already present are left untouched by skip-if-identical, so this
   applies to new uploads; a backfill would be a separate pass.)
3. **Keep/skip gate — opt-out.** A run folder carrying a `DO_NOT_ARCHIVE*` marker (any extension) is
   skipped; `--force` overrides. Unmarked runs archive exactly as before, so nothing that used to be
   archived silently stops. Matches Pi's "marked do-not-archive" fault-reference convention — **Pi to
   confirm the exact marker filename** so the two sides agree.

Tested on Windows: gate skip, clear-path passes the gate, sidecar discovery (excludes the `.h5`),
marker detection + `--force`. The real upload path is a minimal extension of the proven uploader
(same `upload_blob` + `content_settings`). Credential handling, scrubbing, and size-verify unchanged.
