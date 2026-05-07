import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json
from config import DATABASE_URL

def get_db():
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            assigned_number TEXT,
            country_code TEXT,
            service TEXT,
            assigned_at TIMESTAMP,
            status TEXT DEFAULT 'none'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS combos (
            id SERIAL PRIMARY KEY,
            country_code TEXT,
            service TEXT,
            numbers TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS otp_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            number TEXT,
            service TEXT,
            otp_code TEXT,
            sender TEXT,
            message_body TEXT,
            received_at TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_otps (
            id SERIAL PRIMARY KEY,
            number TEXT,
            otp_code TEXT,
            received_at TIMESTAMP,
            UNIQUE(number, otp_code)
        )
    """)

    conn.commit()
    conn.close()

# === USER OPERATIONS ===

def get_user(user_id):
    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT * FROM users WHERE user_id = %s",
        (user_id,)
    )

    user = c.fetchone()
    conn.close()

    return dict(user) if user else None


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


def assign_number_to_user(user_id, number, country_code, service):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET assigned_number = %s,
            country_code = %s,
            service = %s,
            assigned_at = %s,
            status = 'active'
        WHERE user_id = %s
    """, (
        number,
        country_code,
        service,
        datetime.now(),
        user_id
    ))

    conn.commit()
    conn.close()


def release_user_number(user_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET assigned_number = NULL,
            country_code = NULL,
            service = NULL,
            status = 'none'
        WHERE user_id = %s
    """, (user_id,))

    conn.commit()
    conn.close()


def get_user_by_number(number):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM users
        WHERE assigned_number = %s
        AND status = 'active'
    """, (number,))

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

    numbers_json = json.dumps(numbers_list)

    c.execute("""
        INSERT INTO combos (country_code, service, numbers)
        VALUES (%s, %s, %s)
    """, (
        country_code,
        service,
        numbers_json
    ))

    conn.commit()
    conn.close()


def get_combo(country_code, service):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM combos
        WHERE country_code = %s
        AND service = %s
        ORDER BY id DESC
        LIMIT 1
    """, (
        country_code,
        service
    ))

    combo = c.fetchone()
    conn.close()

    return dict(combo) if combo else None


def pop_number_from_combo(country_code, service):
    conn = get_db()
    c = conn.cursor()

    combo = get_combo(country_code, service)

    if not combo:
        conn.close()
        return None

    numbers = json.loads(combo['numbers'])

    if not numbers:
        conn.close()
        return None

    number = numbers.pop(0)

    c.execute("""
        UPDATE combos
        SET numbers = %s
        WHERE id = %s
    """, (
        json.dumps(numbers),
        combo['id']
    ))

    conn.commit()
    conn.close()

    return number

# === OTP OPERATIONS ===

def save_otp_log(user_id, number, service, otp_code, sender, message_body):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO processed_otps
        (number, otp_code, received_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (number, otp_code)
        DO NOTHING
    """, (
        number,
        otp_code,
        datetime.now()
    ))

    c.execute("""
        INSERT INTO otp_logs
        (user_id, number, service, otp_code,
         sender, message_body, received_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        user_id,
        number,
        service,
        otp_code,
        sender,
        message_body,
        datetime.now()
    ))

    conn.commit()
    conn.close()


def is_otp_processed(number, otp_code):
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id FROM processed_otps
        WHERE number = %s
        AND otp_code = %s
    """, (
        number,
        otp_code
    ))

    result = c.fetchone()
    conn.close()

    return result is not None


# Initialize DB
init_db()
