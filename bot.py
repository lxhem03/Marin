import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

API_ID = 23340285
API_HASH = "ab18f905cb5f4a75d41bb48d20acfa50"
BOT_TOKEN = ""

# Available qualities for selection
QUALITIES = ["144p", "240p", "360p", "480p", "720p", "1080p"]

app = Client("yt_download_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Store user link temporarily (for simplicity using a dict; for production use a database or persistent storage)
user_links = {}

def build_quality_keyboard():
    buttons = []
    for q in QUALITIES:
        buttons.append([InlineKeyboardButton(q, callback_data=f"quality_{q}")])
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.private & filters.text)
async def receive_link(client, message):
    link = message.text.strip()
    # Basic validation: check if it looks like a URL
    if not (link.startswith("http://") or link.startswith("https://")):
        await message.reply("Please send a valid URL link.")
        return

    # Save the link for the user
    user_links[message.from_user.id] = link

    # Ask for quality selection
    await message.reply(
        "Select the quality to download:",
        reply_markup=build_quality_keyboard()
    )

@app.on_callback_query(filters.regex(r"^quality_(\d+p)$"))
async def quality_selected(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in user_links:
        await callback_query.answer("No link found. Please send a link first.", show_alert=True)
        return

    quality = callback_query.data.split("_")[1]
    link = user_links[user_id]

    await callback_query.answer(f"Downloading {quality} video...")

    # Downloading video
    await callback_query.message.edit(f"Downloading video in {quality} quality...")

    # yt-dlp options to download specific quality
    ydl_opts = {
        "format": f"bestvideo[height={quality[:-1]}]+bestaudio/best[height<={quality[:-1]}]",
        "outtmpl": f"{user_id}_video.%(ext)s",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            filename = ydl.prepare_filename(info)
    except Exception as e:
        await callback_query.message.edit(f"Error while downloading: {e}")
        user_links.pop(user_id, None)
        return

    await callback_query.message.edit("Uploading the video...")

    try:
        await client.send_video(
            chat_id=user_id,
            video=filename,
            caption=f"Here is your video in {quality} quality."
        )
    except Exception as e:
        await callback_query.message.edit(f"Failed to upload video: {e}")
        user_links.pop(user_id, None)
        os.remove(filename)
        return

    await callback_query.message.delete()
    user_links.pop(user_id, None)

    # Clean up the downloaded file
    if os.path.exists(filename):
        os.remove(filename)

if __name__ == "__main__":
    print("Bot is running...")
    app.run()
