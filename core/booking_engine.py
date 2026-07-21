"""
Module: Booking Engine — Online Advance Slot Booking
=======================================================
Combines with the existing offline (walk-in) flow:
  - OFFLINE  : user clicks a vehicle card → sensors fire immediately → session starts NOW
  - ONLINE   : user picks a future date/time window → slot is reserved in advance →
               user must arrive within the window (or 10 min grace period after start)
               or the booking auto-expires and the slot frees up.

Real-world explanation (for viva):
  This mirrors how apps like ParkMobile / Sukhi Parking work — you can reserve a spot
  ahead of time so it's guaranteed when you arrive, OR just drive in and use a free
  walk-in slot. Both paths converge into the SAME session/billing system once the
  vehicle actually "arrives" (sensor confirmation), so billing logic stays identical.
"""

import time
from datetime import datetime, timedelta, timezone
from database.db_setup import get_connection
from core.slot_manager import VEHICLE_TO_ZONE

# Grace period: if user doesn't arrive within this many minutes of their
# booked START time, the booking auto-expires and slot is freed.
NO_SHOW_GRACE_MINUTES = 10

# ── Timezone fix ─────────────────────────────────────────────────────────────
# The hosting server (e.g. Render) usually runs on UTC, but users/bookings are
# in Indian Standard Time (UTC+5:30). Comparing raw server time against a
# booking time entered by an IST user causes bookings to look "too early" for
# hours after they should actually be arrivable. IST = fixed UTC+5:30 (no DST),
# so this offset is safe to hardcode.
IST = timezone(timedelta(hours=5, minutes=30))

def _now_ist() -> datetime:
    """Current date/time in IST, regardless of the server's own timezone."""
    return datetime.now(timezone.utc).astimezone(IST)

def _today_ist_str() -> str:
    return _now_ist().strftime("%Y-%m-%d")

def _now_ist_str() -> str:
    return _now_ist().strftime("%H:%M")


