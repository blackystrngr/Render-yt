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

        formats = []
        for line in result.stdout.splitlines():
            if line.strip() and line.strip()[0].isdigit():
                parts = line.split(None, 1)
                format_id = parts[0]
                description = parts[1] if len(parts) > 1 else "Unknown"
                formats.append((format_id, description))

        return formats
    except Exception as e:
        print(f"Exception in get_formats: {e}")
        return []

# --- Helper: download video with live progress ---
async def download_video(event, url, format_code):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    timestamp = int(time.time())
    output_template = f"downloads/%(title)s_{timestamp}.%(ext)s"
    msg = await event.edit(f"⏳ Starting download in format {format_code}...")

    command = [
        "yt-dlp",
        "--cookies", "cookies.txt",
        "-f", format_code,
        "-o", output_template,
        url
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    filename = None
    last_update = 0

    while True:
        line = process.stdout.readline()
        if not line:
            break

        if "Destination:" in line:
            filename = line.split("Destination:")[1].strip()

        if "[download]" in line and "%" in line:
            parts = line.strip().split()
            for part in parts:
                if "%" in part:
                    percent = part
                    now = time.time()
                    if now - last_update > 2:
                        await msg.edit(f"📥 Downloading... {percent}")
                        last_update = now
                    break

    process.wait()

    if process.returncode != 0:
        await msg.edit("❌ Download failed.")
        return None

    await msg.edit(f"✅ Download complete: {os.path.basename(filename)}")
    return filename

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
            await event.edit("✅ Upload complete: 100%")

            # Safely delete the file
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                    await event.respond(f"🧹 File deleted from server: {os.path.basename(filename)}")
                else:
                    await event.respond("⚠️ File not found for deletion.")
            except Exception as e:
                await event.respond(f"⚠️ Could not delete file: {str(e)}")

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

# --- Start bot safely under Gunicorn ---
if os.environ.get("RUN_MAIN") == "true":
    Thread(target=start_bot).start()
