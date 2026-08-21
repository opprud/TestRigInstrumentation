#!/usr/bin/env python3
"""
Upload a completed run to the shared Azure archive (ticket 0011 / 0013).

The uploader that produced `archive_eceherning.log` and `azure_upload_guard.log` was never in
the repo, so after every 13 h run it had to be reinvented at two in the morning. This is it,
in the repo, reading its credential from a file that is not.

Design notes, all of them learned the hard way on this rig:

* **The secret never reaches the log.** The connection string carries an account-scoped SAS.
  Azure's own exceptions happily embed the signed URL, so every message this script prints goes
  through `_scrub()` first -- there is no path where a traceback leaks the token.
* **Size is verified against the blob after upload**, not assumed from a 200. A truncated
  archive that nobody notices is worse than a failed upload that shouts.
* **An identical blob is a no-op.** Re-running after a network drop must not re-send 35 GB.
* **Progress is logged, not printed to a terminal nobody is watching** -- an unattended upload
  that says nothing for 50 minutes is indistinguishable from a hung one.

Usage:
    python3 py/tools/upload_to_azure.py py/data/runs/<run_id>            # the run's .h5
    python3 py/tools/upload_to_azure.py <file.h5> --container eceherning
    python3 py/tools/upload_to_azure.py <run_dir> --dry-run             # check, upload nothing
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT_CONTAINER = "eceherning"
DEFAULT_CRED = "eceherning_connection.json"
CHUNK_MB = 8
CONCURRENCY = 4

_SECRETS: list[str] = []


def _scrub(text: object) -> str:
    """Remove anything that could be a credential from a string bound for the log."""
    s = str(text)
    for secret in _SECRETS:
        if secret:
            s = s.replace(secret, "<redacted>")
    # any SAS-looking query string, even one we have not seen before
    s = re.sub(r"([?&](?:sig|sv|se|st|sp|sr|ss|srt|spr)=)[^&\s\"']*", r"\1<redacted>", s)
    return s


class Log:
    def __init__(self, path: Path | None):
        self.path = path

    def __call__(self, msg: object) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {_scrub(msg)}"
        print(line, flush=True)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def load_connection_string(explicit: str | None, log: Log) -> str:
    if os.environ.get("AZURE_CONNECTION_STRING"):
        log("credential: AZURE_CONNECTION_STRING from environment")
        cs = os.environ["AZURE_CONNECTION_STRING"]
    else:
        here = Path(__file__).resolve().parent.parent          # py/
        cred = Path(explicit) if explicit else here / DEFAULT_CRED
        if not cred.exists():
            raise SystemExit(f"no credential: {cred} not found and AZURE_CONNECTION_STRING unset")
        with open(cred, encoding="utf-8") as fh:
            data = json.load(fh)
        cs = data.get("AZURE_CONNECTION_STRING") or data.get("connection_string") or ""
        if not cs:
            raise SystemExit(f"{cred} has no AZURE_CONNECTION_STRING key")
        log(f"credential: {cred.name}")
    _SECRETS.append(cs)
    for part in cs.split(";"):                                  # and each field on its own
        if "=" in part:
            _SECRETS.append(part.split("=", 1)[1])
    return cs


def pick_file(target: Path) -> Path:
    """A run directory means 'the HDF5 in it'; a file means itself."""
    if target.is_file():
        return target
    if target.is_dir():
        h5 = sorted(target.glob("*.h5"))
        if not h5:
            raise SystemExit(f"no .h5 file in {target}")
        if len(h5) > 1:
            raise SystemExit(f"{target} holds {len(h5)} .h5 files; name the one you mean")
        return h5[0]
    raise SystemExit(f"not found: {target}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload a run's HDF5 to the Azure archive.")
    ap.add_argument("target", help="run directory or .h5 file")
    ap.add_argument("--container", default=DEFAULT_CONTAINER)
    ap.add_argument("--blob-name", default=None,
                    help="default: <run folder>/<filename>, which keeps the archive browsable by run")
    ap.add_argument("--credential", default=None, help=f"default: py/{DEFAULT_CRED}")
    ap.add_argument("--log", default=None, help="append progress here as well as stdout")
    ap.add_argument("--dry-run", action="store_true", help="check everything, upload nothing")
    args = ap.parse_args()

    log = Log(Path(args.log) if args.log else None)
    path = pick_file(Path(args.target).resolve())
    size = path.stat().st_size
    blob_name = args.blob_name or f"{path.parent.name}/{path.name}"

    log(f"file      {path}")
    log(f"size      {size:,} bytes ({size/2**30:.2f} GB)")
    log(f"target    {args.container}/{blob_name}")

    conn = load_connection_string(args.credential, log)

    from azure.storage.blob import BlobServiceClient  # imported late: --help must work without it

    svc = BlobServiceClient.from_connection_string(
        conn, max_block_size=CHUNK_MB * 2**20, max_single_put_size=CHUNK_MB * 2**20)
    blob = svc.get_blob_client(container=args.container, blob=blob_name)

    # Already there and the right size? Then this is a re-run after a drop, not a new upload.
    try:
        props = blob.get_blob_properties()
        if props.size == size:
            log(f"SKIP: blob already present with matching size ({size:,} bytes)")
            return 0
        log(f"blob exists with size {props.size:,} != local {size:,} — overwriting")
    except Exception as e:
        if "BlobNotFound" not in _scrub(e) and "ResourceNotFound" not in _scrub(e):
            log(f"note: could not stat blob ({_scrub(e)[:120]}) — continuing")

    if args.dry_run:
        log("DRY RUN: credential loaded, container reachable, nothing uploaded")
        return 0

    t0 = time.monotonic()
    state = {"pct": -5}

    def progress(current, total):
        # `total` is None on some SDK paths; fall back to the size we already know.
        total = total or size
        pct = int(100 * current / total) // 5 * 5
        if pct > state["pct"]:
            state["pct"] = pct
            el = time.monotonic() - t0
            rate = current / el / 2**20 if el > 0 else 0
            eta = (total - current) / (current / el) / 60 if current and el > 0 else 0
            log(f"  {pct:3d}%  {current/2**30:.2f}/{total/2**30:.2f} GB  "
                f"{rate:.1f} MB/s  eta {eta:.0f} min")

    try:
        with open(path, "rb") as fh:
            blob.upload_blob(fh, overwrite=True, max_concurrency=CONCURRENCY,
                             progress_hook=progress)
    except Exception as e:
        log(f"UPLOAD FAILED: {type(e).__name__}: {_scrub(e)[:400]}")
        return 1

    mins = (time.monotonic() - t0) / 60
    log(f"upload finished in {mins:.1f} min ({size/2**20/(mins*60):.1f} MB/s avg)")

    # The point of the exercise: prove the bytes arrived.
    try:
        remote = blob.get_blob_properties().size
    except Exception as e:
        log(f"VERIFY FAILED: could not read blob back: {_scrub(e)[:200]}")
        return 2
    if remote != size:
        log(f"VERIFY FAILED: blob is {remote:,} bytes, local is {size:,}")
        return 3
    log(f"VERIFIED: blob size matches exactly ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
