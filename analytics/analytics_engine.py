"""
Analytics Engine — updated with users_arrived_today count
"""
import time
from database.db_setup import get_connection


def get_occupancy_trend(hours=12):
    conn = get_connection(); c = conn.cursor()
    labels, data = [], []
    now = time.time()
    total_slots = _total_slots(c)
    for i in range(hours-1, -1, -1):
        end   = now - i*3600; start = end - 3600
        label = time.strftime("%H:00", time.localtime(end))
        s_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start))
        e_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end))
        c.execute("""SELECT COUNT(*) FROM sessions
                     WHERE entry_time<=? AND (exit_time>=? OR exit_time IS NULL OR status='active')""",
                  (e_str, s_str))
        count = c.fetchone()[0]
        labels.append(label)
        data.append(min(round(count/total_slots*100, 1) if total_slots else 0, 100))
    conn.close()
    return {"labels": labels, "data": data}


def get_peak_hours():
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT strftime('%H',entry_time) as hour, COUNT(*) as count
                 FROM sessions GROUP BY hour ORDER BY hour""")
    rows = c.fetchall(); conn.close()
    hour_counts = {str(h).zfill(2): 0 for h in range(24)}
    for r in rows:
        hour_counts[r["hour"]] = r["count"]
    return {"labels": [f"{h}:00" for h in range(24)],
            "data":   [hour_counts[str(h).zfill(2)] for h in range(24)]}


def get_revenue_trend(days=7):
    conn = get_connection(); c = conn.cursor()
    labels, data = [], []
    for i in range(days-1, -1, -1):
        ts  = time.time() - i*86400
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        lbl = time.strftime("%a %d %b", time.localtime(ts))
        c.execute("SELECT COALESCE(SUM(amount),0) FROM bills WHERE generated_at LIKE ?", (f"{day}%",))
        labels.append(lbl); data.append(float(c.fetchone()[0]))
    conn.close()
    return {"labels": labels, "data": data}


def get_session_history(search_plate=None, search_date=None, search_zone=None, limit=50):
    conn = get_connection(); c = conn.cursor()
    q = """SELECT s.id, s.vehicle_plate, s.vehicle_type, s.entry_time, s.exit_time, s.status,
                  sl.slot_number, sl.zone, sl.zone_label, b.amount, b.duration_minutes,
                  u.name as user_name
           FROM sessions s JOIN slots sl ON sl.id=s.slot_id
           LEFT JOIN bills b ON b.session_id=s.id
           LEFT JOIN users u ON u.id=s.user_id
           WHERE 1=1"""
    params = []
    if search_plate: q += " AND s.vehicle_plate LIKE ?"; params.append(f"%{search_plate.upper()}%")
    if search_date:  q += " AND s.entry_time LIKE ?";    params.append(f"{search_date}%")
    if search_zone:  q += " AND sl.zone = ?";             params.append(search_zone.upper())
    q += " ORDER BY s.entry_time DESC LIMIT ?"; params.append(limit)
    c.execute(q, params)
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return rows


def predict_peak_time():
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT strftime('%H',entry_time) as hour, COUNT(*) as count
                 FROM sessions WHERE entry_time >= date('now','-7 days')
                 GROUP BY hour ORDER BY count DESC LIMIT 1""")
    row = c.fetchone(); conn.close()
    if row:
        h = int(row["hour"])
        return {"predicted_hour": f"{h:02d}:00",
                "predicted_label": f"{h%12 or 12}:00 {'AM' if h<12 else 'PM'}",
                "entry_count": row["count"],
                "method": "Most frequent entry hour — last 7 days (moving average heuristic)"}
    return {"predicted_hour":"N/A","predicted_label":"Not enough data yet",
            "entry_count":0,"method":"Requires more session data"}


def get_summary_stats():
    """Extended summary — now includes users_arrived_today."""
    conn = get_connection(); c = conn.cursor()
    today = time.strftime("%Y-%m-%d")

    c.execute("SELECT COUNT(*) FROM sessions"); ts = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM bills"); tr = float(c.fetchone()[0])
    c.execute("SELECT COALESCE(AVG(duration_minutes),0) FROM bills"); ad = float(c.fetchone()[0])
    c.execute("""SELECT sl.zone_label, COUNT(*) as cnt FROM sessions s
                 JOIN slots sl ON sl.id=s.slot_id
                 GROUP BY sl.zone ORDER BY cnt DESC LIMIT 1""")
    bz = c.fetchone()

    # NEW: users arrived today (sessions started today)
    c.execute("SELECT COUNT(*) FROM sessions WHERE entry_time LIKE ?", (f"{today}%",))
    arrived_today = c.fetchone()[0]

    # NEW: unique users today
    c.execute("""SELECT COUNT(DISTINCT user_id) FROM sessions
                 WHERE entry_time LIKE ? AND user_id IS NOT NULL""", (f"{today}%",))
    unique_users_today = c.fetchone()[0]

    # NEW: revenue today
    c.execute("SELECT COALESCE(SUM(amount),0) FROM bills WHERE generated_at LIKE ?", (f"{today}%",))
    revenue_today = float(c.fetchone()[0])

    conn.close()
    return {
        "total_sessions":     ts,
        "total_revenue":      round(tr, 2),
        "avg_duration_min":   round(ad, 1),
        "busiest_zone":       bz["zone_label"] if bz else "N/A",
        "arrived_today":      arrived_today,
        "unique_users_today": unique_users_today,
        "revenue_today":      round(revenue_today, 2),
    }


