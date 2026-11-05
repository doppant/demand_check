import asyncio
import json
import os
import re
from datetime import timedelta
from dotenv import load_dotenv

import discord
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

# ==========================================
# 1. CONFIGURATION & FILE LOADERS
# ==========================================

def load_server_selection(filepath="servers.json"):
    """Loads region and server keywords from an external JSON file."""
    if not os.path.exists(filepath):
        print(f"[Warning] {filepath} not found! Returning empty selection.", flush=True)
        return {}
    
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        # Lowercase all server terms for case-insensitive matching
        return {region: [server.lower() for server in servers] for region, servers in data.items()}

# Load server selection dictionary from external servers.json
server_selection = load_server_selection("servers.json")

# Telethon Credentials
api_id = os.getenv("api_id")
api_hash = os.getenv("api_hash")
session_str = os.getenv("SESSION_STRING")

# Convert api_id to int if present
if api_id:
    api_id = int(api_id)

# Discord Credentials
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
discord_channel_env = os.getenv("DISCORD_CHANNEL_ID")
DISCORD_CHANNEL_ID = int(discord_channel_env) if discord_channel_env else None

# Target Telegram groups (usernames, t.me links, or chat IDs)
group_targets = [
    'AION2market',
    'ReyhanEsaDemandGroup',
    'SumberRezekiGameStation',
    'DMGroupgaming'
]

# ==========================================
# 2. CLIENT INITIALIZATION & DUAL-SESSION
# ==========================================

# Dual-Session Logic:
# 1. On Railway: SESSION_STRING environment variable is present -> uses StringSession
# 2. On Local PC: SESSION_STRING is empty -> uses local file 'my_user_account.session'
if session_str:
    session = StringSession(session_str)
    print("Initializing using Railway StringSession...", flush=True)
else:
    session = 'my_user_account'
    print("Initializing using local my_user_account.session file...", flush=True)

tg_client = TelegramClient(session, api_id, api_hash, connection_retries=None, auto_reconnect=True)

intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)

discord_ready = asyncio.Event()

@discord_client.event
async def on_ready():
    print(f"Logged in as Discord Bot: {discord_client.user}", flush=True)
    discord_ready.set()

# ==========================================
# 3. MATCHING LOGIC (LINE-BY-LINE VALIDATION)
# ==========================================

def parse_and_validate_matches(text, server_selection_dict):
    """
    Parses message line-by-line. Extracts bracketed inline regions like [Asia] or [EU]
    and validates server matches strictly against region context.
    """
    lines = text.splitlines()
    matched_details = {}
    current_region = None

    # Normalization lookup table for region names
    region_lookup = {region.lower(): region for region in server_selection_dict.keys()}

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        
        line_lower = line_clean.lower()

        # 1. Check for region headers like [Asia], [EU], [NA East] on the CURRENT line
        line_region = None
        for reg_key_lower, reg_exact in region_lookup.items():
            # Matches "[Asia]", "[EU]", "Asia -", "EU:", etc.
            if re.search(rf'\[?\b{re.escape(reg_key_lower)}\b\]?', line_lower):
                line_region = reg_exact
                break

        # If a region is specified on this line, update current_region section context
        if line_region:
            current_region = line_region

        # 2. Check for server keyword matches on this specific line
        for region, servers in server_selection_dict.items():
            for server in servers:
                # Match server keyword as a whole word to prevent partial matches
                if re.search(rf'\b{re.escape(server)}\b', line_lower):
                    # Determine active region context (line-level region > section region)
                    active_region = line_region or current_region

                    # Accept match ONLY if the active region matches the server's region in servers.json
                    if active_region == region:
                        if region not in matched_details:
                            matched_details[region] = []
                        if server not in matched_details[region]:
                            matched_details[region].append(server)
                    else:
                        print(f"[Ignored Mismatch] Found '{server}' ({region}) on line with region '{active_region}'", flush=True)

    return matched_details

# ==========================================
# 4. DISCORD MESSAGING & TELEGRAM HANDLERS
# ==========================================

async def send_to_discord_channel(chat_name, group_link, matched_details, time_str, text):
    """Sends formatted alert message with region and server details to Discord."""
    await discord_ready.wait()
    
    if not DISCORD_CHANNEL_ID:
        print("[Discord Error] DISCORD_CHANNEL_ID is not configured.", flush=True)
        return

    # Try local cache first
    channel = discord_client.get_channel(DISCORD_CHANNEL_ID)
    
    # Fetch from API if cache is empty
    if channel is None:
        try:
            channel = await discord_client.fetch_channel(DISCORD_CHANNEL_ID)
        except Exception as e:
            print(f"[Discord Error] Failed to fetch channel ID {DISCORD_CHANNEL_ID}: {e}", flush=True)
            return

    if channel:
        match_summary = " | ".join([f"[{region.upper()}] {', '.join(servers)}" for region, servers in matched_details.items()])

        content = (
            f"**Group:** {group_link} (`{chat_name}`)\n"
            f"**Matches:** `{match_summary}`\n"
            f"**Time:** `{time_str}` (UTC+7)\n"
            f"```text\n{text}\n```"
        )
        try:
            await channel.send(content)
            print("Successfully sent to Discord!", flush=True)
        except Exception as e:
            print(f"[Discord Permission Error] Could not send message: {e}", flush=True)
    else:
        print(f"[Discord Error] Channel ID {DISCORD_CHANNEL_ID} not found.", flush=True)

@tg_client.on(events.NewMessage(chats=group_targets))
@tg_client.on(events.MessageEdited(chats=group_targets))
async def handle_tg_message(event):
    text = event.raw_text
    if not text:
        return

    # Strict line-by-line validation matching
    matched_details = parse_and_validate_matches(text, server_selection)

    if matched_details:
        # Convert UTC timestamp to UTC+7 (WIB)
        local_time = event.message.date + timedelta(hours=7)
        time_str = local_time.strftime('%Y-%m-%d %H:%M:%S')
        
        chat = await event.get_chat()
        username = getattr(chat, 'username', None)
        chat_name = username or getattr(chat, 'title', 'Group')
        group_link = f"https://t.me/{username}" if username else "Private Group"

        print(f"[{time_str}] [{chat_name}] Matches: {matched_details} | {text}", flush=True)
        await send_to_discord_channel(chat_name, group_link, matched_details, time_str, text)

# ==========================================
# 5. MAIN ASYNC EXECUTION & CLEANUP
# ==========================================

async def main():
    print(f"Listening for updates across {len(group_targets)} groups...", flush=True)
    print(f"Active Server Watchlist: {server_selection}", flush=True)
    try:
        # Launch both Discord client and Telethon client concurrently
        await asyncio.gather(
            discord_client.start(DISCORD_BOT_TOKEN),
            tg_client.start()
        )
        await tg_client.run_until_disconnected()
    finally:
        # Graceful cleanup to avoid unclosed client session warnings
        if not discord_client.is_closed():
            await discord_client.close()
        if tg_client.is_connected():
            await tg_client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())