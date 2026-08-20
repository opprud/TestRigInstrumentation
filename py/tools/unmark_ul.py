#!/usr/bin/env python3
"""Clear the UL-probe DETACHED markings (ticket 0015) once the probe is physically refitted.
Targeted text replacements -> minimal diff, newline-preserving, JSON-validated.
Usage: python unmark_ul.py <repo_or_worktree_root>
Exit 0 only if every expected marking was found and removed and both files are valid JSON."""
import sys, re, json, io, os

root = sys.argv[1]
cfg = os.path.join(root, "py", "config.json")
krt = os.path.join(root, "react", "public", "config", "Keratech22.json")

BODY = ("UL PROBE DETACHED from 2026-08-19: the ultrasound probe was unscrewed to make room for "
        "mounting the BearingBrain OE BLE sensor, pending a mechanical change. CHAN1 (alias UL) is "
        "therefore NOT measuring acoustic emission - it records whatever sits on a disconnected "
        "cable. The UL group in the HDF5 looks entirely normal, so this note is the only way to "
        "tell. Do not analyse UL data from runs in this period. Remove this note when the probe is "
        "refitted.")
CHAN_NOTE = "  [DETACHED 2026-08-19 - not measuring, see test_parameters.ul_probe_status]"

def rd(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:  # newline='' preserves CRLF/LF
        return f.read()
def wr(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)

ok = True

# --- py/config.json : channel note + test_parameters notes + ul_probe_status key ---
c = rd(cfg); found = []
if CHAN_NOTE in c: c = c.replace(CHAN_NOTE, ""); found.append("chan-note")
app_cfg = ". " + BODY
if app_cfg in c: c = c.replace(app_cfg, ""); found.append("tp-notes")
c2 = re.sub(r',\s*"ul_probe_status":\s*"DETACHED since 2026-08-19"', "", c)
if c2 != c: c = c2; found.append("ul_probe_status")
try:
    json.loads(c); cfg_valid = True
except Exception as e:
    cfg_valid = False; print("config.json INVALID after edit:", e)
if len(found) == 3 and cfg_valid:
    wr(cfg, c); print("config.json: removed", found)
else:
    ok = False; print("config.json: expected 3 markings, found", found, "valid=", cfg_valid)

# --- react/public/config/Keratech22.json : description tail ---
k = rd(krt); app_krt = "  " + BODY; kf = []
if app_krt in k: k = k.replace(app_krt, ""); kf.append("description")
try:
    json.loads(k); krt_valid = True
except Exception as e:
    krt_valid = False; print("KaretTest INVALID after edit:", e)
if len(kf) == 1 and krt_valid:
    wr(krt, k); print("Keratech22.json: removed", kf)
else:
    ok = False; print("KaretTest: expected 1 marking, found", kf, "valid=", krt_valid)

sys.exit(0 if ok else 1)
