import uuid, time
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from services import app, db, utils

@app.on_message(filters.command("search"))
async def search(_, m):
    query = " ".join(m.command[1:])
    if not query:
        return await m.reply("Usage: /search <movie or series name>")
    results = await utils.search_and_cache(db, query)
    if not results:
        return await m.reply("No results found.")
    sid = uuid.uuid4().hex
    await db.search_cache.update_one({"_id": sid}, {"$set": {"results": results, "created_at": int(time.time())}}, upsert=True)
    buttons = [
        [InlineKeyboardButton(f"{r['title']} ({r['year']})", callback_data=f"s_sel|{sid}|{r['type']}|{r['id']}")]
        for r in results[:10]
    ]
    await m.reply_text(f"🔍 Results for <b>{query}</b>:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query()
async def callback(_, q):
    data = q.data
    if data.startswith("s_sel|"):
        _, sid, mtype, mid = data.split("|")
        row = await db.search_cache.find_one({"_id": sid})
        if not row:
            return await q.answer("Expired search.")
        details = await utils.get_details_and_cache(db, mtype, int(mid))
        title = details.get("title") or details.get("name")
        caption = f"🎬 <b>{title}</b>\n⭐ {details.get('vote_average')} | ⏳ {details.get('runtime') or details.get('episode_run_time') or 'Unknown'}m\n\n{details.get('overview')}"
        tmdb = f"https://www.themoviedb.org/{mtype}/{mid}"
        imdb = details.get("imdb_id")
        btns = [[InlineKeyboardButton("TMDB", url=tmdb)]]
        if imdb:
            btns[0].append(InlineKeyboardButton("IMDb", url=f"https://www.imdb.com/title/{imdb}"))
        img = utils.build_image_url(details.get("poster_path"))
        if img:
            await q.message.reply_photo(img, caption=caption, reply_markup=InlineKeyboardMarkup(btns))
        else:
            await q.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(btns))
        await q.answer()
