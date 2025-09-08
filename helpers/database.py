# helpers/database.py - Updated database operations
import motor.motor_asyncio
from config import config
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(config.DATABASE_URL)
        self.db = self.client.merge_bot
        self.users = self.db.users
        self.settings = self.db.settings
    
    async def add_user(self, user_id: int, name: str):
        """Add new user to database."""
        user_data = {
            "_id": user_id,
            "name": name,
            "allowed": False,
            "banned": False,
            "merge_mode": 1,
            "upload_as_doc": False,
            "auto_thumbnail": True
        }
        
        try:
            await self.users.insert_one(user_data)
        except:
            pass  # User might already exist
    
    async def get_user(self, user_id: int):
        """Get user from database."""
        return await self.users.find_one({"_id": user_id})
    
    async def update_user(self, user_id: int, update_data: dict):
        """Update user data."""
        await self.users.update_one(
            {"_id": user_id},
            {"$set": update_data},
            upsert=True
        )
    
    async def get_all_users(self):
        """Get all users."""
        return await self.users.find({}).to_list(length=None)
    
    async def delete_user(self, user_id: int):
        """Delete user from database."""
        await self.users.delete_one({"_id": user_id})
