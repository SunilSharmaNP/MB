# Your complete downloader.py file with minor integration tweaks
import aiohttp
import asyncio
import os
import time
import logging
from datetime import datetime
from config import config
from utils import get_human_readable_size, get_progress_bar, create_progress_text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
from urllib.parse import urlparse, unquote
import re
import requests
from hashlib import sha256
import json

logger = logging.getLogger(__name__)

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = config.EDIT_THROTTLE_SECONDS

# Configuration
DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks
DOWNLOAD_CONNECT_TIMEOUT = 60
DOWNLOAD_READ_TIMEOUT = 600
DOWNLOAD_RETRY_ATTEMPTS = 5
DOWNLOAD_RETRY_WAIT_MIN = 5
DOWNLOAD_RETRY_WAIT_MAX = 60
MAX_URL_LENGTH = 2048

# Gofile configuration
GOFILE_API_URL = "https://api.gofile.io"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
PASSWORD_ERROR_MESSAGE = "ERROR: Password is required for this link\n\nUse: /download {link} password"

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
            await status_message.edit_text(text, parse_mode="markdown")
            last_edit_time[message_key] = now
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")

# [Include all your downloader functions here with integration tweaks...]

async def download_file_from_url(url: str, user_id: int, status_message=None, password: str = None, custom_filename: str = None) -> str:
    """Enhanced main download function with beautiful progress."""
    # Validate URL
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        if status_message:
            await status_message.edit_text(f"❌ **Invalid URL**\n\n`{error_msg}`")
        raise ValueError(error_msg)
    
    user_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    # Handle GoFile URLs
    if 'gofile.io' in url:
        try:
            await smart_progress_editor(status_message, "🔍 **Processing GoFile link...**")
            direct_url, headers = handle_gofile_url(url, password)
            url = direct_url
        except DirectDownloadLinkException as e:
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Error**\n\n`{str(e)}`")
            raise e
    
    # Get filename
    filename = custom_filename or get_filename_from_url(url)
    file_path = os.path.join(user_dir, filename)
    
    # Start download with beautiful progress
    timeout = aiohttp.ClientTimeout(
        connect=DOWNLOAD_CONNECT_TIMEOUT,
        total=DOWNLOAD_READ_TIMEOUT
    )
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            return await _perform_download_request_enhanced(session, url, file_path, status_message, filename, 0)
        except Exception as e:
            if status_message:
                await status_message.edit_text(f"❌ **Download Failed**\n\n`{str(e)}`")
            raise e

async def _perform_download_request_enhanced(session: aiohttp.ClientSession, url: str, dest_path: str, status_message, filename: str, total_size: int):
    """Enhanced download with beautiful progress tracking."""
    start_time = time.time()
    downloaded = 0

    try:
        async with session.get(url) as response:
            response.raise_for_status()
            
            # Get file size
            if total_size == 0 and 'content-length' in response.headers:
                total_size = int(response.headers['content-length'])
            
            with open(dest_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_SIZE):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Update progress with beautiful formatting
                    if status_message and total_size > 0:
                        progress = downloaded / total_size
                        progress_text = create_progress_text(
                            title="📥 Downloading from URL",
                            filename=filename,
                            progress=progress,
                            current_size=downloaded,
                            total_size=total_size,
                            start_time=start_time,
                            extra_info=f"Source: {urlparse(url).netloc}"
                        )
                        await smart_progress_editor(status_message, progress_text)
            
            if status_message:
                await smart_progress_editor(
                    status_message,
                    f"✅ **Download Complete!**\n\n"
                    f"📁 **File:** `{filename}`\n"
                    f"📊 **Size:** {get_human_readable_size(downloaded)}\n"
                    f"⏱️ **Time:** {time.time() - start_time:.1f}s"
                )
            
            logger.info(f"✅ Downloaded: {filename} ({get_human_readable_size(downloaded)})")
            return dest_path
            
    except Exception as e:
        logger.error(f"❌ Download failed for {url}: {e}")
        raise e

# [Rest of your downloader functions continue...]
