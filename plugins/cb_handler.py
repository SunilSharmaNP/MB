# plugins/cb_handler.py - Complete callback handler
import asyncio
import os
import time
import logging
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from utils import get_human_readable_size, get_file_type, UserSettings
from helpers.database import database
from helpers.merger import merge_videos, merge_video_with_audio, merge_video_with_subtitles
from helpers.uploader import upload_to_telegram, dual_upload, generate_thumbnail, GofileUploader

logger = logging.getLogger(__name__)

# Import user data from main bot
from bot import user_files, user_states, app

def create_upload_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Create upload options keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📤 Upload to Telegram", callback_data=f"upload_tg_{user_id}"),
            InlineKeyboardButton("☁️ Upload to GoFile", callback_data=f"upload_gf_{user_id}")
        ],
        [
            InlineKeyboardButton("🚀 Upload to Both", callback_data=f"upload_dual_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔧 Upload Settings", callback_data=f"upload_settings_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def create_settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Create settings keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🎬 Merge Mode", callback_data=f"setting_mode_{user_id}"),
            InlineKeyboardButton("📄 Upload as Doc", callback_data=f"setting_doc_{user_id}")
        ],
        [
            InlineKeyboardButton("🖼️ Auto Thumbnail", callback_data=f"setting_thumb_{user_id}"),
            InlineKeyboardButton("🔔 Notifications", callback_data=f"setting_notif_{user_id}")
        ],
        [
            InlineKeyboardButton("🏷️ Custom Naming", callback_data=f"setting_name_{user_id}"),
            InlineKeyboardButton("🗑️ Auto Delete", callback_data=f"setting_delete_{user_id}")
        ],
        [
            InlineKeyboardButton("💾 Save Settings", callback_data=f"save_settings_{user_id}"),
            InlineKeyboardButton("◀️ Back", callback_data=f"back_main_{user_id}")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

@app.on_callback_query(filters.regex(r"^merge_videos_(\d+)$"))
async def handle_merge_videos(client: Client, query: CallbackQuery):
    """Handle video merge callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        files = user_files.get(user_id, {'videos': []})
        video_files = files['videos']
        
        if len(video_files) < 2:
            await query.answer("❌ Need at least 2 videos to merge!", show_alert=True)
            return
        
        await query.answer("🎬 Starting video merge...")
        
        # Update message to show progress
        progress_message = await query.message.edit_text(
            f"""
🎬 **Video Merge Starting...**

📁 **Files:** `{len(video_files)} videos`
⚡ **Status:** Initializing merge process...

💡 **Please wait, this may take a while...**
"""
        )
        
        # Start merge process
        try:
            output_file = await merge_videos(
                video_files, user_id, progress_message
            )
            
            if output_file:
                # Store merged file for upload
                user_states[user_id] = {
                    'action': 'upload',
                    'file_path': output_file,
                    'file_type': 'video'
                }
                
                file_size = get_human_readable_size(os.path.getsize(output_file))
                
                await progress_message.edit_text(
                    f"""
✅ **Video Merge Complete!**

🎬 **Output:** `{os.path.basename(output_file)}`
📊 **Size:** `{file_size}`
🎉 **Success:** Videos merged successfully!

🚀 **Choose upload destination:**
""",
                    reply_markup=create_upload_keyboard(user_id)
                )
            else:
                await progress_message.edit_text(
                    "❌ **Merge Failed**\n\nPlease check your video files and try again."
                )
        
        except Exception as e:
            logger.error(f"Merge error for user {user_id}: {e}")
            await progress_message.edit_text(
                f"❌ **Merge Error**\n\n**Error:** {str(e)}"
            )
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^merge_audio_(\d+)$"))
async def handle_merge_audio(client: Client, query: CallbackQuery):
    """Handle audio merge callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        files = user_files.get(user_id, {'videos': [], 'audios': []})
        video_files = files['videos']
        audio_files = files['audios']
        
        if len(video_files) != 1:
            await query.answer("❌ Need exactly 1 video for audio merge!", show_alert=True)
            return
        
        if len(audio_files) < 1:
            await query.answer("❌ Need at least 1 audio file!", show_alert=True)
            return
        
        await query.answer("🎵 Starting audio merge...")
        
        progress_message = await query.message.edit_text(
            f"""
🎵 **Audio Merge Starting...**

🎬 **Video:** `{video_files[0]['file_name'] if isinstance(video_files[0], dict) else os.path.basename(video_files[0])}`
🎵 **Audio Files:** `{len(audio_files)} tracks`
⚡ **Status:** Adding audio tracks...

💡 **Please wait, processing audio streams...**
"""
        )
        
        try:
            output_file = await merge_video_with_audio(
                video_files[0], audio_files, user_id, progress_message
            )
            
            if output_file:
                user_states[user_id] = {
                    'action': 'upload',
                    'file_path': output_file,
                    'file_type': 'video'
                }
                
                file_size = get_human_readable_size(os.path.getsize(output_file))
                
                await progress_message.edit_text(
                    f"""
✅ **Audio Merge Complete!**

🎬 **Output:** `{os.path.basename(output_file)}`
📊 **Size:** `{file_size}`
🎵 **Audio Tracks:** `{len(audio_files) + 1} total`

🚀 **Choose upload destination:**
""",
                    reply_markup=create_upload_keyboard(user_id)
                )
            else:
                await progress_message.edit_text(
                    "❌ **Audio Merge Failed**\n\nPlease check your files and try again."
                )
        
        except Exception as e:
            logger.error(f"Audio merge error for user {user_id}: {e}")
            await progress_message.edit_text(
                f"❌ **Audio Merge Error**\n\n**Error:** {str(e)}"
            )
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^merge_subs_(\d+)$"))
async def handle_merge_subtitles(client: Client, query: CallbackQuery):
    """Handle subtitle merge callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        files = user_files.get(user_id, {'videos': [], 'subtitles': []})
        video_files = files['videos']
        subtitle_files = files['subtitles']
        
        if len(video_files) != 1:
            await query.answer("❌ Need exactly 1 video for subtitle merge!", show_alert=True)
            return
        
        if len(subtitle_files) < 1:
            await query.answer("❌ Need at least 1 subtitle file!", show_alert=True)
            return
        
        await query.answer("📝 Starting subtitle merge...")
        
        progress_message = await query.message.edit_text(
            f"""
📝 **Subtitle Merge Starting...**

🎬 **Video:** `{video_files[0]['file_name'] if isinstance(video_files[0], dict) else os.path.basename(video_files[0])}`
📝 **Subtitles:** `{len(subtitle_files)} files`
⚡ **Status:** Embedding subtitle tracks...

💡 **Please wait, processing subtitles...**
"""
        )
        
        try:
            output_file = await merge_video_with_subtitles(
                video_files[0], subtitle_files, user_id, progress_message
            )
            
            if output_file:
                user_states[user_id] = {
                    'action': 'upload',
                    'file_path': output_file,
                    'file_type': 'video'
                }
                
                file_size = get_human_readable_size(os.path.getsize(output_file))
                
                await progress_message.edit_text(
                    f"""
✅ **Subtitle Merge Complete!**

🎬 **Output:** `{os.path.basename(output_file)}`
📊 **Size:** `{file_size}`
📝 **Subtitles:** `{len(subtitle_files)} tracks embedded`

🚀 **Choose upload destination:**
""",
                    reply_markup=create_upload_keyboard(user_id)
                )
            else:
                await progress_message.edit_text(
                    "❌ **Subtitle Merge Failed**\n\nPlease check your files and try again."
                )
        
        except Exception as e:
            logger.error(f"Subtitle merge error for user {user_id}: {e}")
            await progress_message.edit_text(
                f"❌ **Subtitle Merge Error**\n\n**Error:** {str(e)}"
            )
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^upload_(tg|gf|dual)_(\d+)$"))
async def handle_upload(client: Client, query: CallbackQuery):
    """Handle upload callbacks."""
    try:
        parts = query.data.split('_')
        upload_type = parts[1]
        user_id = int(parts[2])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        user_state = user_states.get(user_id)
        if not user_state or user_state.get('action') != 'upload':
            await query.answer("❌ No file to upload!", show_alert=True)
            return
        
        file_path = user_state['file_path']
        if not os.path.exists(file_path):
            await query.answer("❌ File not found!", show_alert=True)
            return
        
        await query.answer(f"📤 Starting {upload_type.upper()} upload...")
        
        filename = os.path.basename(file_path)
        file_size = get_human_readable_size(os.path.getsize(file_path))
        
        progress_message = await query.message.edit_text(
            f"""
📤 **Upload Starting...**

📁 **File:** `{filename}`
📊 **Size:** `{file_size}`
🎯 **Destination:** `{upload_type.upper()}`

⚡ **Status:** Initializing upload...
"""
        )
        
        async def progress_callback(text: str):
            await progress_message.edit_text(text)
        
        try:
            # Generate thumbnail for videos
            thumbnail = None
            if get_file_type(filename) == 'video':
                thumbnail = await generate_thumbnail(file_path)
            
            if upload_type == 'tg':
                # Upload to Telegram only
                message = await upload_to_telegram(
                    client, user_id, file_path, 
                    f"✅ **Merged by AdvancedMergeBot**\n\n📁 **File:** `{filename}`\n📊 **Size:** `{file_size}`",
                    progress_callback, thumbnail
                )
                
                if message:
                    await progress_message.edit_text(
                        f"""
✅ **Upload Complete!**

📤 **Destination:** Telegram
📁 **File:** `{filename}`
📊 **Size:** `{file_size}`
🎉 **Success:** File uploaded successfully!

💡 **File sent to your chat!**
"""
                    )
                else:
                    await progress_message.edit_text("❌ **Upload Failed**\n\nTelegram upload error.")
            
            elif upload_type == 'gf':
                # Upload to GoFile only
                gofile_uploader = GofileUploader()
                result = await gofile_uploader.upload_file(file_path, progress_callback=progress_callback)
                
                if result and result.get('success'):
                    await progress_message.edit_text(
                        f"""
✅ **Upload Complete!**

📤 **Destination:** GoFile
📁 **File:** `{filename}`
📊 **Size:** `{file_size}`

🔗 **Download Link:**
`{result.get('download_page', 'N/A')}`

💡 **Link copied to clipboard!**
"""
                    )
                else:
                    await progress_message.edit_text("❌ **Upload Failed**\n\nGoFile upload error.")
            
            elif upload_type == 'dual':
                # Upload to both platforms
                results = await dual_upload(
                    client, user_id, file_path,
                    f"✅ **Merged by AdvancedMergeBot**\n\n📁 **File:** `{filename}`\n📊 **Size:** `{file_size}`",
                    progress_callback, thumbnail
                )
                
                success_count = sum([1 for r in [results['telegram'], results['gofile']] if r['success']])
                
                status_text = f"""
✅ **Dual Upload Complete!**

📁 **File:** `{filename}`
📊 **Size:** `{file_size}`
🎯 **Success:** `{success_count}/2 platforms`

📤 **Telegram:** {'✅ Success' if results['telegram']['success'] else '❌ Failed'}
☁️ **GoFile:** {'✅ Success' if results['gofile']['success'] else '❌ Failed'}
"""
                
                if results['gofile']['success'] and results['gofile']['data']:
                    status_text += f"\n🔗 **GoFile Link:**\n`{results['gofile']['data'].get('download_page', 'N/A')}`"
                
                await progress_message.edit_text(status_text)
            
            # Clean up
            try:
                os.remove(file_path)
                if thumbnail and os.path.exists(thumbnail):
                    os.remove(thumbnail)
            except:
                pass
            
            # Clear user state
            if user_id in user_states:
                del user_states[user_id]
        
        except Exception as e:
            logger.error(f"Upload error for user {user_id}: {e}")
            await progress_message.edit_text(
                f"❌ **Upload Error**\n\n**Error:** {str(e)}"
            )
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^show_files_(\d+)$"))
async def handle_show_files(client: Client, query: CallbackQuery):
    """Handle show files callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
        
        files_text = "📋 **Your Files:**\n\n"
        
        if files['videos']:
            files_text += "🎞️ **Videos:**\n"
            for i, file_data in enumerate(files['videos'][:5], 1):
                name = file_data['file_name'] if isinstance(file_data, dict) else os.path.basename(file_data)
                size = file_data.get('file_size', 0) if isinstance(file_data, dict) else 0
                files_text += f"  {i}. `{name[:30]}{'...' if len(name) > 30 else ''}` ({get_human_readable_size(size)})\n"
            
            if len(files['videos']) > 5:
                files_text += f"  ... and {len(files['videos']) - 5} more\n"
            files_text += "\n"
        
        if files['audios']:
            files_text += "🎵 **Audios:**\n"
            for i, file_data in enumerate(files['audios'][:5], 1):
                name = file_data['file_name'] if isinstance(file_data, dict) else os.path.basename(file_data)
                size = file_data.get('file_size', 0) if isinstance(file_data, dict) else 0
                files_text += f"  {i}. `{name[:30]}{'...' if len(name) > 30 else ''}` ({get_human_readable_size(size)})\n"
            
            if len(files['audios']) > 5:
                files_text += f"  ... and {len(files['audios']) - 5} more\n"
            files_text += "\n"
        
        if files['subtitles']:
            files_text += "📝 **Subtitles:**\n"
            for i, file_data in enumerate(files['subtitles'][:5], 1):
                name = file_data['file_name'] if isinstance(file_data, dict) else os.path.basename(file_data)
                size = file_data.get('file_size', 0) if isinstance(file_data, dict) else 0
                files_text += f"  {i}. `{name[:30]}{'...' if len(name) > 30 else ''}` ({get_human_readable_size(size)})\n"
            
            if len(files['subtitles']) > 5:
                files_text += f"  ... and {len(files['subtitles']) - 5} more\n"
            files_text += "\n"
        
        if not any([files['videos'], files['audios'], files['subtitles']]):
            files_text += "📭 **No files added yet!**\n\nSend me some files to get started."
        
        # Create back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Menu", callback_data=f"back_main_{user_id}")]
        ])
        
        await query.message.edit_text(files_text, reply_markup=keyboard)
        await query.answer()
    
    except Exception as e:
        logger.error(f"Show files error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^clear_files_(\d+)$"))
