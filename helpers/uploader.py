# helpers/uploader.py - Your enhanced uploader with integration
import os
import time
import asyncio
from aiohttp import ClientSession, FormData, ClientTimeout
from random import choice
from config import config
from utils import get_human_readable_size, get_progress_bar, get_video_properties
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 3.0

# Configuration
GOFILE_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks
GOFILE_UPLOAD_TIMEOUT = 3600  # 1 hour timeout
GOFILE_RETRY_ATTEMPTS = 5
GOFILE_RETRY_WAIT_MIN = 1
GOFILE_RETRY_WAIT_MAX = 60

async def smart_progress_editor(status_message, text: str):
    """Smart progress editor with throttling."""
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
            pass

async def upload_to_telegram(client, file_path: str, chat_id: int, status_message=None, as_document: bool = False, thumbnail_path: str = None, caption: str = None):
    """Upload file to Telegram with progress tracking."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    
    if file_size > config.MAX_FILE_SIZE:
        raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds Telegram limit (2GB)")
    
    start_time = time.time()
    
    async def progress_callback(current, total):
        if status_message:
            progress = current / total if total > 0 else 0
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""
📤 **Uploading to Telegram...**

📁 **File:** `{filename}`
📊 **Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Uploaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
"""
            await smart_progress_editor(status_message, progress_text.strip())
    
    try:
        if as_document:
            return await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                progress=progress_callback,
                thumb=thumbnail_path
            )
        else:
            return await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                progress=progress_callback,
                thumb=thumbnail_path
            )
    except Exception as e:
        if status_message:
            await status_message.edit_text(f"❌ **Upload Failed:** {str(e)}")
        raise e

class GofileUploader:
    """Enhanced GoFile uploader with real-time progress tracking."""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or config.GOFILE_TOKEN
        self.chunk_size = GOFILE_CHUNK_SIZE
        self.session = None
    
    async def upload_file(self, file_path: str, status_message=None):
        """Upload file to GoFile with progress tracking."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        if file_size > (10 * 1024 * 1024 * 1024):  # 10GB limit
            raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds GoFile limit")
        
        # Get upload server
        try:
            if status_message:
                await smart_progress_editor(status_message, "🔗 **Connecting to GoFile servers...**")
            server = await self.__get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
        except Exception as e:
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Connection Failed:** {str(e)}")
            raise e
        
        # [Rest of your GoFile upload implementation...]
        
        return {"status": "ok", "data": {"downloadPage": f"https://gofile.io/d/{file_id}"}}

# [Include rest of your uploader.py functions...]
