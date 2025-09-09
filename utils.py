# utils.py - Complete utility functions for AdvancedMergeBot
import asyncio
import json
import os
import re
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format with emojis."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    size_icons = ["📄", "📋", "💾", "💿", "🗄️"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_icons[i]} {size_bytes:.1f} {size_names[i]}"

def get_progress_bar(percentage: float, length: int = 20, filled_char: str = "█", empty_char: str = "░") -> str:
    """Generate beautiful progress bar with percentage."""
    filled_length = int(length * percentage)
    bar = filled_char * filled_length + empty_char * (length - filled_length)
    return f"[{bar}] {percentage:.1%}"

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate ETA with smart formatting."""
    if current <= 0 or total <= 0:
        return "⏳ Calculating..."
    
    elapsed = time.time() - start_time
    if elapsed <= 0.1:
        return "⏳ Starting..."
    
    rate = current / elapsed
    if rate == 0:
        return "⏳ Calculating..."
    
    remaining_bytes = total - current
    if remaining_bytes <= 0:
        return "✅ Complete!"
    
    remaining_seconds = remaining_bytes / rate
    
    if remaining_seconds < 60:
        return f"⏱️ {int(remaining_seconds)}s left"
    elif remaining_seconds < 3600:
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        return f"⏱️ {minutes}m {seconds}s left"
    else:
        hours = int(remaining_seconds // 3600)
        minutes = int((remaining_seconds % 3600) // 60)
        return f"⏱️ {hours}h {minutes}m left"

def get_speed(start_time: float, current: int) -> str:
    """Calculate speed with beautiful formatting."""
    elapsed = time.time() - start_time
    if elapsed <= 0:
        return "🚀 0 B/s"
    
    speed = current / elapsed
    
    if speed < 1024:
        return f"🐌 {speed:.1f} B/s"
    elif speed < 1024 * 1024:
        return f"🚶 {speed/1024:.1f} KB/s"
    elif speed < 10 * 1024 * 1024:
        return f"🏃 {speed / (1024 * 1024):.1f} MB/s"
    else:
        return f"🚀 {speed / (1024 * 1024):.1f} MB/s"

def get_file_type(filename: str) -> str:
    """Determine file type based on extension."""
    from config import config
    
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    if ext in config.ALLOWED_EXTENSIONS['video']:
        return 'video'
    elif ext in config.ALLOWED_EXTENSIONS['audio']:
        return 'audio' 
    elif ext in config.ALLOWED_EXTENSIONS['subtitle']:
        return 'subtitle'
    else:
        return 'unknown'

async def get_video_properties(file_path: str) -> Optional[Dict[str, Any]]:
    """Get comprehensive video properties using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', file_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"ffprobe failed for {file_path}: {stderr.decode()}")
            return None
        
        data = json.loads(stdout.decode())
        
        # Extract video stream info
        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        subtitle_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'subtitle']
        
        if not video_streams:
            return None
            
        video_stream = video_streams[0]
        audio_stream = audio_streams[0] if audio_streams else None
        
        return {
            'width': int(video_stream['width']),
            'height': int(video_stream['height']),
            'duration': float(data['format'].get('duration', 0)),
            'fps': eval(video_stream.get('r_frame_rate', '30/1')),
            'video_codec': video_stream.get('codec_name', ''),
            'audio_codec': audio_stream.get('codec_name', '') if audio_stream else None,
            'file_size': int(data['format'].get('size', 0)),
            'bitrate': int(data['format'].get('bit_rate', 0)) if data['format'].get('bit_rate') else None,
            'has_audio': audio_stream is not None,
            'has_video': True,
            'streams': {
                'video': len(video_streams),
                'audio': len(audio_streams), 
                'subtitle': len(subtitle_streams)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get video properties for {file_path}: {e}")
        return None

def create_progress_text(operation: str, filename: str, progress: float, speed: str = "", eta: str = "") -> str:
    """Create formatted progress text."""
    progress_bar = get_progress_bar(progress, 20)
    
    text = f"""
🎬 **{operation}**

📁 **File:** `{filename[:40]}{'...' if len(filename) > 40 else ''}`

{progress_bar} `{progress:.1%}`
"""
    
    if speed:
        text += f"\n⚡ **Speed:** `{speed}`"
    if eta:
        text += f"\n⏰ **ETA:** `{eta}`"
        
    return text.strip()

class UserSettings:
    """User settings management."""
    
    def __init__(self, user_id: int, name: str = "Unknown"):
        self.user_id = user_id
        self.name = name
        self.merge_mode = 1  # Default to video merge
        self.upload_as_doc = False
        self.auto_thumbnail = True
        self.allowed = False
        self.banned = False
        self.premium = False
        
        # Load from database (would be implemented with actual database)
        self._load_from_db()
    
    def _load_from_db(self):
        """Load user settings from database."""
        # This would connect to your database
        # For now, using defaults
        pass
    
    def save(self):
        """Save settings to database.""" 
        # Implementation for database save
        pass
    
    def set(self):
        """Alias for save method."""
        self.save()

# Global progress tracking
last_edit_time = {}

async def smart_progress_editor(status_message, text: str, throttle_seconds: float = 2.0):
    """Smart progress editor with throttling to avoid flood limits."""
    if not status_message or not hasattr(status_message, 'chat'):
        return
        
    message_key = f"{status_message.chat.id}_{status_message.id}"
    now = time.time()
    last_time = last_edit_time.get(message_key, 0)
    
    if (now - last_time) > throttle_seconds:
        try:
            await status_message.edit_text(text, parse_mode="markdown")
            last_edit_time[message_key] = now
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")

# Utility functions for file operations
def ensure_directory(directory_path: str):
    """Ensure directory exists."""
    os.makedirs(directory_path, exist_ok=True)

def cleanup_files(file_paths: list):
    """Clean up temporary files."""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Could not remove file {file_path}: {e}")

def get_file_extension(filename: str) -> str:
    """Get file extension in lowercase."""
    return filename.split('.')[-1].lower() if '.' in filename else ''

def is_video_file(filename: str) -> bool:
    """Check if file is a video file."""
    return get_file_type(filename) == 'video'

def is_audio_file(filename: str) -> bool:
    """Check if file is an audio file."""
    return get_file_type(filename) == 'audio'

def is_subtitle_file(filename: str) -> bool:
    """Check if file is a subtitle file."""
    return get_file_type(filename) == 'subtitle'
