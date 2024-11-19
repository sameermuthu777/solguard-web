from token_security import TokenSecurityChecker, TokenSecurityResult
import os
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime
from dateutil.tz import tzutc
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    CallbackContext,
    filters
)
from telegram.constants import ParseMode
from telegram.error import Conflict, NetworkError
from pymongo import MongoClient
import base58
import psutil
import httpx
from user_management import UserManager
from rugcheck_ui import RugcheckUI
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import re
from http import HTTPStatus
from scraper import RugcheckScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize UserManager
user_manager = UserManager()
rugcheck_ui = RugcheckUI()

# Constants
TRIAL_PERIOD = 24 * 60 * 60  # 24 hours
FREE_DAILY_CHECKS = 5
PREMIUM_DAILY_CHECKS = 100
MONTHLY_PLAN = 30 * 24 * 60 * 60
ANNUAL_PLAN = 365 * 24 * 60 * 60

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
try:
    db_client = MongoClient(MONGO_URI)
    # Test the connection
    db_client.admin.command('ping')
    db = db_client.solguardian
    users_collection = db.users
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    raise

# Bot token
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def verify_user_subscription(user_id: int, current_time: float) -> Optional[Dict]:
    """Verify user subscription and limits"""
    user = users_collection.find_one({"telegram_id": user_id})
    if not user:
        return None
        
    last_check_date = float(user.get("last_check_date", 0))
    
    # Handle subscription_end as datetime or timestamp
    subscription_end_value = user.get("subscription_end", 0)
    if isinstance(subscription_end_value, datetime):
        subscription_end = subscription_end_value.timestamp()
    elif isinstance(subscription_end_value, int):
        subscription_end = subscription_end_value
    else:
        subscription_end = float(subscription_end_value)
    
    daily_limit = PREMIUM_DAILY_CHECKS if subscription_end > current_time else FREE_DAILY_CHECKS
    
    # Reset daily checks if it's a new day
    if current_time - last_check_date > 24 * 60 * 60:
        users_collection.update_one(
            {"telegram_id": user_id},
            {"$set": {"daily_checks": 0, "last_check_date": current_time}}
        )
        user["daily_checks"] = 0
    elif user.get("daily_checks", 0) >= daily_limit:
        raise ValueError(f"Daily limit of {daily_limit} checks reached")
        
    return user

async def update_user_check_count(user_id: int):
    """Update user's daily check count"""
    users_collection.update_one(
        {"telegram_id": user_id},
        {"$inc": {"daily_checks": 1}}
    )

def is_valid_solana_address(address: str) -> bool:
    """Validate Solana address format"""
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except:
        return False

