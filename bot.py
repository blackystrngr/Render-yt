import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import yt_dlp

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram Bot API Token
TELEGRAM_API_TOKEN = '8273826418:AAGUG6t6RsZGihebloztt3w7OFOBQXPbN9M'

# Function to download YouTube videos
def download_youtube_video(url: str) -> str:
    """Downloads YouTube video and returns the file path."""
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',  # Store in 'downloads' folder with video title as filename
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        video_file = ydl.prepare_filename(info_dict)
        return video_file

# Start command
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Welcome! Send me a YouTube URL, and I will download it for you.")

# Handle incoming messages
def handle_message(update: Update, context: CallbackContext) -> None:
    message = update.message.text
    if message.startswith('https://www.youtube.com/'):
        try:
            update.message.reply_text('Downloading video... Please wait.')

            video_path = download_youtube_video(message)
            update.message.reply_text('Download complete! Preparing to send video...')

            # Check if video is larger than 100MB
            video_size = os.path.getsize(video_path)
            if video_size > 100 * 1024 * 1024:  # 100MB limit
                # Send as document if larger than 100MB
                with open(video_path, 'rb') as video_file:
                    update.message.reply_document(video_file)
            else:
                # Send as video if smaller than 100MB
                with open(video_path, 'rb') as video_file:
                    update.message.reply_video(video_file)

            # Clean up the downloaded file after upload
            os.remove(video_path)
            logger.info(f"Deleted video file: {video_path}")

        except Exception as e:
            update.message.reply_text(f"An error occurred: {e}")
    else:
        update.message.reply_text("Please send a valid YouTube URL.")

# Main function to set up the bot
def main():
    # Initialize the Updater
    updater = Updater(TELEGRAM_API_TOKEN)
    dispatcher = updater.dispatcher

    # Add command and message handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Start polling for new messages
    updater.start_polling()

    # Run the bot until you send a signal to stop
    updater.idle()

if __name__ == '__main__':
    main()
