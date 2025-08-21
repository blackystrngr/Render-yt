import os
import asyncio
import time
import subprocess
from flask import Flask
from telethon import TelegramClient, events, Button
from threading import Thread

# --- Flask setup ---
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running!"

# --- Telegram bot credentials ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# --- Telegram client ---
bot = TelegramClient("bot_session", API_ID, API_HASH)

# --- Track user URLs and recent messages ---
user_choices = {}       # {user_id: url}
recent_messages = set() # {chat_id:message_id}

# --- Helper: get available formats using subprocess ---
def get_formats(url):
    try:
        command = [
            "yt-dlp",
            "--cookies", "cookies.txt",
            "-F", url
        ]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error fetching formats:\n{result.stderr}")
            return []

        lines = result.stdout.splitlines()
        formats = []
        for line in lines:
            if line.strip().startswith(tuple("0123456789")):
                parts = line.split()
                format_id = parts[0]
                resolution = " ".join(parts[1:])
                formats.append((format_id, resolution))

        return formats
    except Exception as e:
        print(f"Exception in get_formats: {e}")
        return []

# --- Helper: download video using subprocess ---
async def download_video(event, url, format_code):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    timestamp = int(time.time())
    output_template = f"downloads/%(title)s_{timestamp}.%(ext)s"
    msg = await event.edit(f"⏳ Starting download in format {format_code}...")

    try:
        command = [
            "yt-dlp",
            "--cookies", "cookies.txt",
            "-f", format_code,
            "-o", output_template,
            url
        ]

        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode != 0:
            await event.edit(f"❌ Download failed:\n{result.stderr}")
            return None

        # Find the most recent file in downloads
        files = sorted(
            os.listdir("downloads"),
            key=lambda f: os.path.getmtime(os.path.join("downloads", f)),
            reverse=True
        )
        filename = os.path.join("downloads", files[0]) if files else None

        if filename:
            await event.edit(f"✅ Download complete: {os.path.basename(filename)}")
            return filename
        else:
            await event.edit("❌ Could not locate downloaded file.")
            return None

    except Exception as e:
        await event.edit(f"❌ Error: {str(e)}")
        return None

# --- Message handler ---
@bot.on(events.NewMessage(incoming=True))
async def handler(event):
    if not event.is_private or event.out or event.sender.bot:
        return

    message_key = f"{event.chat_id}:{event.message.id}"
    if message_key in recent_messages:
        return
    recent_messages.add(message_key)
    if len(recent_messages) > 1000:
        recent_messages.clear()

    message_text = event.raw_text.strip()
    sender_id = event.sender_id

    if message_text.startswith("/yt "):
        url = message_text[4:].strip()
    elif "youtube.com" in message_text or "youtu.be" in message_text:
        url = message_text
    else:
        await event.respond("👋 Hello there! Send me a YouTube link to get started.")
        return

    await event.respond("⏳ Fetching available qualities...")
    formats = get_formats(url)
    if not formats:
        await event.respond("❌ No formats found.")
        return

    buttons = [Button.inline(f"🎞️ {res}", data=fc) for fc, res in formats[:10]]
    user_choices[sender_id] = url
    await event.respond("Select a quality:", buttons=buttons)

# --- Button callback handler ---
@bot.on(events.CallbackQuery)
async def callback(event):
    sender_id = event.sender_id
    format_code = event.data.decode()
    url = user_choices.get(sender_id)

    if not url:
        await event.answer("❌ No URL found. Send a YouTube link first.")
        return

    try:
        filename = await download_video(event, url, format_code)
        if filename:
            await event.edit(f"📤 Uploading {os.path.basename(filename)}...")
            await event.respond(file=filename)
            os.remove(filename)
            await event.respond(f"✅ Uploaded and deleted: {os.path.basename(filename)}")
    except Exception as e:
        await event.edit(f"❌ Error: {str(e)}")
    finally:
        user_choices.pop(sender_id, None)

# --- Start Telegram bot ---
async def bot_main():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot connected and ready!")
    await bot.run_until_disconnected()

def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_main())

# --- Start bot when Gunicorn loads this file ---
if __name__ != "__main__":
    Thread(target=start_bot).start()
