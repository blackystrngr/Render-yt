from flask import Flask
from telethon import TelegramClient, events
import asyncio
import os

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Flask(__name__)
loop = asyncio.get_event_loop()
client = TelegramClient("bot", API_ID, API_HASH)

@app.route("/")
def index():
    return "Bot is running!"

async def start_bot():
    await client.start(bot_token=BOT_TOKEN)

    @client.on(events.NewMessage)
    async def handler(event):
        await event.respond("hi there")

    await client.run_until_disconnected()

# Schedule the bot to run in the background
loop.create_task(start_bot())
