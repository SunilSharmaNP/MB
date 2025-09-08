# bot.py - Main bot file with integrated custom modules
import asyncio
import os
import time
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from config import config
from helpers.database import Database
from helpers.downloader import download_file_from_url, download_telegram_file
from helpers.merger import merge_videos, merge_video_with_audio, merge_video_with_subtitles
from helpers.uploader import upload_to_telegram, GofileUploader
from helpers.utils import UserSettings, get_human_readable_size

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()

# Bot states
user_states = {}
user_files = {}

class MergeBot(Client):
    def __init__(self):
        super().__init__(
            name="merge-bot",
            api_hash=config.API_HASH,
            api_id=config.TELEGRAM_API,
            bot_token=config.BOT_TOKEN,
            workers=50
        )
    
    async def start(self):
        await super().start()
        # Create directories
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(config.TEMP_DIR, exist_ok=True)
        
        try:
            await self.send_message(chat_id=int(config.OWNER), text="🤖 **Bot Started Successfully!**")
        except:
            logger.error("Could not send start message to owner")
        
        logger.info("🚀 Merge Bot started successfully!")

# Initialize bot
app = MergeBot()

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handle /start command."""
    user = UserSettings(message.from_user.id, message.from_user.first_name)
    
    if not user.allowed and message.from_user.id != int(config.OWNER):
        await message.reply_text(
            f"👋 Hi **{message.from_user.first_name}**!\n\n"
            f"🔒 You need permission to use this bot.\n"
            f"📧 Contact: @{config.OWNER_USERNAME}",
            quote=True
        )
        return
    
    if message.from_user.id == int(config.OWNER):
        user.allowed = True
        user.set()
    
    welcome_text = f"""
👋 **Welcome {message.from_user.first_name}!**

🎬 **I'm an advanced file merger bot!** 

✨ **Features:**
• 📥 Download from URLs & Telegram
• 🔀 Smart video merging  
• 🎵 Audio track merging
• 📝 Subtitle integration
• 📤 Upload to Telegram & GoFile

🚀 **Send me files or URLs to get started!**

**Owner:** @{config.OWNER_USERNAME}
"""
    
    await message.reply_text(welcome_text, quote=True)

@app.on_message(filters.command("settings") & filters.private)
async def settings_handler(client: Client, message: Message):
    """Handle user settings."""
    user = UserSettings(message.from_user.id, message.from_user.first_name)
    
    if not user.allowed:
        await message.reply_text("❌ You don't have permission to use this bot.", quote=True)
        return
    
    settings_text = f"""
⚙️ **Bot Settings for {message.from_user.first_name}**

📊 **Current Settings:**
• **Merge Mode:** {config.MODES[user.merge_mode - 1]}
• **Upload as Document:** {'✅' if user.upload_as_doc else '❌'}
• **Auto Thumbnail:** {'✅' if user.auto_thumbnail else '❌'}

