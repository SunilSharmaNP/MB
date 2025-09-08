# utils.py - Utility functions for the custom modules
import asyncio
import json
import os
import re
from typing import Dict, Any, Optional

def get_human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def get_progress_bar(percentage: float, length: int = 20) -> str:
    """Generate a progress bar string."""
    filled_length = int(length * percentage)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return f"[{bar}]"

def get_time_left(start_time: float, current: int, total: int) -> str:
    """Calculate estimated time remaining."""
    import time
    
    if current <= 0 or total <= 0:
        return "Calculating..."
    
    elapsed = time.time() - start_time
    if elapsed <= 0.1:
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

async def get_video_properties(file_path: str) -> Optional[Dict[str, Any]]:
    """Get video properties using ffprobe."""
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
        
        # Extract basic video information
        video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
        if not video_stream:
            return None
            
        return {
            'width': int(video_stream.get('width', 0)),
            'height': int(video_stream.get('height', 0)),
            'duration': float(data.get('format', {}).get('duration', 0)),
            'bitrate': video_stream.get('bit_rate'),
            'codec': video_stream.get('codec_name'),
            'fps': video_stream.get('r_frame_rate', '30/1')
        }
        
    except Exception:
        return None
