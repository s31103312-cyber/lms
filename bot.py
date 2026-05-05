import json
import re
import sqlite3
import time
import telebot
from telebot import types
from config import *
from database import get_all_users

# --- INGANTA GUDU (MULTITHREADING) ---
bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=20)

DB_PATH = DB_FILE
user_states = {}
last_number_time = {}

# ======================
# 🚀 NOTIFICATION SYSTEM
# ======================
def send_stock_alert(country_name, flag, service, count):
    msg = f"<blockquote>🚀 <b>NEW STOCK ADDED!</b>\n\n🌍 <b>Country:</b> {flag} {country_name}\n🛠 <b>Service:</b> {service}\n🔢 <b>Quantity:</b> {count} Numbers</blockquote>"
    users = get_all_users()
    for u in users:
        try: bot.send_message(u['user_id'], msg, parse_mode="HTML")
        except: continue

def manual_broadcast(text):
    users = get_all_users()
    count = 0
    for u in users:
        try:
            bot.send_message(u['user_id'], text, parse_mode="HTML")
            count += 1
        except: continue
    return count

# ======================
# 🎮 USER UI
# ======================
@bot.message_handler(commands=['start'])
def start(message):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    select_service(message)

def select_service(message):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add( 
        types.InlineKeyboardButton("📱 Telegram", callback_data="srv_Telegram", style="primary"), 
        types.InlineKeyboardButton("💬 WhatsApp", callback_data="srv_WhatsApp", style="success"), 
        types.InlineKeyboardButton("👤 Facebook", callback_data="srv_Facebook", style="primary"), 
        types.InlineKeyboardButton("📦 Others", callback_data="srv_Others", style="danger"), 
        types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services", style="primary") 
    )
    bot.send_message(message.chat.id, "🛠 <b>Select Service:</b>", reply_markup=m, parse_mode="HTML")

