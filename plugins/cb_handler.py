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
from helpers.uploader import upload_to_telegram, dual_upload, generate_thumbnail

logger = logging.getLogger(__name__)

# Import user data from main bot
from bot import user_files, user_states

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

@Client.on_callback_query(filters.regex(r"^merge_videos_(\d+)$"))
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

@Client.on_callback_query(filters.regex(r"^merge_audio_(\d+)$"))
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

🎬 **Video:** `{os.path.basename(video_files[0])}`
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

@Client.on_callback_query(filters.regex(r"^merge_subs_(\d+)$"))
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

🎬 **Video:** `{os.path.basename(video_files[0])}`
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

@Client.on_callback_query(filters.regex(r"^upload_(tg|gf|dual)_(\d+)$"))
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
                # Telegram only
                message = await upload_to_telegram(
                    client, file_path, user_id, progress_callback,
                    f"🎬 Merged by AdvancedMergeBot\n📁 {filename}",
                    thumbnail=thumbnail
                )
                
                await progress_message.edit_text(
                    f"""
✅ **Upload Complete!**

📁 **File:** `{filename}`
📤 **Uploaded to:** Telegram
🎉 **Success:** File uploaded successfully!
"""
                )
                
            elif upload_type == 'gf':
                # GoFile only
                from helpers.uploader import GofileUploader
                
                async with GofileUploader() as uploader:
                    result = await uploader.upload_file(file_path, progress_callback)
                    
                    await progress_message.edit_text(
                        f"""
✅ **GoFile Upload Complete!**

📁 **File:** `{filename}`
☁️ **Uploaded to:** GoFile
🔗 **Link:** {result['download_url'] if result else 'N/A'}

🎉 **Success:** File uploaded successfully!
"""
                    )
                    
            elif upload_type == 'dual':
                # Both platforms
                results = await dual_upload(
                    client, file_path, user_id, progress_callback,
                    f"🎬 Merged by AdvancedMergeBot\n📁 {filename}",
                    thumbnail=thumbnail
                )
                
                # Results already handled in dual_upload
                pass
            
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
                f"❌ **Upload Failed**\n\n**Error:** {str(e)}"
            )
            
    except Exception as e:
        logger.error(f"Upload callback error: {e}")
        await query.answer("❌ Upload failed!", show_alert=True)

@Client.on_callback_query(filters.regex(r"^show_files_(\d+)$"))
async def handle_show_files(client: Client, query: CallbackQuery):
    """Show user's files."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
        
        text = "📁 **Your Files:**\n\n"
        
        if files['videos']:
            text += f"🎬 **Videos ({len(files['videos'])}):**\n"
            for i, file in enumerate(files['videos'][:5], 1):
                text += f"{i}. `{os.path.basename(file)}`\n"
            if len(files['videos']) > 5:
                text += f"... and {len(files['videos']) - 5} more\n"
            text += "\n"
        
        if files['audios']:
            text += f"🎵 **Audio ({len(files['audios'])}):**\n"
            for i, file in enumerate(files['audios'][:5], 1):
                text += f"{i}. `{os.path.basename(file)}`\n"
            if len(files['audios']) > 5:
                text += f"... and {len(files['audios']) - 5} more\n"
            text += "\n"
        
        if files['subtitles']:
            text += f"📝 **Subtitles ({len(files['subtitles'])}):**\n"
            for i, file in enumerate(files['subtitles'][:5], 1):
                text += f"{i}. `{os.path.basename(file)}`\n"
            if len(files['subtitles']) > 5:
                text += f"... and {len(files['subtitles']) - 5} more\n"
            text += "\n"
        
        if not any([files['videos'], files['audios'], files['subtitles']]):
            text += "📭 **No files added yet.**\n\n"
            text += "💡 **Send me files or URLs to get started!**"
        
        keyboard = [[InlineKeyboardButton("◀️ Back to Menu", callback_data=f"back_main_{user_id}")]]
        
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()
        
    except Exception as e:
        logger.error(f"Show files error: {e}")
        await query.answer("❌ Error showing files!", show_alert=True)

@Client.on_callback_query(filters.regex(r"^clear_files_(\d+)$"))
async def handle_clear_files(client: Client, query: CallbackQuery):
    """Clear user's files."""
    try:
        user_id = int(query.data.split('_')[-1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        if user_id in user_files:
            # Clean up physical files
            files = user_files[user_id]
            all_files = files.get('videos', []) + files.get('audios', []) + files.get('subtitles', [])
            
            for file_path in all_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
            
            # Clear file lists
            user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': [], 'last_activity': time.time()}
        
        await query.answer("🗑️ All files cleared!", show_alert=True)
        
        # Update main menu
        from bot import create_main_keyboard
        await query.message.edit_text(
            """
🎬 **AdvancedMergeBot**

🗑️ **Files Cleared Successfully!**

📝 **Send me new files to get started:**
• Videos for merging
• Audio tracks to add
• Subtitle files to embed
• URLs to download

💡 **Ready for new operations!**
""",
            reply_markup=create_main_keyboard(user_id)
        )
        
    except Exception as e:
        logger.error(f"Clear files error: {e}")
        await query.answer("❌ Error clearing files!", show_alert=True)

@Client.on_callback_query(filters.regex(r"^(settings|stats|close)_(\d+)$"))
async def handle_misc_callbacks(client: Client, query: CallbackQuery):
    """Handle miscellaneous callbacks."""
    try:
        action, user_id = query.data.split('_')
        user_id = int(user_id)
        
        if query.from_user.id != user_id:
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
        
        if action == 'settings':
            await query.message.edit_text(
                "⚙️ **Settings**\n\nFeature coming soon!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Back", callback_data=f"back_main_{user_id}")
                ]])
            )
            
        elif action == 'stats':
            files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
            stats_text = f"""
📊 **Your Statistics**

📁 **Current Session:**
🎬 Videos: `{len(files['videos'])}`
🎵 Audio: `{len(files['audios'])}`
📝 Subtitles: `{len(files['subtitles'])}`

💡 **Total Files:** `{len(files['videos']) + len(files['audios']) + len(files['subtitles'])}`
"""
            
            await query.message.edit_text(
                stats_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Back", callback_data=f"back_main_{user_id}")
                ]])
            )
            
        elif action == 'close':
            await query.message.delete()
            await query.answer("👋 Menu closed!")
            
        await query.answer()
        
    except Exception as e:
        logger.error(f"Misc callback error: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

@Client.on_callback_query(filters.regex(r"^back_main_(\d+)$"))
async def handle_back_to_main(client: Client, query: CallbackQuery):
    """Handle back to main menu."""
    try:
        user_id = int(query.data
