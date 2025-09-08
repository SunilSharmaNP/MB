# Enhanced uploader with beautiful progress and dual upload support
import os
import time
import asyncio
from aiohttp import ClientSession, FormData, ClientTimeout
from random import choice
from config import config
from utils import get_human_readable_size, get_progress_bar, get_video_properties, create_progress_text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
import logging

logger = logging.getLogger(__name__)

# Global variables for progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = config.EDIT_THROTTLE_SECONDS

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
            await status_message.edit_text(text, parse_mode="markdown")
            last_edit_time[message_key] = now
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")

async def create_thumbnail(video_path: str, timestamp: float = None) -> str:
    """Create beautiful thumbnail from video."""
    thumbnail_path = f"{os.path.splitext(video_path)[0]}_thumb.jpg"
    
    try:
        metadata = await get_video_properties(video_path)
        if not metadata or not metadata.get("duration"):
            return None
        
        # Use custom timestamp or middle of video
        thumb_time = timestamp if timestamp else metadata["duration"] / 2
        
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-ss', str(thumb_time),
            '-i', video_path,
            '-vframes', '1',
            '-q:v', '2',  # High quality
            '-vf', 'scale=320:240:force_original_aspect_ratio=increase,crop=320:240',
            '-y', thumbnail_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command, 
            stderr=asyncio.subprocess.PIPE
        )
        await process.wait()
        
        if process.returncode == 0 and os.path.exists(thumbnail_path):
            return thumbnail_path
        return None
        
    except Exception as e:
        logger.error(f"Thumbnail creation failed: {e}")
        return None

async def upload_to_telegram(client, file_path: str, chat_id: int, status_message=None, as_document: bool = False, thumbnail_path: str = None, caption: str = None, custom_filename: str = None):
    """Enhanced Telegram upload with beautiful progress."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = os.path.getsize(file_path)
    filename = custom_filename or os.path.basename(file_path)
    
    if file_size > config.MAX_FILE_SIZE:
        raise ValueError(f"File too large: {get_human_readable_size(file_size)} > {get_human_readable_size(config.MAX_FILE_SIZE)}")
    
    start_time = time.time()
    
    # Auto-create thumbnail for videos
    if not thumbnail_path and not as_document:
        file_ext = filename.split('.')[-1].lower()
        if file_ext in config.ALLOWED_EXTENSIONS['video']:
            thumbnail_path = await create_thumbnail(file_path)
    
    async def progress_callback(current, total):
        if status_message:
            progress = current / total if total > 0 else 0
            progress_text = create_progress_text(
                title="📤 Uploading to Telegram",
                filename=filename,
                progress=progress,
                current_size=current,
                total_size=total,
                start_time=start_time,
                extra_info=f"Type: {'Document' if as_document else 'Video'}"
            )
            await smart_progress_editor(status_message, progress_text)
    
    try:
        # Enhanced caption
        if not caption:
            file_info = await get_video_properties(file_path) if not as_document else None
            if file_info:
                caption = f"""
🎬 **{filename}**

📊 **Size:** {get_human_readable_size(file_size)}
⏱️ **Duration:** {file_info.get('duration_formatted', 'Unknown')}
📐 **Resolution:** {file_info.get('width', 0)}x{file_info.get('height', 0)}
🎞️ **Codec:** {file_info.get('codec', 'Unknown').upper()}

🤖 **Merged by AdvancedMergeBot**
"""
            else:
                caption = f"📁 **{filename}**\n💾 **Size:** {get_human_readable_size(file_size)}\n\n🤖 **Processed by AdvancedMergeBot**"
        
        # Upload based on type
        if as_document:
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption[:1024],  # Telegram caption limit
                progress=progress_callback,
                thumb=thumbnail_path,
                file_name=filename
            )
        else:
            message = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption[:1024],
                progress=progress_callback,
                thumb=thumbnail_path,
                duration=int(file_info.get('duration', 0)) if file_info else None,
                width=file_info.get('width') if file_info else None,
                height=file_info.get('height') if file_info else None
            )
        
        # Success message
        upload_time = time.time() - start_time
        if status_message:
            await smart_progress_editor(status_message, f"""
✅ **Telegram Upload Complete!**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}
⏱️ **Time:** `{upload_time:.1f}s`
📤 **Type:** {'Document' if as_document else 'Video'}

🔗 **Message ID:** `{message.id}`
""")
        
        logger.info(f"✅ Telegram upload successful: {filename}")
        return message
        
    except Exception as e:
        if status_message:
            await status_message.edit_text(f"❌ **Telegram Upload Failed**\n\n`{str(e)}`")
        logger.error(f"❌ Telegram upload failed: {e}")
        raise e
    finally:
        # Clean up thumbnail
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except:
                pass

class GofileUploader:
    """Enhanced GoFile uploader with beautiful progress."""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or config.GOFILE_TOKEN
        self.chunk_size = GOFILE_CHUNK_SIZE
        self.session = None
    
    async def _get_session(self):
        """Get or create session."""
        if self.session is None or self.session.closed:
            self.session = ClientSession(
                timeout=ClientTimeout(total=GOFILE_UPLOAD_TIMEOUT)
            )
        return self.session
    
    async def close(self):
        """Close session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    @retry(
        stop=stop_after_attempt(GOFILE_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=GOFILE_RETRY_WAIT_MIN, max=GOFILE_RETRY_WAIT_MAX),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    async def _get_server(self):
        """Get best GoFile server."""
        session = await self._get_session()
        async with session.get(f"{self.api_url}servers") as resp:
            resp.raise_for_status()
            result = await resp.json()
            
            if result.get("status") == "ok":
                servers = result["data"]["servers"]
                selected_server = choice(servers)["name"]
                logger.info(f"Selected GoFile server: {selected_server}")
                return selected_server
            else:
                raise Exception(f"GoFile API error: {result.get('message', 'Unknown error')}")
    
    async def upload_file(self, file_path: str, status_message=None, custom_filename: str = None):
        """Upload file to GoFile with enhanced progress."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = custom_filename or os.path.basename(file_path)
        
        if file_size > (5 * 1024 * 1024 * 1024):  # 5GB limit for free users
            raise ValueError(f"File too large for GoFile: {get_human_readable_size(file_size)}")
        
        try:
            # Get server
            if status_message:
                await smart_progress_editor(status_message, f"""
🔗 **Connecting to GoFile**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}

