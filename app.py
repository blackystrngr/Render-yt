from flask import Flask
from telethon import TelegramClient, events, Button
import os
import threading
import asyncio
import subprocess
import shlex

app = Flask(__name__)

@app.route("/")
def home():
    return "Telethon bot is running!"

# --- Telegram bot setup ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient("bot_session", API_ID, API_HASH)

# --- Helper: get available formats ---
def get_formats(url):
    cmd = f"yt-dlp --cookies cookies.txt --list-formats {shlex.quote(url)}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(result.stderr)
    formats = []
    for line in result.stdout.splitlines():
        if line.strip().startswith("format code"):
            continue
        if line.strip() and line[0].isdigit():
            parts = line.split()
            format_code = parts[0]
            resolution = parts[1] if len(parts) > 1 else format_code
            formats.append((format_code, resolution))
    return formats

# --- Helper: download video in specific format ---
def download_video(url, format_code):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    output_template = "downloads/%(title)s.%(ext)s"
    cmd = [
        "yt-dlp", "--cookies", "cookies.txt",
        "-f", format_code,
        "-o", output_template,
        url
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        yield line  # streaming download progress
    process.wait()
    if process.returncode != 0:
        raise Exception("Download failed.")
    # find downloaded file
    files = os.listdir("downloads")
    if files:
        return os.path.join("downloads", files[0])
    else:
        raise Exception("Downloaded file not found.")

# --- Event handler ---
user_choices = {}  # track which user chose which URL

@bot.on(events.NewMessage)
async def handler(event):
    message_text = event.raw_text
    if message_text.startswith("/yt "):
        url = message_text[4:].strip()
        try:
            await event.respond("⏳ Fetching available qualities...")
            formats = get_formats(url)
            if not formats:
                await event.respond("❌ No formats found.")
                return
            buttons = [Button.inline(f"{res}", data=fc) for fc, res in formats[:10]]  # limit 10 choices
            user_choices[event.sender_id] = url
            await event.respond("Select a quality:", buttons=buttons)
        except Exception as e:
            await event.respond(f"❌ Failed to fetch formats: {str(e)}")
    else:
        await event.respond("hello there")

# --- Button handler ---
@bot.on(events.CallbackQuery)
async def callback(event):
    format_code = event.data.decode()
    user_id = event.sender_id
    url = user_choices.get(user_id)
    if not url:
        await event.answer("❌ No URL found. Send /yt <url> first.")
        return
    await event.edit(f"⏳ Downloading in format {format_code}...")
    try:
        # Stream download progress
        for line in download_video(url, format_code):
            if "Downloading" in line or "ETA" in line:
                await event.edit(f"⏳ {line.strip()}")
        # Send the file
        files = os.listdir("downloads")
        if files:
            filename = os.path.join("downloads", files[0])
            await event.respond(file=filename)
            os.remove(filename)
            await event.respond(f"✅ Uploaded and deleted: {os.path.basename(filename)}")
        else:
            await event.respond("❌ Downloaded file not found.")
    except Exception as e:
        await event.edit(f"❌ Error: {str(e)}")
    finally:
        if user_id in user_choices:
            del user_choices[user_id]

# --- Run bot in background thread ---
def run_bot():
    print("Starting bot thread...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot connected and ready!")
    bot.run_until_disconnected()

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
