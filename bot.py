from telethon import TelegramClient, events
import os

# Get credentials from environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

client = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@client.on(events.NewMessage)
async def handler(event):
    await event.respond("hi there")

def run():
    client.run_until_disconnected()