def _total_slots(cursor):
    cursor.execute("SELECT COUNT(*) FROM slots")
    return cursor.fetchone()[0] or 1


def get_zone_revenue():
    """Zone wise revenue breakdown for chart."""
    conn = get_connection(); c = conn.cursor()
    c.execute("""
        SELECT sl.zone, sl.zone_label, COALESCE(SUM(b.amount),0) as revenue, COUNT(b.id) as sessions
        FROM slots sl
        LEFT JOIN sessions s ON s.slot_id = sl.id
        LEFT JOIN bills b ON b.session_id = s.id
        GROUP BY sl.zone, sl.zone_label
        ORDER BY sl.zone
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_notifications():
    """Generate real-time admin notifications based on current slot status."""
    conn = get_connection(); c = conn.cursor()
    notifications = []

    # Check each zone occupancy
    c.execute("""
        SELECT zone, zone_label,
               COUNT(*) as total,
               SUM(CASE WHEN status='occupied' THEN 1 ELSE 0 END) as occupied,
               SUM(CASE WHEN status='free' THEN 1 ELSE 0 END) as free
        FROM slots GROUP BY zone, zone_label ORDER BY zone
    """)
    zones = c.fetchall()
    for z in zones:
        pct = (z['occupied'] / z['total'] * 100) if z['total'] > 0 else 0
        if z['free'] == 0:
            notifications.append({"type": "danger", "icon": "🔴", "msg": f"{z['zone_label']} is FULL! No slots available."})
        elif pct >= 80:
            notifications.append({"type": "warning", "icon": "🟡", "msg": f"{z['zone_label']} is almost full! Only {z['free']} slot(s) left."})
        elif z['free'] == z['total']:
            notifications.append({"type": "success", "icon": "🟢", "msg": f"{z['zone_label']} is completely free. {z['free']} slots available."})

    # Check active sessions > 3 hours
    c.execute("""
        SELECT COUNT(*) as cnt FROM sessions
        WHERE status='active'
        AND (strftime('%s','now') - strftime('%s', entry_time)) > 10800
    """)
    long_sessions = c.fetchone()['cnt']
    if long_sessions > 0:
        notifications.append({"type": "info", "icon": "⏰", "msg": f"{long_sessions} vehicle(s) parked for more than 3 hours."})

    # Today's revenue milestone
    today = time.strftime("%Y-%m-%d")
    c.execute("SELECT COALESCE(SUM(amount),0) FROM bills WHERE generated_at LIKE ?", (f"{today}%",))
    rev = float(c.fetchone()[0])
    if rev >= 1000:
        notifications.append({"type": "success", "icon": "💰", "msg": f"Today's revenue crossed ₹{rev:.0f}! Great day!"})

    conn.close()
    if not notifications:
        notifications.append({"type": "info", "icon": "✅", "msg": "All zones operating normally. No issues detected."})
    return notifications


def predict_next_hour_occupancy():
    """
    Predicts next hour's occupancy % using simple linear regression
    (least-squares fit) over the last 12 hours of occupancy trend data.
    This is a real statistical prediction (not just a historical readout):
    it fits a line y = mx + c over recent occupancy points and extrapolates
    one step forward, so it reflects the current upward/downward trend.
    """
    trend = get_occupancy_trend(hours=12)
    y = trend["data"]
    n = len(y)
    if n < 3:
        return {"predicted_occupancy": None, "trend": "insufficient_data",
                "method": "Linear regression (needs at least 3 hourly data points)"}

    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    numerator   = sum((x[i]-x_mean)*(y[i]-y_mean) for i in range(n))
    denominator = sum((x[i]-x_mean)**2 for i in range(n))
    slope = numerator / denominator if denominator else 0
    intercept = y_mean - slope * x_mean

    next_x = n  # one hour ahead of the last data point
    predicted = slope * next_x + intercept
    predicted = max(0, min(100, round(predicted, 1)))  # clamp to 0-100%

    if slope > 0.5:
        trend_label = "rising"
    elif slope < -0.5:
        trend_label = "falling"
    else:
        trend_label = "stable"

    return {
        "predicted_occupancy": predicted,
        "trend": trend_label,
        "slope_per_hour": round(slope, 2),
        "based_on_hours": n,
        "method": "Linear regression (least-squares) over last 12 hourly occupancy readings"
    }


def get_most_parked_vehicle():
    """Returns most parked vehicle type today."""
    conn = get_connection(); c = conn.cursor()
    today = time.strftime("%Y-%m-%d")
    c.execute("""
        SELECT vehicle_type, COUNT(*) as cnt
        FROM sessions WHERE entry_time LIKE ?
        GROUP BY vehicle_type ORDER BY cnt DESC LIMIT 1
    """, (f"{today}%",))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {"vehicle_type": "N/A", "cnt": 0}
