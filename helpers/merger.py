# helpers/merger.py - Complete video merger with all functionality
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
from utils import get_video_properties, get_progress_bar, get_time_left, create_progress_text, get_human_readable_size

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Progress throttling
last_edit_time = {}
EDIT_THROTTLE_SECONDS = config.EDIT_THROTTLE_SECONDS

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

async def get_detailed_video_info(file_path: str) -> Optional[Dict[str, Any]]:
    """Get comprehensive video information using ffprobe."""
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
        
        video_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
        subtitle_streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'subtitle']
        
        if not video_streams:
            logger.error(f"No video stream found in {file_path}")
            return None
        
        video_stream = video_streams[0]
        audio_stream = audio_streams[0] if audio_streams else None
        
        # Parse frame rate
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 3) if int(den) != 0 else 30.0
        else:
            fps = round(float(fps_str), 3)
        
        # Get codec information
        video_codec = video_stream.get('codec_name', '').lower()
        audio_codec = audio_stream.get('codec_name', '').lower() if audio_stream else None
        
        # Pixel format and profile
        pixel_format = video_stream.get('pix_fmt', 'yuv420p')
        profile = video_stream.get('profile', 'Unknown')
        
        # Audio properties
        audio_sample_rate = int(audio_stream.get('sample_rate', 48000)) if audio_stream else 48000
        audio_channels = int(audio_stream.get('channels', 2)) if audio_stream else 2
        
        # Container and format info
        container = data['format'].get('format_name', '').lower()
        duration = float(data['format'].get('duration', 0))
        bitrate = int(data['format'].get('bit_rate', 0)) if data['format'].get('bit_rate') else None
        
        return {
            'file_path': file_path,
            'filename': os.path.basename(file_path),
            'has_video': True,
            'has_audio': audio_stream is not None,
            'has_subtitles': len(subtitle_streams) > 0,
            # Video properties
            'width': int(video_stream['width']),
            'height': int(video_stream['height']),
            'fps': fps,
            'video_codec': video_codec,
            'pixel_format': pixel_format,
            'profile': profile,
            # Audio properties
            'audio_codec': audio_codec,
            'audio_sample_rate': audio_sample_rate,
            'audio_channels': audio_channels,
            # General properties
            'duration': duration,
            'bitrate': bitrate,
            'container': container,
            'file_size': os.path.getsize(file_path),
            # Stream counts
            'video_streams_count': len(video_streams),
            'audio_streams_count': len(audio_streams),
            'subtitle_streams_count': len(subtitle_streams)
        }
        
    except Exception as e:
        logger.error(f"Failed to get video info for {file_path}: {e}")
        return None

def videos_are_compatible_for_fast_merge(video_infos: List[Dict[str, Any]]) -> tuple[bool, str]:
    """Enhanced compatibility check with detailed reason."""
    if not video_infos or len(video_infos) < 2:
        return False, "Need at least 2 videos"
    
    reference = video_infos[0]
    
    # Critical parameters for fast concatenation
    critical_params = {
        'width': 'Resolution width',
        'height': 'Resolution height',
        'fps': 'Frame rate',
        'video_codec': 'Video codec',
        'audio_codec': 'Audio codec',
        'pixel_format': 'Pixel format',
        'audio_sample_rate': 'Audio sample rate',
        'audio_channels': 'Audio channels'
    }
    
    for i, video_info in enumerate(video_infos[1:], 1):
        for param, description in critical_params.items():
            ref_val = reference.get(param)
            vid_val = video_info.get(param)
            
            # Handle None values (missing audio)
            if ref_val is None and vid_val is None:
                continue
            if ref_val is None or vid_val is None:
                return False, f"{description} mismatch: Video 1 has {ref_val}, Video {i+1} has {vid_val}"
            
            # Special handling for fps (allow small differences)
            if param == 'fps':
                if abs(ref_val - vid_val) > 0.1:
                    return False, f"Frame rate mismatch: {ref_val:.3f} vs {vid_val:.3f} fps"
            else:
                if ref_val != vid_val:
                    return False, f"{description} mismatch: {ref_val} vs {vid_val}"
    
    return True, "All videos compatible for fast merge"

