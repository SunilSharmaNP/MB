# helpers/uploader.py - Complete upload functionality
import asyncio
import os
import aiohttp
import logging
import time
import json
from typing import Optional, Callable, Dict, Any
from PIL import Image
import subprocess
from pyrogram.types import Message
from config import config
from utils import get_human_readable_size, create_progress_text, smart_progress_editor

logger = logging.getLogger(__name__)

class UploadError(Exception):
    """Custom exception for upload errors."""
    pass

async def generate_thumbnail(video_path: str, output_path: str = None, time_offset: str = "00:00:01") -> Optional[str]:
    """Generate thumbnail from video using FFmpeg."""
    try:
        if not output_path:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(os.path.dirname(video_path), f"{base_name}_thumb.jpg")
        
        # FFmpeg command to generate thumbnail
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-ss', time_offset,
            '-vframes', '1',
            '-vf', 'scale=320:240:force_original_aspect_ratio=increase,crop=320:240',
            '-q:v', '2',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output_path):
            # Optimize thumbnail size
            try:
                img = Image.open(output_path)
                img = img.convert('RGB')
                img.thumbnail((320, 240), Image.Resampling.LANCZOS)
                img.save(output_path, 'JPEG', quality=85, optimize=True)
                logger.info(f"✅ Thumbnail generated: {output_path}")
                return output_path
            except Exception as e:
                logger.warning(f"Could not optimize thumbnail: {e}")
                return output_path
        else:
            logger.error(f"Thumbnail generation failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Thumbnail generation error: {e}")
        return None

