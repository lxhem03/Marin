from motor.motor_asyncio import AsyncIOMotorClient

class Database:
    def __init__(self, uri):
        self.uri = uri
        self.client = None
        self.db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(self.uri)
        self.db = self.client.tmdbbot
        self.search_cache = self.db.search_cache
        self.details_cache = self.db.details_cache
        self.trending_cache = self.db.trending_cache
