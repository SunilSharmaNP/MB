# Enhanced main bot file with beautiful UI and advanced features
import asyncio
import os
import time
import logging
import shutil
import psutil
from datetime import datetime
from typing import Dict, List, Optional

from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, 
    InlineKeyboardMarkup, User
)
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from config import config
from utils import (
    get_human_readable_size, get_file_type, 
    UserSettings, create_progress_text
)
from helpers.database import database
from helpers.downloader import download_file_from_url, download_telegram_file
from helpers.merger import merge_videos, merge_video_with_audio, merge_video_with_subtitles
from helpers.uploader import upload_to_telegram, GofileUploader, dual_upload

# Setup enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot states and user data
user_files = {}      # User file collections
user_states = {}     # User interaction states  
active_processes = {} # Active merge/upload processes

class AdvancedMergeBot(Client):
    """Enhanced Telegram bot with advanced merging capabilities."""
    
    def __init__(self):
        super().__init__(
            name="AdvancedMergeBot",
            api_hash=config.API_HASH,
            api_id=config.TELEGRAM_API,
            bot_token=config.BOT_TOKEN,
            workers=50,
            workdir="session"
        )
    
    async def start(self):
        """Enhanced bot startup with system checks."""
        await super().start()
        
        # Create necessary directories
        directories = [config.DOWNLOAD_DIR, config.TEMP_DIR, config.USERDATA_DIR, "session", "logs"]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        
        # Get bot info
        me = await self.get_me()
        logger.info(f"🤖 Bot started: @{me.username} ({me.id})")
        
        # Send startup message to owner
        try:
            startup_message = f"""
🚀 **AdvancedMergeBot Started Successfully!**

🤖 **Bot:** @{me.username}
📊 **ID:** `{me.id}`
⏰ **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`

🔧 **Features Loaded:**
✅ Enhanced downloader (URLs + Telegram)
✅ Smart video merger (fast + compatible)
✅ Dual uploader (Telegram + GoFile)
✅ Advanced progress tracking
✅ User management system

🌟 **Ready to merge files!**
"""
            await self.send_message(chat_id=int(config.OWNER), text=startup_message)
            
        except Exception as e:
            logger.error(f"❌ Could not send startup message: {e}")
        
        logger.info("🎉 AdvancedMergeBot is ready!")
    
    async def stop(self):
        """Graceful bot shutdown."""
        logger.info("🔄 Shutting down AdvancedMergeBot...")
        
        # Close database connection
        await database.close()
        
        # Clean up temporary files
        try:
            if os.path.exists(config.TEMP_DIR):
                shutil.rmtree(config.TEMP_DIR)
            os.makedirs(config.TEMP_DIR, exist_ok=True)
        except:
            pass
        
        await super().stop()
        logger.info("👋 AdvancedMergeBot stopped successfully!")

# Initialize bot
app = AdvancedMergeBot()

# Helper functions
async def is_user_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    if user_id == int(config.OWNER):
        return True
    
    user_data = await database.get_user(user_id)
    if user_data:
        return not user_data.get('is_banned', False)
    
    return False

async def initialize_user_session(user_id: int, username: str = None):
    """Initialize or update user session."""
    if user_id not in user_files:
        user_files[user_id] = {
            'videos': [],
            'audios': [],
            'subtitles': [],
            'last_activity': time.time()
        }
    
    # Update database
    await database.add_user(user_id, username or "Unknown", username)
    await database.update_user_activity(user_id)

