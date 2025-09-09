# bot.py - Complete Enhanced main bot file with beautiful UI and advanced features
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
user_files = {}  # User file collections
user_states = {}  # User interaction states
active_processes = {}  # Active merge/upload processes

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
"""
    
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
    """Show user and bot statistics."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    # Get user stats
    user_data = await database.get_user(user_id)
    bot_stats = await database.get_bot_stats()
    
    # System stats
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    stats_text = f"""
📊 **Statistics**

👤 **Your Stats:**
🔢 **Merges:** `{user_data.get('total_merges', 0) if user_data else 0}`
💾 **Processed:** `{get_human_readable_size(user_data.get('total_size_processed', 0) if user_data else 0)}`
📅 **Joined:** `{datetime.fromtimestamp(user_data.get('join_date', 0)).strftime('%Y-%m-%d') if user_data else 'Unknown'}`

🤖 **Bot Stats:**
👥 **Total Users:** `{bot_stats.get('total_users', 0)}`
🎬 **Total Merges:** `{bot_stats.get('total_merges', 0)}`
💿 **Total Processed:** `{get_human_readable_size(bot_stats.get('total_size', 0))}`

🖥️ **System Stats:**
🔥 **CPU:** `{cpu_percent}%`
🧠 **RAM:** `{memory.percent}%`
💽 **Disk:** `{disk.percent}%`
"""
    
    await message.reply_text(stats_text, quote=True)

@app.on_message(filters.command("clear") & filters.private)
async def clear_handler(client: Client, message: Message):
    """Clear user files."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    if user_id in user_files:
        user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': [], 'last_activity': time.time()}
    
    await message.reply_text("🗑️ **All files cleared!**", quote=True)

# File handlers
@app.on_message(filters.document | filters.video | filters.audio)
async def file_handler(client: Client, message: Message):
    """Handle incoming files."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    await initialize_user_session(user_id, message.from_user.username)
    
    # Get file info
    file_info = None
    file_name = ""
    file_size = 0
    
    if message.document:
        file_info = message.document
        file_name = file_info.file_name or f"document_{file_info.file_id}"
        file_size = file_info.file_size
    elif message.video:
        file_info = message.video
        file_name = file_info.file_name or f"video_{file_info.file_id}.mp4"
        file_size = file_info.file_size
    elif message.audio:
        file_info = message.audio
        file_name = file_info.file_name or f"audio_{file_info.file_id}.mp3"
        file_size = file_info.file_size
    
    # Check file size
    if file_size > config.MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ **File too large!**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"📊 **Size:** `{get_human_readable_size(file_size)}`\n"
            f"⚠️ **Max allowed:** `{get_human_readable_size(config.MAX_FILE_SIZE)}`",
            quote=True
        )
        return
    
    # Determine file type
    file_type = get_file_type(file_name)
    
    if file_type == 'unknown':
        await message.reply_text(
            f"❌ **Unsupported file type!**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"🔧 **Supported:** Video, Audio, Subtitle files",
            quote=True
        )
        return
    
    # Add to user collection
    if user_id not in user_files:
        user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
    
    file_data = {
        'message': message,
        'file_name': file_name,
        'file_size': file_size,
        'file_type': file_type,
        'added_at': time.time()
    }
    
    user_files[user_id][f"{file_type}s"].append(file_data)
    user_files[user_id]['last_activity'] = time.time()
    
    # Send confirmation with menu
    files = user_files[user_id]
    confirmation_text = f"""
✅ **File Added Successfully!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
🔧 **Type:** `{file_type.title()}`

📋 **Your Collection:**
🎞️ Videos: `{len(files['videos'])}`
🎵 Audios: `{len(files['audios'])}`
📝 Subtitles: `{len(files['subtitles'])}`

💡 **What's next?** Use the buttons below to merge files!
"""
    
    keyboard = create_main_keyboard(user_id)
    
    await message.reply_text(
        confirmation_text,
        reply_markup=keyboard,
        quote=True
    )

