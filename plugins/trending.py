import asyncio
from services import app, db, utils
from config import CHANNEL_ID, TREND_TAGS
import logging

log = logging.getLogger("TMDBBot")

async def post_trending():
    while True:
        trending = await utils.get_trending_and_cache(db)
        for item in trending[:5]:
            title = item.get("title") or item.get("name")
            overview = item.get("overview") or "No description."
            caption = f"🔥 <b>{title}</b>\n\n{overview[:400]}...\n\n{TREND_TAGS}"
            img = utils.build_image_url(item.get("poster_path"))
            try:
                await app.send_photo(CHANNEL_ID, img, caption=caption)
                log.info(f"Posted trending: {title}")
                await asyncio.sleep(5)
            except Exception as e:
                log.error(f"Failed to post {title}: {e}")
        await asyncio.sleep(3600)

@app.on_message()
async def start_trending(_, __):
    asyncio.create_task(post_trending())
