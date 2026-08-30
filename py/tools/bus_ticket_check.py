#!/usr/bin/env python3
"""Check a ticket number for collisions BEFORE you use it (ticket 0009 numbering rule).

Pi-Claude and the architect both mint tickets; on 2026-08-30 the number 0011 was live
on two unrelated tickets at once (azure-uploader vs track-upload-guard). This makes the
collision visible cheaply -- a sentence of checking against a file rename + history fix.

    python3 py/tools/bus_ticket_check.py 0043      # or: 43

Exits 0 and prints FREE if no ``TEAM/tickets/<n>-*.md`` exists on ``origin/<branch>`` or
locally; else exits 1, lists the collisions, and suggests the next free number. Whichever
number you take, announce it on TEAM/BUS.md in the same breath (the 0009 rule).
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_common import git, load_config, repo_root  # noqa: E402


def next_free(listing: str) -> str:
    used = {int(m.group(1)) for m in re.finditer(r"/(\d{4})-", listing)}
    i = 1
    while i in used:
        i += 1
    return f"{i:04d}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Ticket-number collision check (ticket 0009).")
    ap.add_argument("number", help="ticket number, e.g. 0043 or 43")
    a = ap.parse_args()
    n = a.number.zfill(4)
    repo = repo_root()
    cfg = load_config(repo)
    br = cfg["branch"]

    git(["fetch", "-q", "origin", br], repo, check=False)
    listing = git(["ls-tree", "-r", "--name-only", f"origin/{br}", "TEAM/tickets"], repo, check=False)
    remote = [l for l in listing.splitlines() if re.search(rf"/{n}-", l)]

    tdir = os.path.join(repo, "TEAM", "tickets")
    local = [f for f in os.listdir(tdir) if re.match(rf"{n}-", f)] if os.path.isdir(tdir) else []

    if remote or local:
        print(f"COLLISION on {n}:")
        for f in remote:
            print(f"  origin/{br}: {f}")
        for f in sorted(set(local)):
            print(f"  local: TEAM/tickets/{f}")
        print(f"next free number: {next_free(listing)}")
        sys.exit(1)

    print(f"FREE: {n} is unused on origin/{br} and locally.")
    print("Announce it on TEAM/BUS.md the moment you take it (the 0009 rule).")
    sys.exit(0)


if __name__ == "__main__":
    main()
