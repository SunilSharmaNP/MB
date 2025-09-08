# helpers/merger.py - Your enhanced merger with integration modifications
import asyncio
import os
import time
import json
import logging
import re
import shutil
from typing import List, Optional, Dict, Any
from collections import Counter
from config import config
from utils import get_video_properties, get_progress_bar, get_time_left

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = 2.0

async def smart_progress_editor(status_message, text: str):
    """Smart progress editor with throttling."""
    if not status_message or not hasattr(status_message, 'chat'):
        return
    message_key = f"{status_message.chat.id}_{status_message.id}"
    now = time.time()
    last_time = last_edit_time.get(message_key, 0)
    if (now - last_time) > EDIT_THROTTLE_SECONDS:
        try:
            await status_message.edit_text(text)
            last_edit_time[message_key] = now
        except Exception as e:
            logger.debug(f"Progress update failed: {e}")

async def merge_videos(video_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Main video merging function using your enhanced merger."""
    if not video_files or len(video_files) < 2:
        raise ValueError("At least 2 video files are required for merging")
    
    # Get video information for all files
    video_infos = []
    for file_path in video_files:
        info = await get_detailed_video_info(file_path)
        if not info:
            raise ValueError(f"Could not get video information for: {os.path.basename(file_path)}")
        video_infos.append(info)
    
    # Check if videos can be fast-merged
    if videos_are_identical_for_merge(video_infos):
        return await fast_merge_identical_videos(video_files, user_id, status_message, video_infos, output_filename)
    else:
        return await complex_merge_videos(video_files, user_id, status_message, video_infos, output_filename)

async def merge_video_with_audio(video_file: str, audio_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Merge video with multiple audio tracks."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        output_path = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        output_path = os.path.join(user_download_dir, f"merged_audio_{int(time.time())}.mkv")
    
    # Build FFmpeg command for audio merging
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y']
    
    # Add video input
    cmd.extend(['-i', video_file])
    
    # Add audio inputs
    for audio_file in audio_files:
        cmd.extend(['-i', audio_file])
    
    # Map video stream
    cmd.extend(['-map', '0:v'])
    
    # Map all audio streams
    for i in range(len(audio_files)):
        cmd.extend(['-map', f'{i+1}:a'])
    
    # Codec settings
    cmd.extend(['-c:v', 'copy', '-c:a', 'copy'])
    
    # Output
    cmd.append(output_path)
    
    if status_message:
        await smart_progress_editor(status_message, "🎵 **Starting audio merge...**")
    
    process = await asyncio.create_subprocess_exec(*cmd, stderr=asyncio.subprocess.PIPE)
    
    # Track progress
    await track_merge_progress(process, 0, status_message, "Audio Merge")
    
    await process.wait()
    
    if process.returncode == 0 and os.path.exists(output_path):
        return output_path
    return None

async def merge_video_with_subtitles(video_file: str, subtitle_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Merge video with subtitle files."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        output_path = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        output_path = os.path.join(user_download_dir, f"merged_subs_{int(time.time())}.mkv")
    
    # Build FFmpeg command for subtitle merging
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y']
    
    # Add video input
    cmd.extend(['-i', video_file])
    
    # Add subtitle inputs
    for sub_file in subtitle_files:
        cmd.extend(['-i', sub_file])
    
    # Map video and audio streams
    cmd.extend(['-map', '0:v', '-map', '0:a?'])
    
    # Map subtitle streams
    for i in range(len(subtitle_files)):
        cmd.extend(['-map', f'{i+1}:s'])
    
    # Codec settings
    cmd.extend(['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'copy'])
    
    # Output
    cmd.append(output_path)
    
    if status_message:
        await smart_progress_editor(status_message, "📝 **Starting subtitle merge...**")
    
    process = await asyncio.create_subprocess_exec(*cmd, stderr=asyncio.subprocess.PIPE)
    
    # Track progress
    await track_merge_progress(process, 0, status_message, "Subtitle Merge")
    
    await process.wait()
    
    if process.returncode == 0 and os.path.exists(output_path):
        return output_path
    return None

# [Include rest of your merger.py functions here...]
