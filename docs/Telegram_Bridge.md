# Telegram bridge for the rig team (ticket 0043)

Phone access to the rig agents: the bridge **pushes notable bus events** to Kim's Telegram and
**answers read-only commands**. It runs as a daemon on an always-on host — the Pi, beside the bus
timers — and everything it reads (bus, heartbeats, tickets) comes from the git repo it sits in.

Status: **MVP built (outbound notifications + read-only commands), self-tested, not yet live** — it
needs a bot token to connect. Safety ops (heater-off, power-cycle) are deliberately not in this MVP.

## Setup (Kim, one time)
1. In Telegram, message **@BotFather** → `/newbot` → follow the prompts → it gives a **token**
   (`123456789:AA...`). Pick a name that isn't the trading bot.
2. Message **@userinfobot** to get your **numeric user id**.
3. On the Pi, copy the template and fill it in (the real file is git-ignored):
   ```
   cp py/tg_connection.json.example py/tg_connection.json
   # edit py/tg_connection.json: bot_token, allowed_user_id, chat_id (chat_id = your user id for a DM)
   ```
   Or set `TG_BOT_TOKEN` / `TG_ALLOWED_USER_ID` / `TG_CHAT_ID` in the environment instead.
4. Message the bot once (say `/start`) so Telegram has a chat to deliver to.

## Run
```
python3 py/tools/tg_bridge.py --selftest    # validate config + commands + outbound, NO token needed
python3 py/tools/tg_bridge.py               # the daemon (long-polls inbound, checks the bus for outbound)
python3 py/tools/tg_bridge.py --once        # single pass, for a systemd timer instead of a daemon
```
As a service on the Pi, a `tg-bridge.service` (simple, `Restart=always`) beside `rig-health.service`,
or a `--once` timer. It survives reboot the same way the bus timers do.

## What it does
- **Outbound:** every `bus_check_interval_sec` it fetches the bus and forwards any *new* post whose
  text matches `notify_patterns` (watchdog alarms, run complete/archived, heater/freeze, upload
  FAILED) to `chat_id`. Tune the patterns in `py/tg_config.json` so the phone only buzzes on things
  worth buzzing on. This is also the natural target for 0009's watchdog `telegram_cmd` and 0034's
  heater alerts.
- **Inbound (read-only):** `/status` (agent heartbeats + latest run + last bus post), `/bus [n]`
  (last n posts), `/tickets` (open tickets), `/help`. **Only `allowed_user_id` is ever acted on** —
  every other sender is logged and ignored.

## Guard rails (this is a control channel on a PUBLIC repo)
- Token in a git-ignored file (or env), scrubbed from every log line; a bot token is never committed.
- Only Kim's user id is answered; inbound text is treated as data, never as authority.
- A fixed command set, never arbitrary shell. Read-only for now.

## Next (not in this MVP)
Safety ops behind an explicit confirm (`/heateroff` → Shelly ch0, `/picycle` → ch3, `/oecycle` → ch2
once 0041 is wired); richer `/status` from live run telemetry; conversational freetext via a model.
See the ticket for the full plan.
