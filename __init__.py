import os
import logging
from logging.handlers import RotatingFileHandler
from config import config

# 📁 Create necessary directories
directories = [config.DOWNLOAD_DIR, config.TEMP_DIR, config.USERDATA_DIR]
for directory in directories:
    os.makedirs(directory, exist_ok=True)

# 📝 Setup advanced logging
def setup_logging():
    """Setup comprehensive logging with rotation."""
    
    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    
    # Define log format
    log_format = "%(asctime)s | %(levelname)-8s | %(name)-15s | %(funcName)-15s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Setup root logger
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            RotatingFileHandler(
                "logs/merge_bot.log", 
                maxBytes=50 * 1024 * 1024,  # 50MB
                backupCount=5,
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# 🎬 File Extensions
VIDEO_EXTENSIONS = config.ALLOWED_EXTENSIONS['video']
AUDIO_EXTENSIONS = config.ALLOWED_EXTENSIONS['audio'] 
SUBTITLE_EXTENSIONS = config.ALLOWED_EXTENSIONS['subtitle']

# 📊 Global dictionaries for user data management
user_queue = {}          # User file queues
user_settings = {}       # User settings cache
user_processes = {}      # Active user processes
last_edit_time = {}      # Message edit throttling

# 🎨 UI Elements
PROGRESS_EMOJIS = ["⚪", "🔵", "🟢", "🟡", "🟠", "🔴", "🟣", "🟤", "⚫"]
STATUS_EMOJIS = {
    'downloading': '📥',
    'merging': '🔄', 
    'uploading': '📤',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'info': 'ℹ️'
}

logger.info("🚀 Merge Bot initialization completed!")
