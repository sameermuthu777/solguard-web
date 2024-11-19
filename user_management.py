from datetime import datetime, date
import logging
from typing import Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClient
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserManager:
    def __init__(self):
        """Initialize UserManager with MongoDB connection"""
        self.mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
        self.client = AsyncIOMotorClient(self.mongo_uri)
        self.db = self.client.solguardian
        self.users = self.db.users
        self.unlimited_users = {'sameerchk'}  # Set of usernames with unlimited access

    async def check_daily_limit(self, telegram_id: int, username: str = None) -> bool:
        """Check if user has reached their daily limit"""
        try:
            # If username is in unlimited_users, always return True
            if username and username.lower() in self.unlimited_users:
                logger.info(f"Unlimited access granted for user {username}")
                return True

            # Get user document
            user = await self.users.find_one({'telegram_id': telegram_id})
            
            if not user:
                # Create new user document
                user = {
                    'telegram_id': telegram_id,
                    'username': username,
                    'subscription_type': 'free',
                    'daily_usage': [],
                    'created_at': datetime.utcnow()
                }
                await self.users.insert_one(user)
                return True

            # Get today's usage count
            today = datetime.utcnow().date()
            today_usage = sum(1 for usage in user.get('daily_usage', [])
                            if datetime.fromisoformat(usage).date() == today)

            # Check subscription type and limits
            if user.get('subscription_type') == 'premium':
                max_daily = 100
            else:
                max_daily = 5

            # Update usage if within limits
            if today_usage < max_daily:
                await self.users.update_one(
                    {'telegram_id': telegram_id},
                    {'$push': {'daily_usage': datetime.utcnow().isoformat()}}
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error in check_daily_limit: {str(e)}", exc_info=True)
            return True  # Allow usage in case of errors to prevent blocking legitimate users

    async def get_user_info(self, telegram_id: int) -> Optional[Dict]:
        """Get user information"""
        try:
            return await self.users.find_one({'telegram_id': telegram_id})
        except Exception as e:
            logger.error(f"Error in get_user_info: {str(e)}", exc_info=True)
            return None

    async def update_subscription(self, telegram_id: int, subscription_type: str) -> bool:
        """Update user's subscription type"""
        try:
            await self.users.update_one(
                {'telegram_id': telegram_id},
                {'$set': {'subscription_type': subscription_type}}
            )
            return True
        except Exception as e:
            logger.error(f"Error in update_subscription: {str(e)}", exc_info=True)
            return False
