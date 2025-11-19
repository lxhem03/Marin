from pyrogram import filters
from services import app

@app.on_message(filters.command("start"))
async def start(_, m):
    await m.reply_text("👋 Welcome to TMDB Bot!\nUse /search <movie/series name> to find info.\nUse /poster <name> to get posters.")
