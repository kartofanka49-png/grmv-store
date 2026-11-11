import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "GRMV xLUCH store API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Telegram Bot
    BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_IDS: str = ""  # comma-separated IDs
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./grmv_store.db"
    
    # Application URLs
    APP_BASE_URL: str = "http://localhost:5173"
    API_BASE_URL: str = "http://localhost:8000"
    
    # Storage & Uploads
    UPLOAD_DIR: str = "./uploads"
    
    # Security & Development
    DEV_AUTH_ENABLED: bool = False
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    @property
    def admin_id_list(self) -> List[int]:
        ids = []
        for x in self.TELEGRAM_ADMIN_IDS.split(","):
            x = x.strip()
            if x.isdigit():
                ids.append(int(x))
        return ids

settings = Settings()