def create_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Create beautiful main menu keyboard."""
    files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
    
    keyboard = []
    
    # File counts
    video_count = len(files['videos'])
    audio_count = len(files['audios'])
    subtitle_count = len(files['subtitles'])
    
    # Merge options based on available files
    if video_count >= 2:
        keyboard.append([
            InlineKeyboardButton(
                f"🎬 Merge Videos ({video_count})", 
                callback_data=f"merge_videos_{user_id}"
            )
        ])
    
    if video_count >= 1 and audio_count >= 1:
        keyboard.append([
            InlineKeyboardButton(
                f"🎵 Add Audio Tracks ({audio_count})", 
                callback_data=f"merge_audio_{user_id}"
            )
        ])
    
    if video_count >= 1 and subtitle_count >= 1:
        keyboard.append([
            InlineKeyboardButton(
                f"📝 Add Subtitles ({subtitle_count})", 
                callback_data=f"merge_subs_{user_id}"
            )
        ])
    
    # Management options
    if video_count > 0 or audio_count > 0 or subtitle_count > 0:
        keyboard.extend([
            [
                InlineKeyboardButton("📋 Show Files", callback_data=f"show_files_{user_id}"),
                InlineKeyboardButton("🗑 Clear All", callback_data=f"clear_files_{user_id}")
            ]
        ])
    
    # Settings and info
    keyboard.extend([
        [
            InlineKeyboardButton("⚙️ Settings", callback_data=f"settings_{user_id}"),
            InlineKeyboardButton("📊 Stats", callback_data=f"stats_{user_id}")
        ],
        [InlineKeyboardButton("❌ Close Menu", callback_data=f"close_{user_id}")]
    ])
    
    return InlineKeyboardMarkup(keyboard)

# Command handlers
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Enhanced start command with beautiful welcome."""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Check authorization
    if not await is_user_authorized(user_id):
        await message.reply_text(
            f"""
🔒 **Access Restricted**

👋 Hi **{first_name}**!

Unfortunately, you don't have permission to use this bot.

📧 **Contact:** @{config.OWNER_USERNAME}
🆔 **Your ID:** `{user_id}`
""",
            quote=True
        )
        return
    
    # Initialize user session
    await initialize_user_session(user_id, username)
    
    # Create welcome message with system info
    bot_info = await client.get_me()
    
    welcome_message = f"""
🎬 **Welcome to AdvancedMergeBot!**

👋 Hi **{first_name}**! I'm your advanced file merging assistant.

✨ **What I Can Do:**
🎞️ **Smart Video Merging** - Lightning-fast or compatible
🎵 **Audio Track Addition** - Multiple audio streams
📝 **Subtitle Integration** - Embed multiple subtitle tracks  
📥 **Universal Downloads** - URLs, GoFile, Telegram files
📤 **Dual Upload** - Telegram + GoFile simultaneously

🚀 **Advanced Features:**
• Real-time progress tracking
• Auto-thumbnail generation  
• Smart compatibility detection
• Lossless fast merging
• Beautiful progress bars

📝 **How to Start:**
1. Send me video files or URLs
2. Add audio/subtitle files if needed
3. Choose your merge option
4. Get your merged file!

🤖 **Bot:** @{bot_info.username}
👑 **Owner:** @{config.OWNER_USERNAME}

🎯 **Ready to merge? Send me your files!**
""",
    
    keyboard = create_main_keyboard(user_id)
    
    await message.reply_text(
        welcome_message,
        reply_markup=keyboard,
        quote=True
    )

@app.on_message(filters.command(["help", "menu"]) & filters.private)
async def menu_handler(client: Client, message: Message):
    """Show main menu."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    await initialize_user_session(user_id, message.from_user.username)
    
    files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
    
    menu_text = f"""
🎬 **AdvancedMergeBot Menu**

📁 **Current Files:**
🎞️ Videos: `{len(files['videos'])}`
🎵 Audios: `{len(files['audios'])}`  
📝 Subtitles: `{len(files['subtitles'])}`

