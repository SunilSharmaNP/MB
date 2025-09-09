# helpers/downloader.py - Complete download functionality
import asyncio
import os
import aiohttp
import requests
import logging
import re
import time
from typing import Optional, Callable, Dict, Any
from urllib.parse import urlparse, unquote
from pyrogram.types import Message
from config import config
from utils import get_human_readable_size, create_progress_text, smart_progress_editor

logger = logging.getLogger(__name__)

class DownloadError(Exception):
    """Custom exception for download errors."""
    pass

async def download_telegram_file(message: Message, user_id: int, progress_callback: Optional[Callable] = None) -> Optional[str]:
    """Download file from Telegram message."""
    try:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)
        
        # Determine file info based on message type
        file_info = None
        file_name = None
        
        if message.document:
            file_info = message.document
            file_name = file_info.file_name or f"document_{file_info.file_id}.{file_info.mime_type.split('/')[-1] if file_info.mime_type else 'bin'}"
        elif message.video:
            file_info = message.video
            file_name = file_info.file_name or f"video_{file_info.file_id}.mp4"
        elif message.audio:
            file_info = message.audio
            file_name = file_info.file_name or f"audio_{file_info.file_id}.mp3"
        else:
            raise DownloadError("Unsupported file type")
        
        # Sanitize filename
        file_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        file_path = os.path.join(user_download_dir, file_name)
        
        # Check file size
        if file_info.file_size > config.MAX_FILE_SIZE:
            raise DownloadError(f"File too large: {get_human_readable_size(file_info.file_size)}")
        
        # Download with progress
        start_time = time.time()
        
        async def progress_handler(current: int, total: int):
            if progress_callback:
                progress = current / total if total > 0 else 0
                speed = get_human_readable_size(current / (time.time() - start_time + 0.1)) + "/s"
                eta = get_time_left(start_time, current, total)
                
                progress_text = create_progress_text(
                    "📥 Downloading from Telegram",
                    file_name,
                    progress,
                    speed,
                    eta
                )
                
                await progress_callback(progress_text)
        
        # Download the file
        downloaded_path = await message.download(
            file_name=file_path,
            progress=progress_handler
        )
        
        if downloaded_path and os.path.exists(downloaded_path):
            logger.info(f"✅ Downloaded Telegram file: {file_name}")
            return downloaded_path
        else:
            raise DownloadError("Download failed - file not created")
            
    except Exception as e:
        logger.error(f"❌ Failed to download Telegram file: {e}")
        raise DownloadError(f"Telegram download failed: {str(e)}")

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate ETA for downloads."""
    if current <= 0 or total <= 0:
        return "⏳ Calculating..."
    
    elapsed = time.time() - start_time
    if elapsed <= 0.1:
        return "⏳ Starting..."
    
    rate = current / elapsed
    if rate == 0:
        return "⏳ Calculating..."
    
    remaining = (total - current) / rate
    
    if remaining < 60:
        return f"⏱️ {int(remaining)}s"
    elif remaining < 3600:
        return f"⏱️ {int(remaining//60)}m {int(remaining%60)}s"
    else:
        return f"⏱️ {int(remaining//3600)}h {int((remaining%3600)//60)}m"

async def download_file_from_url(url: str, user_id: int, progress_callback: Optional[Callable] = None, custom_filename: str = None) -> Optional[str]:
    """Download file from URL with progress tracking."""
    try:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)
        
        # Special handling for GoFile URLs
        if "gofile.io" in url.lower():
            return await download_from_gofile(url, user_id, progress_callback, custom_filename)
        
        # Get filename from URL or use custom
        if custom_filename:
            filename = custom_filename
        else:
            filename = extract_filename_from_url(url)
        
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        if not filename or '.' not in filename:
            filename = f"download_{int(time.time())}.bin"
        
        file_path = os.path.join(user_download_dir, filename)
        
        # Download with aiohttp for better async support
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3600),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=30)
        ) as session:
            
            start_time = time.time()
            
            async with session.get(url) as response:
                if response.status != 200:
                    raise DownloadError(f"HTTP {response.status}: {response.reason}")
                
                total_size = int(response.headers.get('content-length', 0))
                
                if total_size > config.MAX_FILE_SIZE:
                    raise DownloadError(f"File too large: {get_human_readable_size(total_size)}")
                
                downloaded = 0
                
                with open(file_path, 'wb') as file:
                    async for chunk in response.content.iter_chunked(config.CHUNK_SIZE):
                        file.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress
                        if progress_callback and total_size > 0:
                            progress = downloaded / total_size
                            elapsed = time.time() - start_time
                            speed = get_human_readable_size(downloaded / (elapsed + 0.1)) + "/s"
                            eta = get_time_left(start_time, downloaded, total_size)
                            
                            progress_text = create_progress_text(
                                "📥 Downloading from URL",
                                filename,
                                progress,
                                speed,
                                eta
                            )
                            
                            await progress_callback(progress_text)
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            logger.info(f"✅ Downloaded file from URL: {filename}")
            return file_path
        else:
            raise DownloadError("Download completed but file is empty or missing")
            
    except Exception as e:
        logger.error(f"❌ Failed to download from URL {url}: {e}")
        # Clean up partial download
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise DownloadError(f"URL download failed: {str(e)}")

def extract_filename_from_url(url: str) -> str:
    """Extract filename from URL."""
    try:
        parsed_url = urlparse(url)
        filename = unquote(os.path.basename(parsed_url.path))
        
        if not filename or filename == '/':
            # Try to get from Content-Disposition header
            try:
                response = requests.head(url, timeout=10)
                content_disposition = response.headers.get('content-disposition', '')
                if 'filename=' in content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
            except:
                pass
        
        if not filename or '.' not in filename:
            filename = f"download_{int(time.time())}.bin"
            
        return filename
        
    except Exception as e:
        logger.error(f"Failed to extract filename from {url}: {e}")
        return f"download_{int(time.time())}.bin"

async def download_from_gofile(url: str, user_id: int, progress_callback: Optional[Callable] = None, custom_filename: str = None) -> Optional[str]:
    """Special handler for GoFile downloads."""
    try:
        # Extract file ID from GoFile URL
        file_id_match = re.search(r'/d/([a-zA-Z0-9-]+)', url)
        if not file_id_match:
            raise DownloadError("Invalid GoFile URL format")
        
        file_id = file_id_match.group(1)
        
        # GoFile API endpoint
        api_url = f"https://api.gofile.io/getContent?contentId={file_id}"
        
        async with aiohttp.ClientSession() as session:
            # Get file info
            async with session.get(api_url) as response:
                if response.status != 200:
                    raise DownloadError("Failed to get GoFile info")
                
                data = await response.json()
                
                if data.get('status') != 'ok':
                    raise DownloadError("GoFile API error")
                
                content = data['data']['contents']
                
                # Find the file (GoFile can have multiple files)
                file_info = None
                for item_id, item in content.items():
                    if item.get('type') == 'file':
                        file_info = item
                        break
                
                if not file_info:
                    raise DownloadError("No file found in GoFile link")
                
                download_url = file_info['directLink']
                filename = custom_filename or file_info['name']
                
                # Download using the direct link
                return await download_file_from_url(download_url, user_id, progress_callback, filename)
                
    except Exception as e:
        logger.error(f"❌ GoFile download failed: {e}")
        raise DownloadError(f"GoFile download failed: {str(e)}")

def is_valid_url(url: str) -> bool:
    """Check if URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def get_url_info(url: str) -> Dict[str, Any]:
    """Get basic info about URL."""
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        
        return {
            'url': response.url,
            'status_code': response.status_code,
            'content_type': response.headers.get('content-type', ''),
            'content_length': int(response.headers.get('content-length', 0)),
            'filename': extract_filename_from_url(response.url)
        }
        
    except Exception as e:
        logger.error(f"Failed to get URL info: {e}")
        return {
            'url': url,
            'status_code': 0,
            'content_type': '',
            'content_length': 0,
            'filename': extract_filename_from_url(url)
        }
