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
        return f"🚶 {speed / 1024:.1f} KB/s"
    elif speed < 10 * 1024 * 1024:
        return f"🏃 {speed / (1024 * 1024):.1f} MB/s"
    else:
        return f"🚀 {speed / (1024 * 1024):.1f} MB/s"

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
            return None
            
        data = json.loads(stdout.decode())
        
        # Extract video stream info
        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        subtitle_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'subtitle']
        
        if not video_streams:
            return None
            
        video_stream = video_streams[0]
        format_info = data.get('format', {})
        
        # Parse frame rate
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 2) if int(den) != 0 else 30.0
        else:
            fps = round(float(fps_str), 2)
        
        duration = float(format_info.get('duration', 0))
        
        return {
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'duration': duration,
            'duration_formatted': format_duration(duration),
            'fps': fps,
            'bitrate': video_stream.get('bit_rate'),
            'codec': video_stream.get('codec_name'),
            'format': format_info.get('format_name'),
            'size': int(format_info.get('size', 0)),
            'video_streams': len(video_streams),
            'audio_streams': len(audio_streams),
            'subtitle_streams': len(subtitle_streams),
            'has_audio': len(audio_streams) > 0,
            'has_subtitles': len(subtitle_streams) > 0
        }
        
    except Exception as e:
        logger.error(f"Error getting video properties: {e}")
        return None

def format_duration(seconds: float) -> str:
    """Format duration in HH:MM:SS format."""
    if seconds <= 0:
        return "00:00:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize filename for cross-platform compatibility."""
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    
    # Trim whitespace and dots
    sanitized = sanitized.strip(' .')
    
    # Limit length
    if len(sanitized) > max_length:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:(max_length - len(ext))] + ext
    
    return sanitized or "unnamed_file"

def get_file_type(filename: str) -> str:
    """Determine file type based on extension."""
    from config import config
    
    ext = filename.split('.')[-1].lower()
    
    if ext in config.ALLOWED_EXTENSIONS['video']:
        return 'video'
    elif ext in config.ALLOWED_EXTENSIONS['audio']:
        return 'audio'
    elif ext in config.ALLOWED_EXTENSIONS['subtitle']:
        return 'subtitle'
    else:
        return 'unknown'

def create_progress_text(
    title: str,
    filename: str,
    progress: float,
    current_size: int,
    total_size: int,
    start_time: float,
    extra_info: str = ""
) -> str:
    """Create beautiful progress text with emojis and formatting."""
    
    speed = get_speed(start_time, current_size)
    eta = get_time_left(start_time, current_size, total_size)
    progress_bar = get_progress_bar(progress)
    
    text = f"""
✨ **{title}**

📁 **File:** `{filename[:50]}{'...' if len(filename) > 50 else ''}`
📊 **Size:** {get_human_readable_size(total_size)}

{progress_bar}

📈 **Progress:** {get_human_readable_size(current_size)} / {get_human_readable_size(total_size)}
{speed} | {eta}
"""
    
    if extra_info:
        text += f"\n💡 **Info:** {extra_info}"
    
    return text.strip()

def validate_url(url: str) -> tuple[bool, str]:
    """Validate download URL."""
    from urllib.parse import urlparse
    
    if not url or not isinstance(url, str):
        return False, "Invalid URL format"
    
    if len(url) > 2048:
        return False, "URL too long"

    parsed_url = urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        return False, "URL must have a scheme (http/https) and network location."
    
    if parsed_url.scheme not in ('http', 'https'):
        return False, "URL scheme must be http or https."
    
    return True, "Valid"

def get_filename_from_url(url: str, fallback_name: str = None) -> str:
    """Extract filename from URL with fallbacks."""
    from urllib.parse import urlparse, unquote
    
    try:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        filename = unquote(filename)
        
        if '?' in filename:
            filename = filename.split('?')[0]

        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip(' .').strip()
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)

        if not filename or len(filename) < 5:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = fallback_name or f"download_{timestamp_str}.bin"

        if '.' not in filename:
            filename += '.bin'

        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:(200 - len(ext))] + ext

        return filename
    except Exception as e:
        logger.error(f"Error extracting filename: {e}")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        return fallback_name or f"download_error_{timestamp_str}.bin"

class UserSettings:
    """Enhanced user settings management."""
    
    def __init__(self, user_id: int, name: str):
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
