#!/usr/bin/env python3
"""
Upload a finished run's HDF5 to Azure Blob storage, unattended.

Detached like heater_guard.py, so it does not depend on a Claude session, the
dashboard, or the API server being alive. It waits until the run is genuinely
finished *and the file has stopped growing*, then uploads and verifies.

Why the "stopped growing" check matters: `run_end` is written by the test runner,
but the scope thread may still be flushing the last sweeps into the HDF5. Starting
an upload then would push a truncated file to Azure that still looks like a
complete blob — the same class of silent-bad-data failure as everything else found
on 2026-08-18.

Nothing is ever deleted. Verification is a byte-size comparison against the blob,
because that is what is actually checkable without re-downloading 40 GB.

Usage:
  nohup python3 azure_upload_guard.py --run <run_dir> [--container data] \
      [--deadline <epoch>] >> azure_upload_guard.log 2>&1 &
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def telemetry_file(run_dir: str):
    f = glob.glob(os.path.join(run_dir, "telemetry_*.jsonl"))
    return f[0] if f else None


def saw_run_end(path: str) -> bool:
    try:
        with open(path, errors="replace") as f:
            for ln in f:
                if '"run_end"' not in ln:
                    continue
                try:
                    if json.loads(ln.strip()).get("type") == "run_end":
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def acquisition_running() -> bool:
    try:
        r = subprocess.run(["pgrep", "-f", "python.*acquire_scope_data"],
                           capture_output=True, text=True, timeout=20)
        pids = [p for p in r.stdout.split() if p.strip() and p.strip() != str(os.getpid())]
        return bool(pids)
    except Exception:
        return False


def h5_path(run_dir: str):
    f = sorted(glob.glob(os.path.join(run_dir, "*.h5"))) + \
        sorted(glob.glob(os.path.join(run_dir, "*.hdf5")))
    return f[0] if f else None


def container_client(container: str):
    cfg = json.loads((HERE / "config.json").read_text())
    cs = cfg.get("azure", {}).get("connection_string")
    if not cs:
        raise RuntimeError("no azure.connection_string in config.json")
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(cs).get_container_client(container)


def blob_size(container: str, name: str):
    try:
        return container_client(container).get_blob_client(name).get_blob_properties().size
    except Exception:
        return None


def upload(path: str, container: str, attempts: int = 3) -> bool:
    name = os.path.basename(path)
    local = os.path.getsize(path)
    log(f"uploading {name} ({local/1e9:.2f} GB) -> container '{container}'")

    existing = blob_size(container, name)
    if existing == local:
        log("blob already present with an identical byte size — nothing to do")
        return True
    if existing is not None:
        log(f"a blob of {existing/1e9:.2f} GB already exists and differs — overwriting")

    for i in range(1, attempts + 1):
        t0 = time.time()
        try:
            cc = container_client(container)
            bc = cc.get_blob_client(name)
            last = {"pct": -5}

            def progress(current, total):
                if not total:
                    return
                pct = int(current * 100 / total)
                if pct >= last["pct"] + 5:
                    last["pct"] = pct
                    rate = current / max(1e-6, time.time() - t0) / 1e6
                    log(f"  {pct:3d}%  {current/1e9:.2f}/{total/1e9:.2f} GB  {rate:.1f} MB/s")

            with open(path, "rb") as fh:
                bc.upload_blob(fh, overwrite=True, max_concurrency=4,
                               progress_hook=progress)
            dt = time.time() - t0
            log(f"upload finished in {dt/60:.1f} min ({local/1e6/max(dt,1):.1f} MB/s avg)")

            remote = blob_size(container, name)
            if remote == local:
                log(f"VERIFIED: blob size matches exactly ({remote:,} bytes)")
                return True
            log(f"!!! size mismatch: local {local:,} vs blob {remote}")
        except Exception as e:
            log(f"attempt {i}/{attempts} failed: {e!r}")
        if i < attempts:
            time.sleep(60 * i)

    log("!!! UPLOAD FAILED — the local file is untouched; a human should retry")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    # NOTE: config.json's azure.default_container is "auherning3bearingtester",
    # which does not exist on the account. The real one is "data".
    ap.add_argument("--container", default="data")
    ap.add_argument("--stable-sec", type=float, default=180.0,
                    help="the HDF5 must not grow for this long before uploading")
    ap.add_argument("--deadline", type=float, default=0.0,
                    help="optional epoch after which we upload even without run_end")
    ap.add_argument("--poll", type=float, default=60.0)
    a = ap.parse_args()

    log(f"azure upload guard armed: run={a.run} container={a.container} "
        f"stable={a.stable_sec}s")

    last_size, stable_since = None, None
    while True:
        tel = telemetry_file(a.run)
        f = h5_path(a.run)
        ended = bool(tel and saw_run_end(tel))
        overdue = a.deadline and time.time() >= a.deadline

        if f and (ended or overdue):
            size = os.path.getsize(f)
            if size != last_size:
                last_size, stable_since = size, time.time()
                log(f"run finished; {os.path.basename(f)} still settling at {size/1e9:.2f} GB")
            elif acquisition_running():
                log("file size steady but acquisition process still alive — waiting")
                stable_since = time.time()
            elif time.time() - stable_since >= a.stable_sec:
                log(f"file stable at {size/1e9:.2f} GB for {a.stable_sec:.0f}s — starting upload")
                ok = upload(f, a.container)
                log("azure upload guard done" if ok else "azure upload guard FAILED")
                return 0 if ok else 1

        time.sleep(a.poll)


if __name__ == "__main__":
    sys.exit(main())
