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
def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
    if current <= 0 or total <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    if elapsed <= 0.1: # Avoid division by zero or very small numbers
        return "Calculating..."
    
    rate = current / elapsed
    if rate == 0:
        return "Calculating..."
    
    remaining_bytes = total - current
    if remaining_bytes <= 0:
        return "0s"
        
    remaining = remaining_bytes / rate
    
    if remaining < 60:
        return f"{int(remaining)}s"
    elif remaining < 3600:
        return f"{int(remaining // 60)}m {int(remaining % 60)}s"
    else:
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return f"{hours}h {minutes}m"

def get_speed(start_time: float, current: int) -> str:
    """Calculate download speed."""
    elapsed = time.time() - start_time
    if elapsed <= 0:
        return "0 B/s"
    
    speed = current / elapsed
    if speed < 1024:
        return f"{speed:.1f} B/s"
    elif speed < 1024 * 1024:
        return f"{speed / 1024:.1f} KB/s"
    else:
        return f"{speed / (1024 * 1024):.1f} MB/s"

def validate_url(url: str) -> tuple[bool, str]:
    """Validate download URL."""
    if not url or not isinstance(url, str):
        return False, "Invalid URL format"
    
    if len(url) > MAX_URL_LENGTH:
        return False, f"URL length exceeds maximum allowed ({MAX_URL_LENGTH} characters)."

    parsed_url = urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        return False, "URL must have a scheme (http/https) and network location."
    
    # Allow only http/https schemes and gofile.io
    if parsed_url.scheme not in ('http', 'https') and 'gofile.io' not in parsed_url.netloc:
        return False, "URL scheme must be http or https."
    
    # Check for suspicious extensions in path (basic check)
    path = parsed_url.path.lower()
    dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.pif', '.sh', '.bin']
    if any(path.endswith(ext) for ext in dangerous_extensions):
        return False, "Potentially dangerous file type in URL path."
    
    return True, "Valid"

def get_filename_from_url(url: str, fallback_name: str = None) -> str:
    """Extract filename from URL robustly, with fallbacks and sanitization."""
    try:
        parsed_url = urlparse(url)
        # 1. From Content-Disposition header (if available, best practice, but usually server-side)
        # This function doesn't have access to headers, so we rely on URL path.

        # 2. From URL path
        filename = os.path.basename(parsed_url.path)
        filename = unquote(filename) # Decode URL-encoded characters (%20 -> space)
        
        # Remove query parameters after decoding
        if '?' in filename:
            filename = filename.split('?')[0]

        # Basic sanitization for common invalid characters in filenames
        # Replace characters not allowed in Windows/Unix filenames with underscore
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove leading/trailing dots/spaces and control characters
        filename = filename.strip(' .').strip()
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename) # Remove control chars

        # If filename is still empty or too short/generic (e.g., just a slash or 'download')
        if not filename or len(filename) < 5 or filename.lower() in ('download', 'file', 'index'):
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = fallback_name or f"download_{timestamp_str}.bin" # Use .bin for generic fallback
            logger.info(f"Generated fallback filename: {filename} for URL: {url}")
        
        # Ensure it has an extension, if not, add a common one
        if '.' not in filename:
            filename += '.bin' # Default to binary if no extension

        # Limit filename length to prevent filesystem issues
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:(200 - len(ext))] + ext
            logger.warning(f"Truncated filename to: {filename}")

        return filename
    except Exception as e:
        logger.error(f"Error extracting filename from URL '{url}': {e}")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        return fallback_name or f"download_error_{timestamp_str}.bin"

