from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services import app, utils, db

@app.on_message(filters.command("poster"))
async def poster(_, m):
    query = " ".join(m.command[1:])
    if not query:
        return await m.reply("Usage: /poster <name>")
    results = await utils.search_and_cache(db, query)
    if not results:
        return await m.reply("No results found.")
    buttons = []
    for r in results[:10]:
        link = f"https://www.themoviedb.org/{r['type']}/{r['id']}"
        buttons.append([InlineKeyboardButton(f"{r['title']} ({r['year']})", url=link)])
    await m.reply_text(f"🎬 Posters for <b>{query}</b>:", reply_markup=InlineKeyboardMarkup(buttons))
