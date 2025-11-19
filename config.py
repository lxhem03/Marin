import os

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
ADMINS = [int(x.strip()) for x in os.environ.get("ADMINS", "").split(",") if x.strip().isdigit()]
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/tmdbbot")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", 3600))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 3600))
POST_DELAY = int(os.environ.get("POST_DELAY", 5))
LOG_FILE = os.environ.get("LOG_FILE", "bot.log")