💡 **Quick Actions:**
• Send files/URLs to add to collection
• Use buttons below for merge operations
• Check settings for customization
"""
    
    keyboard = create_main_keyboard(user_id)
    
    await message.reply_text(
        menu_text,
        reply_markup=keyboard,
        quote=True
    )

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    """Enhanced system statistics."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    # System stats
    uptime = time.time() - app.start_time if hasattr(app, 'start_time') else 0
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(".")
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # Bot stats
    bot_stats = await database.get_bot_stats()
    
    # User stats
    user_data = await database.get_user(user_id)
    user_merges = user_data.get('total_merges', 0) if user_data else 0
    user_size_processed = user_data.get('total_size_processed', 0) if user_data else 0
    
    stats_message = f"""
📊 **AdvancedMergeBot Statistics**

🤖 **Bot Stats:**
• Total Users: `{bot_stats.get('total_users', 0)}`
• Total Merges: `{bot_stats.get('total_merges', 0)}`  
• Data Processed: {get_human_readable_size(bot_stats.get('total_size', 0))}
• Uptime: `{uptime/3600:.1f} hours`

👤 **Your Stats:**
• Your Merges: `{user_merges}`
• Data Processed: {get_human_readable_size(user_size_processed)}

🖥️ **System Resources:**
• CPU Usage: `{cpu_percent}%`
• RAM Usage: `{memory.percent}%`
• Disk Free: {get_human_readable_size(disk.free)}
• Active Users: `{len(user_files)}`

⚡ **Performance:** Excellent
"""
    
    await message.reply_text(stats_message, quote=True)

@app.on_message(filters.command("clear") & filters.private)
async def clear_handler(client: Client, message: Message):
    """Clear user's file collection."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    if user_id in user_files:
        # Clean up files
        for file_list in user_files[user_id].values():
            if isinstance(file_list, list):
                for file_path in file_list:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        pass
        
        # Clear user data
        user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
    
    await message.reply_text(
        "🗑️ **Files Cleared Successfully!**\n\nAll your files have been removed from the collection.",
        quote=True
    )

# File handlers
@app.on_message((filters.document | filters.video | filters.audio) & filters.private)
async def file_handler(client: Client, message: Message):
    """Enhanced file processing with beautiful progress."""
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not await is_user_authorized(user_id):
        await message.reply_text("🔒 **Access Denied**\n\nYou don't have permission to use this bot.", quote=True)
        return
    
    await initialize_user_session(user_id, username)
    
    # Check if user has too many active processes
    if user_id in active_processes:
        await message.reply_text(
            "⏳ **Process Already Running**\n\nPlease wait for your current operation to complete.",
            quote=True
        )
        return
    
    status_msg = await message.reply_text("📥 **Processing file...**", quote=True)
    active_processes[user_id] = True
    
    try:
        # Download file with beautiful progress
        file_path = await download_telegram_file(client, message, user_id, status_msg)
        
        # Determine file type
        media = message.document or message.video or message.audio
        filename = media.file_name or f"file_{int(time.time())}"
        file_type = get_file_type(filename)
        
        # Add to appropriate collection
        if user_id not in user_files:
            user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
        
        if file_type == 'video':
            user_files[user_id]['videos'].append(file_path)
            emoji = "🎞️"
            type_name = "Video"
        elif file_type == 'audio':
            user_files[user_id]['audios'].append(file_path)
            emoji = "🎵"
            type_name = "Audio"
        elif file_type == 'subtitle':
            user_files[user_id]['subtitles'].append(file_path)
            emoji = "📝"
            type_name = "Subtitle"
        else:
            await status_msg.edit_text("❌ **Unsupported file format!**")
            return
        
        # Update last activity
        user_files[user_id]['last_activity'] = time.time()
        
        # Show success message with menu
        success_text = f"""
✅ **{type_name} File Added Successfully!**

{emoji} **File:** `{filename}`
💾 **Size:** {get_human_readable_size(media.file_size)}
📂 **Type:** {type_name}

📊 **Current Collection:**
🎞️ Videos: `{len(user_files[user_id]['videos'])}`
🎵 Audios: `{len(user_files[user_id]['audios'])}`
📝 Subtitles: `{len(user_files[user_id]['subtitles'])}`