🔧 **Available Commands:**
• `/mode` - Change merge mode
• `/toggle_doc` - Toggle document upload
• `/toggle_thumb` - Toggle auto thumbnail
"""
    
    await message.reply_text(settings_text, quote=True)

@app.on_message((filters.document | filters.video | filters.audio) & filters.private)
async def file_handler(client: Client, message: Message):
    """Handle file uploads."""
    user_id = message.from_user.id
    user = UserSettings(user_id, message.from_user.first_name)
    
    if not user.allowed and user_id != int(config.OWNER):
        await message.reply_text("❌ You don't have permission to use this bot.", quote=True)
        return
    
    # Initialize user file list
    if user_id not in user_files:
        user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
    
    status_msg = await message.reply_text("📥 **Processing file...**", quote=True)
    
    try:
        # Download file from Telegram
        file_path = await download_telegram_file(client, message, user_id, status_msg)
        
        # Determine file type and add to appropriate list
        media = message.document or message.video or message.audio
        filename = media.file_name or "unknown"
        file_ext = filename.split('.')[-1].lower()
        
        if file_ext in ['mp4', 'mkv', 'avi', 'webm', 'mov']:
            user_files[user_id]['videos'].append(file_path)
            file_type = "video"
        elif file_ext in ['mp3', 'aac', 'wav', 'm4a', 'flac']:
            user_files[user_id]['audios'].append(file_path)
            file_type = "audio"
        elif file_ext in ['srt', 'ass', 'vtt', 'sub']:
            user_files[user_id]['subtitles'].append(file_path)
            file_type = "subtitle"
        else:
            await status_msg.edit_text("❌ **Unsupported file format!**")
            return
        
        # Show current files and merge options
        await show_file_manager(status_msg, user_id, f"✅ **{file_type.title()} file added successfully!**")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error processing file:** `{str(e)}`")

@app.on_message(filters.regex(r'https?://') & filters.private)
async def url_handler(client: Client, message: Message):
    """Handle URL downloads."""
    user_id = message.from_user.id
    user = UserSettings(user_id, message.from_user.first_name)
    
    if not user.allowed and user_id != int(config.OWNER):
        await message.reply_text("❌ You don't have permission to use this bot.", quote=True)
        return
    
    url = message.text.strip()
    status_msg = await message.reply_text("🔗 **Processing URL...**", quote=True)
    
    try:
        # Download file from URL
        file_path = await download_file_from_url(url, user_id, status_msg)
        
        # Initialize user file list
        if user_id not in user_files:
            user_files[user_id] = {'videos': [], 'audios': [], 'subtitles': []}
        
        # Add to video files (assume video for now)
        user_files[user_id]['videos'].append(file_path)
        
        await show_file_manager(status_msg, user_id, "✅ **File downloaded successfully!**")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **Download failed:** `{str(e)}`")

async def show_file_manager(message: Message, user_id: int, header_text: str):
    """Show file manager with merge options."""
    files = user_files.get(user_id, {'videos': [], 'audios': [], 'subtitles': []})
    
    video_count = len(files['videos'])
    audio_count = len(files['audios'])
    subtitle_count = len(files['subtitles'])
    
    manager_text = f"""
{header_text}

📁 **Current Files:**
🎬 Videos: `{video_count}`
🎵 Audios: `{audio_count}`
📝 Subtitles: `{subtitle_count}`

