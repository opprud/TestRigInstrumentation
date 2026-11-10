"""Notify Kim on Telegram when a NEW login appears on this machine:
- console/ssh sessions (`who`, polled every 20 s), and
- Raspberry Pi Connect sessions (screen sharing 'vnc' / remote 'shell'), read from the
  rpi-connect user journal ('Proxy session started' / 'ended').
Baseline = whatever is present at start."""
import re
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from tg_notify import send

HOST = socket.gethostname()


def sessions():
    out = subprocess.run(["who"], capture_output=True, text=True).stdout
    return {l.strip() for l in out.splitlines() if l.strip()}


def watch_who():
    base = sessions()
    print("who baseline:", base, flush=True)
    while True:
        time.sleep(20)
        cur = sessions()
        for s in sorted(cur - base):
            msg = f"Ny login på {HOST}: {s}"
            print(msg, flush=True)
            send(msg)
        base = cur


def watch_connect():
    p = subprocess.Popen(["journalctl", "--user", "-u", "rpi-connect", "-f", "-n", "0", "-o", "cat"],
                         stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        m = re.search(r"\[(vnc|shell)\]: Proxy session (started|ended)", line)
        if m:
            kind = "skærmdeling" if m.group(1) == "vnc" else "remote shell"
            msg = f"Pi Connect {kind} {'STARTET' if m.group(2) == 'started' else 'afsluttet'} på {HOST}"
            print(msg, flush=True)
            send(msg)


threading.Thread(target=watch_connect, daemon=True).start()
watch_who()
