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
# 🌍 FIXED SERVICE SELECTION (POP-UP IF NO STOCK)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("srv_"))
def srv_sel(call):
    srv = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as conn:
        codes = [r[0] for r in conn.execute("SELECT DISTINCT country_code FROM combos WHERE service=?", (srv,)).fetchall()]
    
    # Idan babu stock ko daya na wannan service din, tura Pop-up nan take
    if not codes:
        bot.answer_callback_query(
            call.id, 
            f"❌ Sorry, no numbers available for {srv} at the moment!", 
            show_alert=True
        )
        return

    # Idan akwai stock, sai mu amsa query din mu canza keyboard
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=1)
    for c in codes:
        name, flag = COUNTRY_DATA.get(c, (c, "🌍"))
        m.add(types.InlineKeyboardButton(f"{flag} {name}", callback_data=f"cnt_{c}_{srv}", style="primary"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_srv", style="danger"))
    bot.edit_message_text(f"🌍 <b>Select Country for {srv}:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

# ==========================================
# 💎 NUMBER DISTRIBUTION (NO STICKER + DIRECT COPY)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("cnt_"))
def cnt_sel(call):
    bot.answer_callback_query(call.id)
    _, code, srv = call.data.split("_")
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT numbers FROM combos WHERE country_code=? AND service=?", (code, srv)).fetchone()
        if not row:
            bot.answer_callback_query(call.id, "❌ Out of Stock!", show_alert=True)
            return
        all_nums = json.loads(row[0])
        if not all_nums:
            bot.answer_callback_query(call.id, "❌ Out of Stock!", show_alert=True)
            return
        selected_nums = all_nums[:5]
        remaining = all_nums[5:]
        conn.execute("UPDATE combos SET numbers=? WHERE country_code=? AND service=?", (json.dumps(remaining), code, srv))

    name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
    last_number_time[call.from_user.id] = time.time()
    
    m = types.InlineKeyboardMarkup(row_width=1)
    for num in selected_nums:
        # An cire sticker din 📋 an bar Flag da Lambar kawai
        m.add(types.InlineKeyboardButton(
            text=f"{flag} +{num}", 
            copy_text=types.CopyTextButton(text=f"+{num}")
        ))
    
    m.add(
        types.InlineKeyboardButton("🔄 Change Number", callback_data=f"change_{code}_{srv}", style="danger"),
        types.InlineKeyboardButton("🌐 Change Country", callback_data=f"chcountry_{srv}", style="primary"),
        types.InlineKeyboardButton("🔑 Get OTP ↗", url=OTP_GROUP_LINK, style="success")
    )
    bot.edit_message_text(f"{flag} <b>{name} Number:</b>\n⏳ <i>Waiting for OTP...</i>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

# ==========================================
# 🔄 CHANGE NUMBER (WITH POP-UP COUNTDOWN)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("change_"))
def change_number(call):
    user_id = call.from_user.id
    if user_id in last_number_time:
        elapsed = time.time() - last_number_time[user_id]
        if elapsed < 10:
            remaining = int(10 - elapsed)
            bot.answer_callback_query(call.id, f"⏳ Please wait {remaining}s remaining!", show_alert=True)
            return
    cnt_sel(call)

# ======================
# 🔐 ADMIN PANEL
# ======================
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.chat.id in ADMIN_IDS:
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(
            types.InlineKeyboardButton("📥 Add Stock", callback_data="adm_add", style="success"),
            types.InlineKeyboardButton("🗑 Delete Stock", callback_data="adm_del", style="danger"),
            types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc", style="primary")
        )
        bot.send_message(message.chat.id, "🔐 <b>Admin Panel</b>", reply_markup=m, parse_mode="HTML")

# ======================
# 🚀 NAVIGATION & RUN
# ======================
@bot.callback_query_handler(func=lambda call: call.data == "back_srv")
def back_srv(call):
    bot.answer_callback_query(call.id)
    # Edit text maimakon tura sabo don yayi sauri
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add( 
        types.InlineKeyboardButton("📱 Telegram", callback_data="srv_Telegram", style="primary"), 
        types.InlineKeyboardButton("💬 WhatsApp", callback_data="srv_WhatsApp", style="success"), 
        types.InlineKeyboardButton("👤 Facebook", callback_data="srv_Facebook", style="primary"), 
        types.InlineKeyboardButton("📦 Others", callback_data="srv_Others", style="danger"), 
        types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services", style="primary") 
    )
    bot.edit_message_text("🛠 <b>Select Service:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

def run_bot():
    print("[SERVER] Bot is live! Clean UI, Pop-up stock alerts, and Admin Panel active.")
    bot.infinity_polling(timeout=60, long_polling_timeout=5)

if __name__ == "__main__":
    run_bot()
