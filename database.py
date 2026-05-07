import json
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

# ======================
# RAILWAY POSTGRES CONNECTION (ROBUST)
# ======================
def get_db():
    # Priority 1: DATABASE_URL (Recommended)
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        # Priority 2: Build from Railway PG variables
        host = os.getenv("PGHOST") or os.getenv("PGHOST_PRIVATE")
        port = os.getenv("PGPORT", 5432)
        dbname = os.getenv("PGDATABASE")
        user = os.getenv("PGUSER")
        password = os.getenv("PGPASSWORD")
        
        if host and dbname and user and password:
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        else:
            raise Exception(
                "❌ DATABASE_URL is missing!\n\n"
                "Fix: Go to your Bot Service → Variables → Add:\n"
                "DATABASE_URL = ${{Postgres.DATABASE_URL}}  (use reference)"
            )

    result = urlparse(database_url)
    
    conn = psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port or 5432,
        sslmode="require"
    )
    
    conn.set_session(autocommit=False)
    return conn

def init_db():
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            status TEXT DEFAULT 'none',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_numbers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            number TEXT NOT NULL,
            country_code TEXT,
            service TEXT,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, number)
        );

        CREATE TABLE IF NOT EXISTS combos (
            id SERIAL PRIMARY KEY,
            country_code TEXT NOT NULL,
            service TEXT NOT NULL,
            numbers JSONB NOT NULL DEFAULT '[]'::jsonb,
            UNIQUE(country_code, service)
        );

        CREATE TABLE IF NOT EXISTS otp_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            number TEXT,
            service TEXT,
            otp_code TEXT,
            sender TEXT,
            message_body TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS processed_otps (
            id SERIAL PRIMARY KEY,
            number TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(number, otp_code)
        );
        ''')
        
        conn.commit()
        conn.close()
        print("✅ Railway PostgreSQL Database initialized successfully.")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise

# Initialize on import
init_db()

# ======================
# USER OPERATIONS
# ======================
def get_user(user_id):
    conn = get_db()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def save_user(user_id, username=None, first_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    INSERT INTO users (user_id, username, first_name)
    VALUES (%s, %s, %s)
    ON CONFLICT (user_id) DO UPDATE 
    SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def assign_number_to_user(user_id, number, country_code, service):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    INSERT INTO user_numbers (user_id, number, country_code, service, assigned_at)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (user_id, number) DO NOTHING
    ''', (user_id, number, country_code, service, datetime.now()))
    conn.commit()
    conn.close()

def release_user_number(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM user_numbers WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

def get_user_by_number(number):
    conn = get_db()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute('''
    SELECT u.*, un.number, un.country_code, un.service 
    FROM users u
    JOIN user_numbers un ON u.user_id = un.user_id
    WHERE un.number = %s
    ''', (number,))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def get_all_users():
    conn = get_db()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return [dict(u) for u in users]

# ======================
# COMBO OPERATIONS
# ======================
def add_combo(country_code, service, numbers_list):
    conn = get_db()
    c = conn.cursor()
    numbers_json = json.dumps(numbers_list)
    c.execute('''
    INSERT INTO combos (country_code, service, numbers)
    VALUES (%s, %s, %s::jsonb)
    ON CONFLICT (country_code, service) DO UPDATE 
    SET numbers = combos.numbers || EXCLUDED.numbers
    ''', (country_code, service, numbers_json))
    conn.commit()
    conn.close()

# ======================
# OTP OPERATIONS
# ======================
def save_otp_log(user_id, number, service, otp_code, sender, message_body):
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
    INSERT INTO processed_otps (number, otp_code, received_at)
    VALUES (%s, %s, %s)
    ON CONFLICT (number, otp_code) DO NOTHING
    ''', (number, otp_code, datetime.now()))
    
    c.execute('''
    INSERT INTO otp_logs 
    (user_id, number, service, otp_code, sender, message_body, received_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (user_id, number, service, otp_code, sender, message_body, datetime.now()))
    
    conn.commit()
    conn.close()

def is_otp_processed(number, otp_code):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM processed_otps WHERE number = %s AND otp_code = %s", (number, otp_code))
    result = c.fetchone()
    conn.close()
    return result is not None

# ======================
# HELPER FUNCTIONS
# ======================
def get_available_services():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT service FROM combos")
    services = c.fetchall()
    conn.close()
    return [s[0] for s in services]

def get_countries_for_service(service):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT country_code FROM combos WHERE service = %s", (service,))
    countries = c.fetchall()
    conn.close()
    return [c[0] for c in countries]
