#!/usr/bin/env python3
"""
Upload a completed run to the shared Azure archive (tickets 0011 / 0013).

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

Ticket 0013 adds three things:
* **Sidecars travel with the .h5.** The uploader used to send only the `.h5`, leaving the
  telemetry JSONL and `acquire_scope.log` as the *only* copy of the per-tick record and the
  failure log -- a folder-wide prune destroyed exactly those for two 2026-08-29 runs while the
  blobs were safe. Now every non-`.h5` file in the run folder is uploaded beside it (they are
  KB-MB; noise next to a 38 GB blob), so a prune can never lose telemetry again.
* **A content-MD5 on every upload.** Chunked block-blob uploads set no whole-blob MD5, so
  integrity could only be checked by size + sampled SHA. We compute it and store it, making every
  future verification a free exact checksum. (`--no-md5` skips the extra read pass on slow media.)
* **A keep/skip gate.** A run folder carrying a `DO_NOT_ARCHIVE` marker (any extension) is
  skipped -- for fault-reference and stability runs Pi marks that way. Opt-out: unmarked runs
  archive as before, so nothing that used to be archived silently stops.

Usage:
    python3 py/tools/upload_to_azure.py py/data/runs/<run_id>            # .h5 + sidecars
    python3 py/tools/upload_to_azure.py <file.h5> --container eceherning
    python3 py/tools/upload_to_azure.py <run_dir> --dry-run             # check, upload nothing
    python3 py/tools/upload_to_azure.py <run_dir> --no-sidecars --no-md5
"""
from __future__ import annotations

import argparse
import hashlib
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
SIDECAR_MAX_MB = 256          # a sidecar larger than this is almost certainly not a sidecar; warn + skip
MARKER_PREFIXES = ("do_not_archive", "do-not-archive", "noarchive")

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


def archive_marker(run_dir: Path) -> Path | None:
    """A run folder is left un-archived if it carries a DO_NOT_ARCHIVE-style marker."""
    for f in run_dir.iterdir():
        if f.is_file() and f.stem.lower().startswith(MARKER_PREFIXES):
            return f
    return None


