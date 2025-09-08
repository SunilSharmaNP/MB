# Enhanced bulletproof merger with beautiful UI and advanced features
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
    """Get comprehensive video information using ffprobe with enhanced formatting."""
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
        
        # Parse frame rate with enhanced precision
        fps_str = video_stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = round(float(num) / float(den), 3) if int(den) != 0 else 30.0
        else:
            fps = round(float(fps_str), 3)
            
        # Get enhanced codec information
        video_codec = video_stream.get('codec_name', '').lower()
        audio_codec = audio_stream.get('codec_name', '').lower() if audio_stream else None
        
        # Enhanced pixel format and profile detection
        pixel_format = video_stream.get('pix_fmt', 'yuv420p')
        profile = video_stream.get('profile', 'Unknown')
        level = video_stream.get('level', 'Unknown')
        
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
            'level': level,
            
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
    """Calculate total duration with enhanced error handling."""
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
    """Ultra-fast merge with enhanced compatibility and beautiful progress."""
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
    
    # Generate enhanced output filename
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        final_output = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        timestamp = int(time.time())
        total_files = len(video_files)
        final_output = os.path.join(user_download_dir, f"FastMerged_{total_files}files_{timestamp}.mkv")
    
    inputs_file = os.path.join(user_download_dir, f"merge_list_{int(time.time())}.txt")
    
    try:
        # Show initial merge info
        total_size = sum(info.get('file_size', 0) for info in video_infos)
        total_duration = sum(info.get('duration', 0) for info in video_infos)
        
        init_text = f"""
🚀 **Starting Ultra-Fast Merge**

📊 **Files:** `{len(video_files)} videos`
💾 **Total Size:** {get_human_readable_size(total_size)}
⏱️ **Total Duration:** `{total_duration:.0f}s ({total_duration/60:.1f} min)`
📐 **Resolution:** `{video_infos[0]['width']}x{video_infos[0]['height']}`
🎞️ **Format:** `{video_infos[0]['video_codec'].upper()}` + `{video_infos[0].get('audio_codec', 'No Audio').upper()}`

🔧 **Method:** Fast concatenation (no re-encoding)
"""
        await smart_progress_editor(status_message, init_text.strip())
        
        # Create inputs file with proper path escaping
        with open(inputs_file, 'w', encoding='utf-8') as f:
            for file_path in video_files:
                # Proper path escaping for FFmpeg
                abs_path = os.path.abspath(file_path).replace('\\', '/')
                escaped_path = abs_path.replace("'", "'\"'\"'")
                f.write(f"file '{escaped_path}'\n")
        
        # Enhanced FFmpeg command for fast concatenation
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'info',
            '-f', 'concat', '-safe', '0', '-i', inputs_file,
            
            # Stream copying (no re-encoding) 
            '-c', 'copy',
            
            # Enhanced metadata
            '-metadata', 'title=Merged by AdvancedMergeBot',
            '-metadata', f'comment=Fast merged {len(video_files)} files',
            '-metadata', 'encoder=FFmpeg via AdvancedMergeBot',
            
            # Output format
            '-f', 'matroska',
            
            # Overwrite output
            '-y',
            
            # Progress reporting
            '-progress', 'pipe:2',
            
            final_output
        ]
        
        logger.info(f"🚀 Fast merge command: {' '.join(cmd[:10])}... (truncated)")
        
        # Execute merge with progress tracking
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(
            process, 
            total_duration, 
            status_message, 
            "Ultra-Fast Merge", 
            os.path.basename(final_output)
        )
        
        # Wait for completion
        stdout, stderr = await process.communicate()
        
        # Clean up inputs file
        try:
            os.remove(inputs_file)
        except:
            pass
        
        # Check result
        if process.returncode == 0 and os.path.exists(final_output):
            output_size = os.path.getsize(final_output)
            merge_time = time.time() - time.time()  # This should be calculated from start
            
            success_text = f"""
✅ **Fast Merge Completed Successfully!**

📁 **Output:** `{os.path.basename(final_output)}`
💾 **Size:** {get_human_readable_size(output_size)}
⏱️ **Duration:** `{total_duration:.0f}s`
🚀 **Method:** Ultra-fast concatenation
💡 **Quality:** Lossless (no re-encoding)

🎉 **Ready for upload!**
"""
            await smart_progress_editor(status_message, success_text.strip())
            
            logger.info(f"✅ Fast merge successful: {final_output}")
            return final_output
            
        else:
            error_output = stderr.decode().strip()
            logger.error(f"❌ Fast merge failed: {error_output}")
            await status_message.edit_text(
                f"❌ **Fast Merge Failed**\n\n"
                f"**Error:** `{error_output[-200:] if len(error_output) > 200 else error_output}`\n\n"
                f"🔄 **Trying compatible merge...**"
            )
            return await complex_merge_videos(video_files, user_id, status_message, video_infos, output_filename)
            
    except Exception as e:
        logger.error(f"❌ Fast merge exception: {e}")
        await status_message.edit_text(
            f"❌ **Fast Merge Error**\n\n"
            f"**Exception:** `{str(e)}`\n\n"
            f"🔄 **Switching to compatible merge...**"
        )
        return await complex_merge_videos(video_files, user_id, status_message, video_infos, output_filename)

