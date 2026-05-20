"""Centralized configuration loaded from environment variables."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Supabase ---
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # --- AI Keys ---
    openai_api_key: str = ""
    claude_api: str = ""

    # --- Apify ---
    apify_token: str = ""

    # --- App ---
    frontend_url: str = "https://shreevaidya.com"
    backend_url: str = "https://jobs.shreevaidya.com"
    environment: str = "production"  # development | production
    log_level: str = "INFO"
    port: int = 8000

    # --- Resume Storage ---
    resume_upload_dir: str = "/tmp/resumes"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
