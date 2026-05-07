import json
import re
import sqlite3
import time
import telebot
from telebot import types
from config import *
from database import get_all_users

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=20)

DB_PATH = DB_FILE
user_states = {}
last_number_time = {}

# ======================
# 🚀 NOTIFICATION SYSTEM
# ======================
def send_stock_alert(country_name, flag, service, count):
    msg = f"""<blockquote>🚀 <b>NEW STOCK ADDED!</b>\n\n🌍 <b>Country:</b> {flag} {country_name}\n🛠 <b>Service:</b> {service}\n🔢 <b>Quantity:</b> {count} Numbers</blockquote>"""
    users = get_all_users()
    for u in users:
        try: bot.send_message(u['user_id'], msg, parse_mode="HTML")
        except: continue

def manual_broadcast(text):
    msg = f"<blockquote>📢 <b>ADMIN BROADCAST</b>\n\n{text}</blockquote>"
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
        m.add(types.InlineKeyboardButton(
            text=f"{flag} +{num}", 
            copy_text=types.CopyTextButton(text=f"+{num}"),
            style="primary"
        ))
    
    m.add(
        types.InlineKeyboardButton("🔄 Change Number", callback_data=f"change_{code}_{srv}", style="danger"),
        types.InlineKeyboardButton("🌐 Change Country", callback_data=f"chcountry_{srv}", style="primary"),
        types.InlineKeyboardButton("🔑 Get OTP ↗", url=OTP_GROUP_LINK, style="success")
    )
    bot.edit_message_text(f"{flag} <b>{name} Number:</b>\n⏳ <i>Waiting for OTP...</i>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "refresh_services")
def refresh_services(call):
    bot.answer_callback_query(call.id, "✅ Refreshed successfully!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chcountry_"))
def change_country(call):
    srv = call.data.split("_")[1]
    with sqlite3.connect(DB_PATH) as conn:
        codes = [r[0] for r in conn.execute("SELECT DISTINCT country_code FROM combos WHERE service=?", (srv,)).fetchall()]
    
    if not codes:
        bot.answer_callback_query(call.id, f"❌ No countries available for {srv}!", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=1)
    for c in codes:
        name, flag = COUNTRY_DATA.get(c, (c, "🌍"))
        m.add(types.InlineKeyboardButton(f"{flag} {name}", callback_data=f"cnt_{c}_{srv}", style="primary"))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_srv", style="danger"))
    bot.edit_message_text(f"🌍 <b>Select Country for {srv}:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "back_srv")
def back_srv(call):
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add( 
        types.InlineKeyboardButton("📱 Telegram", callback_data="srv_Telegram", style="primary"), 
        types.InlineKeyboardButton("💬 WhatsApp", callback_data="srv_WhatsApp", style="success"), 
        types.InlineKeyboardButton("👤 Facebook", callback_data="srv_Facebook", style="primary"), 
        types.InlineKeyboardButton("📦 Others", callback_data="srv_Others", style="danger"), 
        types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh_services", style="primary") 
    )
    bot.edit_message_text("🛠 <b>Select Service:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("change_"))
def change_number(call):
    user_id = call.from_user.id
    if user_id in last_number_time:
        elapsed = time.time() - last_number_time[user_id]
        if elapsed < 10:
            bot.answer_callback_query(call.id, f"⏳ Wait {int(10-elapsed)}s!", show_alert=True)
            return
    cnt_sel(call)

# ======================
# 🔐 ADMIN PANEL
# ======================
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.chat.id in ADMIN_IDS:
        admin_panel(message)

def admin_panel(message_or_call, edit=False):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("📥 Add Stock", callback_data="adm_add", style="success"),
        types.InlineKeyboardButton("🗑 Delete Stock", callback_data="adm_del", style="danger"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc", style="primary")
    )
    text = "🔐 <b>Admin Panel</b>"
    if edit and hasattr(message_or_call, 'message'):
        bot.edit_message_text(text, message_or_call.message.chat.id, message_or_call.message.message_id, reply_markup=m, parse_mode="HTML")
    else:
        bot.send_message(message_or_call.chat.id, text, reply_markup=m, parse_mode="HTML")

# ======================
# 📥 ADD STOCK
# ======================
@bot.callback_query_handler(func=lambda call: call.data == "adm_add")
def add_stock_menu(call):
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("📱 Telegram", callback_data="addsrv_Telegram", style="primary"),
        types.InlineKeyboardButton("💬 WhatsApp", callback_data="addsrv_WhatsApp", style="success"),
        types.InlineKeyboardButton("👤 Facebook", callback_data="addsrv_Facebook", style="primary"),
        types.InlineKeyboardButton("📦 Others", callback_data="addsrv_Others", style="danger"),
        types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger")
    )
    bot.edit_message_text("🛠 <b>Select Service to Add Stock:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("addsrv_"))
def select_add_service(call):
    srv = call.data.split("_")[1]
    user_states[call.from_user.id] = {"action": "add_stock", "service": srv}
    
    if srv == "Others":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "✏️ <b>Enter the custom service name:</b>\n<i>(e.g., GoChat, Discord, Msport, Yalla Ludo)</i>", parse_mode="HTML")
        bot.register_next_step_handler(msg, get_custom_service_name)
    else:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, f"📤 <b>Upload .txt file for {srv}:</b>\n<i>Format: One number per line</i>", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_stock_upload)

