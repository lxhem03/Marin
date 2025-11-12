import asyncio
import requests
from pyrogram import Client
from pyrogram.enums import ParseMode
import os
import logging
import json

# ---------------------
# Logging setup
# ---------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------------
# Environment variables
# ---------------------
API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

# ---------------------
# Initialize Bot
# ---------------------
app = Client("movie_news_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ---------------------
# Persistent file for posted titles
# ---------------------
POSTED_FILE = "posted.json"

def load_posted_titles():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_posted_titles(titles):
    with open(POSTED_FILE, "w") as f:
        json.dump(list(titles), f)

# ---------------------
# TMDb Fetch Function
# ---------------------
def get_latest_movies_and_series():
    """Fetch latest trending movies and TV shows from TMDb"""
    try:
        trending_movies = requests.get(
            f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}&language=en-US"
        ).json()

        trending_tv = requests.get(
            f"https://api.themoviedb.org/3/trending/tv/day?api_key={TMDB_API_KEY}&language=en-US"
        ).json()

        combined = []

        for movie in trending_movies.get("results", []):
            combined.append({
                "type": "Movie",
                "title": movie["title"],
                "overview": movie["overview"],
                "release": movie.get("release_date", "Unknown"),
                "poster": f"https://image.tmdb.org/t/p/w780{movie.get('backdrop_path') or movie.get('poster_path')}",
                "url": f"https://www.themoviedb.org/movie/{movie['id']}"
            })

        for tv in trending_tv.get("results", []):
            combined.append({
                "type": "Series",
                "title": tv["name"],
                "overview": tv["overview"],
                "release": tv.get("first_air_date", "Unknown"),
                "poster": f"https://image.tmdb.org/t/p/w780{tv.get('backdrop_path') or tv.get('poster_path')}",
                "url": f"https://www.themoviedb.org/tv/{tv['id']}"
            })

        return combined

    except Exception as e:
        logging.error(f"TMDb fetch error: {e}")
        return []

# ---------------------
# Auto Post Function
# ---------------------
async def post_latest_news():
    """Posts only new movie/series updates periodically"""
    posted_titles = load_posted_titles()
    logging.info(f"Loaded {len(posted_titles)} previously posted titles.")

    # verify channel access
    try:
        me = await app.get_me()
        chat = await app.get_chat(CHANNEL_ID)
        logging.info(f"Connected as {me.username}, posting to {chat.title}")
    except Exception as e:
        logging.error(f"Failed to access channel {CHANNEL_ID}: {e}")
        return

    while True:
        items = get_latest_movies_and_series()
        if not items:
            logging.warning("No data fetched from TMDb.")
            await asyncio.sleep(3600)
            continue

        new_posts = 0
        for item in items:
            if item["title"] in posted_titles:
                continue

            caption = (
                f"🎬 <b>{item['title']}</b> ({item['type']})\n"
                f"📅 Release: <i>{item['release']}</i>\n\n"
                f"📰 {item['overview'][:600]}...\n\n"
                f"🔗 <a href='{item['url']}'>View on TMDb</a>"
            )

            try:
                await app.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=item["poster"],
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
                posted_titles.add(item["title"])
                save_posted_titles(posted_titles)
                new_posts += 1
                logging.info(f"✅ Posted: {item['title']}")
                await asyncio.sleep(10)
            except Exception as e:
                logging.error(f"❌ Failed to post {item['title']}: {e}")

        if new_posts == 0:
            logging.info("No new items found to post.")

        await asyncio.sleep(1 * 60)  # Every 6 hours

# ---------------------
# /start handler (optional)
# ---------------------
@app.on_message()
async def start(client, message):
    await message.reply("🎥 This bot automatically posts the latest movie & series news to the channel!")

# ---------------------
# Run
# ---------------------
if __name__ == "__main__":
    logging.info("🚀 Starting Movie News Bot...")
    app.start()
    asyncio.get_event_loop().run_until_complete(post_latest_news())
