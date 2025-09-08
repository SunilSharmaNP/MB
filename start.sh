#!/bin/bash

# Advanced Merge Bot Startup Script

echo "🚀 Starting AdvancedMergeBot..."

# Create necessary directories
mkdir -p downloads temp userdata logs session

# Set permissions
chmod -R 755 downloads temp userdata logs session

# Check if required environment variables are set
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ Error: BOT_TOKEN not set"
    exit 1
fi

if [ -z "$API_HASH" ]; then
    echo "❌ Error: API_HASH not set"
    exit 1
fi

if [ -z "$TELEGRAM_API" ]; then
    echo "❌ Error: TELEGRAM_API not set"
    exit 1
fi

# Check FFmpeg installation
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ Error: FFmpeg not found"
    exit 1
fi

echo "✅ Environment check passed"

# Start the bot
echo "🤖 Starting bot..."
python bot.py