💡 **What's Next?**
Choose an action from the menu below:
"""
        
        keyboard = create_main_keyboard(user_id)
        await status_msg.edit_text(success_text, reply_markup=keyboard)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error processing file:**\n\n`{str(e)}`")
        logger.error(f"❌ File processing error for user {user_id}: {e}")
    
    finally:
        if user_id in active_processes:
            del active_processes[user_id]

@app.on_message(filters.regex(r'https?://') & filters.private)
async def url_handler(client: Client, message: Message):
    """Enhanced URL download handler."""
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not await is_user_authorized(user_id):
        await message.reply_text("🔒 **Access Denied**", quote=True)
        return
    
    await initialize_user_session(user_id, username)
    
    if user_id in active_processes:
        await message.reply_text("⏳ **Another process is running. Please wait.**", quote=True)
        return
    
    url = message.text.strip()
    status_msg = await message.reply_text("🔗 **Processing URL...**", quote=True)
    active_processes[user_id] = True
    
    try:
        # Extract password if provided
        password = None
        if ' ' in url:
            parts = url.split(' ', 1)
            url = parts[0]
            password = parts[1]
        
        # Download file with progress
        file_path = await download_file_from_url(url, user_id, status_msg, password)
        
        # Add to video collection (assuming video for URLs)
        if user_id not in user_files:
            user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
        
        user_files[user_id]['videos'].append(file_path)
        user_files[user_id]['last_activity'] = time.time()
        
        # Success message
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        success_text = f"""
✅ **URL Download Completed!**

🔗 **Source:** `{url[:50]}{'...' if len(url) > 50 else ''}`
📁 **File:** `{filename}`
💾 **Size:** {get_human_readable_size(file_size)}

📊 **Total Videos:** `{len(user_files[user_id]['videos'])}`

💡 **Ready to merge? Use the menu below:**
"""
        
        keyboard = create_main_keyboard(user_id)
        await status_msg.edit_text(success_text, reply_markup=keyboard)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Download Failed:**\n\n`{str(e)}`")
        logger.error(f"❌ URL download error for user {user_id}: {e}")
    
    finally:
        if user_id in active_processes:
            del active_processes[user_id]

# Callback query handlers
@app.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    """Enhanced callback query handler."""
    data = callback.data
    user_id = callback.from_user.id
    
    # Security check
    if not data.endswith(f"_{user_id}") and user_id != int(config.OWNER):
        await callback.answer("❌ This button is not for you!", show_alert=True)
        return
    
    if not await is_user_authorized(user_id):
        await callback.answer("🔒 Access denied!", show_alert=True)
        return
    
    # Handle different callback types
    if data.startswith("merge_videos"):
        await handle_video_merge(client, callback)
    elif data.startswith("merge_audio"):
        await handle_audio_merge(client, callback)
    elif data.startswith("merge_subs"):
        await handle_subtitle_merge(client, callback)
    elif data.startswith("show_files"):
        await handle_show_files(callback)
    elif data.startswith("clear_files"):
        await handle_clear_files(callback)
    elif data.startswith("settings"):
        await handle_settings(callback)
    elif data.startswith("stats"):
        await stats_handler(client, callback.message)
    elif data.startswith("close"):
        await callback.message.delete()
    else:
        await callback.answer("🔄 Feature coming soon!", show_alert=True)

async def handle_video_merge(client: Client, callback: CallbackQuery):
    """Handle video merge process."""
    user_id = callback.from_user.id
    
    if user_id in active_processes:
        await callback.answer("⏳ Another process is running!", show_alert=True)
        return
    
    files = user_files.get(user_id, {})
    video_files = files.get('videos', [])
    
    if len(video_files) < 2:
        await callback.answer("❌ Need at least 2 videos!", show_alert=True)
        return
    
    await callback.answer("🚀 Starting video merge...")
    active_processes[user_id] = True
    
    try:
        # Start merge process
        merged_file = await merge_videos(
            video_files, 
            user_id, 
            callback.message
        )
        
        if merged_file:
            # Upload options
            upload_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📤 Telegram Only", callback_data=f"upload_tg_{user_id}"),
                    InlineKeyboardButton("🌐 GoFile Only", callback_data=f"upload_gf_{user_id}")
                ],
                [InlineKeyboardButton("🚀 Both Platforms", callback_data=f"upload_dual_{user_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"close_{user_id}")]
            ])
            
            await callback.message.edit_text(
                f"""