def handle_gofile_url(url: str, password: str = None) -> tuple:
    """
    Handle gofile.io URLs and return direct download link.
    Based on the provided gofile function.
    """
    try:
        _password = sha256(password.encode("utf-8")).hexdigest() if password else ""
        _id = url.split("/")[-1]
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}")

    def __get_token(session):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        __url = f"{GOFILE_API_URL}/accounts"
        try:
            __res = session.post(__url, headers=headers).json()
            if __res["status"] != "ok":
                raise DirectDownloadLinkException("ERROR: Failed to get token.")
            return __res["data"]["token"]
        except Exception as e:
            raise e

    def __fetch_links(session, _id, folderPath=""):
        _url = f"{GOFILE_API_URL}/contents/{_id}?wt=4fd6sg89d7s6&cache=true"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": "Bearer" + " " + token,
        }
        if _password:
            _url += f"&password={_password}"
        try:
            _json = session.get(_url, headers=headers).json()
        except Exception as e:
            raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}")
        if _json["status"] in "error-passwordRequired":
            raise DirectDownloadLinkException(
                f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url=url)}"
            )
        if _json["status"] in "error-passwordWrong":
            raise DirectDownloadLinkException("ERROR: This password is wrong !")
        if _json["status"] in "error-notFound":
            raise DirectDownloadLinkException(
                "ERROR: File not found on gofile's server"
            )
        if _json["status"] in "error-notPublic":
            raise DirectDownloadLinkException("ERROR: This folder is not public")

        data = _json["data"]

        if not details["title"]:
            details["title"] = data["name"] if data["type"] == "folder" else _id

        contents = data["children"]
        for content in contents.values():
            if content["type"] == "folder":
                if not content["public"]:
                    continue
                if not folderPath:
                    newFolderPath = os.path.join(details["title"], content["name"])
                else:
                    newFolderPath = os.path.join(folderPath, content["name"])
                __fetch_links(session, content["id"], newFolderPath)
            else:
                if not folderPath:
                    folderPath = details["title"]
                item = {
                    "path": os.path.join(folderPath),
                    "filename": content["name"],
                    "url": content["link"],
                }
                if "size" in content:
                    size = content["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    details = {"contents": [], "title": "", "total_size": 0}
    with requests.Session() as session:
        try:
            token = __get_token(session)
        except Exception as e:
            raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}")
        details["header"] = f"Cookie: accountToken={token}"
        try:
            __fetch_links(session, _id)
        except Exception as e:
            raise DirectDownloadLinkException(e)

    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], details["header"])
    elif len(details["contents"]) > 1:
        # For multiple files, return the first one
        logger.warning(f"Gofile link has multiple files. Downloading the first one: {details['contents'][0]['filename']}")
        return (details["contents"][0]["url"], details["header"])
    else:
        raise DirectDownloadLinkException("No downloadable content found in gofile link")