@app.on_message(filters.text & filters.private)
async def url_handler(client: Client, message: Message):
    """Handle URL downloads."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    text = message.text.strip()
    
    # Check if it's a URL
    if not (text.startswith('http://') or text.startswith('https://')):
        # Check if it's a password
        if user_id in user_states and user_states[user_id].get('waiting_for_password'):
            # Handle password input (implement password verification logic here)
            await message.reply_text("🔐 **Password received!** Processing...", quote=True)
            return
        
        await message.reply_text(
            "❌ **Invalid input!**\n\n"
            "Please send:\n"
            "• Direct download URLs\n"
            "• Video/Audio/Subtitle files\n"
            "• Use /help for more options",
            quote=True
        )
        return
    
    await initialize_user_session(user_id, message.from_user.username)
    
    # Start download
    status_msg = await message.reply_text("📥 **Starting download...**", quote=True)
    
    try:
        async def progress_callback(progress_text):
            await status_msg.edit_text(progress_text)
        
        downloaded_file = await download_file_from_url(text, user_id, progress_callback)
        
        if downloaded_file:
            # Determine file type
            file_name = os.path.basename(downloaded_file)
            file_type = get_file_type(file_name)
            file_size = os.path.getsize(downloaded_file)
            
            if file_type != 'unknown':
                # Add to collection
                if user_id not in user_files:
                    user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
                
                file_data = {
                    'file_path': downloaded_file,
                    'file_name': file_name,
                    'file_size': file_size,
                    'file_type': file_type,
                    'added_at': time.time()
                }
                
                user_files[user_id][f"{file_type}s"].append(file_data)
                
                # Success message
                files = user_files[user_id]
                success_text = f"""
✅ **Download Successful!**

📁 **File:** `{file_name}`
📊 **Size:** `{get_human_readable_size(file_size)}`
🔧 **Type:** `{file_type.title()}`

📋 **Your Collection:**
🎞️ Videos: `{len(files['videos'])}`
🎵 Audios: `{len(files['audios'])}`
📝 Subtitles: `{len(files['subtitles'])}`
"""
                
                keyboard = create_main_keyboard(user_id)
                await status_msg.edit_text(success_text, reply_markup=keyboard)
            else:
                await status_msg.edit_text("❌ **Downloaded file type not supported!**")
        else:
            await status_msg.edit_text("❌ **Download failed!**")
            
    except Exception as e:
        logger.error(f"Download error for user {user_id}: {e}")
        await status_msg.edit_text(f"❌ **Download failed!**\n\n**Error:** `{str(e)}`")

# Owner commands
@app.on_message(filters.command("ban") & filters.user(int(config.OWNER)))
async def ban_handler(client: Client, message: Message):
    """Ban a user."""
    try:
        user_id = int(message.command[1])
        await database.ban_user(user_id)
        await message.reply_text(f"🚫 **User {user_id} has been banned!**")
    except (IndexError, ValueError):
        await message.reply_text("❌ **Usage:** `/ban <user_id>`")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

@app.on_message(filters.command("unban") & filters.user(int(config.OWNER)))
async def unban_handler(client: Client, message: Message):
    """Unban a user."""
    try:
        user_id = int(message.command[1])
        await database.unban_user(user_id)
        await message.reply_text(f"✅ **User {user_id} has been unbanned!**")
    except (IndexError, ValueError):
        await message.reply_text("❌ **Usage:** `/unban <user_id>`")
    except Exception as e:
        await message.reply_text(f"❌ **Error:** `{str(e)}`")

@app.on_message(filters.command("broadcast") & filters.user(int(config.OWNER)))
async def broadcast_handler(client: Client, message: Message):
    """Broadcast message to all users."""
    if not message.reply_to_message:
        await message.reply_text("❌ **Reply to a message to broadcast it!**")
        return
    
    # Get all users from database
    # Implementation would depend on your database structure
    await message.reply_text("📢 **Broadcasting...** (Feature to be implemented)")

# Error handler
@app.on_message()
async def catch_all(client: Client, message: Message):
    """Catch all other messages."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    # Only respond to unhandled text messages
    if message.text and not message.text.startswith('/'):
        await message.reply_text(
            "🤖 **I didn't understand that.**\n\n"
            "Try:\n"
            "• Sending video/audio files\n"
            "• Sending download URLs\n"
            "• Using /help for commands",
            quote=True
        )

# Import callback handlers
from plugins.cb_handler import *

if __name__ == "__main__":
    try:
        # Validate configuration
        config.validate()
        
        print("🚀 Starting AdvancedMergeBot...")
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
