from flask import Flask
from bot import run_bot
import threading

app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running!"

# Start the bot in a separate thread
threading.Thread(target=run_bot, daemon=True).start()
