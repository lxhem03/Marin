import logging
import os
import pickle
import shutil
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pyrogram import Client, filters

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Your bot credentials from my.telegram.org and BotFather
API_ID = 23340285  # Replace with your API ID
API_HASH = "ab18f905cb5f4a75d41bb48d20acfa50"  # Replace with your API Hash
BOT_TOKEN = "8503714406:AAGbGAjnk-WLnPMxMP6MwItzUGKgIRi9_bE"  # Replace with your bot token

# Google Drive scopes
SCOPES = ['https://www.googleapis.com/auth/drive']

# Pyrogram Client
app = Client("drive_auth_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Global dicts to track per-user state
pending_credentials = {}  # user_id: path_to_temp_credentials_json
pending_auth = {}  # user_id: flow object
pending_file_upload = {}  # user_id: True if waiting for credentials file

@app.on_message(filters.command("start"))
async def start_command(client, message):
    welcome_text = (
        "Welcome to the Google Drive Token Generator Bot! 🚀\n"
        "This bot helps you generate a token.pickle file for Google Drive API access.\n"
        "Use /help for instructions on setting up your Google OAuth credentials.\n"
        "Start by sending /credentials to upload your credentials.json.\n"
        "Then use /driveauth to authorize and get your token.pickle."
    )
    await message.reply(welcome_text)
    logger.info(f"/start command from user {message.from_user.id}")

@app.on_message(filters.command("help"))
async def help_command(client, message):
    help_text = (
        "How to use this bot:\n\n"
        "1. Go to Google Cloud Console (console.cloud.google.com).\n"
        "2. Create a new project (or use an existing one).\n"
        "3. Enable the Google Drive API: Search for 'Drive API' in the library and enable it.\n"
        "4. Create OAuth 2.0 credentials: Go to APIs & Services > Credentials > Create Credentials > OAuth client ID.\n"
        "   - Application type: Desktop app.\n"
        "   - Set authorized redirect URIs to: urn:ietf:wg:oauth:2.0:oob and http://localhost.\n"
        "5. Download the credentials.json file.\n\n"
        "Now, send /credentials to the bot, then reply with your credentials.json file.\n"
        "After that, use /driveauth to get the authorization link, paste the code, and receive your token.pickle!"
    )
    await message.reply(help_text)
    logger.info(f"/help command from user {message.from_user.id}")

@app.on_message(filters.command("credentials"))
async def start_credentials_upload(client, message):
    user_id = message.from_user.id
    pending_file_upload[user_id] = True
    await message.reply("Please send your credentials.json file now. I'll use it temporarily to generate your token.pickle and delete it afterward.")
    logger.info(f"Credentials upload started for user {user_id}")

@app.on_message(filters.document)
async def receive_credentials_file(client, message):
    user_id = message.from_user.id
    if user_id not in pending_file_upload:
        await message.reply("Please start with /credentials first before sending the file.")
        return
    
    if message.document.file_name != "credentials.json":
        await message.reply("Please send a file named 'credentials.json'.")
        return
    
    try:
        user_folder = f"temp/{user_id}"
        os.makedirs(user_folder, exist_ok=True)
        file_path = f"{user_folder}/credentials.json"
        
        await message.download(file_path)
        pending_credentials[user_id] = file_path
        del pending_file_upload[user_id]
        
        await message.reply("✅ credentials.json received and saved temporarily. Now use /driveauth to proceed.")
        logger.info(f"Credentials file received for user {user_id} at {file_path}")
    except Exception as e:
        logger.error(f"Error downloading credentials for user {user_id}: {e}")
        await message.reply(f"❌ Error downloading file: {str(e)}. Try again.")

@app.on_message(filters.command("driveauth"))
async def start_drive_auth(client, message):
    user_id = message.from_user.id
    if user_id not in pending_credentials:
        await message.reply("Please upload your credentials.json first using /credentials.")
        return
    
    credentials_file = pending_credentials[user_id]
    try:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            include_granted_scopes='true'
        )
        pending_auth[user_id] = flow
        await message.reply(f"Open this link in your browser and authorize the app:\n\n{auth_url}\n\nAfter authorizing, copy the authorization code and paste it here.")
        logger.info(f"Auth URL sent to user {user_id}")
    except Exception as e:
        logger.error(f"Error starting auth for user {user_id}: {e}")
        await message.reply(f"Error starting authorization: {str(e)}. Check bot logs or re-upload credentials.")

@app.on_message(filters.text & filters.command())
async def receive_code(client, message):
    user_id = message.from_user.id
    code = message.text.strip()
    
    if user_id not in pending_auth:
        await message.reply("No pending authorization. Start with /driveauth first.")
        return
    
    flow = pending_auth[user_id]
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Refresh if needed
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        
        # Save token temporarily
        user_folder = f"temp/{user_id}"
        token_path = f"{user_folder}/token.pickle"
        with open(token_path, "wb") as token_file:
            pickle.dump(creds, token_file)
        
        # Send token.pickle to user
        await message.reply_document(token_path, caption="✅ Here is your token.pickle file!")
        logger.info(f"Token generated and sent to user {user_id}")
        
        # Clean up: Delete temp files and folder
        shutil.rmtree(user_folder)
        if user_id in pending_credentials:
            del pending_credentials[user_id]
        del pending_auth[user_id]
        
        await message.reply("All temporary files deleted from the server for security.")
    except Exception as e:
        logger.error(f"Error fetching token for user {user_id}: {e}")
        await message.reply(f"❌ Error: {str(e)}. Make sure the code is correct and try again with /driveauth.")

# Run the bot
if __name__ == "__main__":
    logger.info("Starting the bot...")
    app.run()
