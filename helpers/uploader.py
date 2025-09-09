# helpers/uploader.py - Complete upload functionality
import asyncio
import os
import time
import json
import logging
import aiohttp
import requests
from typing import Optional, Callable, Dict, Any
from pyrogram import Client
from pyrogram.types import Message
from config import config
from utils import get_human_readable_size, create_progress_text, smart_progress_editor

logger = logging.getLogger(__name__)

class UploadError(Exception):
    """Custom exception for upload errors."""
    pass

async def upload_to_telegram(client: Client, file_path: str, chat_id: int, progress_callback: Optional[Callable] = None, caption: str = "", as_document: bool = False, thumbnail: str = None) -> Optional[Message]:
    """Upload file to Telegram with progress tracking."""
    try:
        if not os.path.exists(file_path):
            raise UploadError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        if file_size > config.MAX_FILE_SIZE:
            raise UploadError(f"File too large: {get_human_readable_size(file_size)}")
        
        filename = os.path.basename(file_path)
        start_time = time.time()
        
        async def progress_handler(current: int, total: int):
            if progress_callback:
                progress = current / total if total > 0 else 0
                elapsed = time.time() - start_time
                speed = get_human_readable_size(current / (elapsed + 0.1)) + "/s"
                eta = get_time_left(start_time, current, total)
                
                progress_text = create_progress_text(
                    "📤 Uploading to Telegram",
                    filename,
                    progress,
                    speed,
                    eta
                )
                
                await progress_callback(progress_text)
        
        # Determine file type and upload accordingly
        from utils import get_file_type
        file_type = get_file_type(filename)
        
        if as_document or file_type == 'unknown':
            # Upload as document
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                progress=progress_handler,
                thumb=thumbnail
            )
        elif file_type == 'video':
            # Upload as video
            message = await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                progress=progress_handler,
                thumb=thumbnail,
                supports_streaming=True
            )
        elif file_type == 'audio':
            # Upload as audio
            message = await client.send_audio(
                chat_id=chat_id,
                audio=file_path,
                caption=caption,
                progress=progress_handler,
                thumb=thumbnail
            )
        else:
            # Fallback to document
            message = await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                progress=progress_handler,
                thumb=thumbnail
            )
        
        logger.info(f"✅ Successfully uploaded to Telegram: {filename}")
        return message
        
    except Exception as e:
        logger.error(f"❌ Failed to upload to Telegram: {e}")
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
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=3600),
            connector=aiohttp.TCPConnector(limit=100)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_server(self) -> str:
        """Get the best server for upload."""
        try:
            async with self.session.get(f"{self.base_url}/getServer") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('status') == 'ok':
                        return data['data']['server']
        except Exception as e:
            logger.warning(f"Failed to get GoFile server: {e}")
        
        return "store1"  # Fallback server
    
    async def upload_file(self, file_path: str, progress_callback: Optional[Callable] = None, folder_id: str = None) -> Optional[Dict[str, Any]]:
        """Upload file to GoFile with progress tracking."""
        try:
            if not os.path.exists(file_path):
                raise UploadError(f"File not found: {file_path}")
            
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            if file_size == 0:
                raise UploadError("File is empty")
            
            # Get upload server
            server = await self.get_server()
            upload_url = f"https://{server}.gofile.io/uploadFile"
            
            start_time = time.time()
            uploaded = 0
            
            # Prepare form data
            data = aiohttp.FormData()
            if folder_id:
                data.add_field('folderId', folder_id)
            if self.token:
                data.add_field('token', self.token)
            
            # Add file with progress tracking
            async def file_sender():
                nonlocal uploaded
                with open(file_path, 'rb') as f:
                    chunk_size = config.CHUNK_SIZE
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        uploaded += len(chunk)
                        
                        # Update progress
                        if progress_callback:
                            progress = uploaded / file_size
                            elapsed = time.time() - start_time
                            speed = get_human_readable_size(uploaded / (elapsed + 0.1)) + "/s"
                            eta = get_time_left(start_time, uploaded, file_size)
                            
                            progress_text = create_progress_text(
                                "☁️ Uploading to GoFile",
                                filename,
                                progress,
                                speed,
                                eta
                            )
                            
                            await progress_callback(progress_text)
                        
                        yield chunk
            
            data.add_field('file', file_sender(), filename=filename, content_type='application/octet-stream')
            
            # Upload file
            async with self.session.post(upload_url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get('status') == 'ok':
                        file_info = result['data']
                        
                        logger.info(f"✅ Successfully uploaded to GoFile: {filename}")
                        
                        return {
                            'success': True,
                            'file_id': file_info.get('fileId'),
                            'filename': filename,
                            'size': file_size,
                            'download_url': file_info.get('downloadPage'),
                            'direct_url': file_info.get('directLink'),
                            'server': server
                        }
                    else:
                        raise UploadError(f"GoFile API error: {result.get('message', 'Unknown error')}")
                else:
                    raise UploadError(f"HTTP {response.status}: {response.reason}")
                    
        except Exception as e:
            logger.error(f"❌ GoFile upload failed: {e}")
            raise UploadError(f"GoFile upload failed: {str(e)}")
    
    async def create_folder(self, name: str, parent_folder: str = None) -> Optional[str]:
        """Create a new folder in GoFile."""
        try:
            if not self.token:
                logger.warning("No GoFile token provided, cannot create folders")
                return None
            
            data = {
                'createFolder': name,
                'token': self.token
            }
            
            if parent_folder:
                data['parentFolderId'] = parent_folder
            
            async with self.session.post(f"{self.base_url}/createFolder", data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('status') == 'ok':
                        return result['data']['folderId']
                        
        except Exception as e:
            logger.error(f"Failed to create GoFile folder: {e}")
        
        return None

async def dual_upload(client: Client, file_path: str, chat_id: int, progress_callback: Optional[Callable] = None, caption: str = "", as_document: bool = False, thumbnail: str = None, gofile_folder: str = None) -> Dict[str, Any]:
    """Upload to both Telegram and GoFile simultaneously."""
    
    results = {
        'telegram': {'success': False, 'message': None, 'error': None},
        'gofile': {'success': False, 'data': None, 'error': None}
    }
    
    filename = os.path.basename(file_path)
    
    async def telegram_upload():
        try:
            if progress_callback:
                await progress_callback("📤 **Starting Telegram upload...**")
            
            message = await upload_to_telegram(
                client, file_path, chat_id, 
                progress_callback, caption, as_document, thumbnail
            )
            
            results['telegram']['success'] = True
            results['telegram']['message'] = message
            
        except Exception as e:
            results['telegram']['error'] = str(e)
            logger.error(f"Telegram upload failed: {e}")
    
    async def gofile_upload():
        try:
            if progress_callback:
                await progress_callback("☁️ **Starting GoFile upload...**")
            
            async with GofileUploader() as uploader:
                data = await uploader.upload_file(
                    file_path, progress_callback, gofile_folder
                )
                
                results['gofile']['success'] = True
                results['gofile']['data'] = data
                
        except Exception as e:
            results['gofile']['error'] = str(e)
            logger.error(f"GoFile upload failed: {e}")
    
    # Run both uploads simultaneously
    if progress_callback:
        await progress_callback(
            f"""
📤 **Dual Upload Started!**

📁 **File:** `{filename}`
📊 **Size:** `{get_human_readable_size(os.path.getsize(file_path))}`

🚀 **Uploading to both platforms...**
"""
        )
    
    await asyncio.gather(
        telegram_upload(),
        gofile_upload(),
        return_exceptions=True
    )
    
    # Generate results summary
    summary = f"📤 **Dual Upload Complete!**\n\n"
    summary += f"📁 **File:** `{filename}`\n\n"
    
    if results['telegram']['success']:
        summary += "✅ **Telegram:** Success\n"
    else:
        summary += f"❌ **Telegram:** {results['telegram']['error']}\n"
    
    if results['gofile']['success']:
        summary += "✅ **GoFile:** Success\n"
        if results['gofile']['data']:
            summary += f"🔗 **Link:** {results['gofile']['data']['download_url']}\n"
    else:
        summary += f"❌ **GoFile:** {results['gofile']['error']}\n"
    
    if progress_callback:
        await progress_callback(summary)
    
    return results

async def generate_thumbnail(video_path: str, output_path: str = None, timestamp: str = "00:00:05") -> Optional[str]:
    """Generate thumbnail from video file."""
    try:
        if not output_path:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(os.path.dirname(video_path), f"{base_name}_thumb.jpg")
        
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-ss', timestamp,
            '-vframes', '1',
            '-vf', 'scale=320:240',
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
            logger.info(f"✅ Thumbnail generated: {output_path}")
            return output_path
        else:
            logger.error(f"Thumbnail generation failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Thumbnail generation error: {e}")
        return None