def get_available_slots_for_window(vehicle_type: str, booking_date: str,
                                    start_time: str, end_time: str) -> list:
    """
    Find slots of the given vehicle_type's zone that are free for the
    requested date/time window — i.e. no existing 'upcoming' booking
    overlaps with the requested window, AND slot is not currently occupied
    by a walk-in session.

    Parameters use simple strings: booking_date='2024-06-15',
    start_time='14:00', end_time='16:00'
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get all slots in the zone that serves this vehicle type.
    # (Slots are seeded with only the zone's primary vehicle_type, e.g. Zone A
    # slots are all stored as "bike" even though the zone also serves "scooty".
    # Matching by zone -- the same way the offline "Park Now" flow does via
    # VEHICLE_TO_ZONE -- keeps this in sync instead of relying on an exact
    # vehicle_type match that scooty/other secondary types would never hit.)
    zone = VEHICLE_TO_ZONE.get(vehicle_type)
    if zone:
        cursor.execute("""
            SELECT id, zone, zone_label, slot_number, vehicle_type, status
            FROM slots WHERE zone = ?
            ORDER BY slot_number
        """, (zone,))
    else:
        cursor.execute("""
            SELECT id, zone, zone_label, slot_number, vehicle_type, status
            FROM slots WHERE vehicle_type = ?
            ORDER BY slot_number
        """, (vehicle_type,))
    all_slots = [dict(r) for r in cursor.fetchall()]

    # Get conflicting bookings (same date, overlapping time, status='upcoming')
    cursor.execute("""
        SELECT slot_id FROM bookings
        WHERE booking_date = ? AND status = 'upcoming'
        AND NOT (end_time <= ? OR start_time >= ?)
    """, (booking_date, start_time, end_time))
    booked_slot_ids = {row["slot_id"] for row in cursor.fetchall()}

    conn.close()

    # Available = not currently occupied AND not booked in that window
    available = [
        s for s in all_slots
        if s["id"] not in booked_slot_ids
    ]
    return available


def create_booking(user_id: int, slot_id: int, vehicle_type: str, vehicle_plate: str,
                   booking_date: str, start_time: str, end_time: str) -> dict:
    """
    Create a new advance booking for a free slot/time window.
    Validates the slot is still available before confirming (race-condition safe).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Re-check availability (avoid double-booking)
    cursor.execute("""
        SELECT id FROM bookings
        WHERE slot_id = ? AND booking_date = ? AND status = 'upcoming'
        AND NOT (end_time <= ? OR start_time >= ?)
    """, (slot_id, booking_date, start_time, end_time))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "error": "This slot was just booked by someone else for that time. Please pick another."}

    cursor.execute("SELECT zone, zone_label, vehicle_type FROM slots WHERE id = ?", (slot_id,))
    slot = cursor.fetchone()
    if not slot:
        conn.close()
        return {"success": False, "error": "Slot not found."}
    if slot["vehicle_type"] != vehicle_type:
        conn.close()
        return {"success": False, "error": "This slot is reserved for a different vehicle type."}

    now = _now_ist().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO bookings (user_id, slot_id, zone, zone_label, vehicle_type,
                              vehicle_plate, booking_date, start_time, end_time,
                              status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'upcoming', ?)
    """, (user_id, slot_id, slot["zone"], slot["zone_label"], vehicle_type,
          vehicle_plate.upper() if vehicle_plate else None,
          booking_date, start_time, end_time, now))

    booking_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "success": True,
        "booking_id": booking_id,
        "zone_label": slot["zone_label"],
        "message": f"Slot booked for {booking_date} {start_time}–{end_time}"
    }


def get_user_bookings(user_id: int) -> list:
    """Get all bookings for a user (upcoming, fulfilled, expired, cancelled)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, s.slot_number
        FROM bookings b
        JOIN slots s ON s.id = b.slot_id
        WHERE b.user_id = ?
        ORDER BY b.booking_date DESC, b.start_time DESC
    """, (user_id,))
    bookings = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return bookings


def get_all_bookings(limit: int = 100) -> list:
    """Admin: get all bookings across all users."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, s.slot_number, u.name as user_name, u.email as user_email
        FROM bookings b
        JOIN slots s ON s.id = b.slot_id
        JOIN users u ON u.id = b.user_id
        ORDER BY b.created_at DESC LIMIT ?
    """, (limit,))
    bookings = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return bookings


def get_booking_by_id(booking_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, s.slot_number FROM bookings b
        JOIN slots s ON s.id = b.slot_id WHERE b.id = ?
    """, (booking_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def cancel_booking(booking_id: int, user_id: int) -> dict:
    """User cancels their own upcoming booking before arrival."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bookings SET status = 'cancelled'
        WHERE id = ? AND user_id = ? AND status = 'upcoming'
    """, (booking_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    if affected:
        return {"success": True, "message": "Booking cancelled successfully."}
    return {"success": False, "error": "Booking not found or already processed."}


def is_booking_arrivable_now(booking: dict) -> dict:
    """
    Check if a booking's "I've Arrived" button should be active right now.
    Allowed window: from start_time up to (start_time + grace period),
    but only on the booking_date.
    """
    today = _today_ist_str()
    now_time = _now_ist_str()

    if booking["booking_date"] != today:
        return {"can_arrive": False, "reason": f"Booking is for {booking['booking_date']}, not today."}

    start_dt = datetime.strptime(booking["start_time"], "%H:%M")
    grace_end_dt = start_dt + timedelta(minutes=NO_SHOW_GRACE_MINUTES)
    now_dt = datetime.strptime(now_time, "%H:%M")

    # Allow arriving slightly early (10 min before start) up to grace period after
    early_allowed_dt = start_dt - timedelta(minutes=10)

    if now_dt < early_allowed_dt:
        return {"can_arrive": False, "reason": f"Too early. Booking starts at {booking['start_time']}."}
    if now_dt > grace_end_dt:
        return {"can_arrive": False, "reason": "Grace period expired. Booking will auto-expire."}
    return {"can_arrive": True, "reason": "Within arrival window."}


def fulfill_booking(booking_id: int, session_id: int) -> dict:
    """Mark a booking as fulfilled once the user's session actually starts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bookings SET status = 'fulfilled', session_id = ?
        WHERE id = ?
    """, (session_id, booking_id))
    conn.commit()
    conn.close()
    return {"success": True}


def expire_overdue_bookings() -> int:
    """
    Background check: find all 'upcoming' bookings whose grace period has
    passed without the user arriving, mark them 'expired', and free their slots.

    Returns the number of bookings expired (useful for logging/demo visibility).
    """
    conn = get_connection()
    cursor = conn.cursor()

    today = _today_ist_str()
    now_time = _now_ist_str()

    cursor.execute("""
        SELECT id, slot_id, start_time FROM bookings
        WHERE status = 'upcoming' AND booking_date <= ?
    """, (today,))
    candidates = cursor.fetchall()

    expired_count = 0
    for row in candidates:
        booking_date_passed = True  # already filtered booking_date <= today
        start_dt = datetime.strptime(row["start_time"], "%H:%M")
        grace_end_dt = start_dt + timedelta(minutes=NO_SHOW_GRACE_MINUTES)
        now_dt = datetime.strptime(now_time, "%H:%M")

        # If booking_date is in the past, it's definitely expired.
        # If it's today, only expire once grace period has passed.
        cursor.execute("SELECT booking_date FROM bookings WHERE id = ?", (row["id"],))
        bdate = cursor.fetchone()["booking_date"]

        should_expire = False
        if bdate < today:
            should_expire = True
        elif bdate == today and now_dt > grace_end_dt:
            should_expire = True

        if should_expire:
            cursor.execute("UPDATE bookings SET status = 'expired' WHERE id = ?", (row["id"],))
            # Free the slot only if it's still 'reserved' (not separately occupied)
            cursor.execute("""
                UPDATE slots SET status = 'free'
                WHERE id = ? AND status = 'reserved'
            """, (row["slot_id"],))
            expired_count += 1

    conn.commit()
    conn.close()
    return expired_count


def reserve_slot_for_booking(slot_id: int):
    """Mark a slot as 'reserved' when an online booking is confirmed."""
    conn = get_connection()
    conn.execute("UPDATE slots SET status = 'reserved' WHERE id = ?", (slot_id,))
    conn.commit()
    conn.close()
