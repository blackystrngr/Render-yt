from telethon import TelegramClient, events
import asyncio
import os

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    client = TelegramClient("bot", API_ID, API_HASH)

    async def main():
        await client.start(bot_token=BOT_TOKEN)

        @client.on(events.NewMessage)
        async def handler(event):
            await event.respond("hi there")

        await client.run_until_disconnected()

    loop.run_until_complete(main())
