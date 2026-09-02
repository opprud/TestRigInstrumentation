#!/usr/bin/env python3
"""Telegram bridge for the rig agent team (ticket 0043).

Gives Kim phone access to the team: it pushes notable bus events to his Telegram, and answers
read-only commands. It runs as a daemon on an always-on host (the Pi, beside the bus timers).

Design, and the guard rails that matter because this is a control channel on a PUBLIC repo:
* **The token never reaches git or a log.** It is read from a git-ignored file (matched by the
  existing `*_connection.json` ignore) or the environment, and scrubbed out of every log line.
* **Only Kim is ever acted on.** Every message from any other Telegram user id is logged and
  dropped -- never answered, never routed.
* **A fixed command set, never arbitrary shell.** This MVP is read-only (status / bus / tickets);
  safety ops (heater-off, power-cycle) are deliberately NOT here yet -- they come later, behind an
  explicit confirm, once the read-only half has run.
* **Inbound text is data, not authority.** A command that isn't in the set is answered with help.

Everything the bridge reads -- the bus, heartbeats, tickets -- comes from the git repo it sits in,
so it works the same on the Pi and (for --selftest) on the architect's box.

Setup:
    Put the bot token + your Telegram user id in py/tg_connection.json (git-ignored):
        { "bot_token": "123:ABC...", "allowed_user_id": 111, "chat_id": 111 }
    (chat_id is where outbound goes -- your DM id, or a group id. Env overrides:
     TG_BOT_TOKEN / TG_ALLOWED_USER_ID / TG_CHAT_ID.)

Run:
    python3 py/tools/tg_bridge.py                 # the daemon
    python3 py/tools/tg_bridge.py --selftest      # validate config + commands + outbound, no token needed
    python3 py/tools/tg_bridge.py --once          # one inbound+outbound pass then exit (for a timer)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_common import git, journal, repo_root, safe_console, utcnow_iso  # noqa: E402

CONFIG_FILE = "py/tg_config.json"
SECRET_FILE = "py/tg_connection.json"          # git-ignored via *_connection.json
STATE_FILE = "py/.tg_bridge_state.json"        # git-ignored
LOG_FILE = "py/tg_bridge.log"                  # git-ignored via *.log

_SECRETS: list[str] = []

DEFAULT_CONFIG = {
    "branch": "AutoDetectScope_moj",
    "poll_timeout_sec": 30,
    "bus_check_interval_sec": 60,
    "notify_patterns": ["BUS WATCHDOG", "gone dark", "is back", "complete", "archived",
                        "heater", "freeze", "FAILED"],
    "max_notify_chars": 1200,
    "commands_enabled": ["status", "bus", "tickets", "help"],
}


# --------------------------------------------------------------------------- logging / secrets
def _scrub(text: object) -> str:
    s = str(text)
    for sec in _SECRETS:
        if sec:
            s = s.replace(sec, "<redacted>")
    return re.sub(r"bot\d{6,}:[A-Za-z0-9_-]{20,}", "bot<redacted>", s)


def log(repo: str, msg: object) -> None:
    line = f"[{utcnow_iso()}] {_scrub(msg)}"
    print(line, flush=True)
    try:
        with open(os.path.join(repo, LOG_FILE), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- config / state
def load_config(repo: str) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    p = os.path.join(repo, CONFIG_FILE)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            cfg.update({k: v for k, v in json.load(fh).items() if not k.startswith("_")})
    return cfg


def load_secret(repo: str) -> dict:
    token = os.environ.get("TG_BOT_TOKEN")
    user = os.environ.get("TG_ALLOWED_USER_ID")
    chat = os.environ.get("TG_CHAT_ID")
    p = os.path.join(repo, SECRET_FILE)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        token = token or d.get("bot_token")
        user = user or d.get("allowed_user_id")
        chat = chat or d.get("chat_id")
    out = {"bot_token": token,
           "allowed_user_id": int(user) if user else None,
           "chat_id": int(chat) if chat else (int(user) if user else None)}
    if out["bot_token"]:
        _SECRETS.append(out["bot_token"])
    return out


def load_state(repo: str) -> dict:
    try:
        with open(os.path.join(repo, STATE_FILE), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(repo: str, st: dict) -> None:
    with open(os.path.join(repo, STATE_FILE), "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)


# --------------------------------------------------------------------------- telegram api
def tg(token: str, method: str, payload: dict, timeout: int = 35) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def send(token: str, chat_id: int, text: str) -> None:
    tg(token, "sendMessage", {"chat_id": chat_id, "text": text,
                              "disable_web_page_preview": True}, timeout=20)


# --------------------------------------------------------------------------- reading the repo
def bus_posts(repo: str, branch: str) -> list[tuple[str, str]]:
    """Every bus post as (iso_timestamp, full_text), oldest first."""
    git(["fetch", "-q", "origin", branch], repo, check=False)
    text = git(["show", f"origin/{branch}:TEAM/BUS.md"], repo, check=False)
    posts = []
    for m in re.finditer(r"^## (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\b.*?(?=^## \d{4}-|\Z)",
                         text, re.S | re.M):
        posts.append((m.group(1), m.group(0).strip()))
    return posts


def heartbeat_age(repo: str, agent: str) -> str:
    git(["fetch", "-q", "origin", f"bus-hb-{agent}"], repo, check=False)
    c = git(["show", f"origin/bus-hb-{agent}:heartbeat.md"], repo, check=False)
    for line in c.splitlines():
        if line.startswith("last_seen_utc:"):
            ts = line.split(":", 1)[1].strip()
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
            return f"{int(age // 60)} min ago"
    return "never seen"


def open_tickets(repo: str) -> list[str]:
    out = []
    tdir = os.path.join(repo, "TEAM", "tickets")
    for f in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        if not f.endswith(".md"):
            continue
        t = open(os.path.join(tdir, f), encoding="utf-8", errors="replace").read()
        fm = re.search(r"^---\s*(.*?)\s*---", t, re.S | re.M)
        st = (re.search(r"^status:\s*(.*)$", fm.group(1), re.M) if fm else None)
        st = st.group(1).strip() if st else ""
        tt = (re.search(r"^title:\s*(.*)$", fm.group(1), re.M) if fm else None)
        tt = tt.group(1).strip() if tt else f
        if st and not st.lower().startswith(("done", "withdrawn", "reserved")) and "DONE" not in st:
            out.append(f"{f[:4]} [{st.split(' ')[0][:10]}] {tt[:52]}")
    return out


def latest_run(repo: str) -> str | None:
    for base in ("py/data/runs", "data/runs"):
        d = os.path.join(repo, base)
        if os.path.isdir(d):
            runs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))
            if runs:
                return runs[-1]
    return None


# --------------------------------------------------------------------------- command handlers
def cmd_status(repo: str, cfg: dict) -> str:
    br = cfg["branch"]
    lines = ["Rig status:",
             f"  pi heartbeat:      {heartbeat_age(repo, 'pi')}",
             f"  windows heartbeat: {heartbeat_age(repo, 'windows')}"]
    lr = latest_run(repo)
    if lr:
        lines.append(f"  latest run folder: {lr}")
    posts = bus_posts(repo, br)
    if posts:
        head = posts[-1][1].splitlines()[0].replace("## ", "")
        lines.append(f"  last bus post:     {head}")
    return "\n".join(lines)


def cmd_bus(repo: str, cfg: dict, arg: str) -> str:
    n = int(arg) if arg.strip().isdigit() else 5
    posts = bus_posts(repo, cfg["branch"])[-n:]
    if not posts:
        return "bus is empty."
    out = []
    for ts, body in posts:
        first = next((l for l in body.splitlines()[1:] if l.strip()), "")
        out.append(f"{body.splitlines()[0].replace('## ', '')}\n  {first[:140]}")
    return "\n\n".join(out)


def cmd_tickets(repo: str, cfg: dict) -> str:
    t = open_tickets(repo)
    return "Open tickets:\n" + "\n".join(f"  {x}" for x in t) if t else "No open tickets."


def cmd_help(repo: str, cfg: dict) -> str:
    return ("Rig bridge commands:\n"
            "  /status  - agent heartbeats + latest run + last bus post\n"
            "  /bus [n] - last n bus posts (default 5)\n"
            "  /tickets - open tickets\n"
            "  /help    - this\n"
            "(read-only for now; safety ops come later, behind a confirm)")


HANDLERS = {"status": cmd_status, "bus": cmd_bus, "tickets": cmd_tickets, "help": cmd_help}


def handle_command(repo: str, cfg: dict, text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lstrip("/").lower().split("@")[0]     # tolerate /status@BotName
    arg = parts[1] if len(parts) > 1 else ""
    if cmd not in cfg["commands_enabled"] or cmd not in HANDLERS:
        return cmd_help(repo, cfg)
    if cmd == "bus":
        return cmd_bus(repo, cfg, arg)
    return HANDLERS[cmd](repo, cfg)


# --------------------------------------------------------------------------- outbound
def notify_worthy(body: str, cfg: dict) -> bool:
    low = body.lower()
    return any(p.lower() in low for p in cfg["notify_patterns"])


def do_outbound(repo: str, cfg: dict, secret: dict, st: dict, dry: bool) -> list[str]:
    """Forward new notify-worthy bus posts to Kim. Returns the messages sent.

    On the VERY FIRST run (no stored watermark) it baselines to the latest post and sends
    nothing — otherwise a fresh bridge would forward the whole bus history's alarms at once
    and flood the phone. After that, only posts newer than the watermark go out.
    """
    posts = bus_posts(repo, cfg["branch"])
    if not posts:
        return []
    if "last_notified_ts" not in st:
        if not dry:
            st["last_notified_ts"] = posts[-1][0]
        return []
    last = st["last_notified_ts"]
    sent = []
    for ts, body in posts:
        if ts <= last or not notify_worthy(body, cfg):
            continue
        msg = body[:cfg["max_notify_chars"]]
        sent.append(msg)
        if not dry and secret["bot_token"] and secret["chat_id"]:
            try:
                send(secret["bot_token"], secret["chat_id"], msg)
            except Exception as e:
                log(repo, f"outbound send failed: {_scrub(e)[:200]}")
    if not dry:
        st["last_notified_ts"] = posts[-1][0]
    return sent


# --------------------------------------------------------------------------- inbound
def do_inbound(repo: str, cfg: dict, secret: dict, st: dict) -> None:
    token, allowed = secret["bot_token"], secret["allowed_user_id"]
    try:
        r = tg(token, "getUpdates",
               {"offset": st.get("update_offset", 0), "timeout": cfg["poll_timeout_sec"]},
               timeout=cfg["poll_timeout_sec"] + 5)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(repo, f"getUpdates: {_scrub(e)[:150]}")
        return
    for upd in r.get("result", []):
        st["update_offset"] = upd["update_id"] + 1
        msg = upd.get("message") or upd.get("edited_message")
        if not msg or "text" not in msg:
            continue
        uid = msg.get("from", {}).get("id")
        if allowed is None or uid != allowed:      # fail closed: no allow-list => answer no one
            log(repo, f"ignored message from user id {uid} (not the allowed user)")
            continue
        reply = handle_command(repo, cfg, msg["text"])
        try:
            send(token, msg["chat"]["id"], reply)
        except Exception as e:
            log(repo, f"reply send failed: {_scrub(e)[:150]}")
    save_state(repo, st)


# --------------------------------------------------------------------------- main
def selftest(repo: str, cfg: dict, secret: dict) -> None:
    print("=== config ==="); print(json.dumps(cfg, indent=1))
    print("=== secret present? ===")
    print(f"  token: {'yes' if secret['bot_token'] else 'NO (set py/tg_connection.json or TG_BOT_TOKEN)'}")
    print(f"  allowed_user_id: {secret['allowed_user_id']}  chat_id: {secret['chat_id']}")
    print("=== /status ==="); print(cmd_status(repo, cfg))
    print("=== /tickets ==="); print(cmd_tickets(repo, cfg))
    print("=== /bus 3 ==="); print(cmd_bus(repo, cfg, "3"))
    print("=== outbound — notify-worthy posts in history (a fresh bridge baselines to now, no flood) ===")
    worthy = [b for _, b in bus_posts(repo, cfg["branch"]) if notify_worthy(b, cfg)]
    print(f"  {len(worthy)} post(s) match notify_patterns; on a live start only NEW matches forward.")
    if worthy:
        print("  most recent match: " + worthy[-1].splitlines()[0].replace("## ", ""))
    print("=== inbound auth ===")
    print("  " + ("allowed_user_id set — inbound enabled" if secret["allowed_user_id"]
                  else "allowed_user_id NOT set — inbound would be DISABLED (fail-closed)"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Telegram bridge for the rig team (ticket 0043).")
    ap.add_argument("--selftest", action="store_true", help="validate config + commands + outbound, no token needed")
    ap.add_argument("--once", action="store_true", help="one inbound+outbound pass, then exit")
    a = ap.parse_args()
    safe_console()
    repo = repo_root()
    cfg = load_config(repo)
    secret = load_secret(repo)

    if a.selftest:
        selftest(repo, cfg, secret)
        return 0
    if not secret["bot_token"]:
        log(repo, "no bot token — set py/tg_connection.json or TG_BOT_TOKEN. (Try --selftest.)")
        return 2

    inbound_ok = secret["allowed_user_id"] is not None
    if not inbound_ok:
        log(repo, "WARNING: allowed_user_id not set — inbound commands DISABLED (a bot with no "
                  "allow-list would answer anyone). Set allowed_user_id in tg_connection.json to enable.")
    log(repo, "tg_bridge up" + (" (single pass)" if a.once else " (daemon)")
              + ("" if inbound_ok else " [OUTBOUND ONLY — no allow-list]"))
    last_bus = 0.0
    while True:
        st = load_state(repo)
        if inbound_ok:
            do_inbound(repo, cfg, secret, st)          # blocks up to poll_timeout_sec (long-poll)
        if time.monotonic() - last_bus >= cfg["bus_check_interval_sec"] or a.once:
            do_outbound(repo, cfg, secret, st, dry=False)
            save_state(repo, st)
            last_bus = time.monotonic()
        if a.once:
            return 0
        if not inbound_ok:
            time.sleep(min(cfg["bus_check_interval_sec"], 30))   # no long-poll to pace us


if __name__ == "__main__":
    sys.exit(main())