def get_custom_service_name(message):
    custom_name = message.text.strip()
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id].get("action") != "add_stock":
        return
    
    user_states[user_id]["custom_service"] = custom_name
    msg = bot.send_message(message.chat.id, f"📤 <b>Upload .txt file for Others - {custom_name}:</b>\n<i>Format: One number per line</i>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_stock_upload)

def process_stock_upload(message):
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id].get("action") != "add_stock":
        return
    
    state = user_states[user_id]
    srv = state["service"]
    custom_name = state.get("custom_service", None)
    
    # Use custom name if Others, else use service name
    final_service = custom_name if custom_name else srv
    
    if not message.document:
        bot.send_message(message.chat.id, "❌ Please upload a .txt file!")
        return
    
    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path).decode('utf-8')
    nums = [re.sub(r'[^\d]', '', n) for n in downloaded.splitlines() if len(n) > 8]
    
    if not nums:
        bot.send_message(message.chat.id, "❌ No valid numbers found in file!")
        return
    
    # Detect country code
    code = "1"
    for c in COUNTRY_DATA.keys():
        if sum(1 for n in nums[:5] if n.startswith(c)) >= 1:
            code = c
            break
    
    with sqlite3.connect(DB_PATH) as conn:
        # Check if combo already exists
        existing = conn.execute(
            "SELECT numbers FROM combos WHERE country_code=? AND service=?", 
            (code, final_service)
        ).fetchone()
        
        if existing:
            old_nums = json.loads(existing[0])
            new_nums = old_nums + nums
            conn.execute(
                "UPDATE combos SET numbers=? WHERE country_code=? AND service=?",
                (json.dumps(new_nums), code, final_service)
            )
        else:
            conn.execute(
                "INSERT INTO combos (country_code, service, numbers) VALUES (?, ?, ?)", 
                (code, final_service, json.dumps(nums))
            )
        conn.commit()
    
    bot.send_message(message.chat.id, f"✅ Added {len(nums)} numbers to <b>{final_service}</b> ({code})!", parse_mode="HTML")
    
    name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
    send_stock_alert(name, flag, final_service, len(nums))
    
    del user_states[user_id]

# ======================
# 🗑 DELETE STOCK
# ======================
@bot.callback_query_handler(func=lambda call: call.data == "adm_del")
def delete_stock_menu(call):
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("📱 Telegram", callback_data="delsrv_Telegram", style="primary"),
        types.InlineKeyboardButton("💬 WhatsApp", callback_data="delsrv_WhatsApp", style="success"),
        types.InlineKeyboardButton("👤 Facebook", callback_data="delsrv_Facebook", style="primary"),
        types.InlineKeyboardButton("📦 Others", callback_data="delsrv_Others", style="danger"),
        types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger")
    )
    bot.edit_message_text("🗑️ <b>Select Service to Delete Stock:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsrv_"))
def select_delete_service(call):
    srv = call.data.split("_")[1]
    bot.answer_callback_query(call.id)
    
    with sqlite3.connect(DB_PATH) as conn:
        codes = [r[0] for r in conn.execute(
            "SELECT DISTINCT country_code FROM combos WHERE service=?", (srv,)
        ).fetchall()]
    
    if not codes:
        bot.answer_callback_query(call.id, f"❌ No stock found for {srv}!", show_alert=True)
        return
    
    m = types.InlineKeyboardMarkup(row_width=1)
    for c in codes:
        name, flag = COUNTRY_DATA.get(c, (c, "🌍"))
        m.add(types.InlineKeyboardButton(f"{flag} {name}", callback_data=f"delcnt_{c}_{srv}", style="danger"))
    m.add(types.InlineKeyboardButton("🔙 Back to Services", callback_data="adm_del", style="primary"))
    m.add(types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger"))
    
    bot.edit_message_text(f"🌍 <b>Select Country under {srv} to delete:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delcnt_"))
