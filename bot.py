# bot.py - Complete main bot file with all functionality
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
    """Show bot statistics."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    # Get system stats
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpu_percent = psutil.cpu_percent()
    
    # Get bot stats
    bot_stats = await database.get_bot_stats()
    
    stats_text = f"""
📊 **Bot Statistics**

👥 **Users:** `{bot_stats.get('total_users', 0)}`
🎬 **Total Merges:** `{bot_stats.get('total_merges', 0)}`
💾 **Data Processed:** `{get_human_readable_size(bot_stats.get('total_size', 0))}`

🖥️ **System Stats:**
💻 **CPU:** `{cpu_percent}%`
🧠 **Memory:** `{memory.percent}%`
💿 **Disk:** `{disk.percent}%`

⚡ **Bot Status:** Online and Ready!
"""
    
    await message.reply_text(stats_text, quote=True)

@app.on_message(filters.document | filters.video | filters.audio)
async def file_handler(client: Client, message: Message):
    """Handle file uploads."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    await initialize_user_session(user_id, message.from_user.username)
    
    # Show processing message
    status_msg = await message.reply_text("📥 **Processing file...**", quote=True)
    
    try:
        # Download file
        async def progress_callback(text: str):
            await status_msg.edit_text(text)
        
        file_path = await download_telegram_file(message, user_id, progress_callback)
        
        if file_path:
            # Determine file type and add to appropriate list
            file_type = get_file_type(os.path.basename(file_path))
            filename = os.path.basename(file_path)
            file_size = get_human_readable_size(os.path.getsize(file_path))
            
            # Add to user files
            if file_type == 'video':
                user_files[user_id]['videos'].append(file_path)
            elif file_type == 'audio':
                user_files[user_id]['audios'].append(file_path)
            elif file_type == 'subtitle':
                user_files[user_id]['subtitles'].append(file_path)
            else:
                await status_msg.edit_text(
                    f"❌ **Unsupported file type**\n\n"
                    f"**File:** `{filename}`\n"
                    f"**Type:** `{file_type}`"
                )
                return
            
            # Update activity
            user_files[user_id]['last_activity'] = time.time()
            
            # Show success message with menu
            await status_msg.edit_text(
                f"""
✅ **File Added Successfully!**

📁 **File:** `{filename}`
📊 **Size:** `{file_size}`
📂 **Type:** `{file_type.title()}`

🎯 **What's next?**
• Add more files
• Start merging operation
• Check current files
""",
                reply_markup=create_main_keyboard(user_id)
            )
        else:
            await status_msg.edit_text("❌ **Failed to download file**")
            
    except Exception as e:
        logger.error(f"File handler error: {e}")
        await status_msg.edit_text(f"❌ **Error:** {str(e)}")

@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "menu", "stats"]))
async def url_handler(client: Client, message: Message):
    """Handle URL downloads."""
    user_id = message.from_user.id
    
    if not await is_user_authorized(user_id):
        return
    
    text = message.text.strip()
    
    # Check if it's a valid URL
    if not (text.startswith('http://') or text.startswith('https://')):
        await message.reply_text(
            """
💡 **Send me:**
• Video files to merge
• Audio files to add
• Subtitle files to embed
• URLs to download

🎬 **Or use /menu to see options**
""",
            quote=True
        )
        return
    
    await initialize_user_session(user_id, message.from_user.username)
    
    status_msg = await message.reply_text(
        f"""
🔍 **URL Detected!**

🔗 **URL:** `{text[:50]}{'...' if len(text) > 50 else ''}`
⚡ **Status:** Analyzing URL...
""",
        quote=True
    )
    
    try:
        # Download from URL
        async def progress_callback(progress_text: str):
            await status_msg.edit_text(progress_text)
        
        file_path = await download_file_from_url(text, user_id, progress_callback)
        
        if file_path:
            # Process downloaded file same as file upload
            file_type = get_file_type(os.path.basename(file_path))
            filename = os.path.basename(file_path)
            file_size = get_human_readable_size(os.path.getsize(file_path))
            
            # Add to user files
            if file_type == 'video':
                user_files[user_id]['videos'].append(file_path)
            elif file_type == 'audio':
                user_files[user_id]['audios'].append(file_path)
            elif file_type == 'subtitle':
                user_files[user_id]['subtitles'].append(file_path)
            else:
                await status_msg.edit_text(
                    f"❌ **Unsupported file type from URL**\n\n"
                    f"**File:** `{filename}`\n"
                    f"**Type:** `{file_type}`"
                )
                return
            
            user_files[user_id]['last_activity'] = time.time()
            
            await status_msg.edit_text(
                f"""
✅ **URL Download Complete!**

📁 **File:** `{filename}`
📊 **Size:** `{file_size}`
📂 **Type:** `{file_type.title()}`

🎯 **Ready for merge operations!**
""",
                reply_markup=create_main_keyboard(user_id)
            )
        else:
            await status_msg.edit_text("❌ **Failed to download from URL**")
            
    except Exception as e:
        logger.error(f"URL handler error: {e}")
        await status_msg.edit_text(f"❌ **Download Error:** {str(