async def complex_merge_videos(video_files: List[str], user_id: int, status_message, video_infos: List[Dict[str, Any]], output_filename: str = None) -> Optional[str]:
    """Complex merge with re-encoding for incompatible videos."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        final_output = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        timestamp = int(time.time())
        final_output = os.path.join(user_download_dir, f"ComplexMerged_{len(video_files)}files_{timestamp}.mkv")
    
    try:
        # Analyze videos for optimal settings
        max_width = max(info['width'] for info in video_infos)
        max_height = max(info['height'] for info in video_infos)
        common_fps = Counter(info['fps'] for info in video_infos).most_common(1)[0][0]
        
        total_size = sum(info.get('file_size', 0) for info in video_infos)
        total_duration = sum(info.get('duration', 0) for info in video_infos)
        
        await smart_progress_editor(status_message, f"""
🔄 **Starting Compatible Merge**

📊 **Analysis:**
• Files: `{len(video_files)} videos`
• Total Size: {get_human_readable_size(total_size)}
• Duration: `{total_duration:.0f}s`
• Output Resolution: `{max_width}x{max_height}`
• Target FPS: `{common_fps:.2f}`

⚙️ **Method:** Re-encoding for compatibility
🎯 **Quality:** High quality H.264
""")
        
        # Build complex FFmpeg command
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y']
        
        # Add all input files
        for file_path in video_files:
            cmd.extend(['-i', file_path])
        
        # Complex filter for scaling and concatenation
        filter_complex = []
        for i in range(len(video_files)):
            filter_complex.append(f"[{i}:v]scale={max_width}:{max_height}:force_original_aspect_ratio=decrease,pad={max_width}:{max_height}:(ow-iw)/2:(oh-ih)/2,fps={common_fps}[v{i}]")
            filter_complex.append(f"[{i}:a]aresample=48000,volume=1.0[a{i}]")
        
        # Concatenation
        v_inputs = ''.join(f"[v{i}]" for i in range(len(video_files)))
        a_inputs = ''.join(f"[a{i}]" for i in range(len(video_files)))
        filter_complex.append(f"{v_inputs}concat=n={len(video_files)}:v=1:a=0[outv]")
        filter_complex.append(f"{a_inputs}concat=n={len(video_files)}:v=0:a=1[outa]")
        
        cmd.extend(['-filter_complex', ';'.join(filter_complex)])
        cmd.extend(['-map', '[outv]', '-map', '[outa]'])
        
        # High quality encoding settings
        cmd.extend([
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
            '-c:a', 'aac', '-b:a', '192k', '-ac', '2',
            '-movflags', '+faststart',
            '-metadata', 'title=Advanced Merged Video',
            '-progress', 'pipe:2',
            final_output
        ])
        
        logger.info(f"🔄 Complex merge starting...")
        
        # Execute merge
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(
            process,
            total_duration,
            status_message,
            "Compatible Merge",
            os.path.basename(final_output)
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            output_size = os.path.getsize(final_output)
            
            await smart_progress_editor(status_message, f"""
✅ **Compatible Merge Completed!**

📁 **Output:** `{os.path.basename(final_output)}`
💾 **Size:** {get_human_readable_size(output_size)}
📐 **Resolution:** `{max_width}x{max_height}`
🎞️ **Quality:** High (CRF 18)

🎉 **Ready for upload!**
""")
            
            logger.info(f"✅ Complex merge successful: {final_output}")
            return final_output
        else:
            error_output = stderr.decode().strip()
            logger.error(f"❌ Complex merge failed: {error_output}")
            await status_message.edit_text(f"❌ **Merge Failed**\n\n`{error_output[-300:]}`")
            return None
            
    except Exception as e:
        logger.error(f"❌ Complex merge exception: {e}")
        await status_message.edit_text(f"❌ **Merge Error**\n\n`{str(e)}`")
        return None

# Main merge functions
async def merge_videos(video_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Main video merging function with intelligent mode selection."""
    if not video_files or len(video_files) < 2:
        raise ValueError("At least 2 video files required for merging")
    
    # Get video information
    await smart_progress_editor(status_message, "🔍 **Analyzing video files...**")
    
    video_infos = []
    for i, file_path in enumerate(video_files, 1):
        await smart_progress_editor(status_message, f"🔍 **Analyzing video {i}/{len(video_files)}...**\n\n📁 `{os.path.basename(file_path)}`")
        
        info = await get_detailed_video_info(file_path)
        if not info:
            raise ValueError(f"Could not analyze video: {os.path.basename(file_path)}")
        video_infos.append(info)
    
    # Choose merge strategy
    is_compatible, reason = videos_are_compatible_for_fast_merge(video_infos)
    
    if is_compatible:
        logger.info("🚀 Using fast merge (no re-encoding)")
        return await fast_merge_identical_videos(video_files, user_id, status_message, video_infos, output_filename)
    else:
        logger.info(f"🔄 Using compatible merge: {reason}")
        return await complex_merge_videos(video_files, user_id, status_message, video_infos, output_filename)

