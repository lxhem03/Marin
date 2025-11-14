#v2
import asyncio
import requests
from pyrogram import Client
from pyrogram.enums import ParseMode
import os
import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------------
# Environment variables
# ---------------------
API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")


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
# TMDb Helper Functions
# ---------------------
def get_tmdb(endpoint):
    url = f"https://api.themoviedb.org/3/{endpoint}?api_key={TMDB_API_KEY}&language=en-US"
    return requests.get(url).json()

def get_detailed_info(media_type, media_id):
    """Fetch extra info for rating, genres, runtime"""
    data = get_tmdb(f"{media_type}/{media_id}")
    info = {}
    info["genres"] = ", ".join([g["name"] for g in data.get("genres", [])]) or "Unknown"
    info["rating"] = data.get("vote_average", 0)
    info["vote_count"] = data.get("vote_count", 0)
    info["runtime"] = data.get("runtime") or (f"{len(data.get('episodes', []))} eps" if media_type == "tv" else "Unknown")
    info["imdb_id"] = data.get("imdb_id")
    return info

def get_latest_trending():
    """Fetch trending movies and TV shows"""
    movies = get_tmdb("trending/movie/day").get("results", [])
    shows = get_tmdb("trending/tv/day").get("results", [])
    combined = []

    for movie in movies:
        combined.append({
            "id": movie["id"],
            "type": "movie",
            "title": movie["title"],
            "overview": movie["overview"],
            "release": movie.get("release_date", "Unknown"),
            "poster": f"https://image.tmdb.org/t/p/w780{movie.get('backdrop_path') or movie.get('poster_path')}",
            "url": f"https://www.themoviedb.org/movie/{movie['id']}"
        })

    for tv in shows:
        combined.append({
            "id": tv["id"],
            "type": "tv",
            "title": tv["name"],
            "overview": tv["overview"],
            "release": tv.get("first_air_date", "Unknown"),
            "poster": f"https://image.tmdb.org/t/p/w780{tv.get('backdrop_path') or tv.get('poster_path')}",
            "url": f"https://www.themoviedb.org/tv/{tv['id']}"
        })
    return combined

# ---------------------
# Caption generator
# ---------------------
def build_caption(item, extra):
    rating = f"⭐ <b>{extra['rating']:.1f}</b> ({extra['vote_count']} votes)"
    genres = f"🎭 {extra['genres']}"
    line = f"🎬 <b>{item['title']}</b>\n📅 {item['release']}\n{rating}\n{genres}\n\n"
    line += f"📰 {item['overview'][:600]}...\n\n"
    if extra["imdb_id"]:
        line += f"🔗 <a href='https://www.imdb.com/title/{extra['imdb_id']}'>IMDb</a> | "
    line += f"<a href='{item['url']}'>TMDb</a>"
    return line

# ---------------------
# Weekly summary
# ---------------------
async def weekly_summary():
    trending = get_tmdb("trending/all/week").get("results", [])[:10]
    if not trending:
        return
    text = "📅 <b>Weekly Trending Movies & Series</b>\n\n"
    for t in trending:
        title = t.get("title") or t.get("name")
        rating = t.get("vote_average", 0)
        text += f"🎬 <b>{title}</b> — ⭐ {rating:.1f}\n"
    text += "\n🔥 Check them out this week!"
    await app.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML)

# ---------------------
# Auto post loop
# ---------------------
async def post_latest_news():
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
        now = datetime.utcnow()

        # Weekly summary every Sunday (UTC)
        if now.weekday() == 6 and now.hour == 9:
            logging.info("Posting weekly summary...")
            await weekly_summary()

        items = get_latest_trending()
        new_items = [i for i in items if i["title"] not in posted_titles]

        for item in new_items:
            extra = get_detailed_info(item["type"], item["id"])
            caption = build_caption(item, extra)

            try:
                await app.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=item["poster"],
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
                posted_titles.add(item["title"])
                save_posted_titles(posted_titles)
                logging.info(f"✅ Posted: {item['title']}")
                await asyncio.sleep(5)  # post delay between new posts
            except Exception as e:
                logging.error(f"❌ Failed to post {item['title']}: {e}")

        if not new_items:
            logging.info("No new movies or shows to post.")
        await asyncio.sleep(60)  # check every hour

# ---------------------
# Run
# ---------------------
if __name__ == "__main__":
    logging.info("🚀 Starting Improved Movie News Bot...")
    app.start()
    asyncio.get_event_loop().run_until_complete(post_latest_news())
