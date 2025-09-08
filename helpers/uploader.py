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

async def create_auto_thumbnail(video_path: str, user_id: int) -> str:
    """Create beautiful auto-thumbnail from video middle frame."""
    try:
        user_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
        thumbnail_path = os.path.join(user_dir, f"thumb_{int(time.time())}.jpg")
        
        # Get video properties
        video_info = await get_video_properties(video_path)
        if not video_info or not video_info.get("duration"):
            return None
        
        # Generate thumbnail from middle of video with enhanced settings
        thumbnail_time = video_info["duration"] / 2
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-ss', str(thumbnail_time),
            '-i', video_path,
            '-vframes', '1',
            '-vf', 'scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'mjpeg',
            '-q:v', '2',  # High quality JPEG
            '-y', thumbnail_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if process.returncode == 0 and os.path.exists(thumbnail_path):
            logger.info(f"✅ Auto-thumbnail created: {thumbnail_path}")
            return thumbnail_path
        else:
            logger.warning(f"⚠️ Failed to create thumbnail for {video_path}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Thumbnail creation error: {e}")
        return None

async def upload_to_telegram(client, file_path: str, chat_id: int, status_message=None, as_document: bool = False, thumbnail_path: str = None, caption: str = None, user_id: int = None):
    """Enhanced Telegram upload with beautiful progress and auto-features."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    
    # Check file size limit
    if file_size > config.MAX_FILE_SIZE:
        raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds Telegram limit (2GB)")
    
    # Auto-create thumbnail for videos if not provided
    if not as_document and not thumbnail_path and user_id:
        from utils import get_file_type
        if get_file_type(filename) == 'video':
            thumbnail_path = await create_auto_thumbnail(file_path, user_id)
    
    start_time = time.time()
    
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
                extra_info=f"Mode: {'Document' if as_document else 'Video'}"
            )
            
            await smart_progress_editor(status_message, progress_text)
    
    try:
        # Enhanced caption with metadata
        if not caption:
            file_info = await get_video_properties(file_path) if get_file_type(filename) == 'video' else None
            
            caption = f"""
✨ **Merged by AdvancedMergeBot**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}
"""
            
            if file_info:
                caption += f"""
📐 **Resolution:** {file_info.get('width', 0)}x{file_info.get('height', 0)}
⏱️ **Duration:** {file_info.get('duration_formatted', 'Unknown')}
🎞️ **Codec:** {file_info.get('codec', 'Unknown').upper()}
"""
            
            caption += f"\n🤖 **Powered by AdvancedMergeBot**"
        
        # Upload with enhanced settings
        if as_document:
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                progress=progress_callback,
                thumb=thumbnail_path,
                file_name=filename
            )
        else:
            message = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                progress=progress_callback,
                thumb=thumbnail_path,
                duration=int(file_info.get('duration', 0)) if file_info else None,
                width=file_info.get('width') if file_info else None,
                height=file_info.get('height') if file_info else None,
                supports_streaming=True
            )
        
        # Final success message
        upload_time = time.time() - start_time
        if status_message:
            await smart_progress_editor(status_message, f"""
✅ **Telegram Upload Complete!**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}
⏱️ **Upload Time:** `{upload_time:.1f}s`
🚀 **Speed:** {get_human_readable_size(file_size/upload_time)}/s

