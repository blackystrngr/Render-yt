from fastapi import FastAPI
from telethon import TelegramClient, events
import asyncio
import os

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()
client = TelegramClient("bot", API_ID, API_HASH)

@app.get("/")
async def root():
    return {"status": "Bot is running!"}

@app.on_event("startup")
async def start_bot():
    await client.start(bot_token=BOT_TOKEN)

    @client.on(events.NewMessage)
    async def handler(event):
        await event.respond("hi there")

    asyncio.create_task(client.run_until_disconnected())
