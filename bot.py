#V3
import asyncio
import os
import json
import logging
from datetime import datetime
import requests
from pyrogram import Client, filters
from pyrogram.enums import ParseMode

# -------------------------------------------------------
# Logging Setup
# -------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -------------------------------------------------------
# Environment Variables
# -------------------------------------------------------
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

# Admin IDs (comma separated)
ADMINS = os.environ.get("ADMINS", "")
ADMINS = [int(x.strip()) for x in ADMINS.split(",") if x.strip().isdigit()]

# -------------------------------------------------------
# Initialize Bot
# -------------------------------------------------------
app = Client("movie_news_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------------------------------------
# Persistent storage for posted titles
# -------------------------------------------------------
POSTED_FILE = "posted.json"

def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_posted(data):
    with open(POSTED_FILE, "w") as f:
        json.dump(list(data), f)

posted_titles = load_posted()

# -------------------------------------------------------
# TMDb Helper Functions
# -------------------------------------------------------
def tmdb_get(url):
    full_url = f"https://api.themoviedb.org/3/{url}?api_key={TMDB_API_KEY}&language=en-US"
    return requests.get(full_url).json()

def get_detailed_info(media_type, media_id):
    d = tmdb_get(f"{media_type}/{media_id}")
    return {
        "genres": ", ".join(g["name"] for g in d.get("genres", [])) or "Unknown",
        "rating": d.get("vote_average", 0),
        "votes": d.get("vote_count", 0),
        "runtime": d.get("runtime") or d.get("episode_run_time", ["Unknown"])[0],
        "imdb": d.get("imdb_id")
    }

def get_trending():
    movies = tmdb_get("trending/movie/day").get("results", [])
    shows  = tmdb_get("trending/tv/day").get("results", [])
    
    combined = []
    for m in movies:
        combined.append({
            "id": m["id"],
            "type": "movie",
            "title": m["title"],
            "overview": m["overview"],
            "release": m.get("release_date", "Unknown"),
            "poster": f"https://image.tmdb.org/t/p/w780{m.get('backdrop_path') or m.get('poster_path')}",
            "url": f"https://www.themoviedb.org/movie/{m['id']}"
        })

    for s in shows:
        combined.append({
            "id": s["id"],
            "type": "tv",
            "title": s["name"],
            "overview": s["overview"],
            "release": s.get("first_air_date", "Unknown"),
            "poster": f"https://image.tmdb.org/t/p/w780{s.get('backdrop_path') or s.get('poster_path')}",
            "url": f"https://www.themoviedb.org/tv/{s['id']}"
        })
    
    return combined

# -------------------------------------------------------
# Caption Builder
# -------------------------------------------------------
def build_caption(item, extra):
    imdb = f"<a href='https://www.imdb.com/title/{extra['imdb']}'>IMDb</a>" if extra["imdb"] else ""
    
    return (
        f"🎬 <b>{item['title']}</b>\n"
        f"📅 Release: <i>{item['release']}</i>\n"
        f"⭐ Rating: <b>{extra['rating']:.1f}</b> ({extra['votes']} votes)\n"
        f"🎭 Genres: {extra['genres']}\n"
        f"⏳ Runtime: {extra['runtime']}\n\n"
        f"📰 {item['overview'][:600]}...\n\n"
        f"🔗 {imdb} | <a href='{item['url']}'>TMDb</a>"
    )

# -------------------------------------------------------
# Weekly Summary Poster
# -------------------------------------------------------
async def post_weekly():
    weekly = tmdb_get("trending/all/week").get("results", [])[:10]
    if not weekly:
        return
    
    text = "📅 <b>Weekly Trending Movies & Series</b>\n\n"
    for w in weekly:
        title = w.get("title") or w.get("name")
        text += f"🎬 {title} — ⭐ {w.get('vote_average', 0)}\n"
    
    await app.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML)

# -------------------------------------------------------
# Posting Function
# -------------------------------------------------------
async def post_new_items():
    global posted_titles

    items = get_trending()
    new_items = [i for i in items if i["title"] not in posted_titles]

    for item in new_items:
        extra = get_detailed_info(item["type"], item["id"])
        caption = build_caption(item, extra)

        try:
            await app.send_photo(
                CHANNEL_ID,
                photo=item["poster"],
                caption=caption,
                parse_mode=ParseMode.HTML
            )
            
            posted_titles.add(item["title"])
            save_posted(posted_titles)

            logging.info(f"Posted: {item['title']}")
            await asyncio.sleep(5)

        except Exception as e:
            logging.error(f"Error posting {item['title']}: {e}")

    if not new_items:
        logging.info("No new items found.")

# -------------------------------------------------------
# ADMIN COMMAND CHECK
# -------------------------------------------------------
def admin_only(func):
    async def wrapper(client, message):
        if message.from_user.id not in ADMINS:
            await message.reply("❌ You are not authorized.")
            return
        await func(client, message)
    return wrapper

# -------------------------------------------------------
# ADMIN COMMANDS
# -------------------------------------------------------
@app.on_message(filters.command("weekly"))
@admin_only
async def manual_weekly(_, msg):
    await msg.reply("Posting weekly trending…")
    await post_weekly()

@app.on_message(filters.command("checknew"))
@admin_only
async def manual_check(_, msg):
    await msg.reply("Checking for new releases…")
    await post_new_items()

@app.on_message(filters.command("status"))
@admin_only
async def status(_, msg):
    await msg.reply(f"📊 Bot is running.\nPosted items: {len(posted_titles)}")

# -------------------------------------------------------
# AUTO LOOP
# -------------------------------------------------------
async def auto_loop():
    while True:
        now = datetime.utcnow()

        # Weekly on Sunday 09:00 UTC
        if now.weekday() == 6 and now.hour == 9:
            await post_weekly()

        await post_new_items()
        await asyncio.sleep(3600)  # check every hour

# -------------------------------------------------------
# START BOT
# -------------------------------------------------------
if __name__ == "__main__":
    app.start()
    asyncio.get_event_loop().run_until_complete(auto_loop())
