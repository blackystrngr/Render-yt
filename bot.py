import os
import time
import asyncio
import subprocess
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events, Button

# 1) Flask health-check
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!"

# 2) Credentials & session
API_ID     = int(os.environ["API_ID"])
API_HASH   = os.environ["API_HASH"]
BOT_TOKEN  = os.environ["BOT_TOKEN"]
SESSION    = "bot_session"               # Telethon writes bot_session.session
COOKIES    = os.environ.get("COOKIES_FILE", "cookies.txt")

bot = TelegramClient(SESSION, API_ID, API_HASH)

# 3) Helpers
def get_title(url):
    try:
        res = subprocess.run(
            ["yt-dlp", "--cookies", COOKIES, "--print", "%(title)s", url],
            capture_output=True, text=True
        )
        return res.stdout.strip() or "Unknown Title"
    except:
        return "Unknown Title"

def get_formats(url):
    try:
        res = subprocess.run(
            ["yt-dlp", "--cookies", COOKIES, "-F", url],
            capture_output=True, text=True
        )
        fmts = []
        for line in res.stdout.splitlines():
            if line and line[0].isdigit():
                code, *desc = line.split(None, 1)
                fmts.append((code, desc[0] if desc else ""))
        return fmts
    except:
        return []

async def download_video(event, url, fmt):
    os.makedirs("downloads", exist_ok=True)
    ts = int(time.time())
    out = f"downloads/%(title)s_{ts}.%(ext)s"
    msg = await event.edit(f"⏳ Downloading format {fmt}...")
    cmd = ["yt-dlp", "--cookies", COOKIES, "-f", fmt, "-o", out, url]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    filename, last = None, time.time()

    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if "Destination:" in line:
            filename = line.split("Destination:")[1].strip()
        if "[download]" in line and "%" in line and time.time() - last > 2:
            await msg.edit(f"📥 {line.strip()}")
            last = time.time()

    proc.wait()
    if proc.returncode != 0 or not filename:
        await msg.edit("❌ Download failed.")
        return None

    await msg.edit("✅ Download complete.")
    return filename

# 4) Handlers
user_choices = {}
seen = set()

@bot.on(events.NewMessage(incoming=True))
async def on_message(event):
    if not event.is_private or event.out or event.sender.bot:
        return

    key = f"{event.chat_id}:{event.id}"
    if key in seen:
        return
    seen.add(key)
    if len(seen) > 1000:
        seen.clear()

    text, uid = event.raw_text.strip(), event.sender_id
    if text.startswith("/yt "):
        url = text[4:].strip()
    elif "youtu.be" in text or "youtube.com" in text:
        url = text
    else:
        return await event.respond("👋 Send a YouTube link to begin.")

    # show loading
    msg = await event.respond("🔎 Fetching video info...")

    title = get_title(url)
    fmts  = get_formats(url)
    if not fmts:
        return await msg.edit("❌ No formats found.")

    buttons = [Button.inline(f"{c} | {d}", data=c) for c, d in fmts[:10]]
    user_choices[uid] = url
    await msg.edit(f"🎬 {title}\nChoose a format:", buttons=buttons)

@bot.on(events.CallbackQuery)
async def on_format(event):
    uid, fmt = event.sender_id, event.data.decode()
    url = user_choices.get(uid)
    if not url:
        return await event.answer("❌ No URL found.")

    # 1) Download
    filepath = await download_video(event, url, fmt)
    if not filepath:
        user_choices.pop(uid, None)
        return

    # 2) Upload with progress
    upload_msg = await event.respond("📤 Uploading: 0.0%")

    def progress(cur, total):
        pct = cur * 100 / total if total else 0
        # schedule async edit on Telethon's loop
        upload_msg.client.loop.create_task(
            upload_msg.edit(f"📤 Uploading: {pct:.1f}%")
        )

    # send_file uses progress callback
    await bot.send_file(event.chat_id, filepath, progress_callback=progress)

    # finalize
    await upload_msg.edit("✅ Upload complete.")
    try:
        os.remove(filepath)
        await event.respond("🧹 File deleted.")
    except Exception as e:
        await event.respond(f"⚠️ Could not delete file: {e}")

    user_choices.pop(uid, None)

# 5) Startup
async def bot_loop():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot is live!")
    await bot.run_until_disconnected()

def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_loop())

Thread(target=start_bot, daemon=True).start()