def find_sidecars(run_dir: Path, h5: Path, log: Log) -> list[Path]:
    """Every regular file in the run folder except the .h5 itself -- the JSONL, the log, the
    ground-truth note, the config. Oversized ones are skipped loudly rather than silently sent."""
    out: list[Path] = []
    for f in sorted(run_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() == ".h5" or f == h5:
            continue
        if f.stat().st_size > SIDECAR_MAX_MB * 2**20:
            log(f"sidecar SKIP (too large, {f.stat().st_size/2**20:.0f} MB > {SIDECAR_MAX_MB}): {f.name}")
            continue
        out.append(f)
    return out


def file_md5(path: Path, log: Log, label: str) -> bytes:
    h = hashlib.md5()
    t0 = time.monotonic()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    dt = time.monotonic() - t0
    if dt > 5:
        log(f"  md5 {label}: {h.hexdigest()} (read pass {dt:.0f}s)")
    return h.digest()


def upload_one(svc, container: str, path: Path, blob_name: str, log: Log,
               dry: bool, want_md5: bool, progress: bool) -> str:
    """Upload one file: skip-if-identical, optional content-MD5, size-verify. Returns
    'ok' | 'skip' | 'dry' | 'fail'."""
    from azure.storage.blob import ContentSettings
    size = path.stat().st_size
    blob = svc.get_blob_client(container=container, blob=blob_name)

    try:
        props = blob.get_blob_properties()
        if props.size == size:
            log(f"SKIP {blob_name}: already present, matching size ({size:,} B)")
            return "skip"
        log(f"{blob_name}: exists {props.size:,} != local {size:,} — overwriting")
    except Exception as e:
        if "BlobNotFound" not in _scrub(e) and "ResourceNotFound" not in _scrub(e):
            log(f"note: could not stat {blob_name} ({_scrub(e)[:100]}) — continuing")

    if dry:
        log(f"DRY: would upload {blob_name} ({size:,} B, {size/2**30:.2f} GB)")
        return "dry"

    content_settings = None
    md5hex = ""
    if want_md5:
        digest = file_md5(path, log, blob_name)
        md5hex = digest.hex()
        content_settings = ContentSettings(content_md5=bytearray(digest))

    t0 = time.monotonic()
    state = {"pct": -5}

    def hook(current, total):
        if not progress:
            return
        total = total or size
        pct = int(100 * current / total) // 5 * 5
        if pct > state["pct"]:
            state["pct"] = pct
            el = time.monotonic() - t0
            rate = current / el / 2**20 if el > 0 else 0
            eta = (total - current) / (current / el) / 60 if current and el > 0 else 0
            log(f"  {pct:3d}%  {current/2**30:.2f}/{total/2**30:.2f} GB  {rate:.1f} MB/s  eta {eta:.0f} min")

    try:
        with open(path, "rb") as fh:
            blob.upload_blob(fh, overwrite=True, max_concurrency=CONCURRENCY,
                             content_settings=content_settings, progress_hook=hook)
    except Exception as e:
        log(f"UPLOAD FAILED {blob_name}: {type(e).__name__}: {_scrub(e)[:400]}")
        return "fail"

    try:
        remote = blob.get_blob_properties().size
    except Exception as e:
        log(f"VERIFY FAILED {blob_name}: could not read blob back: {_scrub(e)[:200]}")
        return "fail"
    if remote != size:
        log(f"VERIFY FAILED {blob_name}: blob {remote:,} != local {size:,}")
        return "fail"
    log(f"VERIFIED {blob_name} ({size:,} B{', md5 ' + md5hex[:12] if md5hex else ''})")
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload a run's HDF5 (+ sidecars) to the Azure archive.")
    ap.add_argument("target", help="run directory or .h5 file")
    ap.add_argument("--container", default=DEFAULT_CONTAINER)
    ap.add_argument("--blob-name", default=None,
                    help="default: <run folder>/<filename>, which keeps the archive browsable by run")
    ap.add_argument("--credential", default=None, help=f"default: py/{DEFAULT_CRED}")
    ap.add_argument("--log", default=None, help="append progress here as well as stdout")
    ap.add_argument("--dry-run", action="store_true", help="check everything, upload nothing")
    ap.add_argument("--no-sidecars", action="store_true", help="upload only the .h5, not the run folder's other files")
    ap.add_argument("--no-md5", action="store_true", help="skip the content-MD5 read pass (faster on slow media)")
    ap.add_argument("--force", action="store_true", help="archive even if the folder has a DO_NOT_ARCHIVE marker")
    args = ap.parse_args()

    log = Log(Path(args.log) if args.log else None)
    h5 = pick_file(Path(args.target).resolve())
    run_dir = h5.parent
    size = h5.stat().st_size
    blob_name = args.blob_name or f"{run_dir.name}/{h5.name}"
    want_md5 = not args.no_md5

    # Keep/skip gate — opt-out. A marked folder is left alone unless --force.
    marker = archive_marker(run_dir)
    if marker and not args.force:
        log(f"SKIP RUN: {run_dir.name} carries archive marker '{marker.name}' — not archiving (use --force to override)")
        return 0
    if marker and args.force:
        log(f"note: {run_dir.name} is marked '{marker.name}' but --force given — archiving anyway")

    log(f"run       {run_dir.name}")
    log(f"h5        {h5}")
    log(f"size      {size:,} bytes ({size/2**30:.2f} GB)")
    log(f"target    {args.container}/{blob_name}")

    conn = load_connection_string(args.credential, log)

    from azure.storage.blob import BlobServiceClient  # imported late: --help must work without it

    svc = BlobServiceClient.from_connection_string(
        conn, max_block_size=CHUNK_MB * 2**20, max_single_put_size=CHUNK_MB * 2**20)

    # The .h5 first: it is the run. Sidecars are worthless without it.
    r = upload_one(svc, args.container, h5, blob_name, log, args.dry_run, want_md5, progress=True)
    failed = 1 if r == "fail" else 0

    # Then the sidecars, each under the same <run folder>/ prefix so the archive mirrors the run.
    sc_ok = sc_skip = sc_fail = 0
    if not args.no_sidecars:
        sidecars = find_sidecars(run_dir, h5, log)
        if sidecars:
            log(f"sidecars  {len(sidecars)}: {', '.join(f.name for f in sidecars)}")
        for f in sidecars:
            name = args.blob_name and f"{Path(args.blob_name).parent}/{f.name}" or f"{run_dir.name}/{f.name}"
            rr = upload_one(svc, args.container, f, name, log, args.dry_run, want_md5, progress=False)
            sc_ok += rr in ("ok", "skip", "dry")
            sc_fail += rr == "fail"

    log(f"SUMMARY   h5={r}; sidecars ok/dry/skip={sc_ok} fail={sc_fail}")
    return 1 if (failed or sc_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
