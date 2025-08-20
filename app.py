# main.py
import os
import asyncio
import time
from telethon import TelegramClient, events, Button
from yt_dlp import YoutubeDL
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

# --- Telegram bot credentials ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH"))
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient("bot_session", API_ID, API_HASH)

user_choices = {}

def get_formats(url):
    with YoutubeDL({'listformats': True, 'cookies': 'cookies.txt'}) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = [(f['format_id'], f.get('format_note', f['ext']))
                   for f in info['formats'] if f.get('filesize') or f.get('height')]
    return formats

async def download_video(event, url, format_code):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    msg = await event.respond(f"⏳ Starting download in format {format_code}...")
    filename = ""
    last_update = 0
    loop = asyncio.get_running_loop()

    def progress_hook(d):
        nonlocal last_update, msg, filename
        if d['status'] == 'finished':
            filename = d['filename']
            loop.create_task(msg.respond(f"✅ Download complete: {os.path.basename(filename)}"))
        elif d['status'] == 'downloading':
            now = time.time()
            if now - last_update > 2:
                loop.create_task(msg.respond(
                    f"⏳ Downloading: {d['_percent_str']} of {d.get('_total_bytes_str','?')} ETA {d.get('_eta_str','?')}"
                ))
                last_update = now

    ydl_opts = {
        'format': format_code,
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'cookies': 'cookies.txt',
        'progress_hooks': [progress_hook]
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return filename

@bot.on(events.NewMessage)
async def handler(event):
    message_text = event.raw_text.strip()
    sender_id = event.sender_id

    if message_text.startswith("/yt "):
        url = message_text[4:].strip()
    elif "youtube.com" in message_text or "youtu.be" in message_text:
        url = message_text
    else:
        await event.respond("hello there")
        return

    try:
        await event.respond("⏳ Fetching available qualities...")
        formats = get_formats(url)
        if not formats:
            await event.respond("❌ No formats found.")
            return

        buttons = [Button.inline(f"{res}", data=fc) for fc, res in formats[:10]]
        user_choices[sender_id] = url
        await event.respond("Select a quality:", buttons=buttons)

    except Exception as e:
        await event.respond(f"❌ Failed to fetch formats: {str(e)}")

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
        await event.respond(f"📤 Uploading {os.path.basename(filename)}...")
        await event.respond(file=filename)
        os.remove(filename)
        await event.respond(f"✅ Uploaded and deleted: {os.path.basename(filename)}")

    except Exception as e:
        await event.respond(f"❌ Error: {str(e)}")

    finally:
        if sender_id in user_choices:
            del user_choices[sender_id]

# --- Start bot ---
async def start_bot():
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot connected and ready!")
    await bot.run_until_disconnected()