🎉 **Video Merge Completed!**

📁 **Output:** `{os.path.basename(merged_file)}`
💾 **Size:** {get_human_readable_size(os.path.getsize(merged_file))}

📤 **Choose upload destination:**
""",
                reply_markup=upload_keyboard
            )
            
            # Store merged file for upload
            user_files[user_id]['merged_file'] = merged_file
            
            # Update user stats
            await database.increment_user_stats(
                user_id, 
                merge_count=1, 
                size_processed=os.path.getsize(merged_file)
            )
        else:
            await callback.message.edit_text("❌ **Merge Failed!** Please try again.")
    
    except Exception as e:
        await callback.message.edit_text(f"❌ **Merge Error:**\n\n`{str(e)}`")
        logger.error(f"❌ Video merge error: {e}")
    
    finally:
        if user_id in active_processes:
            del active_processes[user_id]

async def handle_audio_merge(client: Client, callback: CallbackQuery):
    """Handle video-audio merge process."""
    user_id = callback.from_user.id
    
    if user_id in active_processes:
        await callback.answer("⏳ Another process is running!", show_alert=True)
        return
    
    files = user_files.get(user_id, {})
    video_files = files.get('videos', [])
    audio_files = files.get('audios', [])
    
    if len(video_files) < 1 or len(audio_files) < 1:
        await callback.answer("❌ Need at least 1 video and 1 audio file!", show_alert=True)
        return
    
    await callback.answer("🎵 Starting audio merge...")
    active_processes[user_id] = True
    
    try:
        # Use first video with all audio files
        merged_file = await merge_video_with_audio(
            video_files[0],
            audio_files,
            user_id,
            callback.message
        )
        
        if merged_file:
            # Similar upload options as video merge
            upload_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📤 Telegram Only", callback_data=f"upload_tg_{user_id}"),
                    InlineKeyboardButton("🌐 GoFile Only", callback_data=f"upload_gf_{user_id}")
                ],
                [InlineKeyboardButton("🚀 Both Platforms", callback_data=f"upload_dual_{user_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"close_{user_id}")]
            ])
            
            await callback.message.edit_text(
                f"""
🎵 **Audio Merge Completed!**

📁 **Output:** `{os.path.basename(merged_file)}`
💾 **Size:** {get_human_readable_size(os.path.getsize(merged_file))}
🎵 **Audio Tracks:** `{len(audio_files)} added`

📤 **Choose upload destination:**
""",
                reply_markup=upload_keyboard
            )
            
            user_files[user_id]['merged_file'] = merged_file
            await database.increment_user_stats(user_id, 1, os.path.getsize(merged_file))
        else:
            await callback.message.edit_text("❌ **Audio merge failed!**")
    
    except Exception as e:
        await callback.message.edit_text(f"❌ **Audio Merge Error:**\n\n`{str(e)}`")
        logger.error(f"❌ Audio merge error: {e}")
    
    finally:
        if user_id in active_processes:
            del active_processes[user_id]

async def handle_subtitle_merge(client: Client, callback: CallbackQuery):
    """Handle video-subtitle merge process."""
    user_id = callback.from_user.id
    
    if user_id in active_processes:
        await callback.answer("⏳ Another process is running!", show_alert=True)
        return
    
    files = user_files.get(user_id, {})
    video_files = files.get('videos', [])
    subtitle_files = files.get('subtitles', [])
    
    if len(video_files) < 1 or len(subtitle_files) < 1:
        await callback.answer("❌ Need at least 1 video and 1 subtitle file!", show_alert=True)
        return
    
    await callback.answer("📝 Starting subtitle merge...")
    active_processes[user_id] = True
    
    try:
        merged_file = await merge_video_with_subtitles(
            video_files[0],
            subtitle_files,
            user_id,
            callback.message
        )
        
        if merged_file:
            upload_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📤 Telegram Only", callback_data=f"upload_tg_{user_id}"),
                    InlineKeyboardButton("🌐 GoFile Only", callback_data=f"upload_gf_{user_id}")
                ],
                [InlineKeyboardButton("🚀 Both Platforms", callback_data=f"upload_dual_{user_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"close_{user_id}")]
            ])
            
            await callback.message.edit_text(
                f"""