async def get_total_duration(video_files: List[str]) -> float:
    """Calculate total duration."""
    total_duration = 0.0
    successful_files = 0
    
    for file_path in video_files:
        try:
            info = await get_detailed_video_info(file_path)
            if info and info.get('duration', 0) > 0:
                total_duration += info['duration']
                successful_files += 1
        except Exception as e:
            logger.warning(f"Could not get duration for {file_path}: {e}")
    
    logger.info(f"Total duration calculated: {total_duration:.2f}s from {successful_files}/{len(video_files)} files")
    return total_duration

async def track_merge_progress(process, total_duration: float, status_message, merge_type: str, output_filename: str):
    """Enhanced progress tracking with beautiful formatting."""
    start_time = time.time()
    last_update = 0
    
    while True:
        try:
            line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
            if not line:
                break
            
            line = line.decode().strip()
            
            # Parse FFmpeg progress information
            if 'time=' in line:
                time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                if time_match and total_duration > 0:
                    hours, minutes, seconds = time_match.groups()
                    current_time = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    progress = min(current_time / total_duration, 1.0)
                    elapsed = time.time() - start_time
                    
                    if time.time() - last_update > 2.0:  # Update every 2 seconds
                        speed_multiplier = current_time / elapsed if elapsed > 0 else 1.0
                        eta = ((total_duration - current_time) / speed_multiplier) if speed_multiplier > 0 else 0
                        
                        progress_text = f"""
🎬 **{merge_type} in Progress**

📁 **Output:** `{output_filename[:40]}{'...' if len(output_filename) > 40 else ''}`
⏱️ **Duration:** `{total_duration:.0f}s`

{get_progress_bar(progress, 25)} `{progress:.1%}`

📊 **Processed:** `{current_time:.0f}s` / `{total_duration:.0f}s`
⚡ **Speed:** `{speed_multiplier:.2f}x`
🕐 **Elapsed:** `{elapsed:.0f}s`
⏰ **ETA:** `{eta:.0f}s remaining`

💡 **Status:** Processing video streams...
"""
                        
                        await smart_progress_editor(status_message, progress_text.strip())
                        last_update = time.time()
                        
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.debug(f"Progress tracking error: {e}")
            break

async def fast_merge_identical_videos(video_files: List[str], user_id: int, status_message, video_infos: List[Dict[str, Any]], output_filename: str = None) -> Optional[str]:
    """Ultra-fast merge with enhanced compatibility."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    # Enhanced compatibility check
    is_compatible, reason = videos_are_compatible_for_fast_merge(video_infos)
    if not is_compatible:
        await status_message.edit_text(
            f"⚠️ **Fast Merge Not Possible**\n\n"
            f"**Reason:** {reason}\n\n"
            f"🔄 **Switching to compatible merge mode...**"
        )
        return await complex_merge_videos(video_files, user_id, status_message, video_infos, output_filename)
    
    # Generate output filename
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        final_output = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        timestamp = int(time.time())
        final_output = os.path.join(user_download_dir, f"merged_video_{timestamp}.mkv")
    
    # Create file list for FFmpeg concat
    concat_file = os.path.join(user_download_dir, f"concat_list_{user_id}_{int(time.time())}.txt")
    
    try:
        # Write file list
        with open(concat_file, 'w', encoding='utf-8') as f:
            for video_file in video_files:
                # Escape file paths for FFmpeg
                escaped_path = video_file.replace("'", "'\"'\"'")
                f.write(f"file '{escaped_path}'\n")
        
        # Get total duration for progress tracking
        total_duration = await get_total_duration(video_files)
        
        # Prepare FFmpeg command for fast concatenation
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',  # Copy streams without re-encoding
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts',
            final_output
        ]
        
        # Start progress message
        await status_message.edit_text(
            f"""
