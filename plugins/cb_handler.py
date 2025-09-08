# Enhanced callback handler without rclone features
import asyncio
import os
from pyrogram import filters, Client
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from utils import get_human_readable_size, get_file_type
from config import config
import logging

logger = logging.getLogger(__name__)

async def handle_show_files(callback: CallbackQuery):
    """Show detailed file list with beautiful formatting."""
    user_id = callback.from_user.id
    
    # Import here to avoid circular imports
    from bot import user_files
    
    files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
    
    files_text = "📁 **Your File Collection**\n\n"
    
    # Show videos
    if files['videos']:
        files_text += "🎞️ **Videos:**\n"
        for i, file_path in enumerate(files['videos'], 1):
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                files_text += f"`{i}.` `{filename[:40]}{'...' if len(filename) > 40 else ''}` ({get_human_readable_size(file_size)})\n"
        files_text += "\n"
    
    # Show audios
    if files['audios']:
        files_text += "🎵 **Audio Files:**\n"
        for i, file_path in enumerate(files['audios'], 1):
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                files_text += f"`{i}.` `{filename[:40]}{'...' if len(filename) > 40 else ''}` ({get_human_readable_size(file_size)})\n"
        files_text += "\n"
    
    # Show subtitles
    if files['subtitles']:
        files_text += "📝 **Subtitle Files:**\n"
        for i, file_path in enumerate(files['subtitles'], 1):
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                files_text += f"`{i}.` `{filename[:40]}{'...' if len(filename) > 40 else ''}` ({get_human_readable_size(file_size)})\n"
        files_text += "\n"
    
    if not any([files['videos'], files['audios'], files['subtitles']]):
        files_text += "📭 **No files in collection**\n\nSend me some files to get started!"
    
    # Calculate total size
    total_size = 0
    for file_list in files.values():
        for file_path in file_list:
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
    
    if total_size > 0:
        files_text += f"\n💾 **Total Size:** {get_human_readable_size(total_size)}"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 Clear All", callback_data=f"clear_files_{user_id}"),
            InlineKeyboardButton("🏠 Back to Menu", callback_data=f"menu_{user_id}")
        ]
    ])
    
    await callback.message.edit_text(files_text, reply_markup=keyboard)

async def handle_clear_files(callback: CallbackQuery):
    """Clear all user files with confirmation."""
    user_id = callback.from_user.id
    
    confirm_text = """
🗑️ **Clear All Files**

⚠️ **Warning:** This will remove all files from your collection.

Are you sure you want to continue?
"""
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Clear All", callback_data=f"confirm_clear_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"menu_{user_id}")
        ]
    ])
    
    await callback.message.edit_text(confirm_text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("confirm_clear"))
async def confirm_clear_files(client: Client, callback: CallbackQuery):
    """Actually clear the files."""
    user_id = callback.from_user.id
    
    try:
        # Import here to avoid circular imports
        from bot import user_files
        
        files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
        files_cleared = 0
        
        # Remove physical files
        for file_list in files.values():
            for file_path in file_list:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        files_cleared += 1
                except Exception as e:
                    logger.warning(f"Could not remove file {file_path}: {e}")
        
        # Clear file lists
        user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
        
        success_text = f"""
✅ **Files Cleared Successfully!**

🗑️ **Removed:** `{files_cleared} files`
💽 **Storage:** Freed up space

📁 **Collection is now empty**
Send me new files to start merging!
"""
        
        # Import and create keyboard
        from bot import create_main_keyboard
        keyboard = create_main_keyboard(user_id)
        
        await callback.message.edit_text(success_text, reply_markup=keyboard)
        await callback.answer("✅ All files cleared!")
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ **Clear Files Error**\n\n`{str(e)}`"
        )
        logger.error(f"Clear files error: {e}")

