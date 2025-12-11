import asyncio, os
from collections import defaultdict
from pyrogram import Client, filters
from pyrogram.types import Message

# Load from environment variables (set in deployment platforms)
API_ID = int(os.getenv("API_ID", "23340285"))
API_HASH = os.getenv("API_HASH", "ab18f905cb5f4a75d41bb48d20acfa50")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7987512854:AAGsXDfqyAcRT3wRGVFC9_u02ADd7A45z5k")

# Initialize the bot client
app = Client(
    "thumbchanger",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Dictionary to store pending video file_ids for users (user_id -> video_file_id)
pending_videos = defaultdict(str)

@app.on_message(filters.video & filters.private)
async def handle_video(client: Client, message: Message):
    # Store the video file_id
    pending_videos[message.from_user.id] = message.video.file_id
    await message.reply("Video received! Now send me the image to use as the cover (thumbnail).")

@app.on_message(filters.photo & filters.private)
async def handle_photo(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id not in pending_videos or not pending_videos[user_id]:
        await message.reply("Please send a video first, then the thumbnail image.")
        return
    
    # Get the pending video file_id
    video_file_id = pending_videos[user_id]
    
    # Use the received photo's file_id as thumb (no download needed, Telegram handles it efficiently)
    thumb_file_id = message.photo.file_id  # The largest photo size file_id
    
    # Send the video back with the new thumbnail
    # This re-uses the original video file_id, so no re-upload or quality loss for the video
    # Thumbnail is set directly, preserving its quality as Telegram compresses it minimally for thumbs
    await client.send_video(
        chat_id=message.chat.id,
        video=video_file_id,
        thumb=thumb_file_id,
        caption="Here's your video with the new cover!"
    )
    
    # Clear the pending video
    del pending_videos[user_id]
    
    await message.reply("Thumbnail applied and video sent! It should have taken just a second or two.")

@app.on_message(filters.text & filters.private)
async def handle_text(client: Client, message: Message):
    if message.text.lower() == "/start":
        await message.reply("Hi! Send me a video, and I'll ask for a thumbnail image to set as its cover. I'll send it back quickly without re-encoding the video.")

# Run the bot
if __name__ == "__main__":
    print("Starting the thumbnail bot...")
    app.run()
