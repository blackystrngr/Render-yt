import os
import time
import asyncio
import subprocess
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events, Button

# 1. Flask health-check
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!"

# 2. Telegram credentials & client
API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION   = "bot_session"

bot = TelegramClient(SESSION, API_ID, API_HASH)

# 3. Helper functions
def get_title(url):
    try:
        out = subprocess.run(
            ["yt-dlp", "--cookies", "cookies.txt", "--print", "%(title)s", url],
            capture_output=True, text=True
        )
        return out.stdout.strip()
    except:
        return "Unknown Title"

def get_formats(url):
    try:
        out = subprocess.run(
            ["yt-dlp", "--cookies", "cookies.txt", "-F", url],
            capture_output=True, text=True
        )
        fmts = []
        for line in out.stdout.splitlines():
            if line and line[0].isdigit():
                code, *desc = line.split(None, 1)
                fmts.append((code, desc[0] if desc else ""))
        return fmts
    except:
        return []

async def download_video(event, url, fmt):
    os.makedirs("downloads", exist_ok=True)
    ts = int(time.time())
    template = f"downloads/%(title)s_{ts}.%(ext)s"
    msg = await event.edit(f"⏳ Downloading format {fmt}...")
    cmd = ["yt-dlp", "--cookies", "cookies.txt", "-f", fmt, "-o", template, url]

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

# 4. Event handlers
user_choices = {}
recent = set()

@bot.on(events.NewMessage(incoming=True))
async def on_msg(event):
    if not event.is_private or event.out or event.sender.bot:
        return

    key = f"{event.chat_id}:{event.id}"
    if key in recent:
        return
    recent.add(key)
    if len(recent) > 1000:
        recent.clear()

    text, uid = event.raw_text.strip(), event.sender_id
    if text.startswith("/yt "):
        url = text[4:].strip()
    elif "youtu.be" in text or "youtube.com" in text:
        url = text
    else:
        await event.respond("👋 Send a YouTube link to begin.")
        return

    title, fmts = get_title(url), get_formats(url)
    if not fmts:
        await event.respond("❌ No formats found.")
        return

    buttons = [Button.inline(f"{c} | {d}", data=c) for c, d in fmts[:10]]
    user_choices[uid] = url
    await event.respond(f"🎬 *{title}*\nChoose a format:", buttons=buttons)

@bot.on(events.CallbackQuery)
async def on_click(event):
    uid, fmt = event.sender_id, event.data.decode()
    url = user_choices.get(uid)
    if not url:
        return await event.answer("❌ No URL found.")

    fn = await download_video(event, url, fmt)
    if fn:
        await event.respond(f"📤 Uploading {os.path.basename(fn)}...")
        await event.respond(file=fn)
        await asyncio.sleep(1)
        await event.respond("✅ Upload complete.")
        try:
            os.remove(fn)
            await event.respond("🧹 File deleted.")
        except Exception as e:
            await event.respond(f"⚠️ Could not delete file: {e}")

    user_choices.pop(uid, None)

# 5. Session reuse and startup
async def init_bot():
    sess_file = f"{SESSION}.session"
    if os.path.exists(sess_file):
        await bot.connect()
        print("🔄 Reusing existing session")
    else:
        await bot.start(bot_token=BOT_TOKEN)
        print("🚀 Fresh login, session saved")
    if not await bot.is_user_authorized():
        raise RuntimeError("Bot failed to authorize")

async def bot_loop():
    await init_bot()
    print("✅ Bot is live!")
    await bot.run_until_disconnected()

def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_loop())

# 6. Launch bot thread on import
Thread(target=start_bot, daemon=True).start()
