import logging
import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Hardcoded configuration (replace with your values)
API_ID = '27394279'  # Get from https://my.telegram.org
API_HASH = '90a9aa4c31afa3750da5fd686c410851'  # Get from https://my.telegram.org
BOT_TOKEN = ''  # Get from @BotFather

# Initialize Pyrogram client with Motor storage
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)



# Start command handler
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    logger.info(f"Start command received from {message.chat.id}")
    await message.reply_text("Welcome! Use /channels ")


# Run the bot
if __name__ == "__main__":
    logger.info("Starting bot...")
    app.run()
