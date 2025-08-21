import os
import asyncio
from fastapi import FastAPI
from telethon import TelegramClient, events
from telethon.sessions import SQLiteSession

# Load environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Use a unique session name per worker to avoid SQLite locking
worker_id = os.getpid()
session_name = f"session_{worker_id}"

# Disable SQLite locking to prevent OperationalError
client = TelegramClient(SQLiteSession(session_name, lock=False), API_ID, API_HASH)

# Create FastAPI app
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Bot is running!"}

@app.on_event("startup")
async def start_bot():
    try:
        await client.start(bot_token=BOT_TOKEN)

        @client.on(events.NewMessage)
        async def handler(event):
            await event.respond("hi there 👋")

        # Run the bot in the background
        asyncio.create_task(client.run_until_disconnected())
        print("Bot started successfully.")
    except Exception as e:
        print(f"Bot startup failed: {e}")
