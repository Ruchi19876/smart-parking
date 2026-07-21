"""
Module 8: Database Layer — SQLite Schema Setup & Seeding
=========================================================
MODIFIED: 
  - slots table now has vehicle_type column
  - 36 slots across 5 zones:
      Zone A (Two Wheelers)   : 10 slots — Bike, Scooty
      Zone B (Three Wheelers) :  4 slots — Auto
      Zone C (Four Wheelers)  : 12 slots — Car
      Zone D (EV Cars)        :  6 slots — EV Charged Cars
      Zone E (Heavy Vehicles) :  4 slots — Truck, Bus
"""

import sqlite3
import os
import time
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parking.db")

DEFAULT_ADMIN_EMAIL    = "admin@parking.com"
DEFAULT_ADMIN_PASSWORD = "Admin@1234"
DEFAULT_ADMIN_NAME     = "System Administrator"

# All supported vehicle types
VEHICLE_TYPES = ["bike", "scooty", "auto", "car", "ev", "heavy"]

# Security questions for password recovery (offline, no email server needed)
SECURITY_QUESTIONS = [
    "What is your favorite color?",
    "What is your pet's name?",
    "What city were you born in?",
    "What is your favorite food?",
    "What was the name of your first school?",
]

# Zone definitions: (zone_code, zone_label, vehicle_types_allowed, slot_count, color_class)
ZONES = [
    ("A", "Zone A — Two Wheelers",   ["bike", "scooty"], 10, "zone-tw"),
    ("B", "Zone B — Three Wheelers", ["auto"],            4, "zone-3w"),
    ("C", "Zone C — Four Wheelers",  ["car"],            12, "zone-fw"),
    ("D", "Zone D — EV Cars",        ["ev"],              6, "zone-ev"),
    ("E", "Zone E — Heavy Vehicles", ["heavy"],           4, "zone-hv"),
]