async def upload_to_telegram(client, chat_id: int, file_path: str, caption: str = "", 
                           progress_callback: Optional[Callable] = None, 
                           thumbnail: str = None, upload_as_doc: bool = False) -> Optional[Message]:
    """Upload file to Telegram with progress tracking."""
    try:
        if not os.path.exists(file_path):
            raise UploadError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Check file size limit
        if file_size > config.MAX_FILE_SIZE:
            raise UploadError(f"File too large: {get_human_readable_size(file_size)}")
        
        start_time = time.time()
        
        async def progress_handler(current: int, total: int):
            if progress_callback:
                progress = current / total if total > 0 else 0
                elapsed = time.time() - start_time
                speed = get_human_readable_size(current / (elapsed + 0.1)) + "/s"
                eta = get_time_left(start_time, current, total)
                
                progress_text = create_progress_text(
                    "📤 Uploading to Telegram",
                    file_name,
                    progress,
                    speed,
                    eta
                )
                
                await progress_callback(progress_text)
        
        # Determine upload method based on file type and settings
        if upload_as_doc or file_name.lower().endswith(('.zip', '.rar', '.7z', '.pdf', '.txt')):
            # Upload as document
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption[:1024] if caption else "",
                progress=progress_handler,
                thumb=thumbnail if thumbnail and os.path.exists(thumbnail) else None
            )
        else:
            # Check if it's a video file
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']
            if any(file_name.lower().endswith(ext) for ext in video_extensions):
                # Upload as video
                message = await client.send_video(
                    chat_id=chat_id,
                    video=file_path,
                    caption=caption[:1024] if caption else "",
                    progress=progress_handler,
                    thumb=thumbnail if thumbnail and os.path.exists(thumbnail) else None,
                    supports_streaming=True
                )
            else:
                # Upload as document
                message = await client.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=caption[:1024] if caption else "",
                    progress=progress_handler,
                    thumb=thumbnail if thumbnail and os.path.exists(thumbnail) else None
                )
        
        logger.info(f"✅ Uploaded to Telegram: {file_name}")
        return message
        
    except Exception as e:
        logger.error(f"❌ Telegram upload failed: {e}")
        raise UploadError(f"Telegram upload failed: {str(e)}")

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate ETA for uploads."""
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

class GofileUploader:
    """GoFile upload handler with enhanced features."""
    
    def __init__(self, token: str = None):
        self.token = token or config.GOFILE_TOKEN
        self.base_url = "https://api.gofile.io"
        self.upload_server = None
    
    async def get_upload_server(self) -> Optional[str]:
        """Get the best upload server."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/getServer") as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'ok':
                            self.upload_server = data['data']['server']
                            logger.info(f"Got upload server: {self.upload_server}")
                            return self.upload_server
            return None
        except Exception as e:
            logger.error(f"Failed to get upload server: {e}")
            return None
    
    async def upload_file(self, file_path: str, folder_id: str = None, 
                         progress_callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """Upload file to GoFile with progress tracking."""
        try:
            if not os.path.exists(file_path):
                raise UploadError(f"File not found: {file_path}")
            
            # Get upload server if not set
            if not self.upload_server:
                server = await self.get_upload_server()
                if not server:
                    raise UploadError("Could not get upload server")
            
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            start_time = time.time()
            
            # Prepare upload data
            data = aiohttp.FormData()
            if folder_id:
                data.add_field('folderId', folder_id)
            if self.token:
                data.add_field('token', self.token)
            
            # Add file with progress tracking
            with open(file_path, 'rb') as file:
                data.add_field('file', file, filename=file_name)
                
                async with aiohttp.ClientSession() as session:
                    upload_url = f"https://{self.upload_server}.gofile.io/uploadFile"
                    
                    async with session.post(upload_url, data=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            
                            if result.get('status') == 'ok':
                                upload_data = result['data']
                                logger.info(f"✅ GoFile upload successful: {upload_data.get('downloadPage')}")
                                
                                return {
                                    'success': True,
                                    'download_page': upload_data.get('downloadPage'),
                                    'file_id': upload_data.get('fileId'),
                                    'file_name': upload_data.get('fileName'),
                                    'direct_link': upload_data.get('directLink'),
                                    'file_size': file_size
                                }
                            else:
                                raise UploadError(f"GoFile API error: {result.get('message', 'Unknown error')}")
                        else:
                            raise UploadError(f"HTTP {response.status}: Upload failed")
            
        except Exception as e:
            logger.error(f"❌ GoFile upload failed: {e}")
            raise UploadError(f"GoFile upload failed: {str(e)}")
    
    async def create_folder(self, parent_folder_id: str, folder_name: str) -> Optional[str]:
        """Create a folder in GoFile."""
        try:
            if not self.token:
                logger.warning("Token required for folder creation")
                return None
            
            data = {
                'parentFolderId': parent_folder_id,
                'folderName': folder_name,
                'token': self.token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/createFolder", data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('status') == 'ok':
                            return result['data']['folderId']
            return None
            
        except Exception as e:
            logger.error(f"Failed to create folder: {e}")
            return None

async def dual_upload(client, chat_id: int, file_path: str, caption: str = "",
                     progress_callback: Optional[Callable] = None,
                     thumbnail: str = None, upload_as_doc: bool = False) -> Dict[str, Any]:
    """Upload to both Telegram and GoFile simultaneously."""
    results = {
        'telegram': {'success': False, 'message': None, 'error': None},
        'gofile': {'success': False, 'data': None, 'error': None}
    }
    
    file_name = os.path.basename(file_path)
    
    async def telegram_progress(text):
        if progress_callback:
            await progress_callback(f"📤 **Telegram Upload**\n\n{text}")
    
    async def gofile_progress(text):
        if progress_callback:
            await progress_callback(f"☁️ **GoFile Upload**\n\n{text}")
    
    # Upload to Telegram
    try:
        telegram_msg = await upload_to_telegram(
            client, chat_id, file_path, caption, 
            telegram_progress, thumbnail, upload_as_doc
        )
        results['telegram']['success'] = True
        results['telegram']['message'] = telegram_msg
        logger.info(f"✅ Telegram upload completed: {file_name}")
    except Exception as e:
        results['telegram']['error'] = str(e)
        logger.error(f"❌ Telegram upload failed: {e}")
    
    # Upload to GoFile
    try:
        gofile_uploader = GofileUploader()
        gofile_result = await gofile_uploader.upload_file(file_path, progress_callback=gofile_progress)
        results['gofile']['success'] = True
        results['gofile']['data'] = gofile_result
        logger.info(f"✅ GoFile upload completed: {file_name}")
    except Exception as e:
        results['gofile']['error'] = str(e)
        logger.error(f"❌ GoFile upload failed: {e}")
    
    return results

# Utility functions
async def get_video_duration(file_path: str) -> float:
    """Get video duration using FFprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            data = json.loads(stdout.decode())
            return float(data['format'].get('duration', 0))
        else:
            return 0.0
            
    except Exception as e:
        logger.error(f"Failed to get video duration: {e}")
        return 0.0

def format_file_info(file_path: str) -> str:
    """Format file information for upload caption."""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        info = f"""
📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
🕐 **Uploaded:** `{time.strftime('%Y-%m-%d %H:%M:%S')}`

🤖 **Processed by AdvancedMergeBot**
"""
        return info.strip()
        
    except Exception as e:
        logger.error(f"Failed to format file info: {e}")
        return ""

# Clean up function
def cleanup_upload_files(file_paths: list):
    """Clean up temporary files after upload."""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Cleaned up: {file_path}")
        except Exception as e:
            logger.warning(f"Could not clean up {file_path}: {e}")