📝 **Subtitle Merge Completed!**

📁 **Output:** `{os.path.basename(merged_file)}`
💾 **Size:** {get_human_readable_size(os.path.getsize(merged_file))}
📝 **Subtitles:** `{len(subtitle_files)} embedded`

📤 **Choose upload destination:**
""",
                reply_markup=upload_keyboard
            )
            
            user_files[user_id]['merged_file'] = merged_file
            await database.increment_user_stats(user_id, 1, os.path.getsize(merged_file))
        else:
            await callback.message.edit_text("❌ **Subtitle merge failed!**")
    
    except Exception as e:
        await callback.message.edit_text(f"❌ **Subtitle Merge Error:**\n\n`{str(e)}`")
        logger.error(f"❌ Subtitle merge error: {e}")
    
    finally:
        if user_id in active_processes:
            del active_processes[user_id]

async def handle_show_files(callback: CallbackQuery):
    """Show user's current file collection."""
    user_id = callback.from_user.id
    files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
    
    file_list = "📁 **Your File Collection:**\n\n"
    
    # Videos
    if files['videos']:
        file_list += "🎞️ **Videos:**\n"
        for i, file_path in enumerate(files['videos'], 1):
            filename = os.path.basename(file_path)
            size = get_human_readable_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "Unknown"
            file_list += f"  `{i}.` {filename[:30]}{'...' if len(filename) > 30 else ''} ({size})\n"
        file_list += "\n"
    
    # Audios  
    if files['audios']:
        file_list += "🎵 **Audio Files:**\n"
        for i, file_path in enumerate(files['audios'], 1):
            filename = os.path.basename(file_path)
            size = get_human_readable_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "Unknown"
            file_list += f"  `{i}.` {filename[:30]}{'...' if len(filename) > 30 else ''} ({size})\n"
        file_list += "\n"
    
    # Subtitles
    if files['subtitles']:
        file_list += "📝 **Subtitle Files:**\n"
        for i, file_path in enumerate(files['subtitles'], 1):
            filename = os.path.basename(file_path)
            size = get_human_readable_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "Unknown"
            file_list += f"  `{i}.` {filename[:30]}{'...' if len(filename) > 30 else ''} ({size})\n"
        file_list += "\n"
    
    if not any([files['videos'], files['audios'], files['subtitles']]):
        file_list += "📂 **No files in collection**\n\nSend me some files to get started!"
    
    file_list += f"\n⏰ **Last Activity:** {time.ctime(files.get('last_activity', time.time()))}"
    
    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data=f"menu_{user_id}")]
    ])
    
    await callback.message.edit_text(file_list, reply_markup=back_keyboard)

async def handle_clear_files(callback: CallbackQuery):
    """Clear user's file collection with confirmation."""
    user_id = callback.from_user.id
    
    confirm_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Clear All", callback_data=f"confirm_clear_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"menu_{user_id}")
        ]
    ])
    
    await callback.message.edit_text(
        "🗑️ **Clear All Files?**\n\nThis will remove all files from your collection. Are you sure?",
        reply_markup=confirm_keyboard
    )

