"""
Module 3: Session Manager — MODIFIED
Added vehicle_type to session tracking.
"""
import time, json
from database.db_setup import get_connection
from core.slot_manager import occupy_slot, free_slot


def start_session(vehicle_plate: str, slot_id: int, user_id: int = None,
                  vehicle_type: str = "car") -> dict:
    entry_time = time.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, slot_id, vehicle_plate, vehicle_type, entry_time, status)
        VALUES (?, ?, ?, ?, ?, 'active')
    """, (user_id, slot_id, vehicle_plate.upper(), vehicle_type, entry_time))
    session_id = cursor.lastrowid
    conn.commit(); conn.close()
    occupy_slot(slot_id, vehicle_type)
    return {"session_id": session_id, "vehicle_plate": vehicle_plate.upper(),
            "slot_id": slot_id, "vehicle_type": vehicle_type, "entry_time": entry_time}


def end_session(session_id: int) -> dict:
    exit_time = time.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, sl.slot_number, sl.zone, sl.zone_label, sl.vehicle_type as slot_vtype
        FROM sessions s
        JOIN slots sl ON sl.id = s.slot_id
        WHERE s.id = ? AND s.status = 'active'
    """, (session_id,))
    session = cursor.fetchone()
    if not session:
        conn.close()
        return {"success": False, "error": "Session not found or already completed."}

    entry_dt = time.mktime(time.strptime(session["entry_time"], "%Y-%m-%d %H:%M:%S"))
    exit_dt  = time.mktime(time.strptime(exit_time, "%Y-%m-%d %H:%M:%S"))
    duration_minutes = max(1, int((exit_dt - entry_dt) / 60))

    cursor.execute("UPDATE sessions SET status='completed', exit_time=? WHERE id=?",
                   (exit_time, session_id))
    conn.commit(); conn.close()
    free_slot(session["slot_id"])

    return {
        "success": True, "session_id": session_id,
        "vehicle_plate": session["vehicle_plate"],
        "vehicle_type":  session["vehicle_type"],
        "slot_id":       session["slot_id"],
        "slot_number":   session["slot_number"],
        "zone":          session["zone"],
        "zone_label":    session["zone_label"],
        "entry_time":    session["entry_time"],
        "exit_time":     exit_time,
        "duration_minutes": duration_minutes
    }


def get_active_sessions() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.user_id, s.vehicle_plate, s.vehicle_type, s.entry_time,
               sl.slot_number, sl.zone, sl.zone_label, sl.id as slot_id,
               u.name as user_name, u.phone as user_phone
        FROM sessions s
        JOIN slots sl ON sl.id = s.slot_id
        LEFT JOIN users u ON u.id = s.user_id
        WHERE s.status = 'active' ORDER BY s.entry_time DESC
    """)
    sessions = []
    now_ts = time.time()
    for row in cursor.fetchall():
        sess = dict(row)
        try:
            entry_ts = time.mktime(time.strptime(sess["entry_time"], "%Y-%m-%d %H:%M:%S"))
            elapsed  = int(now_ts - entry_ts)
            sess["elapsed_seconds"] = elapsed
            sess["elapsed_display"] = _fmt(elapsed)
        except:
            sess["elapsed_seconds"] = 0
            sess["elapsed_display"] = "0:00:00"
        sessions.append(sess)
    conn.close()
    return sessions


def get_user_sessions(user_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.vehicle_plate, s.vehicle_type, s.entry_time, s.exit_time, s.status,
               sl.slot_number, sl.zone, sl.zone_label, b.amount, b.duration_minutes
        FROM sessions s
        JOIN slots sl ON sl.id = s.slot_id
        LEFT JOIN bills b ON b.session_id = s.id
        WHERE s.user_id = ? ORDER BY s.entry_time DESC
    """, (user_id,))
    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sessions


def log_sensor_reading(sensor_type, sensor_id, reading_value,
                       slot_id=None, raw_data=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sensor_logs (sensor_type, sensor_id, slot_id, reading_value, raw_data, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (sensor_type, sensor_id, slot_id,
          reading_value, json.dumps(raw_data) if raw_data else None,
          time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    cursor.execute("DELETE FROM sensor_logs WHERE id NOT IN (SELECT id FROM sensor_logs ORDER BY id DESC LIMIT 200)")
    conn.commit(); conn.close()


def get_recent_sensor_logs(limit=30) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sensor_logs ORDER BY id DESC LIMIT ?", (limit,))
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return logs


def _fmt(seconds: int) -> str:
    h = seconds // 3600; m = (seconds % 3600) // 60; s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"