# ==========================================
# 🌍 SERVICE & NUMBER LOGIC (FAST UI)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("srv_"))
def srv_sel(call):
    srv = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as conn:
        codes = [r[0] for r in conn.execute("SELECT DISTINCT country_code FROM combos WHERE service=?", (srv,)).fetchall()]
    
    if not codes:
        bot.answer_callback_query(call.id, f"❌ No numbers available for {srv}!", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=1)
    for c in codes:
        name, flag = COUNTRY_DATA.get(c, (c, "🌍"))
        m.add(types.InlineKeyboardButton(f"{flag} {name}", callback_data=f"cnt_{c}_{srv}", style="primary"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_srv", style="danger"))
    bot.edit_message_text(f"🌍 <b>Select Country for {srv}:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cnt_"))
def cnt_sel(call):
    bot.answer_callback_query(call.id)
    _, code, srv = call.data.split("_")
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT numbers FROM combos WHERE country_code=? AND service=?", (code, srv)).fetchone()
        if not row or not json.loads(row[0]):
            bot.answer_callback_query(call.id, "❌ Out of Stock!", show_alert=True)
            return
        all_nums = json.loads(row[0])
        selected_nums = all_nums[:5]
        remaining = all_nums[5:]
        conn.execute("UPDATE combos SET numbers=? WHERE country_code=? AND service=?", (json.dumps(remaining), code, srv))

    name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
    last_number_time[call.from_user.id] = time.time()
    
    m = types.InlineKeyboardMarkup(row_width=1)
    for num in selected_nums:
        m.add(types.InlineKeyboardButton(text=f"{flag} +{num}", copy_text=types.CopyTextButton(text=f"+{num}")))
    
    m.add(
        types.InlineKeyboardButton("🔄 Change Number", callback_data=f"change_{code}_{srv}", style="danger"),
        types.InlineKeyboardButton("🌐 Change Country", callback_data=f"chcountry_{srv}", style="primary"),
        types.InlineKeyboardButton("🔑 Get OTP ↗", url=OTP_GROUP_LINK, style="success")
    )
    bot.edit_message_text(f"{flag} <b>{name} Number:</b>\n⏳ <i>Waiting for OTP...</i>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

# ======================
# 🔐 ADMIN FEATURES (ALL IN ONE)
# ======================
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.chat.id in ADMIN_IDS:
        users = get_all_users()
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton("📥 Add Stock", callback_data="adm_add"),
            types.InlineKeyboardButton("🗑 Delete Stock", callback_data="adm_del"),
            types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
            types.InlineKeyboardButton("📊 Users Info", callback_data="adm_users")
        )
        bot.send_message(message.chat.id, f"🔐 <b>Admin Panel</b>\n\n👥 Total Users: <b>{len(users)}</b>", reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    if call.from_user.id not in ADMIN_IDS: return
    bot.answer_callback_query(call.id)

    if call.data == "adm_add":
        msg = bot.send_message(call.message.chat.id, "📤 <b>Please upload the combo file (.txt)</b>\nFormat: <code>number:service:country_code</code>")
        bot.register_next_step_handler(msg, handle_stock_upload)
    
    elif call.data == "adm_del":
        msg = bot.send_message(call.message.chat.id, "🗑 <b>Send details to delete:</b>\nFormat: <code>code:service</code>\nExample: <code>US:Telegram</code>")
        bot.register_next_step_handler(msg, handle_stock_delete)
        
    elif call.data == "adm_bc":
        msg = bot.send_message(call.message.chat.id, "📢 <b>Send the message (HTML supported):</b>")
        bot.register_next_step_handler(msg, handle_broadcast_step)
        
    elif call.data == "adm_users":
        users = get_all_users()
        bot.send_message(call.message.chat.id, f"📊 <b>Stats:</b>\nTotal Registered: {len(users)}")

# --- Admin Handlers Logic ---
def handle_broadcast_step(message):
    if message.text == "/cancel": return
    bot.send_message(message.chat.id, "⏳ Sending broadcast...")
    count = manual_broadcast(message.text)
    bot.send_message(message.chat.id, f"✅ Broadcast finished! Sent to {count} users.")

def handle_stock_delete(message):
    try:
        code, srv = message.text.split(":")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM combos WHERE country_code=? AND service=?", (code.strip(), srv.strip()))
        bot.send_message(message.chat.id, f"✅ Deleted stock for {code} {srv}")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format! Use <code>code:service</code>")

def handle_stock_upload(message):
    if not message.document:
        bot.send_message(message.chat.id, "❌ Please upload a file!")
        return
    
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    content = downloaded_file.decode('utf-8')
    
    lines = content.splitlines()
    stock_data = {} # {(code, srv): [nums]}
    
    for line in lines:
        parts = line.split(":")
        if len(parts) == 3:
            num, srv, code = parts
            key = (code.strip(), srv.strip())
            if key not in stock_data: stock_data[key] = []
            stock_data[key].append(num.strip())
            
    with sqlite3.connect(DB_PATH) as conn:
        for (code, srv), nums in stock_data.items():
            existing = conn.execute("SELECT numbers FROM combos WHERE country_code=? AND service=?", (code, srv)).fetchone()
            if existing:
                updated = json.loads(existing[0]) + nums
                conn.execute("UPDATE combos SET numbers=? WHERE country_code=? AND service=?", (json.dumps(updated), code, srv))
            else:
                conn.execute("INSERT INTO combos (country_code, service, numbers) VALUES (?, ?, ?)", (code, srv, json.dumps(nums)))
            
            # Send alert
            name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
            send_stock_alert(name, flag, srv, len(nums))
            
    bot.send_message(message.chat.id, f"✅ Successfully added stock from {len(lines)} lines!")

# ======================
# 🔄 NAVIGATION & REFRESH
# ======================
@bot.callback_query_handler(func=lambda call: call.data == "back_srv")
def back_srv(call):
    bot.answer_callback_query(call.id)
    select_service(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("change_"))
def change_number(call):
    user_id = call.from_user.id
    if user_id in last_number_time:
        elapsed = time.time() - last_number_time[user_id]
        if elapsed < 10:
            bot.answer_callback_query(call.id, f"⏳ Wait {int(10-elapsed)}s!", show_alert=True)
            return
    cnt_sel(call)

def run_bot():
    print("[SERVER] Bot is running with FULL ADMIN FEATURES and FAST UI...")
    bot.infinity_polling(timeout=60, long_polling_timeout=5)

if __name__ == "__main__":
    run_bot()
