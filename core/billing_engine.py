"""
Module 4: Billing Engine — MODIFIED
Uses vehicle-type-specific pricing from VEHICLE_PRICING map.
"""
import math, time
from database.db_setup import get_connection, VEHICLE_PRICING


def calculate_fee(duration_minutes: int, vehicle_type: str = "car") -> float:
    first_hour, per_hour = VEHICLE_PRICING.get(vehicle_type, (20, 10))
    if duration_minutes <= 60:
        return float(first_hour)
    extra_hours = math.ceil((duration_minutes - 60) / 60)
    return float(first_hour + extra_hours * per_hour)


def generate_bill(session_data: dict) -> dict:
    duration_minutes = session_data["duration_minutes"]
    vehicle_type     = session_data.get("vehicle_type", "car")
    amount           = calculate_fee(duration_minutes, vehicle_type)
    generated_at     = time.strftime("%Y-%m-%d %H:%M:%S")

    first_hour, per_hour = VEHICLE_PRICING.get(vehicle_type, (20, 10))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bills (session_id, amount, duration_minutes, entry_time,
                           exit_time, vehicle_plate, vehicle_type, slot_number, zone, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_data["session_id"], amount, duration_minutes,
          session_data["entry_time"], session_data["exit_time"],
          session_data["vehicle_plate"], vehicle_type,
          session_data["slot_number"], session_data.get("zone", "A"), generated_at))
    bill_id = cursor.lastrowid
    conn.commit(); conn.close()

    return {
        "bill_id":           bill_id,
        "session_id":        session_data["session_id"],
        "vehicle_plate":     session_data["vehicle_plate"],
        "vehicle_type":      vehicle_type,
        "zone":              session_data.get("zone", "A"),
        "slot_number":       session_data["slot_number"],
        "entry_time":        session_data["entry_time"],
        "exit_time":         session_data["exit_time"],
        "duration_minutes":  duration_minutes,
        "duration_display":  _fmt(duration_minutes),
        "amount":            amount,
        "amount_display":    f"₹{amount:.0f}",
        "first_hour_rate":   first_hour,
        "additional_rate":   per_hour,
        "generated_at":      generated_at
    }


def get_today_revenue() -> float:
    today = time.strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(amount),0) FROM bills WHERE generated_at LIKE ?", (f"{today}%",))
    rev = float(cursor.fetchone()[0])
    conn.close()
    return rev


def get_all_bills(limit=100) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bills ORDER BY generated_at DESC LIMIT ?", (limit,))
    bills = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return bills


def get_user_bills(user_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT b.* FROM bills b JOIN sessions s ON s.id=b.session_id
                      WHERE s.user_id=? ORDER BY b.generated_at DESC""", (user_id,))
    bills = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return bills


def _fmt(minutes: int) -> str:
    if minutes < 60: return f"{minutes} min"
    h = minutes // 60; m = minutes % 60
    return f"{h} hr {m} min" if m else f"{h} hr"
