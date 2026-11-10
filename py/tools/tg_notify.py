"""Send a short text to Kim's Telegram (the rig bot), e.g. an hourly run status.

Usage: tg_notify.py "message"        (or the message on stdin)

Reads py/telegram_connection.json (git-ignored): TELEGRAM_BOT_TOKEN, allowed_user_ids,
optional chat_id (defaults to the first allowed id). The token is never printed or logged.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CONN = Path(__file__).resolve().parent.parent / "telegram_connection.json"


def send(text: str) -> bool:
    cfg = json.loads(CONN.read_text())
    token = cfg["TELEGRAM_BOT_TOKEN"]
    chat = cfg.get("chat_id") or (cfg.get("allowed_user_ids") or [None])[0]
    if not token or not chat:
        print("tg_notify: no token / chat id configured", file=sys.stderr)
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r).get("ok", False)
    except Exception as e:  # scrub: the URL (with token) can appear in the message
        print("tg_notify: send failed:", str(e).replace(token, "<token>"), file=sys.stderr)
        return False


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or sys.stdin.read()
    ok = send(msg.strip())
    print("sent" if ok else "FAILED")
    sys.exit(0 if ok else 1)
