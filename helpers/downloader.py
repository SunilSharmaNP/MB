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

def extract_filename_from_url(url: str) -> str:
    """Extract filename from URL with intelligent detection."""
    try:
        # Parse URL
        parsed_url = urlparse(url)
        
        # Try to get filename from path
        path = unquote(parsed_url.path)
        if path and '.' in os.path.basename(path):
            filename = os.path.basename(path)
            # Sanitize filename
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
            if filename and '.' in filename:
                return filename
        
        # Try to extract from Content-Disposition header
        try:
            response = requests.head(url, allow_redirects=True, timeout=10)
            if 'content-disposition' in response.headers:
                content_disp = response.headers['content-disposition']
                filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disp)
                if filename_match:
                    filename = filename_match.group(1).strip('"\'')
                    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
                    if filename and '.' in filename:
                        return filename
        except:
            pass
        
        # Fallback to generic name
        return f"download_{int(time.time())}.bin"
        
    except Exception as e:
        logger.warning(f"Could not extract filename from URL: {e}")
        return f"download_{int(time.time())}.bin"

async def download_from_gofile(url: str, user_id: int, progress_callback: Optional[Callable] = None, 
                              custom_filename: str = None, password: str = None) -> Optional[str]:
    """Download file from GoFile with enhanced support."""
    try:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)
        
        # Extract file ID from GoFile URL
        gofile_patterns = [
            r'gofile\.io/d/([a-zA-Z0-9]+)',
            r'gofile\.io/(?:download\?c=)?([a-zA-Z0-9]+)',
        ]
        
        file_id = None
        for pattern in gofile_patterns:
            match = re.search(pattern, url)
            if match:
                file_id = match.group(1)
                break
        
        if not file_id:
            raise DownloadError("Could not extract file ID from GoFile URL")
        
        # Get file info and download link
        api_url = f"https://api.gofile.io/getContent?contentId={file_id}"
        if password:
            api_url += f"&password={password}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    raise DownloadError(f"GoFile API error: HTTP {response.status}")
                
                data = await response.json()
                
                if data.get('status') != 'ok':
                    raise DownloadError(f"GoFile API error: {data.get('message', 'Unknown error')}")
                
                content_data = data['data']
                
                # Handle folder or single file
                if content_data.get('type') == 'folder':
                    files = content_data.get('contents', {})
                    if not files:
                        raise DownloadError("No files found in GoFile folder")
                    
                    # Get first file
                    first_file = next(iter(files.values()))
                    download_url = first_file.get('link')
                    filename = custom_filename or first_file.get('name', 'gofile_download')
                else:
                    download_url = content_data.get('link')
                    filename = custom_filename or content_data.get('name', 'gofile_download')
                
                if not download_url:
                    raise DownloadError("Could not get download link from GoFile")
                
                # Download the file
                return await download_file_from_direct_url(
                    download_url, user_id, progress_callback, filename
                )
                
    except Exception as e:
        logger.error(f"GoFile download error: {e}")
        raise DownloadError(f"GoFile download failed: {str(e)}")

async def download_file_from_direct_url(url: str, user_id: int, progress_callback: Optional[Callable] = None, 
                                       filename: str = None) -> Optional[str]:
    """Download file from direct URL."""
    try:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)
        
        # Get filename
        if not filename:
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

async def download_file_from_url(url: str, user_id: int, progress_callback: Optional[Callable] = None, 
                                custom_filename: str = None, password: str = None) -> Optional[str]:
    """Main download function with support for various URL types."""
    try:
        # Special handling for different services
        if "gofile.io" in url.lower():
            return await download_from_gofile(url, user_id, progress_callback, custom_filename, password)
        elif "drive.google.com" in url.lower():
            return await download_from_google_drive(url, user_id, progress_callback, custom_filename)
        elif "dropbox.com" in url.lower():
            return await download_from_dropbox(url, user_id, progress_callback, custom_filename)
        else:
            # Direct URL download
            return await download_file_from_direct_url(url, user_id, progress_callback, custom_filename)
            
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        raise DownloadError(f"Download failed: {str(e)}")

async def download_from_google_drive(url: str, user_id: int, progress_callback: Optional[Callable] = None, 
                                   custom_filename: str = None) -> Optional[str]:
    """Download file from Google Drive."""
    try:
        # Extract file ID from Google Drive URL
        file_id_match = re.search(r'/d/([a-zA-Z0-9-_]+)', url) or re.search(r'id=([a-zA-Z0-9-_]+)', url)
        
        if not file_id_match:
            raise DownloadError("Could not extract file ID from Google Drive URL")
        
        file_id = file_id_match.group(1)
        
        # Use direct download URL
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        # For large files, we might need to handle the confirmation token
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status == 200:
                    content = await response.text()
                    # Check if we need confirmation
                    if 'confirm=' in content:
                        confirm_match = re.search(r'confirm=([^&]+)', content)
                        if confirm_match:
                            confirm_token = confirm_match.group(1)
                            download_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
        
        # Download the file
        return await download_file_from_direct_url(download_url, user_id, progress_callback, custom_filename)
        
    except Exception as e:
        logger.error(f"Google Drive download error: {e}")
        raise DownloadError(f"Google Drive download failed: {str(e)}")

async def download_from_dropbox(url: str, user_id: int, progress_callback: Optional[Callable] = None, 
                               custom_filename: str = None) -> Optional[str]:
    """Download file from Dropbox."""
    try:
        # Convert Dropbox share URL to direct download URL
        if "dropbox.com" in url and "dl=0" in url:
            download_url = url.replace("dl=0", "dl=1")
        elif "dropbox.com" in url and "dl=1" not in url:
            download_url = url + ("&" if "?" in url else "?") + "dl=1"
        else:
            download_url = url
        
        # Download the file
        return await download_file_from_direct_url(download_url, user_id, progress_callback, custom_filename)
        
    except Exception as e:
        logger.error(f"Dropbox download error: {e}")
        raise DownloadError(f"Dropbox download failed: {str(e)}")

# Utility functions
def validate_url(url: str) -> bool:
    """Validate if URL is properly formatted."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def get_file_size_from_url(url: str) -> int:
    """Get file size from URL headers."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        return int(response.headers.get('content-length', 0))
    except:
        return 0

async def batch_download(urls: list, user_id: int, progress_callback: Optional[Callable] = None) -> list:
    """Download multiple files concurrently."""
    tasks = []
    for i, url in enumerate(urls):
        async def download_with_progress(url, index):
            async def url_progress(text):
                if progress_callback:
                    await progress_callback(f"📥 **Download {index+1}/{len(urls)}**\n\n{text}")
            
            return await download_file_from_url(url, user_id, url_progress)
        
        tasks.append(download_with_progress(url, i))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

# Clean up function
def cleanup_download_files(file_paths: list):
    """Clean up downloaded files."""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Cleaned up: {file_path}")
        except Exception as e:
            logger.warning(f"Could not clean up {file_path}: {e}")
