#!/usr/bin/env python3
import os
import time
import shutil
import asyncio
import logging
import subprocess

from pathlib import Path
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events, Button

# -----------------------------------------------------------------------------
# 1) Configure Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 2) Flask Health-Check
# -----------------------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚦 Starting Flask on 0.0.0.0:{port}")
    # Enable threaded=True so it doesn’t block Telethon
    app.run(host="0.0.0.0", port=port, threaded=True)

# -----------------------------------------------------------------------------
# 3) Telethon Credentials & Paths
# -----------------------------------------------------------------------------
API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

# Sessions & Working folders
BASE_DIR       = Path(__file__).parent.resolve()
SESSION_FILE   = BASE_DIR / "bot_session.session"
DOWNLOADS_DIR  = BASE_DIR / "downloads"
COOKIES_PATH   = Path(os.environ.get("COOKIES_FILE", "cookies.txt")).resolve()

# Ensure download folder exists
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Locate yt-dl binary
YTDLP_BIN = shutil.which("yt-dlp")
if not YTDLP_BIN:
    logger.error("❌ yt-dlp binary not found in PATH – install it with `pip install yt-dlp`")
    raise SystemExit(1)

# Check cookies file presence
if not COOKIES_PATH.exists():
    logger.warning(f"⚠ Cookies file not found at {COOKIES_PATH!r}. "
                   "Requests that require auth may fail.")

# -----------------------------------------------------------------------------
# 4) Subprocess Helpers (wrapped off the event loop)
# -----------------------------------------------------------------------------
async def run_yt_dlp(args: list[str]) -> str:
    """
    Runs yt-dlp with given args, logs everything, returns stdout.
    Executes in a thread to avoid blocking Telethon’s loop.
    """
    def _sync_run():
        cmd = [YTDLP_BIN, *args]
        logger.info("▶️ Running: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        logger.info("   ↪ returncode: %d", proc.returncode)
        if proc.stdout:
            snippet = proc.stdout.strip().splitlines()[:5]
            logger.info("   ↪ stdout (up to 5 lines):\n%s", "\n".join(snippet))
        if proc.stderr:
            logger.warning("   ↪ stderr:\n%s", proc.stderr.strip())
        return proc.stdout

    return await asyncio.to_thread(_sync_run)

async def get_title(url: str) -> str:
    """Fetch the video title via yt-dlp --print."""
    out = await run_yt_dlp(["--cookies", str(COOKIES_PATH), "--print", "%(title)s", url])
    return out.strip() or "Unknown Title"

async def get_formats(url: str) -> list[tuple[str,str]]:
    """
    Fetch the format table, parse lines that start with a digit.
    Returns a list of (format_code, description).
    """
    out = await run_yt_dlp(["--cookies", str(COOKIES_PATH), "-F", url])
    fmts = []
    for line in out.splitlines():
        if not line or not line[0].isdigit():
            continue
        parts = line.split(None, 1)
        code = parts[0]
        desc = parts[1].strip() if len(parts) > 1 else ""
        fmts.append((code, desc))
    return fmts

async def download_video(url: str, fmt: str, progress_callback) -> Path | None:
    """
    Download the chosen format to DOWNLOADS_DIR.
    Progress updates via the provided callback.
    """
    ts = int(time.time())
    # Tell yt-dlp to embed title/ext in its own template
    out_template = str(DOWNLOADS_DIR / f"%(title)s_{ts}.%(ext)s")

    msg = await progress_callback("⏳ Starting download...")
    # Start the subprocess
    proc = await asyncio.create_subprocess_exec(
        YTDLP_BIN,
        "--cookies", str(COOKIES_PATH),
        "-f", fmt,
        "-o", out_template,
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        text=True,
    )

    filename = None
    last_update = time.time()

    while True:
        line = await proc.stdout.readline()
        if not line:
            break

        line = line.strip()
        # Capture the final filename when yt-dlp prints "Destination:"
        if "Destination:" in line:
            filename = line.split("Destination:", 1)[1].strip()

        # Periodically update progress (every 2s)
        if "[download]" in line and "%" in line and time.time() - last_update > 2:
            await progress_callback(f"📥 {line}")
            last_update = time.time()

    await proc.wait()
    if proc.returncode != 0 or not filename:
        await progress_callback("❌ Download failed.")
        return None

    await progress_callback("✅ Download complete.")
    return Path(filename)

# -----------------------------------------------------------------------------
# 5) Telethon Event Handlers
# -----------------------------------------------------------------------------
bot = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)

# Keep track of which user picked which URL
user_url_map: dict[int, str] = {}

@bot.on(events.NewMessage(incoming=True))
async def on_message(event):
    if not event.is_private or event.out or event.sender.bot:
        return

    text = event.raw_text.strip()
    if text.startswith("/yt "):
        url = text[4:].strip()
    elif "youtube.com" in text or "youtu.be" in text:
        url = text
    else:
        return await event.respond("👋 Send me a YouTube link to begin.")

    logger.info("🔗 Got URL from %s: %s", event.sender_id, url)
    info_msg = await event.respond("🔎 Fetching video info…")

    title = await get_title(url)
    formats = await get_formats(url)
    if not formats:
        return await info_msg.edit("❌ No formats found for this video.")

    # Show top 8 formats
    buttons = [Button.inline(f"{code} – {desc[:30]}", data=code)
               for code, desc in formats[:8]]
    user_url_map[event.sender_id] = url

    await info_msg.edit(
        f"🎬 {title}\nChoose a format:",
        buttons=buttons
    )

@bot.on(events.CallbackQuery)
async def on_format(event):
    fmt = event.data.decode()
    user_id = event.sender_id
    url = user_url_map.get(user_id)
    if not url:
        return await event.answer("❌ Could not find your URL. Start over with /yt.")

    # Helper to send progress updates
    async def report(msg_text):
        return await event.edit(msg_text)

    # 1) Download
    video_path = await download_video(url, fmt, report)
    if not video_path:
        user_url_map.pop(user_id, None)
        return

    # 2) Upload with Telethon’s built-in progress callback
    upload_msg = await event.respond("📤 Uploading… 0.0%")
    async def upload_progress(cur, total):
        pct = cur * 100 / total if total else 0
        await upload_msg.edit(f"📤 Uploading… {pct:.1f}%")

    await bot.send_file(
        event.chat_id,
        video_path,
        progress_callback=upload_progress
    )

    await upload_msg.edit("✅ Upload complete!")
    try:
        video_path.unlink()
        await event.respond("🧹 Temp file removed.")
    except Exception as e:
        await event.respond(f"⚠ Could not delete file: {e}")

    user_url_map.pop(user_id, None)

# -----------------------------------------------------------------------------
# 6) Startup: Run Flask + Telethon Together
# -----------------------------------------------------------------------------
async def telethon_main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("🤖 Telegram bot started")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    # 1) Kick off Flask in a daemon thread
    Thread(target=run_flask, daemon=True).start()

    # 2) Run the Telethon bot (blocks here)
    asyncio.run(telethon_main())
