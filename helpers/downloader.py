# helpers/downloader.py - Your enhanced downloader with minor modifications for integration
import aiohttp
import asyncio
import os
import time
import logging
from datetime import datetime
from config import config
from utils import get_human_readable_size, get_progress_bar
from tenacity import retry, stop_after_attempt, wait_exponential, \
    retry_if_exception_type, RetryError
from urllib.parse import urlparse, unquote
import re
import requests
from hashlib import sha256
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 3.0

# Configuration
DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks
DOWNLOAD_CONNECT_TIMEOUT = 60
DOWNLOAD_READ_TIMEOUT = 600
DOWNLOAD_RETRY_ATTEMPTS = 5
DOWNLOAD_RETRY_WAIT_MIN = 5
DOWNLOAD_RETRY_WAIT_MAX = 60
MAX_URL_LENGTH = 2048

# GoFile configuration
GOFILE_API_URL = "https://api.gofile.io"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
PASSWORD_ERROR_MESSAGE = "ERROR: Password is required for this link\n\nUse: /cmd {link} password"

class DirectDownloadLinkException(Exception):
    pass

async def smart_progress_editor(status_message, text: str):
    """Smart progress editor with throttling to avoid flood limits."""
    if not status_message or not hasattr(status_message, 'chat'):
        return
    
    message_key = f"{status_message.chat.id}_{status_message.id}"
    now = time.time()
    last_time = last_edit_time.get(message_key, 0)
    
    if (now - last_time) > EDIT_THROTTLE_SECONDS:
        try:
            await status_message.edit_text(text)
            last_edit_time[message_key] = now
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")

# [Rest of your downloader.py code continues here...]
# I'm including the key functions but truncating for space

async def download_file_from_url(url: str, user_id: int, status_message=None, password: str = None) -> str:
    """Main download function that handles both regular URLs and GoFile links."""
    # Validate URL
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        if status_message:
            await status_message.edit_text(f"❌ **Invalid URL:** {error_msg}")
        raise ValueError(error_msg)
    
    user_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    # Handle GoFile URLs
    if 'gofile.io' in url:
        try:
            direct_url, headers = handle_gofile_url(url, password)
            url = direct_url
        except DirectDownloadLinkException as e:
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Error:** {str(e)}")
            raise e
    
    # Get filename
    filename = get_filename_from_url(url)
    file_path = os.path.join(user_dir, filename)
    
    # Download file
    timeout = aiohttp.ClientTimeout(
        connect=DOWNLOAD_CONNECT_TIMEOUT,
        total=DOWNLOAD_READ_TIMEOUT
    )
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            return await _perform_download_request(session, url, file_path, status_message, 0)
        except Exception as e:
            if status_message:
                await status_message.edit_text(f"❌ **Download Failed:** {str(e)}")
            raise e

async def download_telegram_file(client, message, user_id: int, status_message=None) -> str:
    """Download file from Telegram message."""
    user_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    media = message.document or message.video or message.audio
    if not media:
        raise ValueError("No downloadable media found in message")
    
    filename = media.file_name or f"telegram_file_{int(time.time())}.bin"
    file_path = os.path.join(user_dir, filename)
    
    start_time = time.time()
    
    async def progress_callback(current, total):
        if status_message:
            progress = current / total if total > 0 else 0
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""
📥 **Downloading from Telegram...**

📁 **File:** `{filename}`
📊 **Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Downloaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
"""
            await smart_progress_editor(status_message, progress_text.strip())
    
    await client.download_media(message, file_name=file_path, progress=progress_callback)
    return file_path