@retry(
    stop=stop_after_attempt(DOWNLOAD_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=DOWNLOAD_RETRY_WAIT_MIN, max=DOWNLOAD_RETRY_WAIT_MAX),
    retry=retry_if_exception_type(aiohttp.ClientError) | retry_if_exception_type(asyncio.TimeoutError),
    reraise=True,
    before_sleep=lambda retry_state: logger.warning(f"Retrying download for {retry_state.fn.__name__} (attempt {retry_state.attempt_number})...")
    )


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
async def download_from_url(url: str, user_id: int, status_message, password: str = None) -> str | None:
    """Enhanced URL download with professional progress tracking and robust error handling."""
    start_time = time.time()
    # Handle extremely long URLs
    if len(url) > 1500:  # If URL is very long
        await smart_progress_editor(status_message, "🔍 **Processing long URL...**")
        processed_url, additional_headers = handle_long_url(url)
        if processed_url != url:
            url = processed_url
            await smart_progress_editor(status_message, f"✅ **Long URL processed!**\n\nUsing alternative method for download.")
    
    # Validate URL first
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        await smart_progress_editor(status_message, f"❌ **Invalid URL!**\n\n🚨 **Error:** {error_msg}")
        return None
    
    # Validate URL first
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        await smart_progress_editor(status_message, f"❌ **Invalid URL!**\n\n🚨 **Error:** {error_msg}")
        return None
    
    # Handle gofile.io URLs
    parsed_url = urlparse(url)
    headers_dict = {}
    if 'gofile.io' in parsed_url.netloc:
        try:
            await smart_progress_editor(status_message, "🔍 **Processing gofile.io link...**")
            # Run the synchronous gofile handling in a thread
            direct_url, headers_str = await asyncio.to_thread(handle_gofile_url, url, password)
            
            # Parse headers string into dictionary
            if headers_str:
                for header_line in headers_str.split('\n'):
                    if ':' in header_line:
                        key, value = header_line.split(':', 1)
                        headers_dict[key.strip()] = value.strip()
            
            # Update URL to direct download link
            url = direct_url
            await smart_progress_editor(status_message, f"✅ **Gofile.io link processed!**\n\n📁 **Direct URL:** `{url[:70]}...`")
        except DirectDownloadLinkException as e:
            await smart_progress_editor(status_message, f"❌ **Gofile.io Error!**\n\n🚨 **Error:** {str(e)}")
            return None
        except Exception as e:
            await smart_progress_editor(status_message, f"❌ **Gofile.io Processing Failed!**\n\n🚨 **Error:** {str(e)}")
            return None
    
    # Setup paths
    file_name = get_filename_from_url(url)
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_download_dir, exist_ok=True)
    dest_path = os.path.join(user_download_dir, file_name)

    # Prevent overwriting if file already exists (simple version)
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(file_name)
        timestamp = datetime.now().strftime("_%H%M%S")
        dest_path = os.path.join(user_download_dir, f"{base}{timestamp}{ext}")
        file_name = os.path.basename(dest_path)
        logger.warning(f"File '{file_name}' already exists, saving as '{os.path.basename(dest_path)}'")
    
    try:
        # Initial status
        await smart_progress_editor(
            status_message, 
            f"🔍 **Connecting to server...**\n\n📁 **File:** `{file_name}`"
        )
        
        # Setup session with proper headers and timeouts
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Referer': url # Sometimes helpful
        }
        
        # Add gofile headers if available
        if headers_dict:
            headers.update(headers_dict)
        
        timeout_config = aiohttp.ClientTimeout(
            total=None,  # No total timeout, individual components have timeouts
            connect=DOWNLOAD_CONNECT_TIMEOUT,  # 60 seconds to connect
            sock_read=DOWNLOAD_READ_TIMEOUT   # 600 seconds (10 min) between reads
        )
        
        actual_downloaded_size = 0 # Track bytes for final verification

        async with aiohttp.ClientSession(headers=headers, timeout=timeout_config) as session:
            
            # First, make a head request to get content-length and check for redirects
            try:
                async with session.head(url, allow_redirects=True) as head_response:
                    head_response.raise_for_status()
                    total_size = int(head_response.headers.get('content-length', 0))
                    content_type = head_response.headers.get('content-type', 'application/octet-stream')
                    final_url = str(head_response.url) # Get the final URL after redirects

                    logger.info(f"HEAD request for {url}: Status {head_response.status}, Size: {total_size}, Type: {content_type}, Final URL: {final_url}")

                    if final_url != url:
                        # If redirect occurred, update file_name from final_url if it's better
                        new_file_name = get_filename_from_url(final_url, fallback_name=file_name)
                        if new_file_name != file_name:
                            base_dir = os.path.dirname(dest_path)
                            dest_path = os.path.join(base_dir, new_file_name)
                            file_name = new_file_name
                            logger.info(f"Updated filename due to redirect: {file_name}")

                    # Update status with file info after HEAD request
                    await smart_progress_editor(
                        status_message,
                        f"📡 **Download Starting...**\n\n"
                        f"📁 **File:** `{file_name}`\n"
                        f"📊 **Size:** `{get_human_readable_size(total_size) if total_size > 0 else 'Unknown'}`\n"
                        f"📋 **Type:** `{content_type.split(';')[0].strip()}`" # Clean up content type
                    )

            except aiohttp.ClientError as e:
                logger.warning(f"HEAD request failed for {url}: {e}. Proceeding with GET directly.")
                total_size = 0 # Reset total_size if HEAD failed
                content_type = 'application/octet-stream' # Default content type
                await smart_progress_editor(
                    status_message,
                    f"📡 **Download Starting (HEAD failed, trying GET directly)...**\n\n"
                    f"📁 **File:** `{file_name}`\n"
                    f"📊 **Size:** `Unknown`\n"
                    f"📋 **Type:** `{content_type}`"
                )
            
            # Now perform the actual download using the helper function with retries
            actual_downloaded_size = await _perform_download_request(session, url, dest_path, status_message, total_size)
                
            # Verify download
            actual_file_size_on_disk = os.path.getsize(dest_path)
            if total_size > 0 and actual_file_size_on_disk != total_size:
                logger.error(f"File size mismatch: expected {total_size}, got {actual_file_size_on_disk} for {dest_path}")
                os.remove(dest_path)
                
                error_text = f"""
❌ **Download Failed!**

📁 **File:** `{file_name}`
🚨 **Error:** File size mismatch
📊 **Expected:** `{get_human_readable_size(total_size)}`
📊 **Received:** `{get_human_readable_size(actual_file_size_on_disk)}`

💡 **Tip:** Try downloading again or check your internet connection.
"""
                await smart_progress_editor(status_message, error_text.strip())
                return None
            
            # Success
            elapsed_time = time.time() - start_time
            success_text = f"""
✅ **Download Complete!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(actual_file_size_on_disk)}`
⏱ **Time:** `{elapsed_time:.1f}s`
🚀 **Avg Speed:** `{get_speed(start_time, actual_file_size_on_disk)}`

🔄 **Next:** Preparing for merge...
"""
            await smart_progress_editor(status_message, success_text.strip())
            return dest_path
                
    except RetryError as e:
        error_msg = f"Download failed after multiple retries for '{file_name}': {e.last_attempt.exception()}"
        logger.error(error_msg)
        if os.path.exists(dest_path):
            os.remove(dest_path) # Clean up incomplete file
        await smart_progress_editor(
            status_message,
            f"❌ **Download Failed!**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"🚨 **Error:** `{e.last_attempt.exception().__class__.__name__}: {str(e.last_attempt.exception())}`\n"
            f"💡 **Tip:** Network instability or server issues. Try again later."
        )
        return None
    except aiohttp.ClientResponseError as e:
        error_text = f"""
❌ **Download Failed!**

📁 **File:** `{file_name}`
🚨 **HTTP Error:** `{e.status} - {e.message}`

💡 **Possible Solutions:**
• Check if the URL is correct and accessible
• Try the download link in a browser first
• Contact the file provider if link is expired
"""
        logger.error(f"HTTP response error during final download: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        await smart_progress_editor(status_message, error_text.strip())
        return None
    except aiohttp.ClientError as e:
        error_text = f"""
❌ **Connection Error!**

📁 **File:** `{file_name}`
🚨 **Network Error:** `{type(e).__name__}: {str(e)}`

💡 **Possible Solutions:**
• Check your internet connection
• Verify the URL is accessible
• Try again after a few minutes
• Contact support if problem persists
"""
        logger.error(f"Aiohttp client error: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        await smart_progress_editor(status_message, error_text.strip())
        return None
        
    except Exception as e:
        error_text = f"""
❌ **Download Failed!**

📁 **File:** `{file_name}`
🚨 **Error:** `{type(e).__name__}: {str(e)}`

💡 **Tip:** Please try again or contact support if the problem continues.
"""
        logger.error(f"General download error for {file_name}: {e}", exc_info=True)
        if os.path.exists(dest_path):
            os.remove(dest_path) # Clean up incomplete file
        await smart_progress_editor(status_message, error_text.strip())
        return None

# The rest of the file remains the same (download_from_tg and other functions)
# ... [rest of the code remains unchanged] ...

async def download_from_tg(message, user_id: int, status_message) -> str | None:
    """Enhanced Telegram download with professional progress tracking."""
    
    try:
        # Setup paths
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_download_dir, exist_ok=True)
        
        # Get file information
        file_obj = None
        file_name = "Unknown File"
        file_size = 0
        duration = 0
        resolution = "N/A"
        
        if message.video:
            file_obj = message.video
            file_name = file_obj.file_name or f"video_{message.id}.mp4"
            file_size = file_obj.file_size
            duration = file_obj.duration or 0
            width = getattr(file_obj, 'width', 0)
            height = getattr(file_obj, 'height', 0)
            resolution = f"{width}x{height}" if width and height else "Unknown"
        elif message.document:
            file_obj = message.document
            file_name = file_obj.file_name or f"document_{message.id}"
            file_size = file_obj.file_size
        elif message.photo: # Handle photos too
            # Telegram photos are usually downloaded as JPEGs without a direct file_name attribute on message.photo
            # We'll pick the largest size (last in the list)
            file_obj = message.photo[-1]
            file_name = f"photo_{file_obj.file_id}.jpg"
            file_size = file_obj.file_size
            resolution = f"{file_obj.width}x{file_obj.height}"
        elif message.audio: # Handle audio too
            file_obj = message.audio
            file_name = file_obj.file_name or f"audio_{message.id}.mp3"
            file_size = file_obj.file_size
            duration = file_obj.duration or 0
            
        else:
            await smart_progress_editor(status_message, "❌ **Error:** No downloadable file found in message (video, document, photo, audio expected).")
            logger.warning(f"No downloadable file found in message: {message.id}")
            return None
        
        # Validate file size (Telegram has a 2GB limit for bots uploading, possibly similar for downloading)
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            error_text = f"""
❌ **File Too Large!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
🚨 **Limit:** `2GB (Telegram API Limit)`

💡 **Tip:** Try splitting the file or use a different sharing method.
"""
            await smart_progress_editor(status_message, error_text.strip())
            return None
        
        # Prevent overwriting if file already exists
        dest_path_initial = os.path.join(user_download_dir, file_name)
        if os.path.exists(dest_path_initial):
            base, ext = os.path.splitext(file_name)
            timestamp = datetime.now().strftime("_%H%M%S")
            file_name = f"{base}{timestamp}{ext}"
            dest_path = os.path.join(user_download_dir, file_name)
            logger.warning(f"Telegram file '{file_name}' already exists, saving as '{os.path.basename(dest_path)}'")
        else:
            dest_path = dest_path_initial

        # Initial status with file details
        initial_text = f"""
📡 **Starting Telegram Download...**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
⏱ **Duration:** `{duration // 60}:{duration % 60:02d}` (if video/audio)
📐 **Resolution:** `{resolution}` (if video/photo)
"""
        await smart_progress_editor(status_message, initial_text.strip())
        
        # Progress tracking variables
        start_time = time.time()
        
        async def progress_callback(current, total):
            """Enhanced progress callback with detailed information."""
            # Use global throttle for consistency
            now = time.time()
            message_key = f"{status_message.chat.id}_{status_message.id}"
            last_time = last_edit_time.get(message_key, 0)

            if (now - last_time) < EDIT_THROTTLE_SECONDS and current < total:
                return
            last_edit_time[message_key] = now # Update only if we're actually sending
            
            progress = current / total
            speed = get_speed(start_time, current)
            eta = get_time_left(start_time, current, total)
            
            progress_text = f"""
📥 **Downloading from Telegram...**

📁 **File:** `{file_name}`
📊 **Total Size:** `{get_human_readable_size(total)}`

{get_progress_bar(progress)} `{progress:.1%}`

📈 **Downloaded:** `{get_human_readable_size(current)}`
🚀 **Speed:** `{speed}`
⏱ **ETA:** `{eta}`
📡 **Status:** {'Complete!' if current >= total else 'Downloading...'}
"""
            await smart_progress_editor(status_message, progress_text.strip())
        
        # Download the file
        file_path = await message.download(
            file_name=dest_path,
            progress=progress_callback
        )
        
        # Verify download
        if not os.path.exists(file_path):
            await smart_progress_editor(status_message, "❌ **Download Failed:** File not found after download.")
            logger.error(f"File '{file_path}' not found after Telegram download.")
            return None
        
        actual_size = os.path.getsize(file_path)
        if actual_size != file_size:
            logger.warning(f"Telegram download size mismatch for '{file_name}': expected {file_size}, got {actual_size}")
            # Decide if this is a critical error or just a warning. For now, it's a warning.
            # You might want to remove the file if the mismatch is significant.
        
        # Success message
        elapsed_time = time.time() - start_time
        success_text = f"""
✅ **Telegram Download Complete!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(actual_size)}`
⏱ **Time:** `{elapsed_time:.1f}s`
🚀 **Avg Speed:** `{get_speed(start_time, actual_size)}`

🔄 **Next:** Preparing for merge...
"""
        await smart_progress_editor(status_message, success_text.strip())
        return file_path
        
    except Exception as e:
        extracted_file_name = file_name # Use the most recent file_name
        
        error_text = f"""
❌ **Telegram Download Failed!**

📁 **File:** `{extracted_file_name}`
🚨 **Error:** `{type(e).__name__}: {str(e)}`

💡 **Possible Solutions:**
• Check if the file is still available on Telegram
• Ensure stable internet connection
• Try forwarding the file and downloading again
• Contact support if problem persists
"""
        logger.error(f"Telegram download error for '{extracted_file_name}': {e}", exc_info=True)
        # Attempt to clean up any partially downloaded file
        if 'dest_path' in locals() and os.path.exists(dest_path):
            try:
                os.remove(dest_path)
                logger.info(f"Cleaned up partial Telegram download: {dest_path}")
            except Exception as clean_e:
                logger.error(f"Error cleaning up partial Telegram download: {clean_e}")
        await smart_progress_editor(status_message, error_text.strip())
        return None

# Additional utility functions
def cleanup_failed_downloads(user_id: int):
    """Clean up failed or incomplete downloads."""
    try:
        user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        if os.path.exists(user_download_dir):
            for filename in os.listdir(user_download_dir):
                file_path = os.path.join(user_download_dir, filename)
                if os.path.isfile(file_path):
                    # Remove files that are too small (e.g., less than 50KB, likely incomplete)
                    if os.path.getsize(file_path) < 50 * 1024:
                        os.remove(file_path)
                        logger.info(f"Cleaned up incomplete download (size < 50KB): {filename}")
    except Exception as e:
        logger.error(f"Error during cleanup of user {user_id} directory: {e}")


def get_download_info(file_path: str) -> dict:
    """Get information about a downloaded file."""
    try:
        if not os.path.exists(file_path):
            return {"exists": False}
        
        stat_info = os.stat(file_path)
        return {
            "exists": True,
            "size": stat_info.st_size,
            "size_human": get_human_readable_size(stat_info.st_size),
            "created": datetime.fromtimestamp(stat_info.st_ctime),
            "modified": datetime.fromtimestamp(stat_info.st_mtime),
            "filename": os.path.basename(file_path)
        }
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        return {"exists": False, "error": str(e)}

# Progress bar styles (matching uploader.py)
PROGRESS_STYLES = {
    "default": {"filled": "█", "empty": "░"},
    "modern": {"filled": "▰", "empty": "▱"},
    "dots": {"filled": "●", "empty": "○"},
    "blocks": {"filled": "■", "empty": "□"},
}

def get_styled_progress_bar(progress: float, length: int = 20, style: str = "default") -> str:
    """Get a styled progress bar."""
    style_chars = PROGRESS_STYLES.get(style, PROGRESS_STYLES["default"])
    filled_len = int(length * progress)
 
