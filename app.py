from flask import Flask
from telethon import TelegramClient, events
import os
import threading
import asyncio
import yt_dlp

app = Flask(__name__)

@app.route("/")
def home():
    return "Telethon bot is running!"

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient("bot_session", API_ID, API_HASH)

# --- Helper function to download video ---
def download_video(url):
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'cookies': 'cookies.txt',
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    filename = os.path.join('downloads', info.get('title') + '.' + info.get('ext'))
    return filename

# Event handler for new messages
@bot.on(events.NewMessage)
async def handler(event):
    message_text = event.raw_text
    if message_text.startswith("/yt "):
        url = message_text[4:].strip()
        await event.respond("⏳ Downloading...")
        try:
            filename = download_video(url)
            # Send the video to Telegram
            await event.respond(file=filename)
            # Delete the video after sending
            os.remove(filename)
            await event.respond(f"✅ Uploaded and deleted: {os.path.basename(filename)}")
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}")
    else:
        await event.respond("hello there")

def run_bot():
    print("Starting bot thread...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.start(bot_token=BOT_TOKEN)
    print("✅ Bot connected and ready!")
    bot.run_until_disconnected()

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
