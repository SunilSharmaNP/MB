# helpers/__init__.py
"""Helper modules for AdvancedMergeBot"""

__version__ = "1.0.0"
__author__ = "AdvancedMergeBot"

# Import all helper functions for easy access
from .database import database
from .downloader import download_file_from_url, download_telegram_file
from .merger import merge_videos, merge_video_with_audio, merge_video_with_subtitles
from .uploader import upload_to_telegram, GofileUploader, dual_upload

__all__ = [
    'database',
    'download_file_from_url',
    'download_telegram_file', 
    'merge_videos',
    'merge_video_with_audio',
    'merge_video_with_subtitles',
    'upload_to_telegram',
    'GofileUploader',
    'dual_upload'
]