🔄 **Choose merge option:**
"""
    
    keyboard = []
    
    # Merge options based on available files
    if video_count >= 2:
        keyboard.append([InlineKeyboardButton("🎬 Merge Videos", callback_data=f"merge_videos_{user_id}")])
    
    if video_count >= 1 and audio_count >= 1:
        keyboard.append([InlineKeyboardButton("🎵 Add Audio Tracks", callback_data=f"merge_audio_{user_id}")])
    
    if video_count >= 1 and subtitle_count >= 1:
        keyboard.append([InlineKeyboardButton("📝 Add Subtitles", callback_data=f"merge_subs_{user_id}")])
    
    # Management options
    keyboard.extend([
        [InlineKeyboardButton("📋 Show Files", callback_data=f"show_files_{user_id}"),
         InlineKeyboardButton("🗑 Clear All", callback_data=f"clear_files_{user_id}")],
        [InlineKeyboardButton("❌ Close", callback_data=f"close_{user_id}")]
    ])
    
    await message.edit_text(manager_text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    """Handle callback queries."""
    data = callback.data
    user_id = callback.from_user.id
    
    if not data.endswith(f"_{user_id}") and user_id != int(config.OWNER):
        await callback.answer("❌ This is not for you!", show_alert=True)
        return
    
    if data.startswith("merge_videos"):
        await handle_video_merge(client, callback)
    elif data.startswith("merge_audio"):
        await handle_audio_merge(client, callback)
    elif data.startswith("merge_subs"):
        await handle_subtitle_merge(client, callback)
    elif data.startswith("clear_files"):
        await handle_clear_files(callback)
    elif data.startswith("close"):
        await callback.message.delete()

async def handle_video_merge(client: Client, callback: CallbackQuery):
    """Handle video merge process."""
    user_id = callback.from_user.id
    files = user_files.get(user_id, {})
    
    if len(files.get('videos', [])) < 2:
        await callback.answer("❌ Need at least 2 videos to merge!", show_alert=True)
        return
    
    await callback.message.edit_text("🔄 **Starting video merge...**")
    
    try:
        # Merge videos using your custom merger
        output_file = await merge_videos(
            files['videos'], 
            user_id, 
            callback.message,
            f"merged_video_{int(time.time())}"
        )
        
        if output_file:
            await callback.message.edit_text("📤 **Uploading merged video...**")
            
            # Upload options
            keyboard = [
                [InlineKeyboardButton("📱 Telegram", callback_data=f"upload_tg_{user_id}"),
                 InlineKeyboardButton("☁️ GoFile", callback_data=f"upload_gofile_{user_id}")],
                [InlineKeyboardButton("📱➕☁️ Both", callback_data=f"upload_both_{user_id}")]
            ]
            
            await callback.message.edit_text(
                "✅ **Video merged successfully!**\n\n📤 **Choose upload destination:**",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Store output file for upload
            user_files[user_id]['output'] = output_file
        else:
            await callback.message.edit_text("❌ **Video merge failed!**")
            
    except Exception as e:
        await callback.message.edit_text(f"❌ **Merge error:** `{str(e)}`")

async def handle_audio_merge(client: Client, callback: CallbackQuery):
    """Handle audio merge process."""
    user_id = callback.from_user.id
    files = user_files.get(user_id, {})
    
    videos = files.get('videos', [])
    audios = files.get('audios', [])
    
    if not videos or not audios:
        await callback.answer("❌ Need video and audio files!", show_alert=True)
        return
    
    await callback.message.edit_text("🎵 **Starting audio merge...**")
    
    try:
        output_file = await merge_video_with_audio(
            videos[0],  # Use first video
            audios,
            user_id,
            callback.message,
            f"merged_audio_{int(time.time())}"
        )
        
        if output_file:
            await callback.message.edit_text("✅ **Audio merged successfully!**")
            user_files[user_id]['output'] = output_file
            await show_upload_options(callback, user_id)
        else:
            await callback.message.edit_text("❌ **Audio merge failed!**")
            
    except Exception as e:
        await callback.message.edit_text(f"❌ **Audio merge error:** `{str(e)}`")

async def handle_subtitle_merge(client: Client, callback: CallbackQuery):
    """Handle subtitle merge process."""
    user_id = callback.from_user.id
    files = user_files.get(user_id, {})
    
    videos = files.get('videos', [])
    subtitles = files.get('subtitles', [])
    
    if not videos or not subtitles:
        await callback.answer("❌ Need video and subtitle files!", show_alert=True)
        return
    
    await callback.message.edit_text("📝 **Starting subtitle merge...**")
    
    try:
        output_file = await merge_video_with_subtitles(
            videos[0],  # Use first video
            subtitles,
            user_id,
            callback.message,
            f"merged_subs_{int(time.time())}"
        )
        
        if output_file:
            await callback.message.edit_text("✅ **Subtitles merged successfully!**")
            user_files[user_id]['output'] = output_file
            await show_upload_options(callback, user_id)
        else:
            await callback.message.edit_text("❌ **Subtitle merge failed!**")
            
    except Exception as e:
        await callback.message.edit_text(f"❌ **Subtitle merge error:** `{str(e)}`")

async def show_upload_options(callback: CallbackQuery, user_id: int):
    """Show upload destination options."""
    keyboard = [
        [InlineKeyboardButton("📱 Telegram", callback_data=f"upload_tg_{user_id}"),
         InlineKeyboardButton("☁️ GoFile", callback_data=f"upload_gofile_{user_id}")],
        [InlineKeyboardButton("📱➕☁️ Both", callback_data=f"upload_both_{user_id}")]
    ]
    
    await callback.message.edit_text(
        "📤 **Choose upload destination:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_clear_files(callback: CallbackQuery):
    """Clear all user files."""
    user_id = callback.from_user.id
    
    # Clear user files
    if user_id in user_files:
        # Clean up downloaded files
        for file_list in user_files[user_id].values():
            if isinstance(file_list, list):
                for file_path in file_list:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        pass
        
        del user_files[user_id]
    
    await callback.message.edit_text("🗑 **All files cleared successfully!**")
    
    # Auto delete message after 3 seconds
    await asyncio.sleep(3)
    await callback.message.delete()

if __name__ == "__main__":
    print("🚀 Starting Enhanced Merge Bot...")
    app.run()