🎉 **Successfully uploaded to Telegram!**
""")
        
        logger.info(f"✅ Telegram upload successful: {filename}")
        return message
        
    except Exception as e:
        error_msg = f"❌ **Telegram Upload Failed**\n\n`{str(e)}`"
        if status_message:
            await status_message.edit_text(error_msg)
        logger.error(f"❌ Telegram upload failed: {e}")
        raise e
    
    finally:
        # Clean up auto-generated thumbnail
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except:
                pass

class GofileUploader:
    """Enhanced GoFile uploader with beautiful progress and advanced features."""
    
    def __init__(self, token=None):
        self.api_url = "https://api.gofile.io/"
        self.token = token or config.GOFILE_TOKEN
        if not self.token:
            logger.warning("⚠️ GOFILE_TOKEN not found. Using anonymous upload.")
        self.chunk_size = GOFILE_CHUNK_SIZE
        self.session = None
    
    async def _get_session(self):
        """Get or create aiohttp session with enhanced settings."""
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(
                total=GOFILE_UPLOAD_TIMEOUT,
                connect=30,
                sock_read=300
            )
            self.session = ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        """Close session gracefully."""
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
        """Get optimal GoFile server with retry logic."""
        logger.info("🔍 Finding best GoFile server...")
        session = await self._get_session()
        
        async with session.get(f"{self.api_url}servers") as resp:
            resp.raise_for_status()
            result = await resp.json()
            
            if result.get("status") == "ok":
                servers = result["data"]["servers"]
                # Select server based on location preference or random
                selected_server = choice(servers)["name"]
                logger.info(f"✅ Selected GoFile server: {selected_server}")
                return selected_server
            else:
                raise Exception(f"GoFile API error: {result.get('message', 'Unknown error')}")
    
    async def upload_file(self, file_path: str, status_message=None):
        """Enhanced GoFile upload with real-time progress and beautiful UI."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        # Check file size limits
        if file_size > (10 * 1024 * 1024 * 1024):  # 10GB GoFile limit
            raise ValueError(f"File size {get_human_readable_size(file_size)} exceeds GoFile limit (10GB)")
        
        # Get upload server
        try:
            if status_message:
                await smart_progress_editor(status_message, """
🔗 **Connecting to GoFile**

🌐 **Status:** Finding optimal server...
📡 **Network:** Establishing connection...
""")
            
            server = await self._get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
            
        except Exception as e:
            error_msg = f"""
❌ **GoFile Connection Failed**

🚨 **Error:** `{str(e)}`
💡 **Tip:** Check internet connection or try again later
"""
            if status_message:
                await status_message.edit_text(error_msg)
            raise e
        
        # Initialize upload with beautiful progress
        if status_message:
            await smart_progress_editor(status_message, f"""
🚀 **Starting GoFile Upload**

📁 **File:** `{filename[:40]}{'...' if len(filename) > 40 else ''}`
💾 **Size:** {get_human_readable_size(file_size)}
🌐 **Server:** `{server}.gofile.io`
🔑 **Auth:** {'Premium' if self.token else 'Anonymous'}

⚡ **Preparing upload stream...**
""")
        
        start_time = time.time()
        uploaded_bytes = 0
        
        try:
            session = await self._get_session()
            
            # Custom file reader for progress tracking
            class ProgressFileReader:
                def __init__(self, file_path, chunk_size, progress_callback):
                    self.file_path = file_path
                    self.chunk_size = chunk_size
                    self.progress_callback = progress_callback
                    self.uploaded = 0
                    self.total_size = os.path.getsize(file_path)
                
                async def __aiter__(self):
                    with open(self.file_path, 'rb') as f:
                        while True:
                            chunk = f.read(self.chunk_size)
                            if not chunk:
                                break
                            
                            self.uploaded += len(chunk)
                            if self.progress_callback:
                                await self.progress_callback(self.uploaded, self.total_size)
                            
                            yield chunk
                            await asyncio.sleep(0.001)  # Prevent blocking
            
            async def progress_callback(current, total):
                nonlocal uploaded_bytes
                uploaded_bytes = current
                
                if status_message:
                    progress = current / total if total > 0 else 0
                    
                    progress_text = create_progress_text(
                        title="🌐 Uploading to GoFile",
                        filename=filename,
                        progress=progress,
                        current_size=current,
                        total_size=total,
                        start_time=start_time,
                        extra_info=f"Server: {server}.gofile.io"
                    )
                    
                    await smart_progress_editor(status_message, progress_text)
            
            # Prepare form data
            form = FormData()
            if self.token:
                form.add_field("token", self.token)
            
            # Add file with progress tracking
            file_reader = ProgressFileReader(file_path, self.chunk_size, progress_callback)
            form.add_field(
                "file",
                file_reader,
                filename=filename,
                content_type="application/octet-stream"
            )
            
            # Execute upload with retry logic
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                retry=retry_if_exception_type(Exception),
                reraise=True
            )
            async def _perform_upload():
                async with session.post(upload_url, data=form) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            
            response_data = await _perform_upload()
            
            # Process response
            if response_data.get("status") == "ok":
                download_page = response_data["data"]["downloadPage"]
                file_id = response_data["data"].get("fileId", "unknown")
                upload_time = time.time() - start_time
                
                success_message = f"""
✅ **GoFile Upload Complete!**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}
⏱️ **Upload Time:** `{upload_time:.1f}s`
🚀 **Average Speed:** {get_human_readable_size(file_size/upload_time) if upload_time > 0 else '0 B'}/s

🔗 **Download Link:**
`{download_page}`

📋 **File ID:** `{file_id}`
🌐 **Server:** `{server}.gofile.io`

🎉 **Successfully uploaded to GoFile!**
"""
                
                if status_message:
                    await smart_progress_editor(status_message, success_message)
                
                logger.info(f"✅ GoFile upload successful: {filename}")
                
                return {
                    "status": "success",
                    "download_url": download_page,
                    "file_id": file_id,
                    "server": server,
                    "upload_time": upload_time,
                    "file_size": file_size
                }
            
            else:
                error_msg = response_data.get("message", "Unknown upload error")
                raise Exception(f"GoFile upload failed: {error_msg}")
                
        except Exception as e:
            error_message = f"""
❌ **GoFile Upload Failed**

📁 **File:** `{filename}`
🚨 **Error:** `{str(e)}`

💡 **Suggestions:**
• Check internet connection
• Try again in a few minutes  
• File might be too large
• Server may be busy
"""
            if status_message:
                await status_message.edit_text(error_message)
            
            logger.error(f"❌ GoFile upload failed: {e}")
            raise e
        
        finally:
            # Clean up
            await self.close()

