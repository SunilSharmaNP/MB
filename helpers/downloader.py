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

async def download_from_gofile(url: str, user_id: int, progress_callback: Optional[Callable] = None, custom_filename: str = None) -> Optional[str]:
    """Download from GoFile with special handling."""
    try:
        # Extract file ID from GoFile URL
        file_id_match = re.search(r'/d/([a-zA-Z0-9]+)', url)
        if not file_id_match:
            raise DownloadError("Invalid GoFile URL format")
        
        file_id = file_id_match.group(1)
        
        # Get download link via GoFile API
        api_url = f"https://api.gofile.io/getContent?contentId={file_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    raise DownloadError("Failed to get GoFile download info")
                
                data = await response.json()
                
                if data['status'] != 'ok':
                    raise DownloadError("GoFile API error")
                
                content = data['data']['contents']
                if not content:
                    raise DownloadError("No files found in GoFile link")
                
                # Get first file (or specific file if needed)
                first_file_id = list(content.keys())[0]
                file_info = content[first_file_id]
                
                download_url = file_info['link']
                filename = custom_filename or file_info['name']
                
                # Use regular download function
                return await download_file_from_url(download_url, user_id, progress_callback, filename)
                
    except Exception as e:
        logger.error(f"❌ GoFile download failed: {e}")
        raise DownloadError(f"GoFile download failed: {str(e)}")

def extract_filename_from_url(url: str) -> str:
    """Extract filename from URL."""
    try:
        # Parse URL
        parsed = urlparse(url)
        
        # Get filename from path
        filename = os.path.basename(parsed.path)
        
        # Decode URL encoding
        filename = unquote(filename)
        
        # If no filename in path, generate one
        if not filename or '.' not in filename:
            # Try to get from Content-Disposition header (requires HEAD request)
            try:
                response = requests.head(url, timeout=10, allow_redirects=True)
                content_disposition = response.headers.get('content-disposition', '')
                if 'filename=' in content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
            except:
                pass
            
            # Final fallback
            if not filename or '.' not in filename:
                timestamp = int(time.time())
                filename = f"download_{timestamp}.bin"
        
        return filename
        
    except Exception as e:
        logger.warning(f"Could not extract filename from URL: {e}")
        return f"download_{int(time.time())}.bin"

def is_supported_url(url: str) -> bool:
    """Check if URL is supported for download."""
    supported_domains = [
        'gofile.io',
        'drive.google.com',
        'dropbox.com',
        'mega.nz',
        'mediafire.com',
        'wetransfer.com',
        'github.com',
        'gitlab.com'
    ]
    
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc.replace('www.', '')
        
        # Check if it's a direct file URL (has file extension)
        path = parsed.path.lower()
        file_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.srt', '.ass', '.vtt']
        
        if any(path.endswith(ext) for ext in file_extensions):
            return True
        
        # Check supported domains
        return any(domain.endswith(supported) for supported in supported_domains)
        
    except Exception:
        return False

async def get_url_info(url: str) -> Dict[str, Any]:
    """Get information about a URL without downloading."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                content_length = response.headers.get('content-length')
                content_type = response.headers.get('content-type', '')
                filename = extract_filename_from_url(url)
                
                return {
                    'url': url,
                    'filename': filename,
                    'size': int(content_length) if content_length else 0,
                    'content_type': content_type,
                    'status_code': response.status,
                    'is_supported': is_supported_url(url)
                }
                
    except Exception as e:
        logger.error(f"Failed to get URL info: {e}")
        return {
            'url': url,
            'filename': extract_filename_from_url(url),
            'size': 0,
            'content_type': 'unknown',
            'status_code': 0,
            'is_supported': is_supported_url(url),
            'error': str(e)
        }

# Utility functions for download management
def cleanup_downloads(user_id: int, max_age_hours: int = 24):
    """Clean up old downloaded files."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if not os.path.exists(user_download_dir):
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for filename in os.listdir(user_download_dir):
        file_path = os.path.join(user_download_dir, filename)
        
        try:
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    logger.info(f"🗑️ Cleaned up old file: {filename}")
                    
        except Exception as e:
            logger.warning(f"Could not clean up file {filename}: {e}")

def get_download_stats(user_id: int) -> Dict[str, Any]:
    """Get download statistics for a user."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if not os.path.exists(user_download_dir):
        return {
            'total_files': 0,
            'total_size': 0,
            'files': []
        }
    
    files = []
    total_size = 0
    
    for filename in os.listdir(user_download_dir):
        file_path = os.path.join(user_download_dir, filename)
        
        if os.path.isfile(file_path):
            file_size = os.path.getsize(file_path)
            total_size += file_size
            
            files.append({
                'name': filename,
                'size': file_size,
                'modified': os.path.getmtime(file_path)
            })
    
    return {
        'total_files': len(files),
        'total_size': total_size,
        'files': files
}
