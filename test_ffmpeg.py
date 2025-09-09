# test_ffmpeg.py - Test FFmpeg installation
import asyncio
import subprocess
import sys

async def test_ffmpeg():
    """Test FFmpeg installation and functionality."""
    print("🔍 Testing FFmpeg installation...")
    
    try:
        # Test FFmpeg
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg found: {version_line}")
        else:
            print("❌ FFmpeg not working properly")
            return False
            
        # Test FFprobe
        result = subprocess.run(['ffprobe', '-version'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFprobe found: {version_line}")
        else:
            print("❌ FFprobe not working properly")
            return False
        
        print("🎉 FFmpeg installation is working correctly!")
        return True
        
    except FileNotFoundError:
        print("❌ FFmpeg not found in system PATH")
        print("Please install FFmpeg:")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  CentOS/RHEL: sudo yum install ffmpeg")
        print("  macOS: brew install ffmpeg")
        print("  Windows: Download from https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        print("❌ FFmpeg test timed out")
        return False
    except Exception as e:
        print(f"❌ Error testing FFmpeg: {e}")
        return False

if __name__ == "__main__":
    if asyncio.run(test_ffmpeg()):
        print("\n✅ Your system is ready to run the merger bot!")
        sys.exit(0)
    else:
        print("\n❌ Please fix FFmpeg installation before running the bot.")
        sys.exit(1)