async def handle_clear_files(client: Client, query: CallbackQuery):
    """Handle clear files callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        # Clear user files
        if user_id in user_files:
            user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': [], 'last_activity': time.time()}
        
        await query.answer("🗑️ All files cleared!", show_alert=True)
        
        # Go back to main menu
        from bot import create_main_keyboard
        
        keyboard = create_main_keyboard(user_id)
        
        await query.message.edit_text(
            f"""
🎬 **AdvancedMergeBot Menu**

📁 **Current Files:**
🎞️ Videos: `0`
🎵 Audios: `0`
📝 Subtitles: `0`

💡 **Quick Actions:**
• Send files/URLs to add to collection
• Use buttons below for merge operations
• Check settings for customization
""",
            reply_markup=keyboard
        )
    
    except Exception as e:
        logger.error(f"Clear files error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^back_main_(\d+)$"))
async def handle_back_main(client: Client, query: CallbackQuery):
    """Handle back to main menu callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        from bot import create_main_keyboard
        
        files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
        keyboard = create_main_keyboard(user_id)
        
        await query.message.edit_text(
            f"""
🎬 **AdvancedMergeBot Menu**

📁 **Current Files:**
🎞️ Videos: `{len(files['videos'])}`
🎵 Audios: `{len(files['audios'])}`
📝 Subtitles: `{len(files['subtitles'])}`

💡 **Quick Actions:**
• Send files/URLs to add to collection
• Use buttons below for merge operations
• Check settings for customization
""",
            reply_markup=keyboard
        )
        
        await query.answer()
    
    except Exception as e:
        logger.error(f"Back to main error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^cancel_(\d+)$"))
