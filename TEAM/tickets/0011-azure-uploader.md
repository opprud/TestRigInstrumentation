---
id: 0011
title: Put the Azure archive uploader in the repo, with the secret kept out
area: ops
role: dev
status: done
assignee: pi-claude
branch: ticket/0011-azure-uploader
depends_on: 0010, 0013
pr:
---

## Why
`archive_eceherning.log` and `azure_upload_guard.log` are in `py/`, complete with progress traces
and a verified 37.7 GB upload — but **the script that wrote them is not**. After every 13 h run the
uploader had to be reinvented, at two in the morning, by whoever was awake. That is the worst
possible time to write code that handles a 35 GB file and an account-scoped SAS.

## What
`py/tools/upload_to_azure.py`. Takes a run directory (or an explicit `.h5`), uploads to the
`eceherning` container, verifies, and logs.

```bash
python3 py/tools/upload_to_azure.py py/data/runs/<run_id>
python3 py/tools/upload_to_azure.py py/data/runs/<run_id> --dry-run --log py/archive_eceherning.log
```

Credential comes from `AZURE_CONNECTION_STRING` in the environment, or `py/eceherning_connection.json`
— which stays out of git. Nothing is added to `config.json`; the SAS already sitting there in
cleartext is a separate problem (see the known issue in CLAUDE.md) and this does not add a second one.

## The four decisions, each from something that has bitten this project
- **The secret never reaches the log.** Azure's exceptions embed the signed URL, so every message
  goes through `_scrub()`: the connection string, each of its fields, and any `sig=`/`se=`/`sp=`
  query parameter, including ones we have never seen. There is no path — success or traceback —
  where the token gets written to a file or a terminal.
- **Size is verified against the blob after upload**, by reading the blob back. A 200 is not
  evidence. A truncated archive nobody notices is worse than an upload that fails loudly.
- **An identical blob is a no-op.** Re-running after a network drop must not re-send 35 GB, so a
  blob already present at exactly the local size is a `SKIP`, not an overwrite.
- **Progress is logged every 5 %** with rate and ETA. An unattended upload that says nothing for
  fifty minutes is indistinguishable from a hung one.

Blob name defaults to `<run folder>/<filename>`, so the archive stays browsable by run rather than
becoming a flat pile of `scope_*.h5`.

## Verified
`--dry-run` against the real account: credential loads, container reachable, blob stat returns, and
the log carries no secret. The upload path itself was checked against the installed SDK
(`azure-storage-blob 12.28.0`) rather than by writing a test blob — ticket 0013 is explicit that
small runs must not clutter the shared archive, and that applies doubly to junk:
`upload_blob` supports `progress_hook`, and it is called as `progress_hook(current, total)`, which
is the signature used here. `total` is `None` on some stream paths, so the hook falls back to the
size measured locally.

**Not yet exercised on a real large upload.** The first one will be the 13 h run of 2026-08-20.

---
## Closed 2026-08-30 (windows)
py/tools/upload_to_azure.py is in the repo: log-scrubbed SAS, blob-size verification, idempotent SKIP, 5% progress. It archived run 20260829_145507 (38,813,876,147 bytes, byte-verified). The separate azure_upload_guard.py tracking is its own ticket (renumbered 0042).
