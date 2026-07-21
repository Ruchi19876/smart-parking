"""
dashboard/app.py — SmartPark Flask Application (v4)
=====================================================
New in this version:
  - User dashboard: simulate arrival (auto vehicle type), sensor feed, exit+pay
  - Payment module: UPI payment modal, transaction record
  - /api/user/simulate/arrive  — user triggers their own arrival
  - /api/user/simulate/exit    — user exits and gets bill
  - /api/payment/process       — processes UPI payment
  - /admin/payments            — admin sees all payment records
  - Admin analytics: users arrived today, revenue today
"""

import os, sys, time, json
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash)
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup  import setup_database, add_payments_table, VEHICLE_PRICING, ZONES, SECURITY_QUESTIONS
from auth.auth_manager  import (register_user, login_user, get_user_by_id, get_all_users,
                                 get_security_question_for_email, verify_security_answer,
                                 reset_password)
from core.slot_manager  import (get_all_slots, get_slot_stats, get_stats_by_zone,
                                 find_nearest_free_slot, reserve_slot, free_slot,
                                 admin_override_slot, VEHICLE_TO_ZONE)
from core.session_manager import (start_session, end_session, get_active_sessions,
                                   get_user_sessions, get_recent_sensor_logs,
                                   log_sensor_reading)
from core.billing_engine  import generate_bill, get_today_revenue, get_all_bills, get_user_bills
from core.payment_engine  import (process_upi_payment, process_card_payment,
                                  process_cash_payment, get_payment_by_bill,
                                   get_user_payments, get_all_payments,
                                   get_today_payment_revenue)
from core.booking_engine  import (get_available_slots_for_window, create_booking,
                                   get_user_bookings, get_all_bookings,
                                   get_booking_by_id, cancel_booking,
                                   is_booking_arrivable_now, fulfill_booking,
                                   expire_overdue_bookings, reserve_slot_for_booking,
                                   NO_SHOW_GRACE_MINUTES)
from analytics.analytics_engine import (get_occupancy_trend, get_peak_hours,
                                         get_revenue_trend, get_session_history,
                                         predict_peak_time, get_summary_stats,
                                         predict_next_hour_occupancy,
                                         get_zone_revenue, get_notifications,
                                         get_most_parked_vehicle)
from sensors.rfid_sim       import simulate_rfid_scan, generate_plate_number
from sensors.ir_sim         import trigger_entry_event, trigger_exit_event
from sensors.ultrasonic_sim import read_slot_sensor

app = Flask(__name__)
app.secret_key = "smart_parking_secret_key_2024_demo"

# ── Simple in-memory login rate limiter (brute-force protection) ───────────────
_LOGIN_ATTEMPTS = {}          # {email: [timestamp, timestamp, ...]}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300    # 5 minutes

