import asyncio
import os
from datetime import timedelta
from dotenv import load_dotenv

import discord
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

# Telethon Credentials
api_id = int(os.getenv("api_id"))
api_hash = os.getenv("api_hash")
session_str = os.getenv("SESSION_STRING")

# Discord Credentials
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

# Add multiple groups to this list (usernames, t.me links, or numerical chat IDs)
group_targets = [
    'AION2market',
    'ReyhanEsaDemandGroup',
    'SumberRezekiGameStation',
    'DMGroupgaming'
]

server_selection = ['triniel', 'lumiel']

# Initialize Clients
session = StringSession(session_str) if session_str else 'my_user_account'
tg_client = TelegramClient(session, api_id, api_hash, connection_retries=None, auto_reconnect=True)

intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

discord_ready = asyncio.Event()

@discord_client.event
async def on_ready():
    print(f"Logged in as Discord Bot: {discord_client.user}", flush=True)
    discord_ready.set()

async def send_to_discord_channel(chat_name, matched_servers, time_str, sender_id, text):
    """Sends formatted alert message with group context to Discord Channel."""
    await discord_ready.wait()
    
    # 1. Try to get from local cache first
    channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
    
    # 2. If not in cache, fetch directly from Discord API
    if channel is None:
        try:
            channel = await discord_client.fetch_channel(DISCORD_CHANNEL_ID)
        except Exception as e:
            print(f"[Discord Error] Failed to fetch channel ID {DISCORD_CHANNEL_ID}: {e}", flush=True)
            return

    if channel:
        content = (
            f"**Group:** https://web.telegram.org/k/#@{chat_name}\n"
            f"**Time:** `{time_str}`\n"
            f"```text\n{text}\n```"
        )
        try:
            await channel.send(content)
            print("Successfully sent to Discord!", flush=True)
        except Exception as e:
            print(f"[Discord Permission Error] Could not send message: {e}", flush=True)
    else:
        print(f"[Discord Error] Channel ID {DISCORD_CHANNEL_ID} not found.", flush=True)

# Pass the array of group targets to the decorator
@tg_client.on(events.NewMessage(chats=group_targets))
@tg_client.on(events.MessageEdited(chats=group_targets))
async def handle_tg_message(event):
    text = event.raw_text
    if not text:
        return

    text_lower = text.lower()
    matched_servers = [s for s in server_selection if s in text_lower]

    if matched_servers:
        local_time = event.message.date + timedelta(hours=7)
        time_str = local_time.strftime('%Y-%m-%d %H:%M:%S')
        sender_id = event.sender_id
        
        # Get target group title or username dynamically
        chat = await event.get_chat()
        chat_name = getattr(chat, 'username', None) or getattr(chat, 'title', 'Unknown Group')

        print(f"[{time_str}] {text}", flush=True)
        await send_to_discord_channel(chat_name, matched_servers, time_str, sender_id, text)

async def main():
    # Start Discord Bot and Telethon client concurrently
    asyncio.create_task(discord_client.start(DISCORD_BOT_TOKEN))
    print(f"Listening for updates across {len(group_targets)} groups...", flush=True)
    await tg_client.start()
    await tg_client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())