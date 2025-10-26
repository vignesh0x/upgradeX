# upgradeX

**upgradeX** is a small lab tool that demonstrates controlling a test agent from a Telegram bot using a button-driven UI. It is intended **only** for educational / lab use on machines you own or have explicit permission to test.

---

## Quick description

* **Controller:** a Telegram bot with only buttons (no typing except pasting the target IP once).
* **Agent:** a TCP listener on the target machine that accepts a small whitelist of commands.
* **Screenshot feature:** agent can take a full-screen capture and return it to the bot, which posts it into the Telegram chat.

---

## IMPORTANT — Disclaimer

Use this tool **only** on systems you own or have written permission to test. The author is **not** responsible for misuse, illegal activity, damage, or data loss. If you are unsure, stop and get permission.

---

## Requirements

* Python 3.8+
* On the controller machine: `python-telegram-bot`
* On the agent (victim) machine for screenshots: `mss` (recommended) and optionally `Pillow`

Install core dependencies:

```bash
pip install python-telegram-bot mss pillow
```


## Environment variables

Set required environment variables before running.

**For the bot (controller):**

* `TG_BOT_TOKEN` — your Telegram bot token
* `TG_SECRET` — shared secret (must match victim)
* `TCP_PORT` — optional, default `9999`

**For the victim (agent):**

* `TG_SECRET` — shared secret (must match bot)
* `TCP_PORT` — optional, default `9999`
* `ALLOW_SHUTDOWN` — set to `1` to allow remote shutdown (disabled by default)

Example (Linux/macOS):

```bash
export TG_BOT_TOKEN="123456:ABC-DEF..."
export TG_SECRET="supersecret"
export TCP_PORT=9999
```

Open the Telegram bot, press **Set Target** and paste the agent IP when prompted. After the bot confirms the target, use the action buttons (Screenshot, Flash, Crazy Brightness, LOL, CLI Hack, Stop All, Shutdown).

---

## Available actions (button UI)

* Set Target (paste IP once)
* Get Target / Clear Target
* Screenshot 📸
* Crazy Brightness
* Flash Screen
* LOL (Notepad spam)
* CLI Hack (CMD spam)
* Stop All
* Shutdown (works only if `ALLOW_SHUTDOWN=1`)

---

## Notes & security

* Communications are plain TCP/JSON and **not encrypted**. Use inside isolated lab networks or over VPN.
* Keep `TG_SECRET` secret. Rotate it if leaked.
* Do not expose the agent port to the public internet.

---