def _is_rate_limited(email: str) -> bool:
    now = time.time()
    attempts = [t for t in _LOGIN_ATTEMPTS.get(email, []) if now - t < LOGIN_WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[email] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS

def _record_failed_attempt(email: str):
    _LOGIN_ATTEMPTS.setdefault(email, []).append(time.time())

def _clear_attempts(email: str):
    _LOGIN_ATTEMPTS.pop(email, None)

# ── Basic security headers on every response ────────────────────────────────────
@app.after_request
def _set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

VEHICLE_INFO = {
    "bike":   {"label": "Bike",          "icon": "🏍",  "zone": "A"},
    "scooty": {"label": "Scooty",        "icon": "🛵",  "zone": "A"},
    "auto":   {"label": "Auto-Rickshaw", "icon": "🛺",  "zone": "B"},
    "car":    {"label": "Car",           "icon": "🚗",  "zone": "C"},
    "ev":     {"label": "EV Car",        "icon": "🔋",  "zone": "D"},
    "heavy":  {"label": "Heavy Vehicle", "icon": "🚛",  "zone": "E"},
}

# ── Decorators ─────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            flash("Please login.", "warning")
            return redirect(url_for("login"))
        return f(*a, **k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("user_dashboard"))
        return f(*a, **k)
    return d

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard" if session.get("role")=="admin" else "user_dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if "user_id" in session: return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        if _is_rate_limited(email):
            flash("Too many failed login attempts. Please try again in a few minutes.", "danger")
            return render_template("login.html", vehicle_info=VEHICLE_INFO)
        result = login_user(email, request.form.get("password",""))
        if result["success"]:
            _clear_attempts(email)
            u = result["user"]
            session.update({"user_id":u["id"],"name":u["name"],"email":u["email"],
                            "role":u["role"],"vehicle_type":u.get("vehicle_type","car")})
            flash(f"Welcome back, {u['name']}!", "success")
            return redirect(url_for("admin_dashboard" if u["role"]=="admin" else "user_dashboard"))
        _record_failed_attempt(email)
        flash(result["error"], "danger")
    return render_template("login.html", vehicle_info=VEHICLE_INFO)

@app.route("/register", methods=["GET","POST"])
def register():
    if "user_id" in session: return redirect(url_for("index"))
    if request.method == "POST":
        result = register_user(
            name              = request.form.get("name","").strip(),
            email             = request.form.get("email","").strip(),
            password          = request.form.get("password",""),
            phone             = request.form.get("phone","").strip(),
            vehicle_plate     = request.form.get("vehicle_plate","").strip(),
            vehicle_type      = request.form.get("vehicle_type","car"),
            role              = "user",
            security_question = request.form.get("security_question","").strip(),
            security_answer   = request.form.get("security_answer","").strip()
        )
        if result["success"]:
            flash("Registered! Please login.", "success")
            return redirect(url_for("login"))
        flash(result["error"], "danger")
    return render_template("register.html", vehicle_info=VEHICLE_INFO,
                           security_questions=SECURITY_QUESTIONS)


# ── Forgot Password — Security Question Flow (NEW) ─────────────────────────────

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    Step 1: User enters their email. If found, we show their security question.
    This is a GET-rendered page; the actual lookup happens via POST below into
    a session-stored 'reset flow' state so the next steps know who we're resetting.
    """
    if "user_id" in session: return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        result = get_security_question_for_email(email)
        if result["success"]:
            # Store minimal state in session to drive the next step
            session["reset_email"] = email
            session["reset_user_id"] = result["user_id"]
            flash(f"Hi {result['name']}, please answer your security question.", "info")
            return redirect(url_for("forgot_password_verify"))
        flash(result["error"], "danger")

    return render_template("forgot_password.html")


@app.route("/forgot-password/verify", methods=["GET", "POST"])
def forgot_password_verify():
    """
    Step 2: Show the security question, verify the answer.
    Requires 'reset_email' to be set in session (i.e. came from step 1).
    """
    if "user_id" in session: return redirect(url_for("index"))
    email = session.get("reset_email")
    if not email:
        flash("Please start by entering your email.", "warning")
        return redirect(url_for("forgot_password"))

    q_result = get_security_question_for_email(email)
    if not q_result["success"]:
        session.pop("reset_email", None)
        flash(q_result["error"], "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        answer = request.form.get("security_answer", "")
        result = verify_security_answer(email, answer)
        if result["success"]:
            session["reset_verified"] = True
            flash("Verified! Please set your new password.", "success")
            return redirect(url_for("forgot_password_reset"))
        flash(result["error"], "danger")

    return render_template("forgot_password_verify.html",
                           email=email, security_question=q_result["security_question"])


@app.route("/forgot-password/reset", methods=["GET", "POST"])
def forgot_password_reset():
    """
    Step 3: Set the new password. Only reachable after the security answer
    was verified in step 2 (checked via session flag).
    """
    if "user_id" in session: return redirect(url_for("index"))
    email = session.get("reset_email")
    verified = session.get("reset_verified")
    if not email or not verified:
        flash("Please complete the security question step first.", "warning")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("forgot_password_reset.html", email=email)

        result = reset_password(session["reset_user_id"], new_password)
        if result["success"]:
            # Clear the reset flow state
            session.pop("reset_email", None)
            session.pop("reset_user_id", None)
            session.pop("reset_verified", None)
            flash(result["message"], "success")
            return redirect(url_for("login"))
        flash(result["error"], "danger")

    return render_template("forgot_password_reset.html", email=email)


@app.route("/logout")
def logout():
    name = session.get("name","User"); session.clear()
    flash(f"Goodbye, {name}!", "info")
    return redirect(url_for("login"))

# ── User Routes ────────────────────────────────────────────────────────────────
@app.route("/user/dashboard")
@login_required
def user_dashboard():
    # Auto-expire any overdue bookings (no-show beyond grace period)
    expire_overdue_bookings()

    user       = get_user_by_id(session["user_id"])
    slots      = get_all_slots()
    stats      = get_slot_stats()
    zone_stats = get_stats_by_zone()
    active     = [s for s in get_active_sessions() if s.get("user_id")==session["user_id"]]
    history    = get_user_sessions(session["user_id"])
    bills      = get_user_bills(session["user_id"])
    payments   = get_user_payments(session["user_id"])
    logs       = get_recent_sensor_logs(15)
    bookings   = get_user_bookings(session["user_id"])

    # Attach arrival-eligibility info to each upcoming booking
    for b in bookings:
        if b["status"] == "upcoming":
            b["arrival_check"] = is_booking_arrivable_now(b)
        else:
            b["arrival_check"] = {"can_arrive": False, "reason": ""}

    return render_template("user_dashboard.html",
                           user=user, slots=slots, stats=stats, zone_stats=zone_stats,
                           active_sessions=active, history=history, bills=bills,
                           payments=payments, sensor_logs=logs, bookings=bookings,
                           vehicle_info=VEHICLE_INFO, zones=ZONES,
                           grace_minutes=NO_SHOW_GRACE_MINUTES)

@app.route("/user/book/<int:slot_id>")
@login_required
def book_slot(slot_id):
    reserve_slot(slot_id)
    flash("Slot reserved successfully!", "success")
    return redirect(url_for("user_dashboard"))


# ── Online Advance Booking Routes (NEW) ────────────────────────────────────────

@app.route("/api/booking/search", methods=["POST"])
@login_required
def api_booking_search():
    """
    Find available slots for a vehicle type + future date/time window.
    Used by the 'Book a Slot in Advance' form on the user dashboard.
    """
    data          = request.get_json() or {}
    vehicle_type  = data.get("vehicle_type", "car")
    booking_date  = data.get("booking_date", "")
    start_time    = data.get("start_time", "")
    end_time      = data.get("end_time", "")

    if not (booking_date and start_time and end_time):
        return jsonify({"success": False, "error": "Please fill date, start time, and end time."})
    if start_time >= end_time:
        return jsonify({"success": False, "error": "End time must be after start time."})

    slots = get_available_slots_for_window(vehicle_type, booking_date, start_time, end_time)
    return jsonify({"success": True, "slots": slots, "count": len(slots)})


@app.route("/api/booking/create", methods=["POST"])
@login_required
def api_booking_create():
    """
    Confirm an advance booking for a chosen slot + time window.
    No payment required at booking time (payment happens after parking, as before).
    """
    data = request.get_json() or {}
    user = get_user_by_id(session["user_id"])

    result = create_booking(
        user_id       = session["user_id"],
        slot_id       = data.get("slot_id"),
        vehicle_type  = data.get("vehicle_type", "car"),
        vehicle_plate = data.get("vehicle_plate") or user.get("vehicle_plate", ""),
        booking_date  = data.get("booking_date", ""),
        start_time    = data.get("start_time", ""),
        end_time      = data.get("end_time", "")
    )
    if result["success"]:
        reserve_slot_for_booking(data.get("slot_id"))
    return jsonify(result)


@app.route("/api/booking/cancel", methods=["POST"])
@login_required
def api_booking_cancel():
    """User cancels their own upcoming booking and frees the slot."""
    data       = request.get_json() or {}
    booking_id = data.get("booking_id")

    booking = get_booking_by_id(booking_id)
    result  = cancel_booking(booking_id, session["user_id"])

    if result["success"] and booking:
        free_slot(booking["slot_id"])
    return jsonify(result)


@app.route("/api/booking/arrive", methods=["POST"])
@login_required
def api_booking_arrive():
    """
    User clicks 'I've Arrived' on an upcoming booking.
    Same sensor flow as offline walk-in (IR → RFID → Ultrasonic),
    but uses the slot that was already reserved for this booking.
    The booking is marked 'fulfilled' and linked to the new session.
    """
    data       = request.get_json() or {}
    booking_id = data.get("booking_id")
    booking    = get_booking_by_id(booking_id)

    if not booking:
        return jsonify({"success": False, "error": "Booking not found."})

    arrival_check = is_booking_arrivable_now(booking)
    if not arrival_check["can_arrive"]:
        return jsonify({"success": False, "error": arrival_check["reason"]})

    user          = get_user_by_id(session["user_id"])
    vehicle_type  = booking["vehicle_type"]
    vehicle_plate = booking["vehicle_plate"] or user.get("vehicle_plate") or None

    # IR gate sensor — same as offline flow
    ir_event = trigger_entry_event(booking["zone"])
    log_sensor_reading("IR_PROXIMITY_GATE", ir_event["sensor_id"], ir_event["raw_reading"])

    # RFID/ANPR scan
    if vehicle_plate:
        log_sensor_reading("RFID_ANPR", "ANPR_GATE_CAM_01",
                           f"PLATE_DETECTED: {vehicle_plate} (Pre-Booked Slot #{booking['slot_number']}) conf: 99.9%")
    else:
        rfid_event    = simulate_rfid_scan()
        vehicle_plate = rfid_event["vehicle_plate"]
        log_sensor_reading("RFID_ANPR", rfid_event["sensor_id"], rfid_event["raw_reading"])

    # Start session on the PRE-RESERVED slot (already known, no search needed)
    sess = start_session(vehicle_plate, booking["slot_id"], session["user_id"], vehicle_type)

    # Ultrasonic confirms occupancy
    ultra = read_slot_sensor(booking["slot_number"], True)
    log_sensor_reading("ULTRASONIC_HC_SR04", ultra["sensor_id"],
                       ultra["raw_reading"], booking["slot_id"], ultra)

    # Mark booking fulfilled
    fulfill_booking(booking_id, sess["session_id"])

    vinfo = VEHICLE_INFO.get(vehicle_type, {})
    return jsonify({
        "success":       True,
        "message":       f"{vinfo.get('icon','🚗')} Welcome! Your pre-booked {booking['zone_label']} Slot #{booking['slot_number']} is ready.",
        "vehicle_plate": vehicle_plate,
        "vehicle_type":  vehicle_type,
        "slot_number":   booking["slot_number"],
        "zone_label":    booking["zone_label"],
        "session_id":    sess["session_id"],
    })


@app.route("/api/booking/check_expiry", methods=["POST"])
@login_required
def api_booking_check_expiry():
    """Background poll: expire overdue bookings, return count for live UI feedback."""
    count = expire_overdue_bookings()
    return jsonify({"success": True, "expired_count": count})


# ── Admin Routes ───────────────────────────────────────────────────────────────
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    # Auto-expire overdue bookings on every dashboard load
    expire_overdue_bookings()

    slots      = get_all_slots()
    stats      = get_slot_stats()
    zone_stats = get_stats_by_zone()
    active     = get_active_sessions()
    revenue    = get_today_revenue()
    logs       = get_recent_sensor_logs(20)
    users      = get_all_users()
    # Analytics data for dashboard tabs
    summary    = get_summary_stats()
    occ_trend  = get_occupancy_trend(12)
    rev_trend  = get_revenue_trend(7)
    peak_hours = get_peak_hours()
    prediction = predict_peak_time()
    # Payment history for dashboard tab
    all_payments = get_all_payments(100)
    # Online bookings for dashboard tab
    all_bookings = get_all_bookings(100)
    return render_template("admin_dashboard.html",
                           slots=slots, stats=stats, zone_stats=zone_stats,
                           active_sessions=active, today_revenue=revenue,
                           sensor_logs=logs, users=users,
                           summary=summary, occ_trend=occ_trend,
                           rev_trend=rev_trend, peak_hours=peak_hours,
                           prediction=prediction, all_payments=all_payments,
                           all_bookings=all_bookings,
                           vehicle_info=VEHICLE_INFO, zones=ZONES)

@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    occ_trend  = get_occupancy_trend(12)
    peak_hours = get_peak_hours()
    rev_trend  = get_revenue_trend(7)
    summary    = get_summary_stats()
    prediction = predict_peak_time()
    occ_prediction = predict_next_hour_occupancy()
    history    = get_session_history(
        search_plate = request.args.get("plate",""),
        search_date  = request.args.get("date",""),
        search_zone  = request.args.get("zone",""),
        limit=50
    )
    all_payments = get_all_payments(20)
    return render_template("analytics.html",
                           occ_trend=occ_trend, peak_hours=peak_hours,
                           rev_trend=rev_trend, summary=summary,
                           prediction=prediction, occ_prediction=occ_prediction,
                           history=history,
                           all_payments=all_payments,
                           search_plate=request.args.get("plate",""),
                           search_date =request.args.get("date",""),
                           search_zone =request.args.get("zone",""),
                           vehicle_info=VEHICLE_INFO)

@app.route("/admin/payments")
@admin_required
def admin_payments():
    payments = get_all_payments(200)
    revenue  = get_today_payment_revenue()
    return render_template("admin_payments.html",
                           payments=payments, today_revenue=revenue,
                           vehicle_info=VEHICLE_INFO)

@app.route("/admin/override", methods=["POST"])
@admin_required
def admin_override():
    data = request.get_json(silent=True) or request.form
    slot_id = data.get("slot_id")
    try:
        slot_id = int(slot_id) if slot_id is not None else None
    except (TypeError, ValueError):
        slot_id = None
    status = data.get("status", "free")
    if not slot_id:
        return jsonify({"success": False, "error": "slot_id is required."})
    return jsonify(admin_override_slot(slot_id, status))

@app.route("/admin/users")
@admin_required
def admin_users():
    return render_template("admin_users.html", users=get_all_users(),
                           vehicle_info=VEHICLE_INFO)

# ── API Routes ─────────────────────────────────────────────────────────────────
@app.route("/api/slots")
@login_required
def api_slots():
    return jsonify({"slots": get_all_slots(), "stats": get_slot_stats(),
                    "zone_stats": get_stats_by_zone()})

@app.route("/api/sessions")
@login_required
def api_sessions():
    return jsonify({"sessions": get_active_sessions()})

@app.route("/api/sensor_logs")
@login_required
def api_sensor_logs():
    return jsonify({"logs": get_recent_sensor_logs(25)})

@app.route("/api/revenue")
@login_required
def api_revenue():
    return jsonify({"today_revenue": get_today_revenue()})

# ── User Simulation Routes (NEW) ───────────────────────────────────────────────
@app.route("/api/user/simulate/arrive", methods=["POST"])
@login_required
def user_simulate_arrive():
    """
    User triggers their own vehicle arrival.
    Auto-uses their registered vehicle type — no need to pick.
    Sensor detects → correct zone allocated → session starts.
    """
    user         = get_user_by_id(session["user_id"])
    data = request.get_json() or {}
    vehicle_type = data.get("vehicle_type") or user.get("vehicle_type", "car")
    if vehicle_type not in VEHICLE_INFO: vehicle_type = user.get("vehicle_type", "car")
    vehicle_plate= user.get("vehicle_plate") or None

    # IR gate sensor detects vehicle
    zone_letter = VEHICLE_TO_ZONE.get(vehicle_type, "B")
    ir_event    = trigger_entry_event(zone_letter)
    log_sensor_reading("IR_PROXIMITY_GATE", ir_event["sensor_id"], ir_event["raw_reading"])

    # RFID/ANPR reads plate (use user's registered plate if available)
    if vehicle_plate:
        rfid_reading = f"PLATE_DETECTED: {vehicle_plate} (Registered User: {user['name']}) conf: 99.9%"
        log_sensor_reading("RFID_ANPR", "ANPR_GATE_CAM_01", rfid_reading)
    else:
        rfid_event    = simulate_rfid_scan()
        vehicle_plate = rfid_event["vehicle_plate"]
        log_sensor_reading("RFID_ANPR", rfid_event["sensor_id"], rfid_event["raw_reading"])

    # Find slot in correct zone for this vehicle type
    slot = find_nearest_free_slot(vehicle_type=vehicle_type)
    if not slot:
        vinfo = VEHICLE_INFO.get(vehicle_type, {})
        return jsonify({"success": False,
                        "error": f"No free slots for {vinfo.get('label', vehicle_type)}. Zone {zone_letter} is full!"})

    # Start session linked to this user
    sess  = start_session(vehicle_plate, slot["id"], session["user_id"], vehicle_type)

    # Ultrasonic sensor confirms occupancy
    ultra = read_slot_sensor(slot["slot_number"], True)
    log_sensor_reading("ULTRASONIC_HC_SR04", ultra["sensor_id"],
                       ultra["raw_reading"], slot["id"], ultra)

    vinfo = VEHICLE_INFO.get(vehicle_type, {})
    return jsonify({
        "success":       True,
        "message":       f"{vinfo.get('icon','🚗')} {vehicle_plate} parked in {slot['zone_label']} Slot #{slot['slot_number']}",
        "vehicle_plate": vehicle_plate,
        "vehicle_type":  vehicle_type,
        "slot_number":   slot["slot_number"],
        "zone":          slot["zone"],
        "zone_label":    slot["zone_label"],
        "session_id":    sess["session_id"],
        "entry_time":    sess["entry_time"],
    })


@app.route("/api/user/simulate/exit", methods=["POST"])
@login_required
def user_simulate_exit():
    """
    User exits their active session.
    Returns bill — user then pays via UPI modal.
    """
    data       = request.get_json() or {}
    session_id = data.get("session_id")

    if not session_id:
        # Find user's active session
        active = [s for s in get_active_sessions() if s.get("user_id")==session["user_id"]]
        if not active:
            return jsonify({"success": False, "error": "No active parking session found."})
        session_id = active[0]["id"]

    sess_data = end_session(session_id)
    if not sess_data.get("success"):
        return jsonify(sess_data)

    bill = generate_bill(sess_data)

    # IR exit sensor
    ir_exit = trigger_exit_event(sess_data.get("zone", "A"))
    log_sensor_reading("IR_PROXIMITY_GATE", ir_exit["sensor_id"], ir_exit["raw_reading"])

    # Ultrasonic confirms free
    ultra = read_slot_sensor(sess_data["slot_number"], False)
    log_sensor_reading("ULTRASONIC_HC_SR04", ultra["sensor_id"],
                       ultra["raw_reading"], sess_data["slot_id"], ultra)

    return jsonify({"success": True, "bill": bill,
                    "message": f"Session ended. Please pay ₹{bill['amount']:.0f}"})


# ── Payment Route (NEW) ────────────────────────────────────────────────────────
@app.route("/api/payment/process", methods=["POST"])
@login_required
def process_payment():
    """
    Process UPI payment for a parking bill.
    Validates UPI ID, generates transaction ID, saves to DB.
    """
    data          = request.get_json() or {}
    bill_id       = data.get("bill_id")
    session_id    = data.get("session_id")
    amount        = data.get("amount", 0)
    vehicle_plate = data.get("vehicle_plate", "")
    method        = (data.get("method") or "upi").strip().lower()

    if not bill_id:
        return jsonify({"success": False, "error": "Bill ID missing."})
    if not session_id:
        return jsonify({"success": False, "error": "Session ID missing. Please re-open the bill and try again."})
    if not vehicle_plate:
        return jsonify({"success": False, "error": "Vehicle plate missing. Please re-open the bill and try again."})

    # Check not already paid
    existing = get_payment_by_bill(bill_id)
    if existing:
        return jsonify({"success": False,
                        "error": f"Already paid! Transaction: {existing['transaction_id']}"})

    if method in ("debit_card", "credit_card", "card"):
        card_type = "credit" if method == "credit_card" or data.get("card_type") == "credit" else "debit"
        result = process_card_payment(
            bill_id       = bill_id,
            session_id    = session_id,
            user_id       = session.get("user_id"),
            vehicle_plate = vehicle_plate,
            amount        = float(amount),
            card_number   = data.get("card_number", ""),
            card_holder   = data.get("card_holder", ""),
            expiry        = data.get("expiry", ""),
            cvv           = data.get("cvv", ""),
            card_type     = card_type
        )

    elif method == "cash":
        result = process_cash_payment(
            bill_id       = bill_id,
            session_id    = session_id,
            user_id       = session.get("user_id"),
            vehicle_plate = vehicle_plate,
            amount        = float(amount),
            collected_by  = data.get("collected_by", "Gate Attendant")
        )

    else:
        # Default / unchanged UPI flow
        upi_id = data.get("upi_id", "").strip()
        if not upi_id:
            return jsonify({"success": False, "error": "Please enter your UPI ID."})
        result = process_upi_payment(
            bill_id       = bill_id,
            session_id    = session_id,
            user_id       = session.get("user_id"),
            vehicle_plate = vehicle_plate,
            amount        = float(amount),
            upi_id        = upi_id
        )

    return jsonify(result)


# ── Admin Simulation Routes (unchanged) ───────────────────────────────────────
@app.route("/api/simulate/arrive", methods=["POST"])
@login_required
def simulate_arrive():
    data         = request.get_json() or {}
    vehicle_type = data.get("vehicle_type","car")
    if vehicle_type not in VEHICLE_INFO: vehicle_type = "car"

    zone_letter = VEHICLE_TO_ZONE.get(vehicle_type, "A")
    ir_event    = trigger_entry_event(zone_letter)
    log_sensor_reading("IR_PROXIMITY_GATE", ir_event["sensor_id"], ir_event["raw_reading"])

    rfid_event    = simulate_rfid_scan()
    vehicle_plate = rfid_event["vehicle_plate"]
    log_sensor_reading("RFID_ANPR", rfid_event["sensor_id"], rfid_event["raw_reading"])

    slot = find_nearest_free_slot(vehicle_type=vehicle_type)
    if not slot:
        return jsonify({"success": False,
                        "error": f"No free slots for {vehicle_type}. Zone {zone_letter} is full!"})

    sess  = start_session(vehicle_plate, slot["id"], session.get("user_id"), vehicle_type)
    ultra = read_slot_sensor(slot["slot_number"], True)
    log_sensor_reading("ULTRASONIC_HC_SR04", ultra["sensor_id"],
                       ultra["raw_reading"], slot["id"], ultra)

    vinfo = VEHICLE_INFO.get(vehicle_type, {})
    return jsonify({
        "success": True,
        "message": f"{vinfo.get('icon','🚗')} {vehicle_plate} ({vinfo.get('label',vehicle_type)}) → {slot['zone_label']} Slot {slot['slot_number']}",
        "vehicle_plate": vehicle_plate, "vehicle_type": vehicle_type,
        "slot_number": slot["slot_number"], "zone": slot["zone"],
        "zone_label": slot["zone_label"], "session_id": sess["session_id"],
        "entry_time": sess["entry_time"],
    })

@app.route("/api/simulate/exit", methods=["POST"])
@login_required
def simulate_exit():
    data       = request.get_json() or {}
    session_id = data.get("session_id")
    if not session_id:
        active = get_active_sessions()
        if not active: return jsonify({"success":False,"error":"No active sessions."})
        session_id = active[-1]["id"]

    sess_data = end_session(session_id)
    if not sess_data.get("success"): return jsonify(sess_data)

    bill    = generate_bill(sess_data)
    ir_exit = trigger_exit_event(sess_data.get("zone","A"))
    log_sensor_reading("IR_PROXIMITY_GATE", ir_exit["sensor_id"], ir_exit["raw_reading"])
    ultra   = read_slot_sensor(sess_data["slot_number"], False)
    log_sensor_reading("ULTRASONIC_HC_SR04", ultra["sensor_id"],
                       ultra["raw_reading"], sess_data["slot_id"], ultra)

    return jsonify({"success": True,
                    "message": f"Vehicle exited. Bill: ₹{bill['amount']:.0f}",
                    "bill": bill})

@app.route("/api/simulate/auto", methods=["POST"])
@admin_required
def simulate_auto():
    data    = request.get_json() or {}
    count   = min(data.get("count",3), 8)
    results = []
    vt_list = ["bike","scooty","auto","car","ev","heavy","car","bike"]
    for i in range(count):
        vt   = vt_list[i % len(vt_list)]
        slot = find_nearest_free_slot(vehicle_type=vt)
        if not slot: continue
        plate = generate_plate_number()
        sess  = start_session(plate, slot["id"], vehicle_type=vt)
        ultra = read_slot_sensor(slot["slot_number"], True)
        log_sensor_reading("ULTRASONIC_HC_SR04", ultra["sensor_id"],
                           ultra["raw_reading"], slot["id"], ultra)
        log_sensor_reading("RFID_ANPR","ANPR_GATE_CAM_01",
                           f"PLATE_DETECTED: {plate} ({vt}) conf:97.5%")
        results.append({"plate":plate,"type":vt,"slot":slot["slot_number"],"zone":slot.get("zone_label","")})
    return jsonify({"success":True,"simulated":results,"count":len(results)})

@app.errorhandler(404)
def not_found(e):
    return render_template("login.html", vehicle_info=VEHICLE_INFO), 404

if __name__ == "__main__":
    setup_database()
    add_payments_table()
    app.run(debug=True, host="0.0.0.0", port=5000)


# ── NEW FEATURES v11 ──────────────────────────────────────────────────────────

@app.route("/api/slot_map")
@login_required
def api_slot_map():
    """Returns full slot map + live counter for real-time slot grid."""
    slots = get_all_slots()
    stats = get_slot_stats()
    return jsonify({"slots": slots, "stats": stats})

@app.route("/api/revenue_today")
@admin_required
def api_revenue_today():
    """Returns today's live revenue for admin dashboard."""
    return jsonify({"today_revenue": get_today_revenue()})

@app.route("/user/history")
@login_required
def user_history():
    """Full parking history page for user."""
    user     = get_user_by_id(session["user_id"])
    history  = get_user_sessions(session["user_id"])
    bills    = get_user_bills(session["user_id"])
    payments = get_user_payments(session["user_id"])
    return render_template("user_history.html",
                           user=user, history=history,
                           bills=bills, payments=payments)


# ── NEW FEATURES v14 ──────────────────────────────────────────────────────────

@app.route("/api/notifications")
@login_required
def api_notifications():
    """Real-time admin notifications."""
    return jsonify({"notifications": get_notifications()})

@app.route("/api/zone_revenue")
@admin_required
def api_zone_revenue():
    """Zone wise revenue for chart."""
    return jsonify({"zones": get_zone_revenue()})

@app.route("/api/daily_summary")
@admin_required
def api_daily_summary():
    """Daily summary card data."""
    summary = get_summary_stats()
    most_parked = get_most_parked_vehicle()
    return jsonify({"summary": summary, "most_parked": most_parked})

@app.route("/api/predict_occupancy")
@admin_required
def api_predict_occupancy():
    """Live next-hour occupancy prediction (linear regression over last 12 hrs)."""
    return jsonify(predict_next_hour_occupancy())

@app.route("/api/estimated_bill")
@login_required
def api_estimated_bill():
    """Estimate bill for given vehicle type and duration."""
    import math
    from database.db_setup import VEHICLE_PRICING
    vtype    = request.args.get("vehicle_type", "car")
    duration = int(request.args.get("duration_minutes", 60))
    first_hour, per_hour = VEHICLE_PRICING.get(vtype, (20, 10))
    if duration <= 60:
        amount = first_hour
    else:
        extra = math.ceil((duration - 60) / 60)
        amount = first_hour + extra * per_hour
    return jsonify({"vehicle_type": vtype, "duration_minutes": duration,
                    "estimated_amount": amount, "first_hour_rate": first_hour,
                    "per_hour_rate": per_hour})
