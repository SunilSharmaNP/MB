# 🎬 AdvancedMergeBot
<div align="center">
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-Powered-green.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
**A powerful Telegram bot for merging videos, audio tracks, and subtitles with advanced features**
[Features](#-features) • [Quick Start](#-quick-start) • [Installation](#-installation) • [Configuration](#-configuration) • [Docker](#-docker-deployment) • [Support](#-support)
</div>
---
## 🌟 Features
### 🎞️ **Smart Video Merging**
- **Ultra-Fast Merge**: Lossless concatenation for identical videos
- **Compatible Merge**: Automatic re-encoding for different formats
- **Intelligent Detection**: Automatically chooses optimal merge method
- **Batch Processing**: Merge multiple videos at once (up to 20)
### 🎵 **Audio & Subtitle Integration**
- **Multi-Audio**: Add multiple audio tracks to videos
- **Subtitle Embedding**: Support for SRT, ASS, VTT formats
- **Stream Preservation**: Maintains all existing streams
### 📥 **Universal Downloads**
- **URL Support**: Direct downloads from any URL
- **GoFile Integration**: Advanced GoFile link processing with password support
- **Telegram Files**: Direct file processing from Telegram
- **Smart Filename**: Intelligent filename extraction and sanitization
### 📤 **Dual Upload System**
- **Telegram Upload**: Direct upload with progress tracking
- **GoFile Upload**: Cloud storage with shareable links
- **Simultaneous Upload**: Upload to both platforms at once
- **Auto-Thumbnails**: Automatic thumbnail generation for videos
### 🎨 **Beautiful Interface**
- **Real-time Progress**: Beautiful progress bars with ETA
- **Smart Throttling**: Optimized for Telegram rate limits
- **Responsive UI**: Clean and intuitive button layouts
- **Status Updates**: Detailed operation feedback
### 🛡️ **Advanced Features**
- **User Management**: Authentication and access control
- **Database Storage**: MongoDB integration for user data
- **Error Handling**: Robust error recovery and reporting
- **Statistics**: Detailed usage analytics
- **Owner Commands**: Administrative controls and broadcasting
---
## 🚀 Quick Start
### Prerequisites
- Python 3.11+
- FFmpeg installed
- MongoDB database
- Telegram Bot Token
### 1️⃣ Clone Repository
```bash
git clone https://github.com/yourusername/AdvancedMergeBot.git
cd AdvancedMergeBot
2️⃣ Install Dependencies
pip install -r requirements.txt
3️⃣ Configure Bot
cp sample_config.env config.env
nano config.env  # Edit with your values
4️⃣ Run Bot
python bot.py
📋 Installation
🐧 Linux/Ubuntu
# Install FFmpeg
sudo apt update
sudo apt install ffmpeg python3 python3-pip git
# Clone and setup
git clone https://github.com/yourusername/AdvancedMergeBot.git
cd AdvancedMergeBot
pip3 install -r requirements.txt
# Configure
cp sample_config.env config.env
# Edit config.env with your settings
# Run
python3 bot.py
🪟 Windows
# Install FFmpeg (using chocolatey)
choco install ffmpeg
# Or download from https://ffmpeg.org/download.html
# Clone repository
git clone https://github.com/yourusername/AdvancedMergeBot.git
cd AdvancedMergeBot
# Install dependencies
pip install -r requirements.txt
# Configure and run
copy sample_config.env config.env
python bot.py
🍎 macOS
# Install FFmpeg
brew install ffmpeg python3 git
# Setup bot
git clone https://github.com/yourusername/AdvancedMergeBot.git
cd AdvancedMergeBot
pip3 install -r requirements.txt
# Configure
cp sample_config.env config.env
python3 bot.py
⚙️ Configuration
🔑 Required Settings
Variable	Description	Example
API_HASH	Telegram API Hash	1234567890abcdef...
TELEGRAM_API	Telegram API ID	12345678
BOT_TOKEN	Bot Token from BotFather	1234567890:ABC...
OWNER	Your Telegram User ID	987654321
OWNER_USERNAME	Your Telegram Username	yourusername
PASSWORD	Bot Access Password	MySecretPass123
DATABASE_URL	MongoDB Connection	mongodb://localhost:27017/mergebot
🔧 Optional Settings
Variable	Description	Default
GOFILE_TOKEN	GoFile API Token	None (Anonymous)
LOGCHANNEL	Log Channel ID	None
MAX_FILE_SIZE	Max file size (bytes)	2147483648 (2GB)
EDIT_THROTTLE_SECONDS	Progress update interval	2.0
DEFAULT_QUALITY	Merge quality preset	high
🎬 How to Use
Send Files: Upload videos, audio, or subtitle files
Add More: Send multiple files to build your collection
Choose Action: Use menu buttons to select merge type:
🎞️ Merge Videos
🎵 Add Audio Tracks
📝 Add Subtitles
Upload: Choose destination (Telegram/GoFile/Both)
Done: Get your merged file!
🔧 Advanced Features
🎨 Merge Modes
🚀 Ultra-Fast Merge
Used when all videos have identical parameters
No re-encoding (lossless)
Fastest processing speed
Maintains original quality
🔄 Compatible Merge
Used when videos have different formats/settings
Automatic parameter harmonization
Re-encoding for compatibility
High-quality output (CRF 18)
🎵 Audio Integration
Add multiple audio tracks to video
Preserves original video quality
Supports various audio formats
Stream copying for efficiency
📝 Subtitle Embedding
Embed multiple subtitle tracks
Support for SRT, ASS, VTT formats
Soft subtitles (can be toggled)
Language metadata preservation
📊 Progress Tracking
Real-time progress bars
Download/Upload speeds
ETA calculations
Smart throttling to avoid rate limits
🛡️ Security Features
User authentication system
Owner-only commands
Ban/unban functionality
Access control per user
🏗️ Project Structure
📁 AdvancedMergeBot/
├── 📁 helpers/
│   ├── database.py          # MongoDB operations
│   ├── downloader.py        # URL & file downloads  
│   ├── merger.py           # Video merging logic
│   └── uploader.py         # Upload handlers
├── 📁 plugins/
│   └── cb_handler.py       # Callback handlers
├── 📄 bot.py              # Main bot application
├── 📄 config.py           # Configuration management
├── 📄 utils.py            # Utility functions
├── 📄 requirements.txt    # Python dependencies
├── 📄 Dockerfile          # Docker configuration
├── 📄 docker-compose.yml  # Docker Compose setup
└── 📄 sample_config.env   # Configuration template
🤝 Contributing
We welcome contributions! Here's how you can help:

🐛 Bug Reports
Use GitHub Issues
Include detailed steps to reproduce
Attach relevant logs
💡 Feature Requests
Describe the feature clearly
Explain use cases
Consider implementation complexity
🔧 Pull Requests
Fork the repository
Create feature branch
Make changes with tests
Submit pull request
📋 Development Setup
# Clone your fork
git clone https://github.com/yourusername/AdvancedMergeBot.git
cd AdvancedMergeBot
# Install development dependencies
pip install -r requirements.txt
pip install black flake8 pytest
# Run tests
pytest tests/
# Format code
black .
📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

🆘 Support
📞 Get Help
📧 Email: support@yourbot.com
💬 Telegram: @YourSupportChannel
🐛 Issues: GitHub Issues
📚 Documentation
Installation Guide
Configuration Reference
API Documentation
Troubleshooting
🔧 Common Issues
Bot not responding?
Check bot token
Verify internet connection
Review error logs
Merge failed?
Ensure FFmpeg is installed
Check file formats
Verify sufficient disk space
Database errors?
Confirm MongoDB is running
Check connection string
Verify database permissions
🙏 Acknowledgments
Pyrogram - Modern Telegram Bot API framework
FFmpeg - Multimedia processing library
MongoDB - Database solution
All Contributors - Thank you for making this project better!
📈 Statistics
Unsupported image

Unsupported image

Unsupported image

Unsupported image

<div align="center">
⭐ If you found this project helpful, please give it a star! ⭐

Made with ❤️ by YourName

</div> ```
This comprehensive README includes:

✨ Beautiful formatting with emojis and badges
📋 Complete feature overview
🚀 Quick start guide
📖 Detailed installation instructions
⚙️ Configuration reference
🐳 Docker deployment guide
🎯 Usage instructions
🏗️ Project structure
🤝 Contributing guidelines
🆘 Support information