async def handle_settings(callback: CallbackQuery):
    """Show user settings menu."""
    user_id = callback.from_user.id
    
    # Get user settings from database
    settings = await database.get_user_settings(user_id)
    
    settings_text = f"""
⚙️ **Your Settings**

🔧 **Current Configuration:**
• **Merge Mode:** {config.MODES.get(settings.get('merge_mode', 1), 'Video + Video')}
• **Upload as Document:** {'✅' if settings.get('upload_as_doc', False) else '❌'}  
• **Auto Thumbnail:** {'✅' if settings.get('auto_thumbnail', True) else '❌'}
• **Notifications:** {'✅' if settings.get('notification', True) else '❌'}
• **Quality:** {settings.get('quality_preset', 'High').title()}

💡 **Settings can be modified in future updates!**
"""
    
    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data=f"menu_{user_id}")]
    ])
    
    await callback.message.edit_text(settings_text, reply_markup=back_keyboard)

# Admin commands
@app.on_message(filters.command("broadcast") & filters.user(int(config.OWNER)))
async def broadcast_handler(client: Client, message: Message):
    """Broadcast message to all users."""
    if not message.reply_to_message:
        await message.reply_text("❌ **Reply to a message to broadcast it.**", quote=True)
        return
    
    users = await database.get_all_users()
    total_users = len(users)
    
    status_msg = await message.reply_text(
        f"📡 **Starting broadcast to {total_users} users...**",
        quote=True
    )
    
    success_count = 0
    failed_count = 0
    
    for user in users:
        try:
            await message.reply_to_message.copy(chat_id=user['_id'])
            success_count += 1
            
            if success_count % 10 == 0:  # Update every 10 successful sends
                await status_msg.edit_text(
                    f"📡 **Broadcasting...**\n\n"
                    f"✅ **Sent:** {success_count}\n"
                    f"❌ **Failed:** {failed_count}\n"
                    f"📊 **Progress:** {((success_count + failed_count) / total_users) * 100:.1f}%"
                )
            
            await asyncio.sleep(0.1)  # Rate limiting
            
        except (UserIsBlocked, InputUserDeactivated):
            failed_count += 1
            # Remove inactive users
            await database.ban_user(user['_id'])
            
        except FloodWait as e:
            await asyncio.sleep(e.x)
            await message.reply_to_message.copy(chat_id=user['_id'])
            success_count += 1
            
        except Exception as e:
            failed_count += 1
            logger.error(f"❌ Broadcast failed for {user['_id']}: {e}")
    
    await status_msg.edit_text(
        f"""
📡 **Broadcast Completed!**

📊 **Results:**
✅ **Successful:** {success_count}
❌ **Failed:** {failed_count}
📈 **Success Rate:** {(success_count / total_users * 100):.1f}%

⏱️ **Total Users:** {total_users}
🧹 **Cleaned inactive users:** {failed_count}
"""
    )

# Error handler
@app.on_message(filters.all & filters.private)
async def fallback_handler(client: Client, message: Message):
    """Handle unrecognized commands/messages."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    # If message is not a file or URL, show help
    if not (message.document or message.video or message.audio or 'http' in message.text):
        help_text = f"""
🤔 **I didn't understand that!**

💡 **Here's what I can do:**

📁 **Send me files:**
• Video files (.mp4, .mkv, .avi, etc.)
• Audio files (.mp3, .aac, .wav, etc.)  
• Subtitle files (.srt, .ass, .vtt, etc.)

🔗 **Send me URLs:**
• Direct download links
• GoFile.io links (with password if needed)

⚙️ **Use commands:**
• `/start` - Main menu
• `/help` - Show this help
• `/stats` - Bot statistics  
• `/clear` - Clear your files

📝 **Need help?** Contact @{config.OWNER_USERNAME}
"""
        
        await message.reply_text(help_text, quote=True)

if __name__ == "__main__":
    logger.info("🚀 Starting AdvancedMergeBot...")
    app.start_time = time.time()
    app.run()
