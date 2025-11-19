import time
import json
import requests
from datetime import datetime
from bson import json_util
from config import TMDB_API_KEY, CACHE_TTL_SECONDS
TMDB_BASE = "https://api.themoviedb.org/3"

def tmdb_get(path: str, params: dict = None):
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY
    try:
        r = requests.get(f"{TMDB_BASE}/{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def build_image_url(path: str, size: str = "w780"):
    if not path:
        return ""
    return f"https://image.tmdb.org/t/p/{size}{path}"

async def cache_get(db, key: str):
    row = await db.cache.find_one({"key": key})
    if not row:
        return None
    if row.get("expires_at", 0) < int(time.time()):
        await db.cache.delete_one({"key": key})
        return None
    return json.loads(row.get("value"))

async def cache_set(db, key: str, value, ttl: int = CACHE_TTL_SECONDS):
    doc = {"key": key, "value": json.dumps(value, default=json_util.default), "expires_at": int(time.time()) + int(ttl), "created_at": int(time.time())}
    await db.cache.update_one({"key": key}, {"$set": doc}, upsert=True)

async def search_and_cache(db, query: str, max_results: int = 100):
    key = f"search:{query.lower()}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    data = tmdb_get("search/multi", {"query": query, "page": 1})
    results = data.get("results", [])[:max_results]
    normalized = []
    for r in results:
        media_type = r.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        title = r.get("title") or r.get("name") or ""
        year = (r.get("release_date") or r.get("first_air_date") or "")[:4]
        rating = float(r.get("vote_average") or 0.0)
        normalized.append({"id": int(r.get("id")), "type": media_type, "title": title, "year": year, "rating": rating})
    await cache_set(db, key, normalized)
    return normalized

async def get_images_and_cache(db, media_type: str, media_id: int):
    key = f"images:{media_type}:{media_id}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    data = tmdb_get(f"{media_type}/{media_id}/images")
    posters = data.get("posters", [])
    backdrops = data.get("backdrops", [])
    obj = {"posters": posters, "backdrops": backdrops}
    await cache_set(db, key, obj)
    return obj

async def get_details_and_cache(db, media_type: str, media_id: int):
    key = f"details:{media_type}:{media_id}"
    cached = await cache_get(db, key)
    if cached:
        return cached
    data = tmdb_get(f"{media_type}/{media_id}")
    await cache_set(db, key, data)
    return data

def chunk_list(lst, size):
    return [lst[i:i+size] for i in range(0, len(lst), size)]
