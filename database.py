import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json
from config import DATABASE_URL


# =========================
# DB CONNECTION
# =========================
def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


# =========================
# INIT DATABASE
# =========================
def init_db():
    conn = get_db()
    c = conn.cursor()

    # USERS
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            status TEXT DEFAULT 'none',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # USER NUMBERS
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_numbers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            number TEXT NOT NULL UNIQUE,
            country_code TEXT NOT NULL,
            service TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            is_primary BOOLEAN DEFAULT false
        )
    """)

    # COMBOS
    c.execute("""
        CREATE TABLE IF NOT EXISTS combos (
            id SERIAL PRIMARY KEY,
            country_code TEXT NOT NULL,
            service TEXT NOT NULL,
            numbers TEXT
        )
    """)

    # OTP LOGS
    c.execute("""
        CREATE TABLE IF NOT EXISTS otp_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            number TEXT NOT NULL,
            service TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            sender TEXT,
            message_body TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # PROCESSED OTP
    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_otps (
            id SERIAL PRIMARY KEY,
            number TEXT NOT NULL,
            otp_code TEXT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(number, otp_code)
        )
    """)

    # SAFE COLUMN MIGRATIONS
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
    c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    c.execute("ALTER TABLE user_numbers ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    c.execute("ALTER TABLE user_numbers ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    c.execute("ALTER TABLE user_numbers ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT false")

    conn.commit()
    conn.close()
    print("[DB INIT] ✅ Database initialized successfully")


# =========================
# USER FUNCTIONS
# =========================
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = c.fetchone()

    if user:
        c.execute("""
            SELECT * FROM user_numbers
            WHERE user_id = %s AND status = 'active'
            ORDER BY is_primary DESC, assigned_at DESC
        """, (user_id,))
        numbers = c.fetchall()

        user = dict(user)
        user["numbers"] = [dict(n) for n in numbers] if numbers else []

    conn.close()
    return user


def save_user(user_id, username=None, first_name=None):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO users (user_id, username, first_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name
    """, (user_id, username, first_name))

    conn.commit()
    conn.close()


# =========================
# SAFE GET ALL USERS (FIXED)
# =========================
def get_all_users():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT 
            u.user_id,
            u.username,
            u.first_name,
            u.status,
            u.created_at,
            COALESCE(ARRAY_REMOVE(ARRAY_AGG(un.number), NULL), '{}') AS numbers,
            COALESCE(ARRAY_REMOVE(ARRAY_AGG(un.service), NULL), '{}') AS services
        FROM users u
        LEFT JOIN user_numbers un 
            ON u.user_id = un.user_id 
            AND un.status = 'active'
        GROUP BY u.user_id, u.username, u.first_name, u.status, u.created_at
        ORDER BY u.created_at DESC
    """)

    users = c.fetchall()
    conn.close()
    return [dict(u) for u in users]


# =========================
# USER NUMBER ASSIGNMENT
# =========================
def assign_number_to_user(user_id, number, country_code, service):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT user_id FROM user_numbers
        WHERE number = %s AND status = 'active'
    """, (number,))
    existing = c.fetchone()

    if existing:
        conn.close()
        if existing["user_id"] == user_id:
            return False, "Already assigned to you"
        return False, "Assigned to another user"

    c.execute("""
        SELECT COUNT(*) as count FROM user_numbers
        WHERE user_id = %s AND status = 'active'
    """, (user_id,))
    count = c.fetchone()["count"]

    if count >= 5:
        conn.close()
        return False, "Max 5 numbers allowed"

    is_primary = (count == 0)

    c.execute("""
        INSERT INTO user_numbers
        (user_id, number, country_code, service, is_primary)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, number, country_code, service, is_primary))

    c.execute("""
        UPDATE users SET status = 'active'
        WHERE user_id = %s
    """, (user_id,))

    conn.commit()
    conn.close()
    return True, "Assigned successfully"


# =========================
# RELEASE NUMBER
# =========================
def release_user_number(user_id, number=None):
    conn = get_db()
    c = conn.cursor()

    if number:
        c.execute("""
            UPDATE user_numbers
            SET status = 'released'
            WHERE user_id = %s AND number = %s
        """, (user_id, number))
    else:
        c.execute("""
            UPDATE user_numbers
            SET status = 'released'
            WHERE user_id = %s
        """, (user_id,))

    conn.commit()
    conn.close()
    return True


# =========================
# OTP LOGGING
# =========================
def save_otp_log(user_id, number, service, otp_code, sender, message_body):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO processed_otps (number, otp_code)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
    """, (number, otp_code))

    c.execute("""
        INSERT INTO otp_logs
        (user_id, number, service, otp_code, sender, message_body)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (user_id, number, service, otp_code, sender, message_body))

    conn.commit()
    conn.close()


# =========================
# ACTIVE NUMBERS
# =========================
def get_all_active_numbers():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT un.number, un.user_id, un.service, u.username
        FROM user_numbers un
        JOIN users u ON u.user_id = un.user_id
        WHERE un.status = 'active'
    """)

    data = c.fetchall()
    conn.close()
    return [dict(d) for d in data]


# =========================
# INIT CALL
# =========================
init_db()