async def merge_video_with_audio(video_file: str, audio_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Enhanced video-audio merging with beautiful progress."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        final_output = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        timestamp = int(time.time())
        final_output = os.path.join(user_download_dir, f"AudioMerged_{len(audio_files)}tracks_{timestamp}.mkv")
    
    try:
        # Analyze video
        video_info = await get_detailed_video_info(video_file)
        if not video_info:
            raise ValueError("Could not analyze video file")
        
        await smart_progress_editor(status_message, f"""
🎵 **Starting Audio Merge**

🎬 **Video:** `{os.path.basename(video_file)}`
📊 **Duration:** `{video_info['duration']:.0f}s`
🎵 **Audio Tracks:** `{len(audio_files)} files`

⚙️ **Process:** Adding audio tracks to video
""")
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y']
        
        # Add video input
        cmd.extend(['-i', video_file])
        
        # Add audio inputs
        for audio_file in audio_files:
            cmd.extend(['-i', audio_file])
        
        # Map video stream
        cmd.extend(['-map', '0:v'])
        
        # Map existing audio if present
        if video_info['has_audio']:
            cmd.extend(['-map', '0:a'])
        
        # Map all new audio streams
        for i in range(len(audio_files)):
            cmd.extend(['-map', f'{i+1}:a'])
        
        # Codec settings
        cmd.extend([
            '-c:v', 'copy',  # Copy video without re-encoding
            '-c:a', 'aac',   # Re-encode audio for compatibility
            '-b:a', '192k',  # Good quality audio
            '-ac', '2',      # Stereo output
            '-metadata', 'title=Audio Enhanced Video',
            '-progress', 'pipe:2',
            final_output
        ])
        
        logger.info("🎵 Starting audio merge...")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(
            process,
            video_info['duration'],
            status_message,
            "Audio Merge",
            os.path.basename(final_output)
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            output_size = os.path.getsize(final_output)
            
            await smart_progress_editor(status_message, f"""
✅ **Audio Merge Completed!**

📁 **Output:** `{os.path.basename(final_output)}`
💾 **Size:** {get_human_readable_size(output_size)}
🎵 **Audio Tracks:** `{len(audio_files) + (1 if video_info['has_audio'] else 0)} total`

🎉 **Ready for upload!**
""")
            
            logger.info(f"✅ Audio merge successful: {final_output}")
            return final_output
        else:
            error_output = stderr.decode().strip()
            logger.error(f"❌ Audio merge failed: {error_output}")
            await status_message.edit_text(f"❌ **Audio Merge Failed**\n\n`{error_output[-200:]}`")
            return None
            
    except Exception as e:
        logger.error(f"❌ Audio merge exception: {e}")
        await status_message.edit_text(f"❌ **Audio Merge Error**\n\n`{str(e)}`")
        return None

async def merge_video_with_subtitles(video_file: str, subtitle_files: List[str], user_id: int, status_message, output_filename: str = None) -> Optional[str]:
    """Enhanced video-subtitle merging."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    
    if output_filename:
        base_name = os.path.splitext(output_filename)[0]
        final_output = os.path.join(user_download_dir, f"{base_name}.mkv")
    else:
        timestamp = int(time.time())
        final_output = os.path.join(user_download_dir, f"SubtitleMerged_{len(subtitle_files)}subs_{timestamp}.mkv")
    
    try:
        # Analyze video
        video_info = await get_detailed_video_info(video_file)
        if not video_info:
            raise ValueError("Could not analyze video file")
        
        await smart_progress_editor(status_message, f"""
📝 **Starting Subtitle Merge**

🎬 **Video:** `{os.path.basename(video_file)}`
📊 **Duration:** `{video_info['duration']:.0f}s`
📝 **Subtitles:** `{len(subtitle_files)} files`

⚙️ **Process:** Embedding subtitles into video
""")
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y']
        
        # Add video input
        cmd.extend(['-i', video_file])
        
        # Add subtitle inputs
        for sub_file in subtitle_files:
            cmd.extend(['-i', sub_file])
        
        # Map video and audio streams
        cmd.extend(['-map', '0:v'])
        if video_info['has_audio']:
            cmd.extend(['-map', '0:a'])
        
        # Map existing subtitles if present
        if video_info['has_subtitles']:
            cmd.extend(['-map', '0:s?'])
        
        # Map new subtitle streams
        for i in range(len(subtitle_files)):
            cmd.extend(['-map', f'{i+1}:s'])
        
        # Codec settings
        cmd.extend([
            '-c:v', 'copy',     # Copy video
            '-c:a', 'copy',     # Copy audio
            '-c:s', 'srt',      # Convert subtitles to SRT
            '-metadata', 'title=Subtitle Enhanced Video',
            '-progress', 'pipe:2',
            final_output
        ])
        
        logger.info("📝 Starting subtitle merge...")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Track progress
        await track_merge_progress(
            process,
            video_info['duration'],
            status_message,
            "Subtitle Merge",
            os.path.basename(final_output)
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(final_output):
            output_size = os.path.getsize(final_output)
            total_subs = len(subtitle_files) + (video_info['subtitle_streams_count'] if video_info['has_subtitles'] else 0)
            
            await smart_progress_editor(status_message, f"""
✅ **Subtitle Merge Completed!**

📁 **Output:** `{os.path.basename(final_output)}`
💾 **Size:** {get_human_readable_size(output_size)}
📝 **Subtitles:** `{total_subs} tracks embedded`

🎉 **Ready for upload!**
""")
            
            logger.info(f"✅ Subtitle merge successful: {final_output}")
            return final_output
        else:
            error_output = stderr.decode().strip()
            logger.error(f"❌ Subtitle merge failed: {error_output}")
            await status_message.edit_text(f"❌ **Subtitle Merge Failed**\n\n`{error_output[-200:]}`")
            return None
            
    except Exception as e:
        logger.error(f"❌ Subtitle merge exception: {e}")
        await status_message.edit_text(f"❌ **Subtitle Merge Error**\n\n`{str(e)}`")
        return None

async def extract_streams(video_file: str, user_id: int, status_message, extract_audio: bool = True, extract_subtitles: bool = True) -> Dict[str, List[str]]:
    """Extract audio and subtitle streams from video."""
    user_download_dir = os.path.join(config.DOWNLOAD_DIR, str(user_id))
    extracted_files = {"audio": [], "subtitles": []}
    
    try:
        video_info = await get_detailed_video_info(video_file)
        if not video_info:
            raise ValueError("Could not analyze video file")
        
        base_name = os.path.splitext(os.path.basename(video_file))[0]
        
        await smart_progress_editor(status_message, f"""
🔍 **Starting Stream Extraction**

🎬 **Video:** `{os.path.basename(video_file)}`
🎵 **Audio Streams:** `{video_info['audio_streams_count']}`
📝 **Subtitle Streams:** `{video_info['subtitle_streams_count']}`

⚙️ **Extracting streams...**
""")
        
        # Extract audio streams
        if extract_audio and video_info['has_audio']:
            audio_output = os.path.join(user_download_dir, f"{base_name}_extracted_audio.aac")
            
            cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
                '-i', video_file,
                '-vn', '-c:a', 'aac', '-b:a', '192k',
                '-progress', 'pipe:2',
                audio_output
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await track_merge_progress(
                process,
                video_info['duration'],
                status_message,
                "Audio Extraction",
                f"{base_name}_audio.aac"
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(audio_output):
                extracted_files["audio"].append(audio_output)
        
        # Extract subtitle streams
        if extract_subtitles and video_info['has_subtitles']:
            subs_output = os.path.join(user_download_dir, f"{base_name}_extracted_subs.srt")
            
            cmd = [
                'ffmpeg', '-hide_banner', '-loglevel', 'info', '-y',
                '-i', video_file,
                '-vn', '-an', '-c:s', 'srt',
                subs_output
            ]
            
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()
            
            if process.returncode == 0 and os.path.exists(subs_output):
                extracted_files["subtitles"].append(subs_output)
        
        # Final result
        total_extracted = len(extracted_files["audio"]) + len(extracted_files["subtitles"])
        
        await smart_progress_editor(status_message, f"""
✅ **Stream Extraction Completed!**

📁 **Video:** `{os.path.basename(video_file)}`
🎵 **Audio Files:** `{len(extracted_files["audio"])}`
📝 **Subtitle Files:** `{len(extracted_files["subtitles"])}`
📦 **Total Extracted:** `{total_extracted} files`

🎉 **Extraction complete!**
""")
        
        return extracted_files
        
    except Exception as e:
        logger.error(f"❌ Stream extraction failed: {e}")
        await status_message.edit_text(f"❌ **Stream Extraction Failed**\n\n`{str(e)}`")
        return {"audio": [], "subtitles": []}
