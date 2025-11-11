import asyncio
import os
from pyrogram import Client, filters
import pyttsx3
import io
from pyrogram.types import Message
import tempfile

# Load from environment variables (set in deployment platforms)
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client("tts_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize TTS engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')

# Set default voice (e.g., female if available; adjust index after testing)
if voices:
    # Try to pick a female voice (common on Ubuntu: index 0 is often male, 1 female)
    engine.setProperty('voice', voices[1].id if len(voices) > 1 else voices[0].id)
    engine.setProperty('rate', 150)  # Speed
    engine.setProperty('volume', 0.9)  # Volume

@app.on_message(filters.text & filters.private)
async def tts_handler(client: Client, message: Message):
    text = message.text
    if text.lower() == "/start":
        await message.reply("Send me text, and I'll convert it to speech! Use /voices to list available voices.")
        return
    if text.lower() == "/voices":
        voice_list = "\n".join([f"{i}: {v.name} ({v.languages})" for i, v in enumerate(voices)])
        await message.reply(f"Available voices:\n{voice_list}")
        return

    try:
        # Use temp file to avoid conflicts
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            filename = tmp.name
        engine.save_to_file(text, filename)
        engine.runAndWait()

        # Send audio
        await message.reply_audio(filename, title="TTS Audio")

        os.unlink(filename)
    except Exception as e:
        await message.reply(f"Error generating speech: {str(e)}")

if __name__ == "__main__":
    app.run()
