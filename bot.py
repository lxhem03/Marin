import logging
import requests
import os
import tempfile
import subprocess
from urllib.parse import quote
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Hardcoded configuration (replace with your values)
API_ID = 'YOUR_TELEGRAM_API_ID'  # Get from https://my.telegram.org
API_HASH = 'YOUR_TELEGRAM_API_HASH'  # Get from https://my.telegram.org
BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'  # Get from @BotFather
API_BASE_URL = 'https://adultcolony.site/xhamster/search'

# Initialize Pyrogram client
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Conversation states (simulated with user data)
SHOW_RESULT, SELECT_QUALITY = range(2)

# Supported qualities
QUALITIES = ['240p', '480p', '720p', '1080p']

# File size limit in MB (2GB for free users)
FILE_SIZE_LIMIT_MB = 2000

# Function to fetch API results for a page
def fetch_api_page(query, page):
    try:
        encoded_query = quote(query.replace(' ', '%20'))
        url = f"{API_BASE_URL}?query={encoded_query}&page={page}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('success') and 'data' in data:
            return data['data']
        return []
    except Exception as e:
        logger.error(f"API error on page {page}: {e}")
        return []

# Function to get video metadata using ffprobe
def get_video_metadata(file_path):
    try:
        probe = subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
            'default=noprint_wrappers=1:nokey=1', file_path
        ], stderr=subprocess.STDOUT, text=True).strip()
        duration = float(probe) if probe else 0
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        return duration, file_size
    except Exception as e:
        logger.error(f"Metadata error: {e}")
        return 0, 0

# Start command handler
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text("Welcome! Use /search <query> (e.g., /search latest news).")

# Search command handler
@app.on_message(filters.command("search"))
async def search(client, message: Message):
    query = ' '.join(message.command[1:])  # Extract query after /search
    if not query:
        await message.reply_text("Please provide a query, e.g., /search latest news")
        return

    # Initialize user data
    user_data = message.chat.id
    await client.set_user_data(user_data, {
        'query': query,
        'current_page': 1,
        'results': [],
        'current_index': 0
    })

    new_results = fetch_api_page(query, 1)
    if not new_results:
        await message.reply_text("No results found or API error.")
        return

    await client.set_user_data(user_data, {'results': new_results})
    await show_result(client, message, 0)

# Function to show a specific result
async def show_result(client, message: Message, index):
    user_data = message.chat.id
    results = (await client.get_user_data(user_data))['results']
    if index < 0 or index >= len(results):
        return

    item = results[index]
    title = item.get('title', 'No title')
    duration = item.get('duration', 'N/A')
    views = item.get('views', 'N/A')
    thumbnail = item.get('image')
    watch_url = item.get('link')

    # Initial caption
    caption = f"<b>{title}</b>\nDuration: {duration}\nViews: {views}"

    # Build keyboard
    keyboard = []
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"prev_{index}"))
    if True:  # Always show next; fetch if needed
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"next_{index}"))
    if nav_row:
        keyboard.append(nav_row)

    action_row = [
        InlineKeyboardButton("Download", callback_data=f"download_{index}"),
        InlineKeyboardButton("Watch Online", url=watch_url)
    ]
    keyboard.append(action_row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send or edit message with photo
    if hasattr(message, 'message_id'):
        await client.edit_message_media(
            chat_id=message.chat.id,
            message_id=message.message_id,
            media=InputFile(requests.get(thumbnail).content, filename='thumbnail.jpg') if thumbnail else None,
            reply_markup=reply_markup
        )
        await client.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=caption,
            parse_mode='HTML'
        )
    else:
        sent_message = await message.reply_photo(
            photo=thumbnail,
            caption=caption,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        await client.set_user_data(user_data, {'message_id': sent_message.message_id})

# Callback query handler
@app.on_callback_query()
async def button_handler(client, callback_query):
    data = callback_query.data
    user_data = callback_query.message.chat.id
    current_index = (await client.get_user_data(user_data))['current_index']
    results = (await client.get_user_data(user_data))['results']

    if data.startswith('prev_'):
        new_index = int(data.split('_')[1]) - 1
        if new_index >= 0:
            await client.set_user_data(user_data, {'current_index': new_index})
            await show_result(client, callback_query.message, new_index)

    elif data.startswith('next_'):
        new_index = int(data.split('_')[1]) + 1
        if new_index >= len(results):
            current_page = (await client.get_user_data(user_data))['current_page'] + 1
            new_results = fetch_api_page((await client.get_user_data(user_data))['query'], current_page)
            if new_results:
                results.extend(new_results)
                await client.set_user_data(user_data, {'results': results, 'current_page': current_page})
            else:
                await callback_query.message.reply_text("No more results.")
                return

        await client.set_user_data(user_data, {'current_index': new_index})
        await show_result(client, callback_query.message, new_index)

    elif data.startswith('download_'):
        index = int(data.split('_')[1])
        await client.set_user_data(user_data, {'selected_index': index})

        keyboard = [[InlineKeyboardButton(q, callback_data=f"quality_{q}")] for q in QUALITIES]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await callback_query.message.reply_text("Select the quality:", reply_markup=reply_markup)

    await callback_query.answer()

# Handle quality selection
@app.on_callback_query(filters.regex(r'^quality_'))
async def select_quality(client, callback_query):
    data = callback_query.data
    user_data = callback_query.message.chat.id
    quality = data.split('_')[1]
    index = (await client.get_user_data(user_data))['selected_index']
    results = (await client.get_user_data(user_data))['results']
    item = results[index]
    video_url = item.get('video')
    title = item.get('title', 'video')
    thumbnail_url = item.get('image')

    await callback_query.message.reply_text(f"Downloading '{title}' in {quality}...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, f"{title[:50]}.%(ext)s")
            ydl_opts = {
                'format': f'best[height<={quality[:-1]}]',
                'outtmpl': output_file,
                'quiet': True,
                'merge_output_format': 'mp4',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
                downloaded_file = next((f for f in os.listdir(tmpdir) if os.path.isfile(os.path.join(tmpdir, f))), None)
                if not downloaded_file:
                    raise Exception("No file downloaded")

            file_path = os.path.join(tmpdir, downloaded_file)
            duration, file_size_mb = get_video_metadata(file_path)

            if file_size_mb > FILE_SIZE_LIMIT_MB:
                await callback_query.message.reply_text(f"Error: File too large ({file_size_mb:.2f} MB > {FILE_SIZE_LIMIT_MB} MB).")
                return

            thumb = None
            if thumbnail_url:
                thumb_response = requests.get(thumbnail_url)
                if thumb_response.status_code == 200:
                    thumb = InputFile(BytesIO(thumb_response.content), filename='thumb.jpg')

            duration_min = int(duration // 60)
            duration_sec = int(duration % 60)
            formatted_duration = f"{duration_min}:{duration_sec:02d}" if duration else item.get('duration', 'N/A')

            caption = f"<b>{title}</b>\nDuration: {formatted_duration}\nQuality: {quality}\nFile size: {file_size_mb:.2f} MB"

            with open(file_path, 'rb') as f:
                await callback_query.message.reply_video(
                    video=f,
                    caption=caption,
                    duration=int(duration) if duration else 0,
                    thumb=thumb,
                    supports_streaming=True
                )

    except Exception as e:
        logger.error(f"Download/upload error: {e}")
        await callback_query.message.reply_text(f"Error: {str(e)}")

# Run the bot
if __name__ == '__main__':
    app.run()