def select_delete_country(call):
    _, code, srv = call.data.split("_")
    bot.answer_callback_query(call.id)
    
    # If service is Others, show sub-services under this country
    if srv == "Others":
        with sqlite3.connect(DB_PATH) as conn:
            sub_services = [r[0] for r in conn.execute(
                "SELECT DISTINCT service FROM combos WHERE country_code=? AND service != 'Telegram' AND service != 'WhatsApp' AND service != 'Facebook'", 
                (code,)
            ).fetchall()]
        
        if not sub_services:
            bot.answer_callback_query(call.id, "❌ No sub-services found!", show_alert=True)
            return
        
        m = types.InlineKeyboardMarkup(row_width=1)
        for sub in sub_services:
            m.add(types.InlineKeyboardButton(f"🛠 {sub}", callback_data=f"delsub_{code}_{sub}", style="danger"))
        m.add(types.InlineKeyboardButton("🔙 Back to Countries", callback_data=f"delsrv_{srv}", style="primary"))
        m.add(types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger"))
        
        name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
        bot.edit_message_text(f"📦 <b>Select Service under Others - {flag} {name}:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")
    else:
        # Direct delete for Telegram, WhatsApp, Facebook
        confirm_delete(call, code, srv)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delsub_"))
def delete_sub_service(call):
    _, code, sub_srv = call.data.split("_")
    confirm_delete(call, code, sub_srv)

def confirm_delete(call, code, srv):
    name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
    
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirmdel_{code}_{srv}", style="danger"),
        types.InlineKeyboardButton("❌ Cancel", callback_data=f"delcnt_{code}_{'Others' if srv not in ['Telegram','WhatsApp','Facebook'] else srv}", style="primary")
    )
    
    # Adjust back button based on service type
    if srv in ['Telegram', 'WhatsApp', 'Facebook']:
        m.add(types.InlineKeyboardButton("🔙 Back to Countries", callback_data=f"delsrv_{srv}", style="primary"))
    else:
        m.add(types.InlineKeyboardButton("🔙 Back to Sub-Services", callback_data=f"delcnt_{code}_Others", style="primary"))
    m.add(types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger"))
    
    bot.edit_message_text(f"⚠️ <b>Confirm Delete?</b>\n\n🌍 Country: {flag} {name}\n🛠 Service: {srv}\n\n<i>This will remove ALL numbers for this combo!</i>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirmdel_"))
def execute_delete(call):
    _, code, srv = call.data.split("_")
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM combos WHERE country_code=? AND service=?", (code, srv))
        conn.commit()
    
    bot.answer_callback_query(call.id, f"✅ Deleted {srv} stock for {code}!", show_alert=True)
    
    # Go back to appropriate menu
    if srv in ['Telegram', 'WhatsApp', 'Facebook']:
        # Back to countries for that service
        with sqlite3.connect(DB_PATH) as conn:
            codes = [r[0] for r in conn.execute(
                "SELECT DISTINCT country_code FROM combos WHERE service=?", (srv,)
            ).fetchall()]
        
        if codes:
            m = types.InlineKeyboardMarkup(row_width=1)
            for c in codes:
                name, flag = COUNTRY_DATA.get(c, (c, "🌍"))
                m.add(types.InlineKeyboardButton(f"{flag} {name}", callback_data=f"delcnt_{c}_{srv}", style="danger"))
            m.add(types.InlineKeyboardButton("🔙 Back to Services", callback_data="adm_del", style="primary"))
            m.add(types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger"))
            bot.edit_message_text(f"🌍 <b>Select Country under {srv} to delete:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")
        else:
            # No more stock, back to services
            delete_stock_menu(call)
    else:
        # Back to sub-services under Others for this country
        with sqlite3.connect(DB_PATH) as conn:
            sub_services = [r[0] for r in conn.execute(
                "SELECT DISTINCT service FROM combos WHERE country_code=? AND service != 'Telegram' AND service != 'WhatsApp' AND service != 'Facebook'", 
                (code,)
            ).fetchall()]
        
        if sub_services:
            m = types.InlineKeyboardMarkup(row_width=1)
            for sub in sub_services:
                m.add(types.InlineKeyboardButton(f"🛠 {sub}", callback_data=f"delsub_{code}_{sub}", style="danger"))
            m.add(types.InlineKeyboardButton("🔙 Back to Countries", callback_data="delsrv_Others", style="primary"))
            m.add(types.InlineKeyboardButton("🔙 Back to Panel", callback_data="back_admin", style="danger"))
            name, flag = COUNTRY_DATA.get(code, (code, "🌍"))
            bot.edit_message_text(f"📦 <b>Select Service under Others - {flag} {name}:</b>", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode="HTML")
        else:
            # No more sub-services, back to countries
            select_delete_service(call)

# ======================
# 📢 BROADCAST
# ======================
@bot.callback_query_handler(func=lambda call: call.data == "adm_bc")
def bc_req(call):
    bot.answer_callback_query(call.id)
    user_states[call.from_user.id] = "bc_msg"
    msg = bot.send_message(call.message.chat.id, "💬 <b>Send message to broadcast:</b>\n<i>Type your message or /cancel to abort</i>", parse_mode="HTML")
    bot.register_next_step_handler(msg, bc_process)

def bc_process(message):
    if message.text == "/cancel":
        bot.send_message(message.chat.id, "❌ Broadcast cancelled.")
        if message.from_user.id in user_states:
            del user_states[message.from_user.id]
        return
    
    manual_broadcast(message.text)
    bot.reply_to(message, "✅ Broadcast Sent to all users!")
    
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]

# ======================
# 🔙 BACK HANDLERS
# ======================
@bot.callback_query_handler(func=lambda call: call.data == "back_admin")
def back_to_admin(call):
    bot.answer_callback_query(call.id)
    admin_panel(call, edit=True)

# ======================
# 🚀 RUN BOT
# ======================
def run_bot():
    print("[SERVER] Bot is live! Advanced Admin Panel with custom services.")
    bot.infinity_polling(timeout=60, long_polling_timeout=5)

if __name__ == "__main__":
    run_bot()
