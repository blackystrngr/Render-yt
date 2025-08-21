import os
import time
import asyncio
import subprocess
from flask import Flask
from telethon import TelegramClient, events, Button
from threading import Thread

# --- Auto-clear Telethon session ---
for file in os.listdir():
    if file.startswith("bot_session") and file.endswith(".session"):
        try:
            os.remove(file)
            print(f"🧹 Removed session file: {file}")
        except Exception as e:
            print(f"⚠️ Could not delete {file}: {e}")

# --- Flask setup ---
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!"

# --- Telegram credentials ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient("bot_session", API_ID, API_HASH)

# --- Track user choices ---
user_choices = {}
recent_messages = set()

# --- Get video title ---
def get_title(url):
    try:
        result = subprocess.run(
            ["yt-dlp", "--cookies", "cookies.txt", "--print", "%(title)s", url],
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except:
        return "Unknown Title"

# --- Get format list ---
def get_formats(url):
    try:
        result = subprocess.run(
            ["yt-dlp", "--cookies", "cookies.txt", "-F", url],
            capture_output=True, text=True
        )
        formats = []
        for line in result.stdout.splitlines():
            if line.strip() and line.strip()[0].isdigit():
                parts = line.split(None, 1)
                formats.append((parts[0], parts[1] if len(parts) > 1 else ""))
        return formats
    except:
        return []

# --- Download video ---
async def download_video(event, url, format_code):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    timestamp = int(time.time())
    output_template = f"downloads/%(title)s_{timestamp}.%(ext)s"
    msg = await event.edit(f"⏳ Downloading format {format_code}...")

    command = [
        "yt-dlp", "--cookies", "cookies.txt",
        "-f", format_code,
        "-o", output_template,
        url
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    filename = None

    while True:
        line = process.stdout.readline()
        if not line:
            break
        if "Destination:" in line:
            filename = line.split("Destination:")[1].strip()
        if "[download]" in line and "%" in line:
            await msg.edit(f"📥 {line.strip()}")

    process.wait()
    if process.returncode != 0 or not filename:
        await msg.edit("❌ Download failed.")
        return None

    await msg.edit("✅ Download complete.")
    return filename

# --- Handle messages ---
@bot.on(events.NewMessage(incoming=True))
async def handle_message(event):
    if not event.is_private or event.out or event.sender.bot:
        return

    key = f"{event.chat_id}:{event.message.id}"
    if key in recent_messages:
        return
    recent_messages.add(key)
    if len(recent_messages) > 1000:
        recent_messages.clear()

    text = event.raw_text.strip()
    sender_id = event.sender_id

    if text.startswith("/yt "):
        url = text[4:].strip()
    elif "youtube.com" in text or "youtu.be" in text:
        url = text
    else:
        await event.respond("👋 Send a YouTube link to begin.")
        return

    title = get_title(url)
    formats = get_formats(url)
    if not formats:
        await event.respond("❌ No formats found.")
        return

    buttons = [Button.inline(f"{fc} | {desc}", data=fc) for fc, desc in formats[:10]]
    user_choices[sender_id] = url
    await event.respond(f"🎬 *{title}*\nChoose a format:", buttons=buttons)

# --- Handle button clicks ---
@bot.on(events.CallbackQuery)
async def handle_callback(event):
    sender_id = event.sender_id
    format_code = event.data.decode()
    url = user_choices.get(sender_id)

    if not url:
        await event.answer("❌ No URL found.")
        return

    filename = await download_video(event, url, format_code)
    if filename:
        await event.respond(f"📤 Uploading {os.path.basename(filename)}...")
        await event.respond(file=filename)
        await event.respond("✅ Upload complete.")

        try:
            os.remove(filename)
            await event.respond("🧹 File deleted.")
        except Exception as e:
            await event.respond(f"⚠️ Could not delete file: {e}")

    user_choices.pop(sender_id, None)

# --- Start bot thread ---
async def bot_main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot is live!")
    await bot.run_until_disconnected()

def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_main())

# --- Gunicorn entry point ---
if os.environ.get("RUN_MAIN") == "true":
    Thread(target=start_bot).start()
