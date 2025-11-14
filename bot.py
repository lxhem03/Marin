#V4
import os
import json
import logging
import asyncio
import requests
from datetime import datetime
from typing import List, Dict, Any

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -------------------------
# Environment variables
# -------------------------
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")  # e.g. @yourchannel
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")

# Admin IDs env: comma separated integers
ADMINS = os.environ.get("ADMINS", "")
ADMINS = [int(x.strip()) for x in ADMINS.split(",") if x.strip().isdigit()]

# Files for persistence
POSTED_FILE = "posted.json"
STATE_FILE = "state.json"

# runtime defaults
CHECK_INTERVAL = 60  # seconds (1 hour)
POST_DELAY = 7  # seconds between posting new items

# -------------------------
# Client init
# -------------------------
app = Client("movie_news_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------
# State utilities
# -------------------------
def load_json_file(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load {path}: {e}")
    return default

def save_json_file(path: str, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Failed to save {path}: {e}")

posted_titles = set(load_json_file(POSTED_FILE, []))
state = load_json_file(STATE_FILE, {"paused": False})
PAUSED = bool(state.get("paused", False))

def add_posted(title: str):
    posted_titles.add(title)
    save_json_file(POSTED_FILE, list(posted_titles))

def set_paused(flag: bool):
    global PAUSED
    PAUSED = bool(flag)
    state["paused"] = PAUSED
    save_json_file(STATE_FILE, state)

# -------------------------
# TMDb helpers
# -------------------------
TMDB_BASE = "https://api.themoviedb.org/3"

def tmdb_request(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Make a TMDb GET request, return parsed JSON or {}."""
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY
    try:
        r = requests.get(f"{TMDB_BASE}/{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"TMDb request failed for {path}: {e}")
        return {}

def build_image_url(path: str, size: str = "w780") -> str:
    if not path:
        return ""
    return f"https://image.tmdb.org/t/p/{size}{path}"

def get_trending_all_day() -> List[Dict]:
    movies = tmdb_request("trending/movie/day").get("results", [])
    tv = tmdb_request("trending/tv/day").get("results", [])
    combined = []
    for m in movies:
        combined.append({
            "id": m.get("id"),
            "type": "movie",
            "title": m.get("title"),
            "overview": m.get("overview", ""),
            "release": m.get("release_date", "Unknown"),
            "poster": build_image_url(m.get("backdrop_path") or m.get("poster_path")),
            "url": f"https://www.themoviedb.org/movie/{m.get('id')}"
        })
    for t in tv:
        combined.append({
            "id": t.get("id"),
            "type": "tv",
            "title": t.get("name"),
            "overview": t.get("overview", ""),
            "release": t.get("first_air_date", "Unknown"),
            "poster": build_image_url(t.get("backdrop_path") or t.get("poster_path")),
            "url": f"https://www.themoviedb.org/tv/{t.get('id')}"
        })
    return combined

def get_detailed_info(media_type: str, media_id: int) -> Dict[str, Any]:
    d = tmdb_request(f"{media_type}/{media_id}")
    # genres as CSV
    genres = ", ".join(g.get("name") for g in d.get("genres", [])) or "Unknown"
    # runtime
    if media_type == "movie":
        runtime = d.get("runtime") or "Unknown"
    else:
        # tv
        ep_run = d.get("episode_run_time") or []
        runtime = f"{ep_run[0]} min" if ep_run else "Unknown"
    return {
        "genres": genres,
        "rating": float(d.get("vote_average") or 0.0),
        "votes": int(d.get("vote_count") or 0),
        "runtime": runtime,
        "imdb": d.get("imdb_id"),
        "status": d.get("status"),
        "production_companies": ", ".join(c.get("name") for c in d.get("production_companies", [])) or "Unknown",
        "spoken_languages": ", ".join(l.get("english_name") for l in d.get("spoken_languages", [])) or "Unknown",
        "overview": d.get("overview", "")
    }

# -------------------------
# Caption builders
# -------------------------
def build_post_caption(item: Dict, extra: Dict) -> str:
    imdb_part = f"<a href='https://www.imdb.com/title/{extra.get('imdb')}'>IMDb</a> | " if extra.get("imdb") else ""
    return (
        f"🎬 <b>{item['title']}</b>\n"
        f"📅 Release: <i>{item['release']}</i>\n"
        f"⭐ Rating: <b>{extra['rating']:.1f}</b> ({extra['votes']} votes)\n"
        f"🎭 Genres: {extra['genres']}\n"
        f"⏳ Runtime: {extra['runtime']}\n\n"
        f"📰 {item.get('overview','')[:600]}...\n\n"
        f"🔗 {imdb_part}<a href='{item['url']}'>TMDb</a>"
    )

# -------------------------
# Posting loop & weekly summary
# -------------------------
async def post_weekly_summary():
    weekly = tmdb_request("trending/all/week").get("results", [])[:10]
    if not weekly:
        logging.info("No weekly trending results.")
        return
    text = "📅 <b>Weekly Trending Movies & Series</b>\n\n"
    for w in weekly:
        title = w.get("title") or w.get("name")
        rating = float(w.get("vote_average") or 0.0)
        text += f"🎬 <b>{title}</b> — ⭐ {rating:.1f}\n"
    try:
        await app.send_message(CHANNEL_ID, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Failed to send weekly summary: {e}")

async def post_new_items_once():
    """Check trending and post items not yet posted. Posts 1 item every POST_DELAY seconds."""
    items = get_trending_all_day()
    new_items = [i for i in items if i.get("title") and i["title"] not in posted_titles]

    if not new_items:
        logging.info("No new items found to post.")
        return

    for item in new_items:
        extra = get_detailed_info(item["type"], item["id"])
        caption = build_post_caption(item, extra)
        try:
            await app.send_photo(CHANNEL_ID, item["poster"] or None, caption=caption, parse_mode=ParseMode.HTML)
            add_posted(item["title"])
            logging.info(f"Posted: {item['title']}")
        except Exception as e:
            logging.error(f"Failed to post {item.get('title')}: {e}")
        await asyncio.sleep(POST_DELAY)

async def auto_loop():
    logging.info("Auto loop started")
    while True:
        now = datetime.utcnow()
        # Weekly Sunday 09:00 UTC
        try:
            if now.weekday() == 6 and now.hour == 9:
                logging.info("Posting weekly summary (auto).")
                await post_weekly_summary()
        except Exception as e:
            logging.error(f"Weekly check error: {e}")

        if not PAUSED:
            try:
                await post_new_items_once()
            except Exception as e:
                logging.error(f"Error in post_new_items_once: {e}")
        else:
            logging.info("Posting is currently paused by admin.")

        await asyncio.sleep(CHECK_INTERVAL)

# -------------------------
# Admin helper decorator
# -------------------------
def is_admin_user(user_id: int) -> bool:
    return user_id in ADMINS

def admin_only_handler(func):
    async def wrapper(client, message):
        if not message.from_user:
            return  # ignore non-user events
        if not is_admin_user(message.from_user.id):
            await message.reply("❌ You are not authorized to use this command.")
            return
        await func(client, message)
    return wrapper


# -------------------------
# /search (PM only)
# -------------------------
@app.on_message(filters.command("search") & filters.private)
async def search_cmd(_, msg):
    query = " ".join(msg.command[1:]).strip()
    if not query:
        await msg.reply("❗ Usage: <b>/search Movie or Series Name</b>", parse_mode=ParseMode.HTML)
        return

    results = tmdb_request("search/multi", {"query": query}).get("results", [])
    if not results:
        await msg.reply("❌ No results found.", parse_mode=ParseMode.HTML)
        return

    # take first result as the primary result
    result = results[0]
    media_type = result.get("media_type")
    media_id = result.get("id")
    details = tmdb_request(f"{media_type}/{media_id}")

    title = details.get("title") or details.get("name", "Unknown")
    release = details.get("release_date") or details.get("first_air_date") or "Unknown"
    genres = ", ".join(g.get("name") for g in details.get("genres", [])) or "Unknown"
    languages = ", ".join(l.get("english_name") for l in details.get("spoken_languages", [])) or "Unknown"
    prod_companies = ", ".join(c.get("name") for c in details.get("production_companies", [])) or "Unknown"
    status = details.get("status", "Unknown")
    imdb = details.get("imdb_id")
    rating = float(details.get("vote_average") or 0.0)
    votes = int(details.get("vote_count") or 0)
    runtime = details.get("runtime") or (str(details.get("number_of_episodes")) + " eps" if details.get("number_of_episodes") else "Unknown")
    overview = details.get("overview", "No overview available.")
    poster_path = details.get("poster_path") or details.get("backdrop_path")
    poster_url = build_image_url(poster_path) if poster_path else None

    text = (
        f"🎬 <b>{title}</b>\n"
        f"📅 <b>Release:</b> {release}\n"
        f"⭐ <b>Rating:</b> {rating:.1f} ({votes} votes)\n"
        f"🎭 <b>Genres:</b> {genres}\n"
        f"🌍 <b>Languages:</b> {languages}\n"
        f"🏢 <b>Studios:</b> {prod_companies}\n"
        f"📌 <b>Status:</b> {status}\n"
        f"⏳ <b>Runtime / Episodes:</b> {runtime}\n\n"
        f"📝 <b>Overview:</b>\n{overview[:1500]}\n\n"
        f"🔗 <b>Links:</b>\n"
        f"TMDb: https://www.themoviedb.org/{media_type}/{media_id}\n"
        f"{('IMDb: https://www.imdb.com/title/' + imdb) if imdb else ''}"
    )

    try:
        if poster_url:
            await msg.reply_photo(poster_url, caption=text, parse_mode=ParseMode.HTML)
        else:
            await msg.reply(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Failed to send search result: {e}")
        await msg.reply(text, parse_mode=ParseMode.HTML)

# -------------------------
# /poster command (PM & groups) - builds paginated inline list
# -------------------------
# Pagination constants
PAGE_SIZE = 10
MAX_RESULTS = 100  # cap search results to avoid huge lists

def chunk_list(lst: List, size: int) -> List[List]:
    return [lst[i:i+size] for i in range(0, len(lst), size)]

def build_results_keyboard(results: List[Dict], query: str, page: int) -> InlineKeyboardMarkup:
    # results is a list of result dicts (each has id, type, title, year, rating)
    pages = chunk_list(results, PAGE_SIZE)
    total_pages = len(pages)
    page = max(0, min(page, total_pages - 1))
    page_items = pages[page]

    buttons = []
    for r in page_items:
        # label style (Option B earlier choice for page header; for title buttons we use C - include type and rating)
        label = f"{r['title']} ({r.get('year','?')}) — {r['type'].upper()} — ⭐ {r.get('rating',0):.1f}"
        cb = f"poster_select|{r['type']}|{r['id']}|{r['title'].replace('|',' ')}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])

    # navigation row
    nav_buttons = []
    if total_pages > 1 and page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ PREV", callback_data=f"poster_page|{query}|{page-1}"))
    if total_pages > 1 and page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("NEXT ➡️", callback_data=f"poster_page|{query}|{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("poster"))
async def poster_cmd(_, msg):
    # Accept in PM and groups; if group, user must provide query
    query = " ".join(msg.command[1:]).strip()
    if not query:
        await msg.reply("❗ Usage: <b>/poster Movie or Series Name</b>", parse_mode=ParseMode.HTML)
        return

    # perform TMDb multi search
    res = tmdb_request("search/multi", {"query": query, "page": 1})
    results = res.get("results", [])[:MAX_RESULTS]
    if not results:
        await msg.reply(f"❌ No results found for <b>{query}</b>.", parse_mode=ParseMode.HTML)
        return

    # normalize results to needed fields
    normalized = []
    for r in results:
        media_type = r.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        title = r.get("title") or r.get("name") or "Unknown"
        # extract year
        year = (r.get("release_date") or r.get("first_air_date") or "")[:4]
        rating = float(r.get("vote_average") or 0.0)
        normalized.append({
            "id": r.get("id"),
            "type": media_type,
            "title": title,
            "year": year,
            "rating": rating
        })

    if not normalized:
        await msg.reply(f"❌ No movie/series results found for <b>{query}</b>.", parse_mode=ParseMode.HTML)
        return

    # show first page
    page = 0
    keyboard = build_results_keyboard(normalized, query.replace("|"," "), page)
    header = f"🔍 <b>Results for:</b> <i>{query}</i>\n📄 <b>Page {page+1} / {((len(normalized)-1)//PAGE_SIZE)+1}</b>"
    await msg.reply(header, reply_markup=keyboard, parse_mode=ParseMode.HTML)

# -------------------------
# Callback query handler for /poster
# -------------------------
@app.on_callback_query()
async def poster_callback(client: Client, cq: CallbackQuery):
    data = cq.data or ""
    # poster_select|type|id|title
    # poster_page|query|page
    try:
        if data.startswith("poster_page|"):
            # navigation pressed
            parts = data.split("|", 2)
            if len(parts) < 3:
                await cq.answer("Invalid data", show_alert=True)
                return
            _, query, page_str = parts
            page = int(page_str)
            # re-run search to rebuild keyboard (we could cache results but keep simple)
            res = tmdb_request("search/multi", {"query": query, "page": 1})
            results = res.get("results", [])[:MAX_RESULTS]
            normalized = []
            for r in results:
                media_type = r.get("media_type")
                if media_type not in ("movie", "tv"):
                    continue
                title = r.get("title") or r.get("name") or "Unknown"
                year = (r.get("release_date") or r.get("first_air_date") or "")[:4]
                rating = float(r.get("vote_average") or 0.0)
                normalized.append({
                    "id": r.get("id"),
                    "type": media_type,
                    "title": title,
                    "year": year,
                    "rating": rating
                })
            if not normalized:
                await cq.answer("No results.", show_alert=True)
                return
            keyboard = build_results_keyboard(normalized, query.replace("|"," "), page)
            total_pages = ((len(normalized)-1)//PAGE_SIZE)+1
            header = f"🔍 <b>Results for:</b> <i>{query}</i>\n📄 <b>Page {page+1} / {total_pages}</b>"
            try:
                await cq.message.edit_text(header, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                await cq.answer()
            except Exception as e:
                logging.error(f"Failed to edit page message: {e}")
                await cq.answer("Failed to change page", show_alert=True)
            return

        if data.startswith("poster_select|"):
            parts = data.split("|", 3)
            if len(parts) < 4:
                await cq.answer("Invalid selection", show_alert=True)
                return
            _, media_type, media_id_str, title = parts
            media_id = int(media_id_str)
            query_title = title

            # Edit original reply to "Finding posters..."
            try:
                await cq.message.edit_text(f"⏳ Finding posters for <b>{query_title}</b>...", parse_mode=ParseMode.HTML)
            except Exception:
                # sometimes callback message can't be edited (channel etc)
                pass
            await cq.answer()  # remove loading spinner

            # fetch images
            images = tmdb_request(f"{media_type}/{media_id}/images")
            posters = images.get("posters", []) or []
            backdrops = images.get("backdrops", []) or []

            # official poster: the first poster that has 'iso_639_1' == 'en' or else first overall
            official_poster = None
            for p in posters:
                if p.get("iso_639_1") == "en" and p.get("vote_count", 0) >= 0:
                    official_poster = p
                    break
            if not official_poster and posters:
                official_poster = posters[0]

            # build lists limited to 30 each
            portrait_list = [build_image_url(p.get("file_path"), "w780") for p in posters][:30]
            landscape_list = [build_image_url(b.get("file_path"), "w1280") for b in backdrops][:30]
            official_url = build_image_url(official_poster.get("file_path")) if official_poster else ""

            # Build final message (Option B aesthetics)
            title_link = query_title
            imdb_id = None
            try:
                details = tmdb_request(f"{media_type}/{media_id}")
                imdb_id = details.get("imdb_id")
                title_link = details.get("title") or details.get("name") or query_title
            except Exception:
                pass

            text_lines = []
            text_lines.append(f"🎬 <b>{title_link}</b>\n")
            # Official poster
            if official_url:
                text_lines.append("🎞 <b>Official Poster</b>\n")
                text_lines.append(f"👉 <a href=\"{official_url}\">Get Now</a>\n")
            else:
                text_lines.append("🎞 <b>Official Poster</b>\nNo official poster found.\n")

            # Landscape posters
            text_lines.append("\n🏞 <b>Landscape Posters</b>\n")
            if landscape_list:
                for i, url in enumerate(landscape_list, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get Now</a>\n")
            else:
                text_lines.append("No landscape posters found.\n")

            # Portrait posters
            text_lines.append("\n🖼 <b>Portrait Posters</b>\n")
            if portrait_list:
                for i, url in enumerate(portrait_list, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get Now</a>\n")
            else:
                text_lines.append("No portrait posters found.\n")

            # Add TMDb / IMDb links
            tmdb_link = f"https://www.themoviedb.org/{media_type}/{media_id}"
            links_line = f"\n🔗 <a href=\"{tmdb_link}\">TMDb</a>"
            if imdb_id:
                links_line += f" | <a href=\"https://www.imdb.com/title/{imdb_id}\">IMDb</a>"
            text_lines.append(links_line)

            full_text = "\n".join(text_lines)

            # Telegram has message length limits — trim if necessary
            if len(full_text) > 4000:
                # trim lists progressively to fit
                logging.warning("Poster message too long, trimming lists to fit message size.")
                # rebuild with smaller lists
                # try limiting to 10 each
                portrait_list_small = portrait_list[:10]
                landscape_list_small = landscape_list[:10]
                text_lines = []
                text_lines.append(f"🎬 <b>{title_link}</b>\n")
                if official_url:
                    text_lines.append("🎞 <b>Official Poster</b>\n")
                    text_lines.append(f"👉 <a href=\"{official_url}\">Get Now</a>\n")
                else:
                    text_lines.append("🎞 <b>Official Poster</b>\nNo official poster found.\n")
                text_lines.append("\n🏞 <b>Landscape Posters</b>\n")
                for i, url in enumerate(landscape_list_small, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get Now</a>\n")
                text_lines.append("\n🖼 <b>Portrait Posters</b>\n")
                for i, url in enumerate(portrait_list_small, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get Now</a>\n")
                text_lines.append(links_line)
                full_text = "\n".join(text_lines)
                # if still too long, further trim to 5 each
                if len(full_text) > 4000:
                    portrait_list_small = portrait_list_small[:5]
                    landscape_list_small = landscape_list_small[:5]
                    text_lines = []
                    text_lines.append(f"🎬 <b>{title_link}</b>\n")
                    if official_url:
                        text_lines.append("🎞 <b>Official Poster</b>\n")
                        text_lines.append(f"👉 <a href=\"{official_url}\">Get Now</a>\n")
                    text_lines.append("\n🏞 <b>Landscape Posters</b>\n")
                    for i, url in enumerate(landscape_list_small, start=1):
                        text_lines.append(f"{i}. <a href=\"{url}\">Get Now</a>\n")
                    text_lines.append("\n🖼 <b>Portrait Posters</b>\n")
                    for i, url in enumerate(portrait_list_small, start=1):
                        text_lines.append(f"{i}. <a href=\"{url}\">Get Now</a>\n")
                    text_lines.append(links_line)
                    full_text = "\n".join(text_lines)

            # Now edit the original message (or reply if editing fails)
            try:
                await cq.message.edit_text(full_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                logging.error(f"Failed to edit with posters: {e}")
                # fallback: send a new message
                try:
                    await cq.message.reply_text(full_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception as ex:
                    logging.error(f"Fallback send failed: {ex}")
            return

    except Exception as e:
        logging.error(f"Error in poster_callback: {e}")
        try:
            await cq.answer("An error occurred.", show_alert=True)
        except Exception:
            pass

@app.on_message(filters.command("pause") & filters.private)
@admin_only_handler
async def pause_cmd(_, msg):
    set_paused(True)
    await msg.reply("⏸️ Auto-posting has been <b>paused</b>.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("resume") & filters.private)
@admin_only_handler
async def resume_cmd(_, msg):
    set_paused(False)
    await msg.reply("▶️ Auto-posting has <b>resumed</b>.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("weekly") & filters.private)
@admin_only_handler
async def manual_weekly(_, msg):
    await msg.reply("Posting weekly trending now...", parse_mode=ParseMode.HTML)
    await post_weekly_summary()
    await msg.reply("Done.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("checknew") & filters.private)
@admin_only_handler
async def manual_checknew(_, msg):
    await msg.reply("Checking for new releases now...", parse_mode=ParseMode.HTML)
    await post_new_items_once()
    await msg.reply("Done.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("status") & filters.private)
@admin_only_handler
async def status_cmd(_, msg):
    total = len(posted_titles)
    paused_txt = "Yes" if PAUSED else "No"
    await msg.reply(f"📊 Status:\nPosted items: {total}\nPaused: {paused_txt}", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("start") & ~filters.private)
async def start_group(_, msg):
    await msg.reply("🎬 I can provide movie/series info and posters. Use /poster <name> or message me in private for /search.", parse_mode=ParseMode.HTML)

if __name__ == "__main__":
    logging.info("Starting Movie News Bot...")
    app.start()
    loop = asyncio.get_event_loop()
    loop.create_task(auto_loop())
    try:
        logging.info("Bot is running. Press Ctrl+C to stop.")
        loop.run_forever()
    finally:
        app.stop()
        logging.info("Bot stopped.")
