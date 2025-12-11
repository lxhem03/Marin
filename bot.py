import os
import ffmpeg
from pyrogram import Client, filters
from pyrogram.types import Message

# Store pending videos by user
PENDING = {}

# Load from environment variables (set in deployment platforms)
API_ID = int(os.getenv("API_ID", "23340285"))
API_HASH = os.getenv("API_HASH", "ab18f905cb5f4a75d41bb48d20acfa50")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7987512854:AAGsXDfqyAcRT3wRGVFC9_u02ADd7A45z5k")

app = Client(
    "thumbchanger",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# User sends video first
@app.on_message(filters.private & (filters.video | filters.document))
async def handle_video(_, message: Message):
    user_id = message.from_user.id

    # Store file object
    PENDING[user_id] = message

    # Ask for thumbnail instantly (silent mode)
    await message.reply("Send the thumbnail image now.")


# User sends image next
@app.on_message(filters.private & filters.photo)
async def handle_thumb(_, message: Message):
    user_id = message.from_user.id

    if user_id not in PENDING:
        return await message.reply("Please send a video first.")

    video_msg = PENDING[user_id]

    # Paths
    video_path = f"video_{user_id}.mp4"
    image_path = f"thumb_{user_id}.jpg"
    output_path = f"final_{user_id}.mp4"

    # Silent-fast download of both files
    await video_msg.download(video_path)
    await message.download(image_path)

    # ffmpeg: attach thumbnail without re-encoding
    (
        ffmpeg
        .input(video_path)
        .input(image_path)
        .output(
            output_path,
            map='0',
            map_='1',
            c='copy',
            **{"disposition:v:1": "attached_pic"},
            **{"metadata:s:v:1": "title=Cover Image"}
        )
        .overwrite_output()
        .run(quiet=True)
    )

    # Send back final video
    await message.reply_video(output_path, caption="Thumbnail replaced!")

    # Cleanup
    os.remove(video_path)
    os.remove(image_path)
    os.remove(output_path)
    PENDING.pop(user_id, None)


app.run()
