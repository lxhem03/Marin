import asyncio
import requests
from pyrogram import Client
import os
import logging

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

        for movie in trending_movies.get("results", [])[:3]:
            combined.append({
                "type": "Movie",
                "title": movie["title"],
                "overview": movie["overview"],
                "release": movie.get("release_date", "Unknown"),
                "poster": f"https://image.tmdb.org/t/p/w780{movie['backdrop_path'] or movie['poster_path']}",
                "url": f"https://www.themoviedb.org/movie/{movie['id']}"
            })

        for tv in trending_tv.get("results", [])[:3]:
            combined.append({
                "type": "Series",
                "title": tv["name"],
                "overview": tv["overview"],
                "release": tv.get("first_air_date", "Unknown"),
                "poster": f"https://image.tmdb.org/t/p/w780{tv['backdrop_path'] or tv['poster_path']}",
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
    """Posts latest movie/series news periodically"""
    posted_titles = set()

    while True:
        items = get_latest_movies_and_series()
        if not items:
            logging.warning("No data fetched from TMDb.")
            await asyncio.sleep(3600)
            continue

        for item in items:
            if item["title"] in posted_titles:
                continue

            caption = (
                f"🎬 **{item['title']}** ({item['type']})\n"
                f"📅 Release: {item['release']}\n\n"
                f"📰 {item['overview'][:500]}...\n\n"
                f"🔗 [View on TMDb]({item['url']})"
            )

            try:
                await app.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=item["poster"],
                    caption=caption,
                    parse_mode="markdown"
                )
                logging.info(f"Posted: {item['title']}")
                posted_titles.add(item["title"])
                await asyncio.sleep(10)
            except Exception as e:
                logging.error(f"Failed to post {item['title']}: {e}")

        await asyncio.sleep(1 * 60)

@app.on_message()
async def start(client, message):
    await message.reply("🎥 This bot automatically posts latest movie and series updates to the channel!")

if __name__ == "__main__":
    logging.info("Starting Movie News Bot...")
    app.start()
    asyncio.get_event_loop().run_until_complete(post_latest_news())
