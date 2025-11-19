from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, DB_NAME

_client = AsyncIOMotorClient(MONGO_URL)
db = _client[DB_NAME]