# Utility functions for dual upload
async def dual_upload(client, file_path: str, chat_id: int, user_id: int, status_message=None, upload_settings: dict = None):
    """Upload file to both Telegram and GoFile with beautiful progress management."""
    upload_settings = upload_settings or {}
    
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    results = {
        "telegram": None,
        "gofile": None,
        "errors": []
    }
    
    try:
        if status_message:
            await smart_progress_editor(status_message, f"""
🚀 **Starting Dual Upload**

📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}

📤 **Destinations:** Telegram + GoFile
⚡ **Mode:** Parallel upload
""")
        
        # Upload to Telegram
        try:
            telegram_msg = await upload_to_telegram(
                client=client,
                file_path=file_path,
                chat_id=chat_id,
                status_message=status_message,
                as_document=upload_settings.get('as_document', False),
                user_id=user_id
            )
            results["telegram"] = telegram_msg
            
        except Exception as e:
            results["errors"].append(f"Telegram upload failed: {str(e)}")
            logger.error(f"❌ Telegram upload error: {e}")
        
        # Upload to GoFile
        try:
            gofile_uploader = GofileUploader()
            gofile_result = await gofile_uploader.upload_file(file_path, status_message)
            results["gofile"] = gofile_result
            
        except Exception as e:
            results["errors"].append(f"GoFile upload failed: {str(e)}")
            logger.error(f"❌ GoFile upload error: {e}")
        
        # Final results summary
        success_count = sum(1 for result in [results["telegram"], results["gofile"]] if result is not None)
        
        if success_count > 0:
            summary = f"""
🎉 **Upload Summary**

📁 **File:** `{filename}`
✅ **Successful:** `{success_count}/2 platforms`

"""
            
            if results["telegram"]:
                summary += "📱 **Telegram:** ✅ Uploaded successfully\n"
            
            if results["gofile"]:
                summary += f"🌐 **GoFile:** ✅ {results['gofile']['download_url']}\n"
            
            if results["errors"]:
                summary += f"\n⚠️ **Errors:** `{len(results['errors'])} issues`"
            
            if status_message:
                await smart_progress_editor(status_message, summary)
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Dual upload error: {e}")
        if status_message:
            await status_message.edit_text(f"❌ **Dual Upload Failed**\n\n`{str(e)}`")
        raise e