async def start(update: Update, context: CallbackContext):
    """Start command handler"""
    try:
        user_id = update.effective_user.id
        current_time = datetime.now(tzutc()).timestamp()
        
        try:
            user = users_collection.find_one({"telegram_id": user_id})
            if not user:
                users_collection.insert_one({
                    "telegram_id": user_id,
                    "username": update.effective_user.username,
                    "subscription_end": current_time + TRIAL_PERIOD,
                    "subscription_type": "trial",
                    "daily_checks": 0,
                    "last_check_date": current_time,
                    "created_at": current_time,
                    "welcome_shown": True
                })
                show_welcome = True
                logger.info(f"New user registered: {user_id}")
            else:
                show_welcome = not user.get("welcome_shown", False)
                if show_welcome:
                    users_collection.update_one(
                        {"telegram_id": user_id},
                        {"$set": {"welcome_shown": True}}
                    )
        except Exception as e:
            logger.error(f"MongoDB operation failed for user {user_id}: {str(e)}")
            await update.message.reply_text(
                "❌ An error occurred while setting up your account. Please try again later."
            )
            return
        
        keyboard = [
            [InlineKeyboardButton("🛡️ Check Token", callback_data="guide_check"),
             InlineKeyboardButton("⭐️ Premium", callback_data="guide_premium")],
            [InlineKeyboardButton("🔍 Rugcheck UI", callback_data="rugcheck_ui")],
            [InlineKeyboardButton("❓ Help", callback_data="guide_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if show_welcome:
            welcome_message = (
                "🌟 <b>Welcome to Solana Guard!</b> 🌟\n\n"
                "I'm your advanced Solana token security assistant. Let me help you make safer trading decisions!\n\n"
                "🔍 <b>What I Can Do:</b>\n"
                "• Rugpull & scam detection\n"
                "• Honeypot analysis\n"
                "• Liquidity lock check\n"
                "• Holder concentration\n"
                "• Risk scoring & alerts\n\n"
                "🛠 <b>Available Commands:</b>\n"
                "• /check [token_address] - Analyze token security\n"
                "• /subscribe - View premium features\n"
                "• /status - Check account status\n\n"
                "🎁 <b>Trial Benefits:</b>\n"
                f"• {FREE_DAILY_CHECKS} free checks per day\n"
                "• Basic security analysis\n"
                "• 24-hour trial period\n\n"
                "🔐 <b>Premium Features:</b>\n"
                "• Unlimited token checks\n"
                "• Advanced risk metrics\n"
                "• Real-time monitoring\n"
                "• Priority support\n\n"
                "Ready to check a token? Choose below! 👇"
            )
            await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        else:
            brief_message = (
                "🛡️ <b>SOLANA GUARD</b>\n"
                "🔒 <b>Your Solana Security Guardian</b>\n\n"
                "🎯 <b>AVAILABLE ACTIONS:</b>\n\n"
                "🔍 <b>Check Token Security</b>\n"
                "   • Rugpull & scam detection\n"
                "   • Honeypot analysis\n"
                "   • Liquidity lock check\n"
                "   • Holder concentration\n"
                "   • Risk scoring & alerts\n\n"
                "💎 <b>Premium Features</b>\n"
                "   • Advanced metrics\n"
                "   • Unlimited checks\n\n"
                "ℹ️ <b>Help & Support</b>\n"
                "   • Usage guides\n"
                "   • Command list\n\n"
                "<i>Select an option below to begin:</i>"
            )
            await update.message.reply_text(brief_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        await update.message.reply_text(
            "❌ An error occurred. Please try again later."
        )

async def check_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle token address input and perform security analysis."""
    try:
        user_id = update.effective_user.id
        
        # Check daily limit
        can_proceed = await user_manager.check_daily_limit(user_id, update.effective_user.username)
        if not can_proceed:
            await update.message.reply_text(
                "❌ You have reached your daily limit of token checks.\n"
                "Please subscribe to our premium plan for unlimited checks! /subscribe"
            )
            return

        token_address = update.message.text.strip()
        
        if not is_valid_solana_address(token_address):
            await update.message.reply_text(
                "❌ Invalid Solana token address. Please provide a valid address."
            )
            return
        
        # Send initial processing message with loading animation
        loading_messages = [
            "🔍 Initializing Security Scan...",
            "🔍 Analyzing Token Contract...",
            "🔍 Checking Liquidity Pools...",
            "🔍 Scanning Holder Distribution...",
            "🔍 Detecting Market Patterns...",
            "🔍 Verifying Lock Status...",
            "🔍 Running Risk Assessment...",
            "🔍 Finalizing Analysis..."
        ]
        
        status_message = await update.message.reply_text(loading_messages[0])
        
        try:
            # Initialize security checker
            security_checker = TokenSecurityChecker()
            
            # Start the actual security check in the background
            analysis_task = asyncio.create_task(security_checker.check_token(token_address))
            
            # Simulate loading sequence
            for i, message in enumerate(loading_messages[1:], 1):
                await asyncio.sleep(1.0)  # Add delay between messages
                progress = "▰" * i + "▱" * (len(loading_messages) - i - 1)
                await status_message.edit_text(
                    f"{message}\n\n"
                    f"Progress: {progress} {i * 100 // (len(loading_messages)-1)}%\n"
                    f"⏳ Time Remaining: {len(loading_messages) - i} seconds"
                )
            
            # After animation, show processing state if analysis isn't complete
            processing_dots = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            dot_idx = 0
            
            while not analysis_task.done():
                await status_message.edit_text(
                    f"🔄 Deep Analysis in Progress {processing_dots[dot_idx]}\n\n"
                    "🔍 Running Extended Security Checks...\n"
                    "⏳ Please wait a moment..."
                )
                dot_idx = (dot_idx + 1) % len(processing_dots)
                await asyncio.sleep(0.3)  # Smooth spinner animation
            
            # Get the analysis result
            result = await analysis_task
            
            # Show completion message briefly
            await status_message.edit_text(
                "✅ Analysis Complete!\n\n"
                "📊 Generating Detailed Report..."
            )
            await asyncio.sleep(0.5)
            
            # Format and send final results
            analysis_text = security_checker.format_token_analysis(result)
            await status_message.edit_text(analysis_text, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            error_message = (
                "❌ Error analyzing token:\n"
                f"{str(e)}\n\n"
                "Please verify the token address and try again."
            )
            await status_message.edit_text(error_message, parse_mode=ParseMode.HTML)
        
        # Reset waiting flags
        if 'waiting_for_token' in context.user_data:
            context.user_data['waiting_for_token'] = False
        if 'meme_check' in context.user_data:
            context.user_data['meme_check'] = False

    except Exception as e:
        logger.error(f"Error in check token: {str(e)}")
        await update.message.reply_text(
            "❌ An error occurred. Please try again later."
        )

async def subscribe(update: Update, context: CallbackContext):
    """Subscribe command handler"""
    keyboard = [
        [InlineKeyboardButton("🌟 Premium Monthly - $25", callback_data="plan_premium_monthly")],
        [InlineKeyboardButton("💎 Premium Annual - $250", callback_data="plan_premium_annual")],
        [InlineKeyboardButton("👑 Enterprise - Contact Us", callback_data="plan_enterprise")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        "🌟 <b>SolGuardian Premium Features</b>\n\n"
        "Upgrade your trading security with our premium plans!\n\n"
        "🎯 <b>Premium Monthly - $25</b>\n"
        "• Unlimited token checks\n"
        "• Advanced risk metrics\n"
        "• Real-time monitoring\n"
        "• Priority support\n"
        "• Early access to new features\n\n"
        "💎 <b>Premium Annual - $250</b>\n"
        "• All Premium Monthly features\n"
        "• 17% discount\n"
        "• Custom alerts\n"
        "• Market insights\n"
        "• API access\n\n"
        "👑 <b>Enterprise</b>\n"
        "• Custom solutions\n"
        "• Dedicated support\n"
        "• API integration\n"
        "• Custom metrics\n"
        "• Team management\n\n"
        "<i>Choose your plan below:</i>"
    )
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def status(update: Update, context: CallbackContext):
    """Status command handler"""
    user_id = update.effective_user.id
    user = users_collection.find_one({"telegram_id": user_id})
    
    if not user:
        await update.message.reply_text(
            "❌ <b>Account Not Found</b>\n\n"
            "Please use /start to create your account.",
            parse_mode=ParseMode.HTML
        )
        return
    
    current_time = datetime.now(tzutc()).timestamp()
    subscription_end = float(user.get("subscription_end", 0))
    subscription_type = user.get("subscription_type", "trial")
    daily_checks = user.get("daily_checks", 0)
    daily_limit = PREMIUM_DAILY_CHECKS if subscription_end > current_time else FREE_DAILY_CHECKS
    
    time_left = subscription_end - current_time
    days_left = max(0, int(time_left / (24 * 60 * 60)))
    hours_left = max(0, int((time_left % (24 * 60 * 60)) / 3600))
    
    status_message = (
        "📊 <b>Your Account Status</b>\n\n"
        f"🎫 <b>Plan:</b> {subscription_type.title()}\n"
        f"📈 <b>Daily Checks:</b> {daily_checks}/{daily_limit}\n"
        f"⏳ <b>Time Remaining:</b> {days_left}d {hours_left}h\n\n"
    )
    
    # Add usage tips based on subscription type
    if subscription_type == "trial":
        status_message += (
            "🎁 <b>Trial Benefits:</b>\n"
            f"• {FREE_DAILY_CHECKS} free checks daily\n"
            "• Basic security analysis\n"
            "• Community support\n\n"
            "🌟 <b>Upgrade to Premium for:</b>\n"
            "• Unlimited daily checks\n"
            "• Advanced risk metrics\n"
            "• Priority support"
        )
    else:
        status_message += (
            "✨ <b>Premium Benefits Active:</b>\n"
            "• Unlimited daily checks\n"
            "• Advanced risk metrics\n"
            "• Priority support\n"
            "• Real-time monitoring"
        )
    
    if current_time > subscription_end:
        keyboard = [[InlineKeyboardButton("🌟 Upgrade to Premium", callback_data="subscribe")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        status_message += (
            "\n\n❗️ <b>Subscription Expired</b>\n"
            "Upgrade now to unlock premium features!"
        )
        await update.message.reply_text(status_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(status_message, parse_mode=ParseMode.HTML)

async def handle_subscription(query: CallbackQuery, plan: str):
    """Handle subscription callbacks"""
    try:
        user_id = query.from_user.id
        current_time = datetime.now(tzutc()).timestamp()
        
        if plan == "monthly":
            subscription_duration = MONTHLY_PLAN
        elif plan == "annual":
            subscription_duration = ANNUAL_PLAN
        else:
            subscription_duration = MONTHLY_PLAN
            
        subscription_end = current_time + subscription_duration
        
        subscription_data = {
            "telegram_id": user_id,
            "subscription_type": plan,
            "subscription_end": subscription_end,
            "status": "pending",
            "updated_at": current_time
        }
        
        users_collection.update_one(
            {"telegram_id": user_id},
            {"$set": subscription_data},
            upsert=True
        )
        
        await query.message.reply_text(
            f"Thanks for choosing the {plan.title()} plan!\n\n"
            "For now, please contact @admin to complete your subscription."
        )
        
    except Exception as e:
        logger.error(f"Error handling subscription: {str(e)}")
        await query.message.reply_text(
            "❌ Error processing subscription request.\n"
            "Please try again later or contact support."
        )

async def handle_callback_query(update: Update, context: CallbackContext):
    """Callback query handler"""
    try:
        query = update.callback_query
        await query.answer()

        if query.data.startswith("plan_"):
            plan = query.data.split("_")[1]
            await handle_subscription(query, plan)
        elif query.data == "subscribe":
            await subscribe(update, context)
        elif query.data == "guide_check":
            context.user_data['waiting_for_token'] = True
            guide_message = (
                "🔍 <b>Enter Token Address for Security Check:</b>\n\n"
                "Simply paste the Solana token address here and I'll check its security for you.\n\n"
                "Example address:\n"
                "<code>So11111111111111111111111111111111111111112</code>\n\n"
                "✨ <b>Tips:</b>\n"
                "• Make sure to use the correct token address\n"
                "• Wait for the security check to complete\n"
                "• Review all risk indicators carefully\n\n"
                "🔍 <b>Where to find the token address:</b>\n"
                "• Solscan.io\n"
                "• Solana Explorer\n"
                "• DexScreener\n"
                "• Birdeye\n\n"
            )
            await query.message.edit_text(guide_message, parse_mode=ParseMode.HTML)
        elif query.data == "guide_help":
            await query.message.edit_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)
        elif query.data == "rugcheck_ui":
            try:
                await rugcheck_ui.show_rugcheck_input(update, context)
            except Exception as e:
                logger.error(f"Error showing Rugcheck UI: {str(e)}")
                await query.message.edit_text(
                    "❌ Error launching Rugcheck UI. Please try again later.",
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Error in callback query handler: {str(e)}")
        try:
            await update.callback_query.message.edit_text(
                "❌ An error occurred. Please try again later.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

async def handle_message(update: Update, context: CallbackContext):
    """Handle regular messages"""
    if not context.user_data.get('waiting_for_token'):
        return

    # Pass the message to check_token function
    await check_token(update, context)

async def error_handler(update: Update, context: CallbackContext):
    """Error handler"""
    error = context.error
    
    try:
        raise error
    except Conflict:
        logger.warning('Conflict error: %s', error)
    except NetworkError:
        logger.warning('Network error: %s', error)
    except Exception as e:
        logger.error('Update "%s" caused error "%s"', update, error)
        if update and update.message:
            await update.message.reply_text(
                "❌ An error occurred. Please try again later."
            )

# Initialize scraper
scraper = RugcheckScraper()

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if MongoDB is connected
        client = MongoClient(MONGO_URI)
        client.admin.command('ping')
        
        # Check system resources
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        return {
            "status": "healthy",
            "mongodb": "connected",
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analyze/{token_address}")
async def analyze_token(token_address: str):
    """Analyze a token address"""
    logger.info(f"Received analysis request for token: {token_address}")
    try:
        # Basic validation
        if not token_address or len(token_address) < 32 or len(token_address) > 44:
            logger.warning(f"Invalid token address format: {token_address}")
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid token address format"
            )
        
        try:
            # Validate base58 format
            base58.b58decode(token_address)
        except Exception as e:
            logger.warning(f"Invalid base58 encoding for token: {token_address}, error: {str(e)}")
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid token address encoding"
            )
        
        logger.info(f"Starting token analysis for: {token_address}")
        # Initialize scraper for each request to avoid state conflicts
        scraper_instance = RugcheckScraper()
        
        try:
            data = await scraper_instance.analyze_token(token_address)
            
            if not data:
                logger.warning(f"No data found for token: {token_address}")
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail="Token data not found"
                )
            
            # Ensure all required fields are present
            required_fields = {
                'token_info': ['mint', 'name', 'symbol', 'supply'],
                'market_data': ['total_liquidity', 'lp_providers', 'markets'],
                'security': ['is_rugged', 'transfer_fee', 'risks', 'score', 'security_score'],
                'verification': ['is_verified', 'links'],
                'community': ['upvotes', 'downvotes']
            }
            
            for section, fields in required_fields.items():
                if section not in data:
                    logger.error(f"Missing section in response: {section}")
                    data[section] = {}
                
                for field in fields:
                    if field not in data[section]:
                        logger.warning(f"Missing field in {section}: {field}")
                        if field in ['risks', 'markets']:
                            data[section][field] = []
                        elif field in ['links']:
                            data[section][field] = {}
                        elif field in ['is_rugged', 'is_verified']:
                            data[section][field] = False
                        elif field in ['score', 'security_score']:
                            data[section][field] = 0
                        else:
                            data[section][field] = None
            
            logger.info(f"Successfully analyzed token: {token_address}")
            return data
            
        except Exception as e:
            logger.error(f"Error analyzing token: {token_address}, error: {str(e)}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f"Error analyzing token: {str(e)}"
            )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Unexpected error analyzing token: {token_address}, error: {str(e)}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )

def run_fastapi():
    """Run the FastAPI server"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

def main():
    """Main function"""
    try:
        # Start FastAPI server in a separate thread
        import threading
        fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
        fastapi_thread.start()
        logger.info("Started FastAPI server on port 8000")

        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("check", check_token))
        application.add_handler(CommandHandler("subscribe", subscribe))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(CallbackQueryHandler(handle_callback_query))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        logger.info("Starting bot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        pid_file = "bot.pid"
        
        def is_pid_running(pid):
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                if is_pid_running(old_pid):
                    print(f"Another bot instance (PID: {old_pid}) is already running. Exiting...")
                    import sys
                    sys.exit(1)
                else:
                    # PID file exists but process is not running
                    os.remove(pid_file)
            except (ValueError, OSError):
                # Invalid PID file content or other error
                os.remove(pid_file)
        
        # Write current PID to file
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
            
        try:
            main()
        finally:
            # Clean up PID file when bot exits
            try:
                if os.path.exists(pid_file):
                    os.remove(pid_file)
            except OSError:
                pass
                
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot stopped due to error: {str(e)}")
        logger.error("Fatal error", exc_info=True)