🚀 **Ultra-Fast Merge Started!**

🎬 **Mode:** Lossless concatenation
📁 **Files:** `{len(video_files)} videos`
⏱️ **Total Duration:** `{total_duration:.0f}s`
🎯 **Output:** `{os.path.basename(final_output)}`

💡 **Status:** Initializing fast merge...
"""
        )
        
        # Execute FFmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(process, total_duration, status_message, "🚀 Ultra-Fast Merge", os.path.basename(final_output))
        
        # Wait for completion
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            # Clean up
            try:
                os.remove(concat_file)
            except:
                pass
            
            logger.info(f"✅ Fast merge successful: {final_output}")
            return final_output
        else:
            logger.error(f"Fast merge failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Fast merge error: {e}")
        return None
    finally:
        # Clean up concat file
        try:
            if os.path.exists(concat_file):
                os.remove(concat_file)
        except:
            pass

async def complex_merge_videos(video_files: List[str], user_id: int, status_message, video_infos: List[Dict[str, Any]], output_filename: str = None) -> Optional[str]:
    """Complex merge with re-encoding for compatibility."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    # Generate output filename
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        final_output = os.path.join(user_download_dir, f"{base_name}_reencoded.mkv")
    else:
        timestamp = int(time.time())
        final_output = os.path.join(user_download_dir, f"merged_reencoded_{timestamp}.mkv")
    
    try:
        # Get total duration
        total_duration = await get_total_duration(video_files)
        
        # Determine best common format from video infos
        if video_infos:
            # Find most common resolution
            resolutions = [(info['width'], info['height']) for info in video_infos]
            common_resolution = max(set(resolutions), key=resolutions.count)
            
            # Find best codec
            video_codecs = [info['video_codec'] for info in video_infos]
            common_codec = max(set(video_codecs), key=video_codecs.count)
        else:
            common_resolution = (1920, 1080)
            common_codec = 'h264'
        
        # Build FFmpeg command for complex merge
        cmd = ['ffmpeg', '-y']
        
        # Add input files
        for video_file in video_files:
            cmd.extend(['-i', video_file])
        
        # Filter complex for concatenation with re-encoding
        filter_parts = []
        for i in range(len(video_files)):
            filter_parts.append(f"[{i}:v]scale={common_resolution[0]}:{common_resolution[1]}:force_original_aspect_ratio=decrease,pad={common_resolution[0]}:{common_resolution[1]}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];")
            filter_parts.append(f"[{i}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[a{i}];")
        
        # Concatenate all streams
        video_concat = ''.join([f"[v{i}]" for i in range(len(video_files))]) + f"concat=n={len(video_files)}:v=1:a=0[outv];"
        audio_concat = ''.join([f"[a{i}]" for i in range(len(video_files))]) + f"concat=n={len(video_files)}:v=0:a=1[outa]"
        
        filter_complex = ''.join(filter_parts) + video_concat + audio_concat
        
        cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '18',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            final_output
        ])
        
        # Start progress message
        await status_message.edit_text(
            f"""
🔄 **Compatible Merge Started!**

🎬 **Mode:** Re-encoding for compatibility
📁 **Files:** `{len(video_files)} videos`
⏱️ **Total Duration:** `{total_duration:.0f}s`
🎯 **Output:** `{os.path.basename(final_output)}`
📐 **Resolution:** `{common_resolution[0]}x{common_resolution[1]}`

💡 **Status:** Initializing compatible merge...
"""
        )
        
        # Execute FFmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(process, total_duration, status_message, "🔄 Compatible Merge", os.path.basename(final_output))
        
        # Wait for completion
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            logger.info(f"✅ Complex merge successful: {final_output}")
            return final_output
        else:
            logger.error(f"Complex merge failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Complex merge error: {e}")
        return None

