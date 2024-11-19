from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Update
from telegram.ext import CallbackContext
import os

# Constants
RUGCHECK_BASE_URL = "https://rugcheck.xyz"
CUSTOM_UI_URL = "https://sameermuthu777.github.io/solguard-web/"  # Updated to GitHub Pages URL

class RugcheckUI:
    def __init__(self):
        self.logo_url = "https://rugcheck.xyz/logo.png"  # Replace with actual logo URL
    
    async def show_rugcheck_input(self, update: Update, context: CallbackContext):
        """Show the Rugcheck input interface"""
        webapp_data = {
            'source': 'solguardian',
            'theme': 'dark'  # You can customize the theme
        }
        
        keyboard = [[
            InlineKeyboardButton(
                "🔍 Open Rugcheck Scanner",
                web_app=WebAppInfo(url=CUSTOM_UI_URL)  # Use our custom UI
            )
        ]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🔍 <b>Solana Guard Rugcheck Scanner</b>\n\n"
            "Our advanced token analysis tool helps you:\n"
            "• Detect potential rugpulls\n"
            "• Analyze contract security\n"
            "• Check liquidity locks\n"
            "• Monitor holder distribution\n\n"
            "🚀 <i>Click the button below to start scanning!</i>"
        )

        # Handle both regular messages and callback queries
        if update.callback_query:
            await update.callback_query.message.edit_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    
    async def handle_rugcheck_result(self, update: Update, context: CallbackContext, token_address: str):
        """Handle the result from Rugcheck scan"""
        keyboard = [[
            InlineKeyboardButton(
                "📊 View Detailed Analysis",
                url=f"{RUGCHECK_BASE_URL}/token/{token_address}"
            )
        ]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        result_text = (
            "✅ Analysis Ready!\n"
            "Click below to view the detailed Rugcheck analysis."
        )

        # Handle both regular messages and callback queries
        if update.callback_query:
            await update.callback_query.message.edit_text(
                result_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                result_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
