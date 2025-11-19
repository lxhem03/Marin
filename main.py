import logging, asyncio
from pyrogram import Client
from config import *
from database.mongo import Database
import utils, importlib
from pathlib import Path

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
log = logging.getLogger("TMDBBot")

# Initialize app
app = Client("TMDBBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB setup
db = Database(MONGO_URL)
utils.db = db

# Share across modules
import services
services.app = app
services.db = db
services.utils = utils

# Load plugins
for p in Path("plugins").glob("*.py"):
    importlib.import_module(f"plugins.{p.stem}")
    log.info(f"Loaded plugin: {p.stem}")

async def main():
    await db.connect()
    log.info("Database connected")
    await app.start()
    log.info("Bot started")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
