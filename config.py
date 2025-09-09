# config.py - Enhanced configuration with validation
import os
from typing import Optional

class Config:
    # 🤖 Bot Configuration (Required)
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN") 
    TELEGRAM_API = int(os.environ.get("TELEGRAM_API", 0))
    OWNER = int(os.environ.get("OWNER", 0))
    OWNER_USERNAME = os.environ.get("OWNER_USERNAME")
    PASSWORD = os.environ.get("PASSWORD")
    
    # 🗄️ Database Configuration
    DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb://localhost:27017/mergebot")
    LOGCHANNEL = os.environ.get("LOGCHANNEL")
    
    # 📤 Upload Configuration  
    GOFILE_TOKEN = os.environ.get("GOFILE_TOKEN", None)
    
    # 📁 Directory Configuration
    DOWNLOAD_DIR = "downloads"
    TEMP_DIR = "temp" 
    USERDATA_DIR = "userdata"
    
    # ⚙️ File Configuration
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB for Telegram
    CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunks
    MAX_MERGE_FILES = 20  # Maximum files to merge at once
    
    # 🔄 Merge Modes
    MODES = {
        1: "🎬 Video + Video",
        2: "🎵 Video + Audio", 
        3: "📝 Video + Subtitle",
        4: "🔍 Extract Streams"
    }
    
    # 🎨 UI Configuration
    PROGRESS_BAR_LENGTH = 20
    EDIT_THROTTLE_SECONDS = 2.0
    
    # 🛡️ Security
    IS_PREMIUM = False
    ALLOWED_EXTENSIONS = {
        'video': ['mp4', 'mkv', 'avi', 'webm', 'mov', 'flv', 'wmv', 'm4v', 'ts'],
        'audio': ['mp3', 'aac', 'wav', 'flac', 'm4a', 'ogg', 'wma', 'ac3', 'dts'],
        'subtitle': ['srt', 'ass', 'vtt', 'sub', 'ssa', 'idx', 'sup']
    }
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        required_fields = ['API_HASH', 'BOT_TOKEN', 'TELEGRAM_API', 'OWNER']
        missing = [field for field in required_fields if not getattr(cls, field)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        return True

# Global instance
config = Config()
