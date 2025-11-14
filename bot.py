#V5
import os
import json
import logging
import asyncio
import requests
import uuid
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

# persistence files
POSTED_FILE = "posted.json"
STATE_FILE = "state.json"
SEARCH_CACHE_FILE = "search_cache.json"

# runtime settings
CHECK_INTERVAL = 120  # seconds (1 hour)
POST_DELAY = 10  # seconds between posting new items (per your request)
PAGE_SIZE = 10
MAX_SEARCH_RESULTS = 100

# -------------------------
# Pyrogram client
# -------------------------
app = Client("movie_news_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------
# Utilities for JSON persistence
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

# search cache: {search_id: [ {id,type,title,year,rating}, ... ] }
search_cache = load_json_file(SEARCH_CACHE_FILE, {})

def persist_posted():
    save_json_file(POSTED_FILE, list(posted_titles))

def persist_state():
    state["paused"] = PAUSED
    save_json_file(STATE_FILE, state)

def persist_search_cache():
    # keep cache small: trim entries older than some threshold or limit size (simple approach here)
    save_json_file(SEARCH_CACHE_FILE, search_cache)

def add_posted(title: str):
    posted_titles.add(title)
    persist_posted()

def set_paused(flag: bool):
    global PAUSED
    PAUSED = bool(flag)
    persist_state()

# -------------------------
# TMDb helpers
# -------------------------
TMDB_BASE = "https://api.themoviedb.org/3"

def tmdb_request(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
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

def search_tmdb_multi(query: str, max_results: int = MAX_SEARCH_RESULTS) -> List[Dict[str, Any]]:
    data = tmdb_request("search/multi", {"query": query, "page": 1})
    results = data.get("results", [])[:max_results]
    normalized = []
    for r in results:
        media_type = r.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        title = r.get("title") or r.get("name") or "Unknown"
        year = (r.get("release_date") or r.get("first_air_date") or "")[:4]
        rating = float(r.get("vote_average") or 0.0)
        normalized.append({
            "id": int(r.get("id")),
            "type": media_type,
            "title": title,
            "year": year,
            "rating": rating
        })
    return normalized

def get_trending_all_day() -> List[Dict[str, Any]]:
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

def get_details(media_type: str, media_id: int) -> Dict[str, Any]:
    d = tmdb_request(f"{media_type}/{media_id}")
    genres = ", ".join(g.get("name") for g in d.get("genres", [])) or "Unknown"
    # runtime
    if media_type == "movie":
        runtime = d.get("runtime") or "Unknown"
    else:
        ep_run = d.get("episode_run_time") or []
        runtime = f"{ep_run[0]} min" if ep_run else "Unknown"
    # main production company (first)
    companies = d.get("production_companies", []) or []
    main_company = companies[0].get("name") if companies else None
    return {
        "genres": genres,
        "rating": float(d.get("vote_average") or 0.0),
        "votes": int(d.get("vote_count") or 0),
        "runtime": runtime,
        "imdb": d.get("imdb_id"),
        "status": d.get("status"),
        "production_company": main_company,
        "spoken_languages": ", ".join(l.get("english_name") for l in d.get("spoken_languages", [])) or "Unknown",
        "overview": d.get("overview", ""),
        "number_of_seasons": d.get("number_of_seasons"),
        "number_of_episodes": d.get("number_of_episodes"),
        "poster_path": d.get("poster_path") or d.get("backdrop_path")
    }

# -------------------------
# Caption builders & post formatting
# -------------------------
def build_post_caption(item: Dict[str, Any], extra: Dict[str, Any]) -> str:
    imdb_link = f"<a href='https://www.imdb.com/title/{extra.get('imdb')}'>IMDb</a> | " if extra.get("imdb") else ""
    return (
        f"🎬 <b>{item['title']}</b>\n"
        f"📅 Release: <i>{item['release']}</i>\n"
        f"⭐ Rating: <b>{extra['rating']:.1f}</b> ({extra['votes']} votes)\n"
        f"🎭 Genres: {extra['genres']}\n"
        f"⏳ Duration: {extra['runtime']}\n\n"
        f"📰 {item.get('overview','')[:600]}...\n\n"
        f"🔗 {imdb_link}<a href='{item['url']}'>TMDb</a>"
    )

# -------------------------
# Posting loop (respects PAUSED)
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
    items = get_trending_all_day()
    new_items = [i for i in items if i.get("title") and i["title"] not in posted_titles]

    if not new_items:
        logging.info("No new items to post.")
        return

    for item in new_items:
        # respect pause every iteration
        if PAUSED:
            logging.info("Posting paused; halting posting loop.")
            return

        extra = get_details(item["type"], item["id"])
        caption = build_post_caption(item, extra)
        try:
            # send poster image if available, else send message only
            poster = item.get("poster") or (build_image_url(extra.get("poster_path")) if extra.get("poster_path") else None)
            if poster:
                await app.send_photo(CHANNEL_ID, poster, caption=caption, parse_mode=ParseMode.HTML)
            else:
                await app.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.HTML)
            add_posted(item["title"])
            logging.info(f"Posted: {item['title']}")
        except Exception as e:
            logging.error(f"Failed to post {item.get('title')}: {e}")
        # delay between posts
        await asyncio.sleep(POST_DELAY)

async def auto_loop():
    logging.info("Auto loop started")
    while True:
        now = datetime.utcnow()
        try:
            # Weekly Sunday 09:00 UTC
            if now.weekday() == 6 and now.hour == 9:
                logging.info("Posting weekly summary (auto).")
                if not PAUSED:
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
# Admin helper
# -------------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def admin_only(func):
    async def wrapper(client, message):
        if not message.from_user:
            return
        if not is_admin(message.from_user.id):
            await message.reply("❌ You are not authorized to use this command.")
            return
        await func(client, message)
    return wrapper

# -------------------------
# /start handlers
# -------------------------
@app.on_message(filters.command("start") & filters.private)
async def start_private(_, msg):
    await msg.reply(
        "🎬 <b>Welcome!</b>\n\n"
        "I'm a Movie & Series Info Bot powered by TMDb.\n\n"
        "Commands:\n"
        "• <b>/search Movie or Series Name</b> — (private) search & get full details (paginated)\n"
        "• <b>/poster Name</b> — (pm & groups) find posters/backdrops (paginated)\n\n"
        "Admins: /pause /resume /weekly /checknew /status\n\nEnjoy! 🍿",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("start") & ~filters.private)
async def start_group(_, msg):
    await msg.reply("🎬 Use /poster <name> here, or message me privately for /search.", parse_mode=ParseMode.HTML)

# -------------------------
# Search command (PM only) with pagination + cached search_id
# -------------------------
def chunk_list(lst: List, size: int) -> List[List]:
    return [lst[i:i+size] for i in range(0, len(lst), size)]

def build_results_keyboard_from_cache(results: List[Dict[str, Any]], search_id: str, page: int) -> InlineKeyboardMarkup:
    pages = chunk_list(results, PAGE_SIZE)
    total_pages = len(pages)
    page = max(0, min(page, total_pages - 1))
    page_items = pages[page]
    buttons = []
    for r in page_items:
        label = f"{r['title']} ({r.get('year','?')})"
        cb = f"s_sel|{search_id}|{r['type']}|{r['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])
    nav_buttons = []
    if total_pages > 1 and page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ PREV", callback_data=f"s_pg|{search_id}|{page-1}"))
    if total_pages > 1 and page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("NEXT ➡️", callback_data=f"s_pg|{search_id}|{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    # Add TMDB or IMDB buttons not needed here — they appear after user selects a result
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("search") & filters.private)
async def search_cmd(_, msg):
    query = " ".join(msg.command[1:]).strip()
    if not query:
        await msg.reply("❗ Usage: <b>/search Movie or Series Name</b>", parse_mode=ParseMode.HTML)
        return

    normalized = search_tmdb_multi(query)
    if not normalized:
        await msg.reply(f"❌ No results found for <b>{query}</b>.", parse_mode=ParseMode.HTML)
        return

    # create a search_id and cache results
    search_id = uuid.uuid4().hex[:32]
    search_cache[search_id] = normalized
    persist_search_cache()

    page = 0
    keyboard = build_results_keyboard_from_cache(normalized, search_id, page)
    header = f"🔍 <b>Results for:</b> <i>{query}</i>\n📄 <b>Page {page+1} / {((len(normalized)-1)//PAGE_SIZE)+1}</b>"
    await msg.reply(header, reply_markup=keyboard, parse_mode=ParseMode.HTML)

# -------------------------
# /poster command (PM & groups) - behaves similarly with caching for pagination
# -------------------------
def build_results_keyboard_for_poster(results: List[Dict[str, Any]], search_id: str, page: int) -> InlineKeyboardMarkup:
    # reuse same format but label includes type & rating as you chose earlier? You selected Q1=A (Title (Year) header style),
    # but earlier asked title buttons to include rating/type in prior conversation; we'll show Title (Year) here to keep clean.
    pages = chunk_list(results, PAGE_SIZE)
    total_pages = len(pages)
    page = max(0, min(page, total_pages - 1))
    page_items = pages[page]
    buttons = []
    for r in page_items:
        label = f"{r['title']} ({r.get('year','?')})"
        cb = f"p_sel|{search_id}|{r['type']}|{r['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])
    nav_buttons = []
    if total_pages > 1 and page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ PREV", callback_data=f"p_pg|{search_id}|{page-1}"))
    if total_pages > 1 and page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("NEXT ➡️", callback_data=f"p_pg|{search_id}|{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    return InlineKeyboardMarkup(buttons)

@app.on_message(filters.command("poster"))
async def poster_cmd(_, msg):
    query = " ".join(msg.command[1:]).strip()
    if not query:
        await msg.reply("❗ Usage: <b>/poster Movie or Series Name</b>", parse_mode=ParseMode.HTML)
        return

    normalized = search_tmdb_multi(query)
    if not normalized:
        await msg.reply(f"❌ No results found for <b>{query}</b>.", parse_mode=ParseMode.HTML)
        return

    search_id = uuid.uuid4().hex[:32]
    search_cache[search_id] = normalized
    persist_search_cache()

    page = 0
    keyboard = build_results_keyboard_for_poster(normalized, search_id, page)
    header = f"🔍 <b>Results for:</b> <i>{query}</i>\n📄 <b>Page {page+1} / {((len(normalized)-1)//PAGE_SIZE)+1}</b>"
    await msg.reply(header, reply_markup=keyboard, parse_mode=ParseMode.HTML)

# -------------------------
# Callback handler (pagination & selection) for both search & poster
# -------------------------
@app.on_callback_query()
async def callback_router(client: Client, cq: CallbackQuery):
    data = cq.data or ""
    try:
        # Search pagination: s_pg|searchid|page
        if data.startswith("s_pg|"):
            _, search_id, page_str = data.split("|", 2)
            page = int(page_str)
            results = search_cache.get(search_id)
            if not results:
                await cq.answer("Search expired. Please run the search again.", show_alert=True)
                return
            keyboard = build_results_keyboard_from_cache(results, search_id, page)
            total_pages = ((len(results)-1)//PAGE_SIZE) + 1
            header = f"🔍 <b>Results</b>\n📄 <b>Page {page+1} / {total_pages}</b>"
            await cq.message.edit_text(header, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            await cq.answer()
            return

        # Search selection: s_sel|searchid|type|id
        if data.startswith("s_sel|"):
            _, search_id, mtype, mid = data.split("|", 3)
            results = search_cache.get(search_id)
            if not results:
                await cq.answer("Search expired. Please run the search again.", show_alert=True)
                return
            # find item info (optional)
            # edit message to show finding...
            await cq.message.edit_text("⏳ Fetching details, please wait...", parse_mode=ParseMode.HTML)
            await cq.answer()
            mid_int = int(mid)
            details = get_details(mtype, mid_int)
            title = ""
            try:
                d_full = tmdb_request(f"{mtype}/{mid_int}")
                title = d_full.get("title") or d_full.get("name") or ""
            except Exception:
                title = ""
            poster_path = details.get("poster_path")
            poster_url = build_image_url(poster_path) if poster_path else None

            # build detailed message per your Q2=A preference (but limited: main studio only, no producers, no networks)
            lines = []
            lines.append(f"🎬 <b>{title or 'Title'}</b>")
            if mtype == "movie":
                lines.append(f"📅 <b>Release:</b> {d_full.get('release_date') or 'Unknown'}")
                lines.append(f"⏳ <b>Duration:</b> {details.get('runtime')}")
            else:
                lines.append(f"📅 <b>First Air:</b> {d_full.get('first_air_date') or 'Unknown'}")
                # seasons & episodes
                if details.get("number_of_seasons") is not None:
                    lines.append(f"📺 <b>Seasons:</b> {details.get('number_of_seasons')}")
                if details.get("number_of_episodes") is not None:
                    lines.append(f"🔢 <b>Episodes:</b> {details.get('number_of_episodes')}")
                lines.append(f"⏳ <b>Episode duration:</b> {details.get('runtime')}")
            lines.append(f"⭐ <b>Rating:</b> {details.get('rating'):.1f} ({details.get('votes')} votes)")
            lines.append(f"🎭 <b>Genres:</b> {details.get('genres')}")
            if details.get("production_company"):
                lines.append(f"🏢 <b>Studio:</b> {details.get('production_company')}")
            lines.append(f"🌍 <b>Languages:</b> {details.get('spoken_languages')}")
            lines.append("\n📝 <b>Overview:</b>")
            lines.append(details.get("overview") or "No overview available.")
            # build footer buttons: TMDB & IMDb (if available)
            tmdb_link = f"https://www.themoviedb.org/{mtype}/{mid}"
            imdb_id = details.get("imdb")
            buttons = [InlineKeyboardButton("TMDB", url=tmdb_link)]
            if imdb_id:
                buttons.append(InlineKeyboardButton("IMDb", url=f"https://www.imdb.com/title/{imdb_id}"))
            markup = InlineKeyboardMarkup([buttons])

            text = "\n".join(lines)[:3900]  # safety
            try:
                if poster_url:
                    # send poster photo with caption, buttons
                    await cq.message.reply_photo(poster_url, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
                else:
                    await cq.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
                # edit the original inline message back to a small "Completed" note or delete to reduce clutter
                try:
                    await cq.message.edit_text(f"✅ Sent details for: <b>{title}</b>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            except Exception as e:
                logging.error(f"Failed to send search detail: {e}")
                await cq.answer("Failed to send details.", show_alert=True)
            return

        # Poster pagination: p_pg|searchid|page
        if data.startswith("p_pg|"):
            _, search_id, page_str = data.split("|", 2)
            page = int(page_str)
            results = search_cache.get(search_id)
            if not results:
                await cq.answer("Search expired. Please run the /poster again.", show_alert=True)
                return
            keyboard = build_results_keyboard_for_poster(results, search_id, page)
            total_pages = ((len(results)-1)//PAGE_SIZE) + 1
            header = f"🔍 <b>Results</b>\n📄 <b>Page {page+1} / {total_pages}</b>"
            try:
                await cq.message.edit_text(header, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                await cq.answer()
            except Exception as e:
                logging.error(f"Failed to edit poster page: {e}")
                await cq.answer("Failed to change page.", show_alert=True)
            return

        # Poster selection: p_sel|searchid|type|id
        if data.startswith("p_sel|"):
            _, search_id, mtype, mid = data.split("|", 3)
            results = search_cache.get(search_id)
            if not results:
                await cq.answer("Search expired. Please run the /poster again.", show_alert=True)
                return
            # attempt to get title from TMDb details, but show the user's chosen label as fallback
            mid_int = int(mid)
            # edit to "Finding posters..." on original message
            try:
                await cq.message.edit_text("⏳ Finding posters... Please wait.", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            await cq.answer()
            images = tmdb_request(f"{mtype}/{mid_int}/images")
            posters = images.get("posters", []) or []
            backdrops = images.get("backdrops", []) or []

            # official poster: prefer english iso if available, else first
            official = None
            for p in posters:
                if p.get("iso_639_1") == "en":
                    official = p
                    break
            if not official and posters:
                official = posters[0]
            official_url = build_image_url(official.get("file_path"), "original") if official else ""

            portrait_list = [build_image_url(p.get("file_path"), "w780") for p in posters][:30]
            landscape_list = [build_image_url(b.get("file_path"), "w1280") for b in backdrops][:30]

            # Build final HTML message (Option B aesthetic you chose)
            title = ""
            try:
                details_full = tmdb_request(f"{mtype}/{mid_int}")
                title = details_full.get("title") or details_full.get("name") or ""
                imdb_id = details_full.get("imdb_id")
            except Exception:
                imdb_id = None

            text_lines = []
            text_lines.append(f"🎬 <b>{title or 'Title'}</b>\n")
            if official_url:
                text_lines.append("🎞 <b>Official Poster</b>\n")
                text_lines.append(f"👉 <a href=\"{official_url}\">Get now</a>\n")
            else:
                text_lines.append("🎞 <b>Official Poster</b>\nNo official poster found.\n")

            text_lines.append("\n🏞 <b>Landscape Posters</b>\n")
            if landscape_list:
                for i, url in enumerate(landscape_list, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get now</a>\n")
            else:
                text_lines.append("No landscape posters found.\n")

            text_lines.append("\n🖼 <b>Portrait Posters</b>\n")
            if portrait_list:
                for i, url in enumerate(portrait_list, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get now</a>\n")
            else:
                text_lines.append("No portrait posters found.\n")

            # append links
            tmdb_link = f"https://www.themoviedb.org/{mtype}/{mid_int}"
            links = f"\n🔗 <a href=\"{tmdb_link}\">TMDb</a>"
            if imdb_id:
                links += f" | <a href=\"https://www.imdb.com/title/{imdb_id}\">IMDb</a>"
            text_lines.append(links)

            full_text = "\n".join(text_lines)

            # Trim if exceeds size (try to keep as much as possible)
            if len(full_text) > 4000:
                logging.warning("Poster message too long; trimming lists.")
                # reduce to 10 each
                portrait_list = portrait_list[:10]
                landscape_list = landscape_list[:10]
                text_lines = []
                text_lines.append(f"🎬 <b>{title or 'Title'}</b>\n")
                if official_url:
                    text_lines.append("🎞 <b>Official Poster</b>\n")
                    text_lines.append(f"👉 <a href=\"{official_url}\">Get now</a>\n")
                text_lines.append("\n🏞 <b>Landscape Posters</b>\n")
                for i, url in enumerate(landscape_list, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get now</a>\n")
                text_lines.append("\n🖼 <b>Portrait Posters</b>\n")
                for i, url in enumerate(portrait_list, start=1):
                    text_lines.append(f"{i}. <a href=\"{url}\">Get now</a>\n")
                text_lines.append(links)
                full_text = "\n".join(text_lines)
                if len(full_text) > 4000:
                    # further trim to 5 each
                    portrait_list = portrait_list[:5]
                    landscape_list = landscape_list[:5]
                    text_lines = []
                    text_lines.append(f"🎬 <b>{title or 'Title'}</b>\n")
                    if official_url:
                        text_lines.append("🎞 <b>Official Poster</b>\n")
                        text_lines.append(f"👉 <a href=\"{official_url}\">Get now</a>\n")
                    text_lines.append("\n🏞 <b>Landscape Posters</b>\n")
                    for i, url in enumerate(landscape_list, start=1):
                        text_lines.append(f"{i}. <a href=\"{url}\">Get now</a>\n")
                    text_lines.append("\n🖼 <b>Portrait Posters</b>\n")
                    for i, url in enumerate(portrait_list, start=1):
                        text_lines.append(f"{i}. <a href=\"{url}\">Get now</a>\n")
                    text_lines.append(links)
                    full_text = "\n".join(text_lines)

            # Attempt to edit original message with final text
            try:
                await cq.message.edit_text(full_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                logging.error(f"Failed to edit original message with posters: {e}")
                try:
                    await cq.message.reply_text(full_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception as ex:
                    logging.error(f"Failed to fallback send poster message: {ex}")
            return

    except Exception as e:
        logging.error(f"Unhandled exception in callback handler: {e}")
        try:
            await cq.answer("An error occurred.", show_alert=True)
        except Exception:
            pass

# -------------------------
# Admin commands (private only)
# -------------------------
@app.on_message(filters.command("pause") & filters.private)
@admin_only
async def cmd_pause(_, msg):
    set_paused(True)
    await msg.reply("⏸️ Auto-posting paused.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("resume") & filters.private)
@admin_only
async def cmd_resume(_, msg):
    set_paused(False)
    await msg.reply("▶️ Auto-posting resumed.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("weekly") & filters.private)
@admin_only
async def cmd_weekly(_, msg):
    await msg.reply("Posting weekly trending now...", parse_mode=ParseMode.HTML)
    await post_weekly_summary()
    await msg.reply("Done.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("checknew") & filters.private)
@admin_only
async def cmd_checknew(_, msg):
    await msg.reply("Checking for new releases now...", parse_mode=ParseMode.HTML)
    await post_new_items_once()
    await msg.reply("Done.", parse_mode=ParseMode.HTML)

@app.on_message(filters.command("status") & filters.private)
@admin_only
async def cmd_status(_, msg):
    total = len(posted_titles)
    paused_txt = "Yes" if PAUSED else "No"
    await msg.reply(f"📊 Status:\nPosted items: {total}\nPaused: {paused_txt}", parse_mode=ParseMode.HTML)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    logging.info("Starting Movie News Bot (final)...")
    # ensure persisted files exist
    persist_posted()
    persist_state()
    persist_search_cache()
    app.start()
    loop = asyncio.get_event_loop()
    # start background auto loop
    loop.create_task(auto_loop())
    try:
        loop.run_forever()
    finally:
        app.stop()
        logging.info("Bot stopped.")
