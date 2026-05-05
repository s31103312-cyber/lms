import sqlite3
from datetime import datetime
from config import DB_FILE

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            assigned_number TEXT,
            country_code TEXT,
            service TEXT,
            assigned_at TIMESTAMP,
            status TEXT DEFAULT 'none'
        );
        
        CREATE TABLE IF NOT EXISTS combos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code TEXT,
            service TEXT,
            numbers TEXT
        );
        
        CREATE TABLE IF NOT EXISTS otp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            number TEXT,
            service TEXT,
            otp_code TEXT,
            sender TEXT,
            message_body TEXT,
            received_at TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS processed_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT,
            otp_code TEXT,
            received_at TIMESTAMP,
            UNIQUE(number, otp_code)
        );
    ''')
    
    conn.commit()
    conn.close()

# === USER OPERATIONS ===
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def save_user(user_id, username=None, first_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def assign_number_to_user(user_id, number, country_code, service):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE users 
        SET assigned_number = ?, country_code = ?, service = ?, 
            assigned_at = ?, status = 'active'
        WHERE user_id = ?
    ''', (number, country_code, service, datetime.now(), user_id))
    conn.commit()
    conn.close()

def release_user_number(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE users 
        SET assigned_number = NULL, country_code = NULL, 
            service = NULL, status = 'none'
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()

def get_user_by_number(number):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE assigned_number = ? AND status = 'active'", (number,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return [dict(u) for u in users]

# === COMBO OPERATIONS ===
def add_combo(country_code, service, numbers_list):
    conn = get_db()
    c = conn.cursor()
    import json
    numbers_json = json.dumps(numbers_list)
    c.execute('''
        INSERT INTO combos (country_code, service, numbers)
        VALUES (?, ?, ?)
    ''', (country_code, service, numbers_json))
    conn.commit()
    conn.close()

def get_combo(country_code, service):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT * FROM combos 
        WHERE country_code = ? AND service = ?
        ORDER BY id DESC LIMIT 1
    ''', (country_code, service))
    combo = c.fetchone()
    conn.close()
    return dict(combo) if combo else None

def pop_number_from_combo(country_code, service):
    conn = get_db()
    c = conn.cursor()
    import json
    combo = get_combo(country_code, service)
    if not combo:
        conn.close()
        return None
    
    numbers = json.loads(combo['numbers'])
    if not numbers:
        conn.close()
        return None
    
    number = numbers.pop(0)
    numbers_json = json.dumps(numbers)
    c.execute("UPDATE combos SET numbers = ? WHERE id = ?", (numbers_json, combo['id']))
    conn.commit()
    conn.close()
    return number

def get_available_services():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT service FROM combos")
    services = c.fetchall()
    conn.close()
    return [s['service'] for s in services]

def get_countries_for_service(service):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT country_code FROM combos WHERE service = ?", (service,))
    countries = c.fetchall()
    conn.close()
    return [c['country_code'] for c in countries]

def delete_combo(country_code, service):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM combos WHERE country_code = ? AND service = ?", (country_code, service))
    conn.commit()
    conn.close()

# === OTP LOG OPERATIONS ===
def save_otp_log(user_id, number, service, otp_code, sender, message_body):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO processed_otps (number, otp_code, received_at)
        VALUES (?, ?, ?)
    ''', (number, otp_code, datetime.now()))
    
    c.execute('''
        INSERT INTO otp_logs (user_id, number, service, otp_code, sender, message_body, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, number, service, otp_code, sender, message_body, datetime.now()))
    conn.commit()
    conn.close()

def is_otp_processed(number, otp_code):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM processed_otps WHERE number = ? AND otp_code = ?", (number, otp_code))
    result = c.fetchone()
    conn.close()
    return result is not None

# Initialize database on import
init_db()
