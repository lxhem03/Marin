import asyncio
import logging
import os
import sys

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def get_env(key: str, required: bool = True) -> str:
    val = os.environ.get(key, "").strip()
    if required and not val:
        log.error(f"Missing required environment variable: {key}")
        sys.exit(1)
    return val


def main():
    DATABASE_URL    = get_env("DATABASE_URL")
    BOT_TOKEN       = get_env("BOT_TOKEN")
    UPSTREAM_BRANCH = get_env("UPSTREAM_BRANCH", required=False) or "lxhem03"
    UPSTREAM_REPO   = get_env("UPSTREAM_REPO",   required=False)  # optional

    # The _id used in every settings document is the numeric bot-id
    BOT_ID = BOT_TOKEN.split(":", 1)[0]

    log.info(f"Connecting to MongoDB …")
    try:
        client = MongoClient(DATABASE_URL, server_api=ServerApi("1"))
        db = client.wzmlx
    except PyMongoError as e:
        log.error(f"MongoDB connection failed: {e}")
        sys.exit(1)

    # ── patch settings.config ────────────────────────────────────────────────
    patch = {"UPSTREAM_BRANCH": UPSTREAM_BRANCH}
    if UPSTREAM_REPO:
        patch["UPSTREAM_REPO"] = UPSTREAM_REPO

    result = db.settings.config.update_one(
        {"_id": BOT_ID},
        {"$set": patch},
        upsert=True,
    )

    if result.matched_count:
        log.info(f"settings.config  ✔  updated  (matched={result.matched_count}, modified={result.modified_count})")
    else:
        log.info(f"settings.config  ✔  upserted (document was missing, created it)")

    # ── patch settings.deployConfig too (keeps both in sync) ─────────────────
    result2 = db.settings.deployConfig.update_one(
        {"_id": BOT_ID},
        {"$set": patch},
        upsert=False,          # don't create if absent – deployConfig is optional
    )
    if result2.matched_count:
        log.info(f"settings.deployConfig  ✔  updated  (modified={result2.modified_count})")
    else:
        log.info("settings.deployConfig  –  document not found, skipped")

    log.info(f"Done. UPSTREAM_BRANCH → {UPSTREAM_BRANCH!r}" + (f"  |  UPSTREAM_REPO → {UPSTREAM_REPO!r}" if UPSTREAM_REPO else ""))
    client.close()


if __name__ == "__main__":
    main()
