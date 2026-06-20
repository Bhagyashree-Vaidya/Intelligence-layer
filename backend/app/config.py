"""Centralized configuration loaded from environment variables.

All new service keys default to empty string — features gracefully
degrade when keys aren't set. No crashes, just skipped functionality.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Supabase ---
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # --- AI Keys ---
    openai_api_key: str = ""
    claude_api: str = ""

    # --- Scraping ---
    apify_token: str = ""
    firecrawl_api_key: str = ""
    theirstack_api_key: str = ""   # jobs API for the no-public-ATS gap companies

    # --- Browser Automation ---
    browserbase_api_key: str = ""
    browserbase_project_id: str = ""

    # --- Queue ---
    redis_url: str = ""  # rediss://default:xxx@xxx.upstash.io:6379

    # --- App ---
    frontend_url: str = "https://hire.shreevaidya.com"
    backend_url: str = "https://jobs.shreevaidya.com"
    environment: str = "production"  # development | production
    log_level: str = "INFO"
    port: int = 8000

    # --- Resume Storage ---
    resume_upload_dir: str = "/tmp/resumes"

    # --- Auto-Apply ---
    auto_apply_enabled: bool = False
    auto_apply_max_per_run: int = 30
    auto_apply_min_score: int = 0
    auto_apply_exclude_companies: str = ""  # comma-separated

    # --- Alerts ---
    alert_email: str = "bhagyashreevaidya08@gmail.com"
    smtp_password: str = ""        # Gmail App Password (16-char)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
