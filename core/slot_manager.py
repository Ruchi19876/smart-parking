"""
Module 2: Slot Allocation Engine — MODIFIED
============================================
Key change: slots are now allocated BY VEHICLE TYPE.
  - Bike/Scooter  → Zone A slots only
  - Car/Auto      → Zone B slots only
  - EV            → Zone C slots only
  - Heavy         → Zone D slots only
"""

import time
from database.db_setup import get_connection, ZONES, VEHICLE_PRICING
import math


def get_all_slots() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.zone, s.zone_label, s.slot_number, s.vehicle_type,
               s.status, s.sensor_id,
               sess.vehicle_plate, sess.entry_time, sess.id as session_id,
               sess.vehicle_type as session_vtype
        FROM slots s
        LEFT JOIN sessions sess ON sess.slot_id = s.id AND sess.status = 'active'
        ORDER BY s.slot_number
    """)
    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return slots


def get_slot_by_id(slot_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM slots WHERE id = ?", (slot_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# Map vehicle type → which zone it belongs to
VEHICLE_TO_ZONE = {
    "bike":   "A",
    "scooty": "A",
    "auto":   "B",
    "car":    "C",
    "ev":     "D",
    "heavy":  "E",
}


def find_nearest_free_slot(vehicle_type: str = None, preferred_zone: str = None) -> dict:
    """
    Find nearest free slot matching the vehicle type.
    If vehicle_type is given, only search in the correct zone.
    Falls back to preferred_zone or any free slot if not specified.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if vehicle_type and vehicle_type in VEHICLE_TO_ZONE:
        # Smart allocation: find slot in the correct zone for this vehicle
        zone = VEHICLE_TO_ZONE[vehicle_type]
        cursor.execute("""
            SELECT * FROM slots WHERE status = 'free' AND zone = ?
            ORDER BY slot_number LIMIT 1
        """, (zone,))
        slot = cursor.fetchone()
    elif preferred_zone:
        cursor.execute("""
            SELECT * FROM slots WHERE status = 'free' AND zone = ?
            ORDER BY slot_number LIMIT 1
        """, (preferred_zone,))
        slot = cursor.fetchone()
        if not slot:
            cursor.execute("SELECT * FROM slots WHERE status='free' ORDER BY slot_number LIMIT 1")
            slot = cursor.fetchone()
    else:
        cursor.execute("SELECT * FROM slots WHERE status='free' ORDER BY slot_number LIMIT 1")
        slot = cursor.fetchone()

    conn.close()
    return dict(slot) if slot else None


def occupy_slot(slot_id: int, vehicle_type: str = None) -> bool:
    conn = get_connection()
    if vehicle_type:
        conn.execute("UPDATE slots SET status = 'occupied', vehicle_type = ? WHERE id = ?", (vehicle_type, slot_id))
    else:
        conn.execute("UPDATE slots SET status = 'occupied' WHERE id = ?", (slot_id,))
    conn.commit(); conn.close()
    return True


def free_slot(slot_id: int) -> bool:
    conn = get_connection()
    conn.execute("UPDATE slots SET status = 'free' WHERE id = ?", (slot_id,))
    conn.commit(); conn.close()
    return True


def reserve_slot(slot_id: int) -> bool:
    conn = get_connection()
    conn.execute("UPDATE slots SET status = 'reserved' WHERE id = ?", (slot_id,))
    conn.commit(); conn.close()
    return True


def get_slot_stats() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM slots"); total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM slots WHERE status='occupied'"); occupied = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM slots WHERE status='free'"); free = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM slots WHERE status='reserved'"); reserved = cursor.fetchone()[0]
    conn.close()
    occupancy_pct = round(((occupied + reserved) / total * 100) if total > 0 else 0, 1)
    return {"total": total, "occupied": occupied, "free": free,
            "reserved": reserved, "occupancy_pct": occupancy_pct}


def get_stats_by_zone() -> list:
    """Get occupancy stats per zone — used for zone summary cards on dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT zone, zone_label, vehicle_type,
               COUNT(*) as total,
               SUM(CASE WHEN status='free' THEN 1 ELSE 0 END) as free,
               SUM(CASE WHEN status='occupied' THEN 1 ELSE 0 END) as occupied,
               SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) as reserved
        FROM slots GROUP BY zone ORDER BY zone
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def admin_override_slot(slot_id: int, new_status: str) -> dict:
    valid = ["free", "occupied", "reserved"]
    if new_status not in valid:
        return {"success": False, "error": f"Invalid status."}
    conn = get_connection()
    cursor = conn.cursor()
    if new_status == "free":
        cursor.execute("""UPDATE sessions SET status='completed', exit_time=?
                          WHERE slot_id=? AND status='active'""",
                       (time.strftime("%Y-%m-%d %H:%M:%S"), slot_id))
    cursor.execute("UPDATE slots SET status=? WHERE id=?", (new_status, slot_id))
    conn.commit(); conn.close()
    return {"success": True, "message": f"Slot {slot_id} set to '{new_status}'."}


def get_fee_for_vehicle(vehicle_type: str, duration_minutes: int) -> float:
    """Calculate fee based on vehicle type pricing."""
    first_hour, per_hour = VEHICLE_PRICING.get(vehicle_type, (20, 10))
    if duration_minutes <= 60:
        return float(first_hour)
    extra_hours = math.ceil((duration_minutes - 60) / 60)
    return float(first_hour + extra_hours * per_hour)
