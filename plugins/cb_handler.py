# plugins/cb_handler.py - Enhanced callback handler without rclone
import asyncio
import os
import logging
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from utils import get_human_readable_size, smart_progress_editor
from config import config

logger = logging.getLogger(__name__)

@Client.on_callback_query()
async def callback_router(client: Client, callback: CallbackQuery):
    """Main callback router for all button interactions."""
    data = callback.data
    user_id = callback.from_user.id
    
    # Security check
    if not data.endswith(f"_{user_id}") and user_id != int(config.OWNER):
        await callback.answer("❌ This button is not for you!", show_alert=True)
        return
    
    try:
        # Route different callback types
        if data.startswith("show_files"):
            await handle_show_files(callback)
        elif data.startswith("clear_files") or data.startswith("confirm_clear"):
            await handle_clear_files(callback)
        elif data.startswith("settings"):
            await handle_settings(callback)
        elif data.startswith("toggle_"):
            await handle_toggle_setting(callback)
        elif data.startswith("menu"):
            await handle_back_to_menu(callback)
        elif data.startswith("close"):
            await callback.message.delete()
            await callback.answer("Menu closed ✅")
        else:
            await callback.answer("❓ Unknown action", show_alert=True)
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await callback.answer("❌ An error occurred", show_alert=True)

async def handle_show_files(callback: CallbackQuery):
    """Show detailed file list."""
    user_id = callback.from_user.id
    
    # Import user_files from bot.py
    try:
        from bot import user_files
    except ImportError:
        await callback.answer("❌ Error accessing files", show_alert=True)
        return
    
    files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
    
    files_text = "📁 **Your File Collection**\n\n"
    
    # Show videos
    if files['videos']:
        files_text += "🎞️ **Videos:**\n"
        for i, file_path in enumerate(files['videos'], 1):
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                files_text += f"`{i}.` `{filename[:35]}{'...' if len(filename) > 35 else ''}` ({get_human_readable_size(file_size)})\n"
        files_text += "\n"
    
    # Show audios
    if files['audios']:
        files_text += "🎵 **Audio Files:**\n"
        for i, file_path in enumerate(files['audios'], 1):
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                files_text += f"`{i}.` `{filename[:35]}{'...' if len(filename) > 35 else ''}` ({get_human_readable_size(file_size)})\n"
        files_text += "\n"
    
    # Show subtitles
    if files['subtitles']:
        files_text += "📝 **Subtitle Files:**\n"
        for i, file_path in enumerate(files['subtitles'], 1):
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                files_text += f"`{i}.` `{filename[:35]}{'...' if len(filename) > 35 else ''}` ({get_human_readable_size(file_size)})\n"
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
    """Handle file clearing with confirmation."""
    user_id = callback.from_user.id
    
    if callback.data.startswith("confirm_clear"):
        # Actually clear the files
        try:
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
            
            from bot import create_main_keyboard
            keyboard = create_main_keyboard(user_id)
            
            await callback.message.edit_text(success_text, reply_markup=keyboard)
            await callback.answer("✅ All files cleared!")
            
        except Exception as e:
            await callback.message.edit_text(f"❌ **Clear Files Error**\n\n`{str(e)}`")
            logger.error(f"Clear files error: {e}")
    
    else:
        # Show confirmation
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

async def handle_settings(callback: CallbackQuery):
    """Show user settings interface."""
    user_id = callback.from_user.id
    
    try:
        from helpers.database import database
        
        user_settings = await database.get_user_settings(user_id)
        
        settings_text = f"""
⚙️ **Bot Settings**

📊 **Current Configuration:**

🔄 **Merge Mode:** `{config.MODES.get(user_settings.get('merge_mode', 1))}`
📄 **Upload as Document:** `{'✅ On' if user_settings.get('upload_as_doc', False) else '❌ Off'}`
🖼️ **Auto Thumbnail:** `{'✅ On' if user_settings.get('auto_thumbnail', True) else '❌ Off'}`
🔔 **Notifications:** `{'✅ On' if user_settings.get('notification', True) else '❌ Off'}`
🎯 **Quality:** `{user_settings.get('quality_preset', 'high').title()}`

💡 **File Naming:** `{user_settings.get('custom_name_format', 'Default')}`
"""
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📄 Toggle Document", callback_data=f"toggle_doc_{user_id}"),
                InlineKeyboardButton("🖼️ Toggle Thumbnail", callback_data=f"toggle_thumb_{user_id}")
            ],
            [
                InlineKeyboardButton("🔔 Toggle Notifications", callback_data=f"toggle_notif_{user_id}"),
                InlineKeyboardButton("🎯 Quality Settings", callback_data=f"quality_{user_id}")
            ],
            [InlineKeyboardButton("🏠 Back to Menu", callback_data=f"menu_{user_id}")]
        ])
        
        await callback.message.edit_text(settings_text, reply_markup=keyboard)
        
    except Exception as e:
        await callback.message.edit_text(f"❌ **Settings Error**\n\n`{str(e)}`")
        logger.error(f"Settings error: {e}")

async def handle_toggle_setting(callback: CallbackQuery):
    """Handle toggle settings."""
    user_id = callback.from_user.id
    setting_type = callback.data.split("_")[1]  # doc, thumb, notif, etc.
    
    try:
        from helpers.database import database
        
        user_settings = await database.get_user_settings(user_id)
        
        if setting_type == "doc":
            user_settings['upload_as_doc'] = not user_settings.get('upload_as_doc', False)
            status = "enabled" if user_settings['upload_as_doc'] else "disabled"
            await callback.answer(f"📄 Document upload {status}!")
            
        elif setting_type == "thumb":
            user_settings['auto_thumbnail'] = not user_settings.get('auto_thumbnail', True)
            status = "enabled" if user_settings['auto_thumbnail'] else "disabled"
            await callback.answer(f"🖼️ Auto thumbnail {status}!")
            
        elif setting_type == "notif":
            user_settings['notification'] = not user_settings.get('notification', True)
            status = "enabled" if user_settings['notification'] else "disabled"
            await callback.answer(f"🔔 Notifications {status}!")
        
        # Save settings
        await database.update_user_settings(user_id, user_settings)
        
        # Refresh settings page
        await handle_settings(callback)
        
    except Exception as e:
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)
        logger.error(f"Toggle setting error: {e}")

async def handle_back_to_menu(callback: CallbackQuery):
    """Return to main menu."""
    user_id = callback.from_user.id
    
    try:
        from bot import user_files, create_main_keyboard
        
        files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
        
        menu_text = f"""
🎬 **AdvancedMergeBot Menu**

📁 **Current Files:**
🎞️ Videos: `{len(files['videos'])}`
🎵 Audios: `{len(files['audios'])}`  
📝 Subtitles: `{len(files['subtitles'])}`

💡 **Send files or URLs to add to your collection**
🎯 **Use buttons below for merge operations**
"""
        
        keyboard = create_main_keyboard(user_id)
        await callback.message.edit_text(menu_text, reply_markup=keyboard)
        
    except Exception as e:
        await callback.message.edit_text(f"❌ **Menu Error**\n\n`{str(e)}`")
        logger.error(f"Menu error: {e}")