🌐 **Getting best server...**
""")
            
            server = await self._get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
            
            # Prepare upload
            session = await self._get_session()
            start_time = time.time()
            
            if status_message:
                await smart_progress_editor(status_message, f"""
🚀 **Starting GoFile Upload**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}
🌐 **Server:** `{server}`

⏳ **Preparing upload...**
""")
            
            # Create form data with progress tracking
            with open(file_path, 'rb') as f:
                form = FormData()
                if self.token:
                    form.add_field("token", self.token)
                
                # Custom progress wrapper
                class ProgressFile:
                    def __init__(self, file_obj, callback):
                        self.file = file_obj
                        self.callback = callback
                        self.uploaded = 0
                    
                    def read(self, size=-1):
                        chunk = self.file.read(size)
                        if chunk:
                            self.uploaded += len(chunk)
                            if self.callback:
                                asyncio.create_task(self.callback(self.uploaded))
                        return chunk
                    
                    def __getattr__(self, name):
                        return getattr(self.file, name)
                
                async def update_progress(uploaded):
                    if status_message:
                        progress = uploaded / file_size
                        progress_text = create_progress_text(
                            title="🌐 Uploading to GoFile",
                            filename=filename,
                            progress=progress,
                            current_size=uploaded,
                            total_size=file_size,
                            start_time=start_time,
                            extra_info=f"Server: {server}"
                        )
                        await smart_progress_editor(status_message, progress_text)
                
                progress_file = ProgressFile(f, update_progress)
                form.add_field("file", progress_file, filename=filename)
                
                # Upload with retry
                @retry(
                    stop=stop_after_attempt(GOFILE_RETRY_ATTEMPTS),
                    wait=wait_exponential(multiplier=1, min=GOFILE_RETRY_WAIT_MIN, max=GOFILE_RETRY_WAIT_MAX),
                    retry=retry_if_exception_type(Exception),
                    reraise=True
                )
                async def perform_upload():
                    async with session.post(upload_url, data=form) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                
                result = await perform_upload()
                
                if result.get("status") == "ok":
                    download_page = result["data"]["downloadPage"]
                    file_id = result["data"]["fileId"]
                    
                    upload_time = time.time() - start_time
                    
                    if status_message:
                        await smart_progress_editor(status_message, f"""
✅ **GoFile Upload Complete!**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}
⏱️ **Time:** `{upload_time:.1f}s`
🌐 **Server:** `{server}`

🔗 **Download:** `{download_page}`
🆔 **File ID:** `{file_id}`
""")
                    
                    logger.info(f"✅ GoFile upload successful: {filename}")
                    return {
                        "status": "success",
                        "url": download_page,
                        "file_id": file_id,
                        "server": server,
                        "filename": filename,
                        "size": file_size
                    }
                else:
                    error_msg = result.get("message", "Unknown GoFile error")
                    raise Exception(f"GoFile upload failed: {error_msg}")
                
        except RetryError as e:
            error_msg = f"Failed after {GOFILE_RETRY_ATTEMPTS} attempts: {e.last_attempt.exception()}"
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Upload Failed**\n\n`{error_msg}`")
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            if status_message:
                await status_message.edit_text(f"❌ **GoFile Upload Failed**\n\n`{str(e)}`")
            logger.error(f"❌ GoFile upload failed: {e}")
            raise e

# Utility functions for dual upload
async def upload_to_both(client, file_path: str, chat_id: int, status_message=None, as_document: bool = False, custom_filename: str = None):
    """Upload to both Telegram and GoFile."""
    results = {"telegram": None, "gofile": None}
    
    try:
        # Upload to Telegram first
        if status_message:
            await smart_progress_editor(status_message, "📤 **Starting Telegram upload...**")
        
        telegram_msg = await upload_to_telegram(
            client, file_path, chat_id, status_message, as_document, None, None, custom_filename
        )
        results["telegram"] = telegram_msg
        
        # Upload to GoFile
        if status_message:
            await smart_progress_editor(status_message, "🌐 **Starting GoFile upload...**")
        
        gofile_uploader = GofileUploader()
        try:
            gofile_result = await gofile_uploader.upload_file(file_path, status_message, custom_filename)
            results["gofile"] = gofile_result
        finally:
            await gofile_uploader.close()
        
        # Success summary
        if status_message:
            filename = custom_filename or os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            summary_text = f"""
🎉 **Dual Upload Complete!**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}

✅ **Telegram:** Uploaded successfully
• Message ID: `{telegram_msg.id}`

✅ **GoFile:** Uploaded successfully
• URL: `{results["gofile"]["url"]}`

🎊 **Both uploads completed!**
"""
            await smart_progress_editor(status_message, summary_text)
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Dual upload failed: {e}")
        if status_message:
            await status_message.edit_text(f"❌ **Dual Upload Failed**\n\n`{str(e)}`")
        return results
