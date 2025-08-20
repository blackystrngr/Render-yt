from flask import Flask
from telethon import TelegramClient, events
import os
import threading

# Flask app (to keep Render web service alive)
app = Flask(__name__)

@app.route("/")
def home():
    return "Telethon bot is running!"

# --- Telegram bot setup ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@bot.on(events.NewMessage)
async def handler(event):
    await event.respond("hello there")

def run_bot():
    print("Bot started...")
    bot.run_until_disconnected()

# Run Telethon in a background thread
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
