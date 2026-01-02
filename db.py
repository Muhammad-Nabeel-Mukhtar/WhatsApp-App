# db.py
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import get_settings

settings = get_settings()

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        client = get_client()
        _db = client[settings.mongodb_db_name]
    return _db


async def close_client():
    global _client
    if _client is not None:
        _client.close()
        _client = None
