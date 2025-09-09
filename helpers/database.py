# helpers/database.py - Complete and working database implementation
import asyncio
import logging
from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from config import config

logger = logging.getLogger(__name__)

class Database:
    """Enhanced MongoDB database handler with complete functionality."""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.users = None
        self.settings = None
        self.files = None
        self.stats = None
        self._connect()
    
    def _connect(self):
        """Establish database connection."""
        try:
            if config.DATABASE_URL:
                self.client = MongoClient(config.DATABASE_URL)
                self.db = self.client.merge_bot
                self.users = self.db.users
                self.settings = self.db.user_settings  
                self.files = self.db.user_files
                self.stats = self.db.bot_stats
                logger.info("✅ Database connected successfully!")
            else:
                logger.warning("⚠️ No DATABASE_URL provided. Using memory storage.")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            self.client = None
    
    async def add_user(self, user_id: int, name: str, username: str = None) -> bool:
        """Add new user to database."""
        try:
            if not self.users:
                return False
                
            user_data = {
                "_id": user_id,
                "name": name,
                "username": username,
                "join_date": asyncio.get_event_loop().time(),
                "total_merges": 0,
                "total_size_processed": 0,
                "is_premium": False,
                "is_banned": False,
                "last_activity": asyncio.get_event_loop().time()
            }
            
            result = await asyncio.to_thread(
                self.users.update_one,
                {"_id": user_id},
                {"$setOnInsert": user_data},
                upsert=True
            )
            
            logger.info(f"👤 User {name} ({user_id}) added to database")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add user {user_id}: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information."""
        try:
            if not self.users:
                return None
                
            user = await asyncio.to_thread(
                self.users.find_one,
                {"_id": user_id}
            )
            return user
            
        except Exception as e:
            logger.error(f"❌ Failed to get user {user_id}: {e}")
            return None
    
    async def update_user_activity(self, user_id: int) -> bool:
        """Update user's last activity timestamp."""
        try:
            if not self.users:
                return False
                
            await asyncio.to_thread(
                self.users.update_one,
                {"_id": user_id},
                {"$set": {"last_activity": asyncio.get_event_loop().time()}}
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update activity for {user_id}: {e}")
            return False
    
    async def ban_user(self, user_id: int) -> bool:
        """Ban a user."""
        try:
            if not self.users:
                return False
                
            await asyncio.to_thread(
                self.users.update_one,
                {"_id": user_id},
                {"$set": {"is_banned": True}}
            )
            logger.info(f"🚫 User {user_id} has been banned")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to ban user {user_id}: {e}")
            return False
    
    async def unban_user(self, user_id: int) -> bool:
        """Unban a user."""
        try:
            if not self.users:
                return False
                
            await asyncio.to_thread(
                self.users.update_one,
                {"_id": user_id},
                {"$set": {"is_banned": False}}
            )
            logger.info(f"✅ User {user_id} has been unbanned")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to unban user {user_id}: {e}")
            return False
    
    async def get_user_settings(self, user_id: int) -> Dict:
        """Get user settings."""
        try:
            if not self.settings:
                return self._default_settings()
                
            settings = await asyncio.to_thread(
                self.settings.find_one,
                {"_id": user_id}
            )
            
            if settings:
                return settings
            else:
                # Create default settings for new user
                default = self._default_settings()
                default["_id"] = user_id
                await asyncio.to_thread(
                    self.settings.insert_one,
                    default
                )
                return default
                
        except Exception as e:
            logger.error(f"❌ Failed to get settings for {user_id}: {e}")
            return self._default_settings()
    
    async def update_user_settings(self, user_id: int, settings: Dict) -> bool:
        """Update user settings."""
        try:
            if not self.settings:
                return False
                
            await asyncio.to_thread(
                self.settings.update_one,
                {"_id": user_id},
                {"$set": settings},
                upsert=True
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update settings for {user_id}: {e}")
            return False
    
    async def increment_user_stats(self, user_id: int, merges: int = 1, size: int = 0) -> bool:
        """Increment user statistics."""
        try:
            if not self.users:
                return False
                
            await asyncio.to_thread(
                self.users.update_one,
                {"_id": user_id},
                {
                    "$inc": {
                        "total_merges": merges,
                        "total_size_processed": size
                    }
                }
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update stats for {user_id}: {e}")
            return False
    
    async def get_bot_stats(self) -> Dict:
        """Get overall bot statistics."""
        try:
            if not self.users:
                return {"total_users": 0, "total_merges": 0, "total_size": 0}
                
            pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_users": {"$sum": 1},
                        "total_merges": {"$sum": "$total_merges"},
                        "total_size": {"$sum": "$total_size_processed"}
                    }
                }
            ]
            
            result = await asyncio.to_thread(
                lambda: list(self.users.aggregate(pipeline))
            )
            
            if result:
                return result[0]
            else:
                return {"total_users": 0, "total_merges": 0, "total_size": 0}
                
        except Exception as e:
            logger.error(f"❌ Failed to get bot stats: {e}")
            return {"total_users": 0, "total_merges": 0, "total_size": 0}
    
    def _default_settings(self) -> Dict:
        """Return default user settings."""
        return {
            "merge_mode": 1,
            "upload_as_doc": False,
            "auto_thumbnail": True,
            "notification": True,
            "quality_preset": "high",
            "custom_name_format": "[MergedBot]_{original_name}",
            "auto_delete_source": False
        }
    
    async def close(self):
        """Close database connection."""
        try:
            if self.client:
                await asyncio.to_thread(self.client.close)
                logger.info("🔌 Database connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing database: {e}")

# Global database instance
database = Database()