async def merge_videos(video_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Main video merge function with intelligent mode selection."""
    try:
        # Extract file paths from video_files (handle both file paths and file objects)
        file_paths = []
        for video_file in video_files:
            if isinstance(video_file, dict):
                if 'file_path' in video_file:
                    file_paths.append(video_file['file_path'])
                elif 'message' in video_file:
                    # Download Telegram file first
                    from helpers.downloader import download_telegram_file
                    downloaded_path = await download_telegram_file(video_file['message'], user_id)
                    if downloaded_path:
                        file_paths.append(downloaded_path)
            else:
                file_paths.append(video_file)
        
        if len(file_paths) < 2:
            logger.error("Need at least 2 video files to merge")
            return None
        
        # Get video information for all files
        video_infos = []
        for file_path in file_paths:
            info = await get_detailed_video_info(file_path)
            if info:
                video_infos.append(info)
            else:
                logger.error(f"Could not get video info for {file_path}")
                return None
        
        # Check compatibility and choose merge method
        is_compatible, reason = videos_are_compatible_for_fast_merge(video_infos)
        
        if is_compatible:
            logger.info("Using fast merge (lossless concatenation)")
            return await fast_merge_identical_videos(file_paths, user_id, status_message, video_infos, output_filename)
        else:
            logger.info(f"Using complex merge (re-encoding): {reason}")
            return await complex_merge_videos(file_paths, user_id, status_message, video_infos, output_filename)
            
    except Exception as e:
        logger.error(f"Merge videos error: {e}")
        return None

async def merge_video_with_audio(video_file, audio_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Merge video with additional audio tracks."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    try:
        # Handle video file (could be dict or path)
        if isinstance(video_file, dict):
            if 'file_path' in video_file:
                video_path = video_file['file_path']
            elif 'message' in video_file:
                from helpers.downloader import download_telegram_file
                video_path = await download_telegram_file(video_file['message'], user_id)
            else:
                logger.error("Invalid video file format")
                return None
        else:
            video_path = video_file
        
        # Handle audio files
        audio_paths = []
        for audio_file in audio_files:
            if isinstance(audio_file, dict):
                if 'file_path' in audio_file:
                    audio_paths.append(audio_file['file_path'])
                elif 'message' in audio_file:
                    from helpers.downloader import download_telegram_file
                    downloaded_path = await download_telegram_file(audio_file['message'], user_id)
                    if downloaded_path:
                        audio_paths.append(downloaded_path)
            else:
                audio_paths.append(audio_file)
        
        if not video_path or not audio_paths:
            logger.error("Invalid video or audio files")
            return None
        
        # Generate output filename
        if output_filename:
            base_name = os.path.splitext(output_filename)[0]
            final_output = os.path.join(user_download_dir, f"{base_name}_with_audio.mkv")
        else:
            timestamp = int(time.time())
            final_output = os.path.join(user_download_dir, f"video_with_audio_{timestamp}.mkv")
        
        # Get video duration for progress tracking
        video_info = await get_detailed_video_info(video_path)
        duration = video_info['duration'] if video_info else 0
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-y', '-i', video_path]
        
        # Add audio inputs
        for audio_path in audio_paths:
            cmd.extend(['-i', audio_path])
        
        # Map video stream
        cmd.extend(['-map', '0:v'])
        
        # Map original audio stream if exists
        if video_info and video_info.get('has_audio'):
            cmd.extend(['-map', '0:a'])
        
        # Map additional audio streams
        for i, _ in enumerate(audio_paths, 1):
            cmd.extend(['-map', f'{i}:a'])
        
        # Output settings
        cmd.extend([
            '-c:v', 'copy',  # Copy video without re-encoding
            '-c:a', 'aac',   # Re-encode audio to AAC
            '-b:a', '128k',  # Audio bitrate
            final_output
        ])
        
        # Start progress message
        await status_message.edit_text(
            f"""
🎵 **Audio Merge in Progress**

🎬 **Video:** `{os.path.basename(video_path)}`
🎵 **Audio Tracks:** `{len(audio_paths)} additional`
🎯 **Output:** `{os.path.basename(final_output)}`

💡 **Status:** Adding audio tracks...
"""
        )
        
        # Execute FFmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(process, duration, status_message, "🎵 Audio Integration", os.path.basename(final_output))
        
        # Wait for completion
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            logger.info(f"✅ Audio merge successful: {final_output}")
            return final_output
        else:
            logger.error(f"Audio merge failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Audio merge error: {e}")
        return None

async def merge_video_with_subtitles(video_file, subtitle_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Merge video with subtitle tracks."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    try:
        # Handle video file
        if isinstance(video_file, dict):
            if 'file_path' in video_file:
                video_path = video_file['file_path']
            elif 'message' in video_file:
                from helpers.downloader import download_telegram_file
                video_path = await download_telegram_file(video_file['message'], user_id)
            else:
                logger.error("Invalid video file format")
                return None
        else:
            video_path = video_file
        
        # Handle subtitle files
        subtitle_paths = []
        for subtitle_file in subtitle_files:
            if isinstance(subtitle_file, dict):
                if 'file_path' in subtitle_file:
                    subtitle_paths.append(subtitle_file['file_path'])
                elif 'message' in subtitle_file:
                    from helpers.downloader import download_telegram_file
                    downloaded_path = await download_telegram_file(subtitle_file['message'], user_id)
                    if downloaded_path:
                        subtitle_paths.append(downloaded_path)
            else:
                subtitle_paths.append(subtitle_file)
        
        if not video_path or not subtitle_paths:
            logger.error("Invalid video or subtitle files")
            return None
        
        # Generate output filename
        if output_filename:
            base_name = os.path.splitext(output_filename)[0]
            final_output = os.path.join(user_download_dir, f"{base_name}_with_subs.mkv")
        else:
            timestamp = int(time.time())
            final_output = os.path.join(user_download_dir, f"video_with_subs_{timestamp}.mkv")
        
        # Get video duration for progress tracking
        video_info = await get_detailed_video_info(video_path)
        duration = video_info['duration'] if video_info else 0
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-y', '-i', video_path]
        
        # Add subtitle inputs
        for subtitle_path in subtitle_paths:
            cmd.extend(['-i', subtitle_path])
        
        # Map video and audio streams
        cmd.extend(['-map', '0:v'])
        if video_info and video_info.get('has_audio'):
            cmd.extend(['-map', '0:a'])
        
        # Map subtitle streams
        for i, _ in enumerate(subtitle_paths, 1):
            cmd.extend(['-map', f'{i}:s'])
        
        # Output settings
        cmd.extend([
            '-c:v', 'copy',  # Copy video without re-encoding
            '-c:a', 'copy',  # Copy audio without re-encoding
            '-c:s', 'srt',   # Convert subtitles to SRT
            final_output
        ])
        
        # Start progress message
        await status_message.edit_text(
            f"""
📝 **Subtitle Merge in Progress**

🎬 **Video:** `{os.path.basename(video_path)}`
📝 **Subtitles:** `{len(subtitle_paths)} tracks`
🎯 **Output:** `{os.path.basename(final_output)}`

💡 **Status:** Embedding subtitle tracks...
"""
        )
        
        # Execute FFmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(process, duration, status_message, "📝 Subtitle Integration", os.path.basename(final_output))
        
        # Wait for completion
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            logger.info(f"✅ Subtitle merge successful: {final_output}")
            return final_output
        else:
            logger.error(f"Subtitle merge failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Subtitle merge error: {e}")
        return None

# Utility function for cleanup
def cleanup_temp_files(file_list: List[str]):
    """Clean up temporary files."""
    for file_path in file_list:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"🗑️ Cleaned up: {file_path}")
        except Exception as e:
            logger.warning(f"Could not clean up {file_path}: {e}")
