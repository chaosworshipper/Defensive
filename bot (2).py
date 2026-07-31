#!/usr/bin/env python3
"""
Rubika Media Downloader Bot
Built using the official Rubika Bot API (https://rubika.ir/botapi)
"""

import os
import re
import json
import asyncio
import tempfile
import shutil
import logging
from pathlib import Path

import aiohttp
import yt_dlp


# ─── Config ──────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
API_BASE = "https://botapi.rubika.ir/v3"
MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_DIR = tempfile.mkdtemp(prefix="rubika_dl_")

URL_PATTERN = re.compile(
    r'https?://(?:www\.)?'
    r'(?:(?:youtube\.com|youtu\.be|m\.youtube\.com)'
    r'|(?:tiktok\.com|vm\.tiktok\.com)'
    r'|(?:instagram\.com)'
    r'|(?:twitter\.com|x\.com)'
    r'|(?:facebook\.com|fb\.watch)'
    r'|(?:reddit\.com|v\.redd\.it)'
    r'|(?:vimeo\.com)'
    r'|(?:dailymotion\.com)'
    r'|(?:soundcloud\.com)'
    r')',
    re.IGNORECASE,
)

BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 30,
}

VIDEO_OPTS = {
    **BASE_OPTS,
    "format": "best[filesize<50M]/best[height<=720]/best",
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
}

