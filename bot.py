import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message

API_ID = int(os.getenv("API_ID", ""))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

app = Client(
    "subs_muxer_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Temporary session storage
user_action = {}   # {user_id: "hard" or "soft"}
user_video = {}    # {user_id: Message}


# -------------------- COMMANDS --------------------

@app.on_message(filters.command(["start", "help"]))
async def start_help(_, message: Message):
    await message.reply(
        "**👋 Welcome to Subtitles Muxer Bot!**\n"
        "Send me a **video or document**, and choose:\n"
        "• Hard Subtitles (burn-in)\n"
        "• Soft Subtitles (attach SRT track)"
    )


# -------------------- VIDEO/DOCUMENT HANDLER --------------------

@app.on_message(filters.video | filters.document)
async def file_received(_, message: Message):
    user_id = message.from_user.id

    user_video[user_id] = message  # store video/document message

    await message.reply(
        "Choose what to do with the file:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Hard Subtitles", callback_data="hard_sub")],
            [InlineKeyboardButton("🎬 Soft Subtitles", callback_data="soft_sub")]
        ])
    )


# -------------------- CALLBACK --------------------

@app.on_callback_query()
async def callback_handler(_, query):
    user_id = query.from_user.id
    data = query.data

    if data == "hard_sub":
        user_action[user_id] = "hard"
        await query.message.edit("🔥 You selected **Hard Subtitles**.\nSend me the `.srt` subtitle file.")
    elif data == "soft_sub":
        user_action[user_id] = "soft"
        await query.message.edit("🎬 You selected **Soft Subtitles**.\nSend me the `.srt` subtitle file.")

    await query.answer()


# -------------------- SUBTITLE FILE HANDLER --------------------

@app.on_message(filters.document & filters.regex(r".*\\.srt$"))
async def srt_received(_, message: Message):
    user_id = message.from_user.id

    if user_id not in user_action or user_id not in user_video:
        return await message.reply("❗ First send a video, then choose Hard/Soft Subtitles.")

    mode = user_action[user_id]
    video_msg = user_video[user_id]

    await message.reply("⬇️ Downloading files, please wait...")

    # Download video + srt
    video_path = await video_msg.download()
    srt_path = await message.download()

    output_file = video_path.rsplit('.', 1)[0] + "_subbed.mp4"

    # FFmpeg commands
    if mode == "hard":
        cmd = f"ffmpeg -i '{video_path}' -vf subtitles='{srt_path}' -c:a copy '{output_file}' -y"
    else:
        cmd = f"ffmpeg -i '{video_path}' -i '{srt_path}' -c copy -c:s mov_text '{output_file}' -y"

    # Process using FFmpeg
    process = await asyncio.create_subprocess_shell(cmd)
    await process.communicate()

    await message.reply_video(output_file, caption="✅ Here is your processed file.")

    # Cleanup
    os.remove(video_path)
    os.remove(srt_path)
    os.remove(output_file)

    user_action.pop(user_id, None)
    user_video.pop(user_id, None)


# -------------------- RUN BOT --------------------

app.run()