async def handle_settings(callback: CallbackQuery):
    """Show user settings with beautiful interface."""
    user_id = callback.from_user.id
    
    # Import database here to avoid circular imports
    from helpers.database import database
    
    user_settings = await database.get_user_settings(user_id)
    
    settings_text = f"""
⚙️ **Bot Settings**

📊 **Current Configuration:**

🔄 **Merge Mode:** `{config.MODES.get(user_settings.get('merge_mode', 1))}`
📄 **Upload as Document:** `{'✅ Enabled' if user_settings.get('upload_as_doc', False) else '❌ Disabled'}`
🖼️ **Auto Thumbnail:** `{'✅ Enabled' if user_settings.get('auto_thumbnail', True) else '❌ Disabled'}`
🔔 **Notifications:** `{'✅ Enabled' if user_settings.get('notification', True) else '❌ Disabled'}`
🎯 **Quality Preset:** `{user_settings.get('quality_preset', 'high').title()}`

💡 **File Naming:** `{user_settings.get('custom_name_format', 'Default')}`
"""
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Change Mode", callback_data=f"change_mode_{user_id}"),
            InlineKeyboardButton("📄 Toggle Document", callback_data=f"toggle_doc_{user_id}")
        ],
        [
            InlineKeyboardButton("🖼️ Toggle Thumbnail", callback_data=f"toggle_thumb_{user_id}"),
            InlineKeyboardButton("🔔 Toggle Notifications", callback_data=f"toggle_notif_{user_id}")
        ],
        [
            InlineKeyboardButton("🎯 Quality Settings", callback_data=f"quality_settings_{user_id}"),
            InlineKeyboardButton("💡 Naming Format", callback_data=f"naming_format_{user_id}")
        ],
        [InlineKeyboardButton("🏠 Back to Menu", callback_data=f"menu_{user_id}")]
    ])
    
    await callback.message.edit_text(settings_text, reply_markup=keyboard)

async def handle_user_stats(callback: CallbackQuery):
    """Show detailed user statistics."""
    user_id = callback.from_user.id
    
    # Import database here
    from helpers.database import database
    
    user_data = await database.get_user(user_id)
    
    if not user_data:
        await callback.answer("❌ No user data found!", show_alert=True)
        return
    
    # Calculate additional stats
    join_date = user_data.get('join_date', 0)
    total_merges = user_data.get('total_merges', 0)
    total_size = user_data.get('total_size_processed', 0)
    last_activity = user_data.get('last_activity', 0)
    
    # Calculate averages
    avg_file_size = total_size / total_merges if total_merges > 0 else 0
    days_active = max(1, (time.time() - join_date) / 86400)
    merges_per_day = total_merges / days_active if days_active > 0 else 0
    
    stats_text = f"""
📊 **Your Statistics**

👤 **Account Info:**
🆔 **User ID:** `{user_id}`
📅 **Joined:** `{datetime.fromtimestamp(join_date).strftime('%Y-%m-%d') if join_date else 'Unknown'}`
⏰ **Last Active:** `{datetime.fromtimestamp(last_activity).strftime('%Y-%m-%d %H:%M') if last_activity else 'Unknown'}`

🎬 **Merge Statistics:**
🔄 **Total Merges:** `{total_merges}`
💾 **Data Processed:** {get_human_readable_size(total_size)}
📈 **Average File Size:** {get_human_readable_size(avg_file_size)}
📊 **Daily Average:** `{merges_per_day:.1f} merges/day`

🏆 **Achievements:**
{'🥇 **Power User** - 100+ merges' if total_merges >= 100 else ''}
{'💎 **Data Master** - 10GB+ processed' if total_size >= 10*1024*1024*1024 else ''}
{'⚡ **Speed Demon** - 10+ merges/day average' if merges_per_day >= 10 else ''}

🎯 **Status:** {'🌟 Premium' if user_data.get('is_premium', False) else '🆓 Free User'}
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Back to Menu", callback_data=f"menu_{user_id}")]
    ])
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard)