AUDIO_OPTS = {
    **BASE_OPTS,
    "format": "bestaudio/best",
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── Rubika Bot API Client ──────────────────────────────────────

class RubikaBot:
    """
    Rubika Bot API Client
    API Docs: https://rubika.ir/botapi
    Base URL: https://botapi.rubika.ir/v3/{token}/
    """

    def __init__(self, token: str):
        self.token = token
        self.base_url = f"{API_BASE}/{token}"
        self.session = None
        self.offset = None

    async def start(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def _request(self, method: str, data: dict = None) -> dict:
        """Make an API request."""
        url = f"{self.base_url}/{method}"
        try:
            async with self.session.post(url, json=data or {}) as resp:
                result = await resp.json()
                return result
        except Exception as e:
            logger.error(f"API request failed ({method}): {e}")
            return {"status": "ERROR"}

    async def get_me(self) -> dict:
        """Get bot info."""
        return await self._request("getMe")

    async def get_updates(self) -> list:
        """Get new updates (long polling)."""
        data = {
            "offset": self.offset,
            "updates": ["Message"]
        }
        result = await self._request("getUpdates", data)
        updates = result.get("updates", [])
        if updates:
            last_id = updates[-1].get("update_id", 0)
            self.offset = str(int(last_id) + 1)
        return updates

    async def send_message(self, chat_id: str, text: str) -> dict:
        """Send a text message."""
        data = {
            "chat_id": chat_id,
            "text": text,
        }
        return await self._request("sendMessage", data)

    async def send_file(self, chat_id: str, file_path: str, text: str = "") -> dict:
        """Send a file (video, audio, document)."""
        url = f"{self.base_url}/sendFile"
        try:
            form = aiohttp.FormData()
            form.add_field("chat_id", chat_id)

            file_obj = open(file_path, "rb")
            filename = os.path.basename(file_path)
            form.add_field("file", file_obj, filename=filename)

            if text:
                form.add_field("text", text)

            async with self.session.post(url, data=form) as resp:
                result = await resp.json()
                file_obj.close()
                return result
        except Exception as e:
            logger.error(f"Send file failed: {e}")
            return {"status": "ERROR"}


# ─── Helpers ─────────────────────────────────────────────────────

def is_url(text: str) -> bool:
    return bool(URL_PATTERN.match(text.strip()))


def human_size(n: int) -> str:
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def cleanup(path: str):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except:
        pass


def download_video(url: str) -> tuple:
    with yt_dlp.YoutubeDL({**BASE_OPTS}) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get("title", "video")[:128]
        vid_id = info.get("id", "x")
        ext = info.get("ext", "mp4")
        filepath = os.path.join(DOWNLOAD_DIR, f"{vid_id}.{ext}")

    with yt_dlp.YoutubeDL({**VIDEO_OPTS}) as ydl:
        ydl.download([url])

    if not os.path.exists(filepath):
        for f in os.listdir(DOWNLOAD_DIR):
            if vid_id in f:
                filepath = os.path.join(DOWNLOAD_DIR, f)
                break

    return filepath, title


def download_audio(url: str) -> tuple:
    with yt_dlp.YoutubeDL({**BASE_OPTS}) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get("title", "audio")[:128]
        vid_id = info.get("id", "x")
        filepath = os.path.join(DOWNLOAD_DIR, f"{vid_id}.mp3")

    with yt_dlp.YoutubeDL({**AUDIO_OPTS}) as ydl:
        ydl.download([url])

    if not os.path.exists(filepath):
        for f in os.listdir(DOWNLOAD_DIR):
            if vid_id in f and f.endswith(".mp3"):
                filepath = os.path.join(DOWNLOAD_DIR, f)
                break

    return filepath, title


# ─── Handlers ────────────────────────────────────────────────────

HELP_TEXT = """🎬 *Media Downloader Bot*

Send me a URL and I'll download it!

*Supported:*
• YouTube (videos & shorts)
• TikTok
• Instagram (posts & reels)
• Twitter / X
• Reddit
• Facebook
• And 1000+ more sites!

*Commands:*
/video <url> — Download as video
/audio <url> — Download as MP3
/help — Show this message"""


async def handle_start(bot: RubikaBot, chat_id: str):
    await bot.send_message(chat_id, HELP_TEXT)


async def handle_video(bot: RubikaBot, chat_id: str, url: str):
    await bot.send_message(chat_id, "⏳ Downloading video...")

    filepath = None
    try:
        loop = asyncio.get_event_loop()
        filepath, title = await loop.run_in_executor(None, download_video, url)

        if not filepath or not os.path.exists(filepath):
            await bot.send_message(chat_id, "❌ Download failed.")
            return

        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            await bot.send_message(chat_id, f"❌ File too large ({human_size(size)}). Max 50MB.")
            return

        result = await bot.send_file(chat_id, filepath, f"🎬 {title}")
        if result.get("status") != "OK":
            await bot.send_message(chat_id, f"🎬 {title}\n(Send failed: {result.get('status', 'unknown')})")

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "Private" in err:
            await bot.send_message(chat_id, "❌ This video is private.")
        else:
            await bot.send_message(chat_id, f"❌ Error: {err[:200]}")
    except Exception as e:
        logger.error(f"Video error: {e}")
        await bot.send_message(chat_id, f"❌ Error: {str(e)[:200]}")
    finally:
        if filepath:
            cleanup(filepath)


async def handle_audio(bot: RubikaBot, chat_id: str, url: str):
    await bot.send_message(chat_id, "⏳ Downloading audio...")

    filepath = None
    try:
        loop = asyncio.get_event_loop()
        filepath, title = await loop.run_in_executor(None, download_audio, url)

        if not filepath or not os.path.exists(filepath):
            await bot.send_message(chat_id, "❌ Download failed.")
            return

        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            await bot.send_message(chat_id, f"❌ File too large ({human_size(size)}). Max 50MB.")
            return

        result = await bot.send_file(chat_id, filepath, f"🎵 {title}")
        if result.get("status") != "OK":
            await bot.send_message(chat_id, f"🎵 {title}\n(Send failed: {result.get('status', 'unknown')})")

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "Private" in err:
            await bot.send_message(chat_id, "❌ This video is private.")
        else:
            await bot.send_message(chat_id, f"❌ Error: {err[:200]}")
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await bot.send_message(chat_id, f"❌ Error: {str(e)[:200]}")
    finally:
        if filepath:
            cleanup(filepath)


# ─── Main Loop ───────────────────────────────────────────────────

async def process_update(bot: RubikaBot, update: dict):
    """Process a single update."""
    update_type = update.get("type", "")

    if update_type != "Message":
        return

    new_msg = update.get("new_message", {})
    if not new_msg:
        return

    chat_id = update.get("chat_id", "")
    text = new_msg.get("text", "").strip()

    if not text or not chat_id:
        return

    logger.info(f"Message from {chat_id}: {text[:50]}")

    # /start or /help
    if text in ("/start", "/help"):
        await handle_start(bot, chat_id)
        return

    # /video <url>
    if text.startswith("/video"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await bot.send_message(chat_id, "Usage: /video <url>")
            return
        url = parts[1].strip()
        if not is_url(url):
            await bot.send_message(chat_id, "❌ Please send a valid URL.")
            return
        await handle_video(bot, chat_id, url)
        return

    # /audio <url>
    if text.startswith("/audio"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await bot.send_message(chat_id, "Usage: /audio <url>")
            return
        url = parts[1].strip()
        if not is_url(url):
            await bot.send_message(chat_id, "❌ Please send a valid URL.")
            return
        await handle_audio(bot, chat_id, url)
        return

    # Auto-detect URL
    if is_url(text):
        await handle_video(bot, chat_id, text)


async def run_bot(token: str):
    bot = RubikaBot(token)
    await bot.start()

    # Verify bot
    me = await bot.get_me()
    logger.info(f"getMe response: {me}")
    if me.get("status") == "OK":
        # Try different response formats
        bot_info = me.get("bot") or me.get("data") or me.get("result") or {}
        name = bot_info.get("first_name") or bot_info.get("name") or "Unknown"
        username = bot_info.get("username") or bot_info.get("bot_username") or "unknown"
        logger.info(f"Bot started: @{username} ({name})")
    else:
        logger.error(f"Failed to verify bot: {me}")
        return

    # Poll for updates
    try:
        while True:
            updates = await bot.get_updates()
            for update in updates:
                asyncio.create_task(process_update(bot, update))
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
    finally:
        await bot.close()


# ─── Entry Point ─────────────────────────────────────────────────

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("=" * 50)
        print("  Rubika Media Downloader Bot")
        print("=" * 50)
        print()
        print("  Get a token from @BotFather on Rubika:")
        print("  1. Open Rubika")
        print("  2. Search for @BotFather")
        print("  3. Send /newbot")
        print("  4. Follow instructions")
        print("  5. Copy the token")
        print()
        print("  Then run:")
        print("    python bot.py --token YOUR_TOKEN")
        print()
        print("  Or set environment variable:")
        print("    set RUBIKA_BOT_TOKEN=your_token")
        print()
        return

    asyncio.run(run_bot(BOT_TOKEN))


if __name__ == "__main__":
    import sys
    if "--token" in sys.argv:
        idx = sys.argv.index("--token")
        if idx + 1 < len(sys.argv):
            BOT_TOKEN = sys.argv[idx + 1]
    main()