async def handle_cancel(client: Client, query: CallbackQuery):
    """Handle cancel callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        # Clear user state
        if user_id in user_states:
            del user_states[user_id]
        
        await query.answer("❌ Operation cancelled!")
        
        # Go back to main menu
        from bot import create_main_keyboard
        
        files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
        keyboard = create_main_keyboard(user_id)
        
        await query.message.edit_text(
            f"""
🎬 **AdvancedMergeBot Menu**

📁 **Current Files:**
🎞️ Videos: `{len(files['videos'])}`
🎵 Audios: `{len(files['audios'])}`
📝 Subtitles: `{len(files['subtitles'])}`

💡 **Quick Actions:**
• Send files/URLs to add to collection
• Use buttons below for merge operations
• Check settings for customization
""",
            reply_markup=keyboard
        )
    
    except Exception as e:
        logger.error(f"Cancel error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^close_(\d+)$"))
async def handle_close(client: Client, query: CallbackQuery):
    """Handle close menu callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        await query.message.delete()
        await query.answer("✅ Menu closed!")
    
    except Exception as e:
        logger.error(f"Close error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

# Settings callbacks (basic implementation)
@app.on_callback_query(filters.regex(r"^settings_(\d+)$"))
async def handle_settings(client: Client, query: CallbackQuery):
    """Handle settings callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        settings_text = """
⚙️ **Bot Settings**

🎬 **Merge Mode:** Auto-detect
📄 **Upload as Doc:** Disabled
🖼️ **Auto Thumbnail:** Enabled
🔔 **Notifications:** Enabled

💡 **Configure your bot preferences below:**
"""
        
        keyboard = create_settings_keyboard(user_id)
        
        await query.message.edit_text(settings_text, reply_markup=keyboard)
        await query.answer()
    
    except Exception as e:
        logger.error(f"Settings error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@app.on_callback_query(filters.regex(r"^stats_(\d+)$"))
async def handle_stats(client: Client, query: CallbackQuery):
    """Handle stats callback."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        # Get stats from database
        user_data = await database.get_user(user_id)
        bot_stats = await database.get_bot_stats()
        
        stats_text = f"""
📊 **Your Statistics**

🔢 **Merges:** `{user_data.get('total_merges', 0) if user_data else 0}`
💾 **Processed:** `{get_human_readable_size(user_data.get('total_size_processed', 0) if user_data else 0)}`
📅 **Member since:** `{time.strftime('%Y-%m-%d', time.localtime(user_data.get('join_date', 0))) if user_data else 'Unknown'}`

🤖 **Bot Statistics**

👥 **Total Users:** `{bot_stats.get('total_users', 0)}`
🎬 **Total Merges:** `{bot_stats.get('total_merges', 0)}`
💿 **Total Processed:** `{get_human_readable_size(bot_stats.get('total_size', 0))}`
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Menu", callback_data=f"back_main_{user_id}")]
        ])
        
        await query.message.edit_text(stats_text, reply_markup=keyboard)
        await query.answer()
    
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)
