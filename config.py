# config.py
from functools import lru_cache

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core WhatsApp Cloud API settings
    whatsapp_phone_number_id: str
    whatsapp_access_token: str
    whatsapp_webhook_verify_token: str

    # MongoDB settings
    mongodb_uri: str
    mongodb_db_name: str

    # Graph API base URL (version can be bumped later)
    whatsapp_graph_base_url: AnyHttpUrl = AnyHttpUrl("https://graph.facebook.com/v20.0")

    class Config:
        env_prefix = ""   # read exact names from env
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance so we don't re-read env vars on every import.

    Env vars expected in .env (same folder where you run python):

      WHATSAPP_PHONE_NUMBER_ID=...
      WHATSAPP_ACCESS_TOKEN=...
      WHATSAPP_WEBHOOK_VERIFY_TOKEN=...
      MONGODB_URI=...
      MONGODB_DB_NAME=...
    """
    return Settings(
        _env_file=".env",
        _env_file_encoding="utf-8",
    )