# Pricing per vehicle type: (first_hour_rate, per_additional_hour_rate)
VEHICLE_PRICING = {
    "bike":   (10, 5),
    "scooty": (10, 5),
    "auto":   (15, 8),
    "car":    (20, 10),
    "ev":     (25, 12),
    "heavy":  (40, 20),
}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # TABLE: users — added vehicle_type column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT    NOT NULL,
            email                 TEXT    NOT NULL UNIQUE,
            password_hash         TEXT    NOT NULL,
            phone                 TEXT,
            vehicle_plate         TEXT,
            vehicle_type          TEXT    DEFAULT 'car',
            role                  TEXT    NOT NULL DEFAULT 'user',
            security_question     TEXT,
            security_answer_hash  TEXT,
            created_at            TEXT    NOT NULL
        )
    """)

    # TABLE: slots — added vehicle_type and zone_label columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            zone         TEXT    NOT NULL,
            zone_label   TEXT    NOT NULL,
            slot_number  INTEGER NOT NULL,
            vehicle_type TEXT    NOT NULL DEFAULT 'car',
            status       TEXT    NOT NULL DEFAULT 'free',
            sensor_id    TEXT    NOT NULL
        )
    """)

    # TABLE: sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER REFERENCES users(id),
            slot_id       INTEGER NOT NULL REFERENCES slots(id),
            vehicle_plate TEXT    NOT NULL,
            vehicle_type  TEXT    NOT NULL DEFAULT 'car',
            entry_time    TEXT    NOT NULL,
            exit_time     TEXT,
            status        TEXT    NOT NULL DEFAULT 'active'
        )
    """)

    # TABLE: bills
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id       INTEGER NOT NULL REFERENCES sessions(id),
            amount           REAL    NOT NULL,
            duration_minutes INTEGER NOT NULL,
            entry_time       TEXT    NOT NULL,
            exit_time        TEXT    NOT NULL,
            vehicle_plate    TEXT    NOT NULL,
            vehicle_type     TEXT    NOT NULL DEFAULT 'car',
            slot_number      INTEGER NOT NULL,
            zone             TEXT    NOT NULL,
            generated_at     TEXT    NOT NULL
        )
    """)

    # TABLE: sensor_logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_type   TEXT    NOT NULL,
            sensor_id     TEXT    NOT NULL,
            slot_id       INTEGER,
            reading_value TEXT    NOT NULL,
            raw_data      TEXT,
            timestamp     TEXT    NOT NULL
        )
    """)

    # TABLE: bookings — ONLINE ADVANCE SLOT BOOKING (NEW)
    # Lets a user reserve a slot for a future date/time window.
    # status: 'upcoming' (booked, not yet arrived)
    #         'fulfilled' (user arrived, session started)
    #         'expired'   (user did not arrive within 10 min grace period)
    #         'cancelled' (user manually cancelled before arrival)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(id),
            slot_id        INTEGER NOT NULL REFERENCES slots(id),
            zone           TEXT    NOT NULL,
            zone_label     TEXT    NOT NULL,
            vehicle_type   TEXT    NOT NULL,
            vehicle_plate  TEXT,
            booking_date   TEXT    NOT NULL,
            start_time     TEXT    NOT NULL,
            end_time       TEXT    NOT NULL,
            status         TEXT    NOT NULL DEFAULT 'upcoming',
            session_id     INTEGER REFERENCES sessions(id),
            created_at     TEXT    NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Tables created / verified.")


def seed_slots():
    """
    Seed 36 slots across 5 zones.
    Zone A: 10 two-wheeler slots (bike/scooty)
    Zone B:  4 three-wheeler slots (auto)
    Zone C: 12 four-wheeler slots (car)
    Zone D:  6 EV slots
    Zone E:  4 heavy vehicle slots
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM slots")
    if cursor.fetchone()[0] > 0:
        print("[DB] Slots already seeded — skipping.")
        conn.close()
        return

    slot_num = 1
    rows = []
    for zone_code, zone_label, vtypes, count, _ in ZONES:
        # Primary vehicle type for the zone (first in list)
        primary_vtype = vtypes[0]
        for i in range(count):
            rows.append((
                zone_code,
                zone_label,
                slot_num,
                primary_vtype,
                "free",
                f"ULTRA_SLOT_{slot_num:02d}"
            ))
            slot_num += 1

    cursor.executemany(
        "INSERT INTO slots (zone, zone_label, slot_number, vehicle_type, status, sensor_id) VALUES (?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    conn.close()
    print(f"[DB] 36 slots seeded across 5 zones (A:10 B:4 C:12 D:6 E:4).")


def seed_admin():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_ADMIN_EMAIL,))
    if cursor.fetchone():
        print(f"[DB] Admin exists. Login: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")
        conn.close()
        return

    hashed_pw = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
    cursor.execute("""
        INSERT INTO users (name, email, password_hash, phone, vehicle_type, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (DEFAULT_ADMIN_NAME, DEFAULT_ADMIN_EMAIL, hashed_pw,
          "9999999999", "car", "admin", time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    print("\n" + "="*55)
    print("  DEFAULT ADMIN ACCOUNT CREATED")
    print("="*55)
    print(f"  Email   : {DEFAULT_ADMIN_EMAIL}")
    print(f"  Password: {DEFAULT_ADMIN_PASSWORD}")
    print("="*55 + "\n")


def migrate_users_table():
    """
    Safe migration: adds security_question / security_answer_hash columns
    to an EXISTING users table if it was created before this feature existed.
    SQLite doesn't support 'ADD COLUMN IF NOT EXISTS', so we check first.
    This means upgrading an old parking.db won't break — no data is lost.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    existing_cols = {row["name"] for row in cursor.fetchall()}

    if "security_question" not in existing_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN security_question TEXT")
        print("[DB] Migrated: added security_question column.")
    if "security_answer_hash" not in existing_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN security_answer_hash TEXT")
        print("[DB] Migrated: added security_answer_hash column.")

    conn.commit()
    conn.close()


def setup_database():
    print("[DB] Initializing database...")
    init_db()
    migrate_users_table()
    seed_slots()
    seed_admin()
    print("[DB] Database ready.\n")


def add_payments_table():
    """
    Add payments table for the payment module.
    Called at startup — safe to call multiple times (IF NOT EXISTS).
    Stores UPI / Card / Cash payment records with transaction ID and status.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id        INTEGER NOT NULL,
            session_id     INTEGER NOT NULL,
            user_id        INTEGER,
            vehicle_plate  TEXT NOT NULL,
            amount         REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'upi',
            upi_id         TEXT,
            transaction_id TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'success',
            paid_at        TEXT NOT NULL
        )
    """)
    conn.commit()

    # Safe migration (same idiom as migrate_users_table): adds a generic
    # payment_ref column so Card (masked card no.) and Cash (collected-by
    # note) payments have somewhere to store their reference detail
    # without touching the existing upi_id column or any UPI logic.
    cursor.execute("PRAGMA table_info(payments)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    if "payment_ref" not in existing_cols:
        cursor.execute("ALTER TABLE payments ADD COLUMN payment_ref TEXT")
        print("[DB] Migrated: added payment_ref column to payments.")

    conn.commit()
    conn.close()
