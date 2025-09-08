import asyncio
import json
import os
import re
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta

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
        
        # Load from database
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
