# config.py - Updated configuration
import os
from typing import Optional

class Config:
    # Bot Configuration
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    TELEGRAM_API = os.environ.get("TELEGRAM_API")
    OWNER = os.environ.get("OWNER")
    OWNER_USERNAME = os.environ.get("OWNER_USERNAME")
    PASSWORD = os.environ.get("PASSWORD")
    
    # Database Configuration
    DATABASE_URL = os.environ.get("DATABASE_URL")
    LOGCHANNEL = os.environ.get("LOGCHANNEL")
    
    # Custom Uploader Configuration
    GOFILE_TOKEN = os.environ.get("GOFILE_TOKEN", None)  # Optional for GoFile uploads
    
    # Directory Configuration
    DOWNLOAD_DIR = "downloads"
    TEMP_DIR = "temp"
    
    # Upload Configuration
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB limit for Telegram
    CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks
    
    # Merge Modes
    MODES = ["video-video", "video-audio", "video-subtitle", "extract-streams"]
    IS_PREMIUM = False

# Global config instance
config = Config()
