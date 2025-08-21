#!/usr/bin/env python3
import os
import re
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
# 1) Logging
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
    logger.info(f"🚦 Flask listening on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)

# -----------------------------------------------------------------------------
# 3) Telethon & Paths Setup
# -----------------------------------------------------------------------------
API_ID     = int(os.environ["API_ID"])
API_HASH   = os.environ["API_HASH"]
BOT_TOKEN  = os.environ["BOT_TOKEN"]

BASE_DIR      = Path(__file__).parent.resolve()
SESSION_FILE  = BASE_DIR / "bot_session.session"
DOWNLOADS_DIR = BASE_DIR / "downloads"
COOKIES_PATH  = Path(os.environ.get("COOKIES_FILE", "cookies.txt")).resolve()

DOWNLOADS_DIR.mkdir(exist_ok=True)

YTDLP_BIN = shutil.which("yt-dlp")
if not YTDLP_BIN:
    logger.error("❌ yt-dlp not found. Install with `pip install yt-dlp`")
    raise SystemExit(1)

if not COOKIES_PATH.exists():
    logger.warning(f"⚠ Cookies file missing at {COOKIES_PATH!r}. Auth may fail.")

bot = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)

# Keep track of user → URL for callback
user_url_map: dict[int,str] = {}

# -----------------------------------------------------------------------------
# 4) Subprocess Wrappers & Helpers
# -----------------------------------------------------------------------------
async def run_yt_dlp(args: list[str]) -> str:
    def _sync():
        cmd = [YTDLP_BIN, *args]
        logger.info("▶️ Running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True)
        logger.info("   ↪ returncode: %d", proc.returncode)
        if proc.stdout:
            snippet = proc.stdout.strip().splitlines()[:5]
            logger.info("   ↪ stdout:\n%s", "\n".join(snippet))
        if proc.stderr:
            logger.warning("   ↪ stderr:\n%s", proc.stderr.strip())
        return proc.stdout
    return await asyncio.to_thread(_sync)

async def get_title(url: str) -> str:
    out = await run_yt_dlp([
        "--cookies", str(COOKIES_PATH),
        "--print", "%(title)s",
        url
    ])
    return out.strip() or "Unknown Title"

async def get_formats(url: str) -> list[tuple[str,str]]:
    out = await run_yt_dlp([
        "--cookies", str(COOKIES_PATH),
        "-F", url
    ])
    fmts = []
    for line in out.splitlines():
        if not re.match(r'^\d+', line):
            continue
        code, desc = line.split(None,1)
        res = re.search(r'(\d{2,4}p)', desc)
        ext = re.search(r'\b(mp4|m4a|webm|opus|ogg)\b', desc)
        label = f"{code} | {res.group(1) if res else '??'} | {ext.group(1) if ext else 'bin'}"
        fmts.append((code, label))
    return fmts

async def download_video(url: str, fmt: str, report) -> Path | None:
    ts = int(time.time())
    out_tmpl = str(DOWNLOADS_DIR / f"%(title)s_{ts}.%(ext)s")

    await report(f"⏳ Starting download: format {fmt}")
    proc = await asyncio.create_subprocess_exec(
        YTDLP_BIN,
        "--cookies", str(COOKIES_PATH),
        "-f", fmt,
        "-o", out_tmpl,
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        text=True,
    )

    filename = None
    last = time.time()
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if "Destination:" in line:
            filename = line.split("Destination:",1)[1].strip()
        if "[download]" in line and "%" in line and time.time() - last > 2:
            await report(f"📥 {line}")
            last = time.time()

    await proc.wait()
    if proc.returncode != 0 or not filename:
        await report("❌ Download failed.")
        return None

    await report("✅ Download complete.")
    return Path(filename)

# -----------------------------------------------------------------------------
# 5) Telegram Handlers
# -----------------------------------------------------------------------------
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
        return await event.respond("👋 Send a YouTube link or `/yt <url>` to begin.")

    logger.info("🔗 URL from %s: %s", event.sender_id, url)
    info = await event.respond("🔎 Fetching info…")

    title   = await get_title(url)
    formats = await get_formats(url)
    if not formats:
        return await info.edit("❌ No formats found.")

    buttons = [Button.inline(label, data=code) for code,label in formats[:8]]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    user_url_map[event.sender_id] = url

    await info.edit(f"🎬 {title}\nChoose format:", buttons=rows)

@bot.on(events.CallbackQuery)
async def on_format(event):
    await event.answer()
    fmt     = event.data.decode()
    user_id = event.sender_id
    url     = user_url_map.get(user_id)
    if not url:
        return await event.edit("❌ Session expired. Send the link again.")

    # progress reporter edits the same message
    async def report(text):
        return await event.edit(text)

    video_path = await download_video(url, fmt, report)
    if not video_path:
        user_url_map.pop(user_id, None)
        return

    upload_msg = await event.respond("📤 Uploading… 0.0%")
    async def upload_pr(c, t):
        pct = (c * 100 / t) if t else 0
        await upload_msg.edit(f"📤 Uploading… {pct:.1f}%")

    await bot.send_file(
        event.chat_id,
        video_path,
        progress_callback=upload_pr
    )

    await upload_msg.edit("✅ Upload complete!")
    try:
        video_path.unlink()
        await event.respond("🧹 Temp file removed.")
    except Exception as e:
        await event.respond(f"⚠️ Cleanup failed: {e}")

    user_url_map.pop(user_id, None)

# -----------------------------------------------------------------------------
# 6) Startup
# -----------------------------------------------------------------------------
async def telethon_main():
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("🤖 Bot started")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    asyncio.run(telethon_main())
