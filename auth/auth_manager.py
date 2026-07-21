"""
Module 7: Auth Manager — MODIFIED
Added vehicle_type field to users.
Added security question + answer for offline "Forgot Password" recovery
  — no email server required, works fully offline for demo purposes.
  The answer is hashed exactly like the password (PBKDF2+SHA256), so even
  the database itself never stores the plain-text answer.
"""
import time, re
from werkzeug.security import generate_password_hash, check_password_hash
from database.db_setup import get_connection


def register_user(name, email, password, phone="", vehicle_plate="",
                  vehicle_type="car", role="user",
                  security_question="", security_answer="") -> dict:
    email = email.strip().lower()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return {"success": False, "error": "Invalid email format."}
    if len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters."}

    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email=?", (email,))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "error": "Email already registered. Please login."}

    hashed_pw = generate_password_hash(password)

    # Hash the security answer too — normalize case/whitespace before hashing
    # so "Blue" and "blue " both match correctly during recovery.
    answer_hash = None
    if security_answer:
        normalized_answer = security_answer.strip().lower()
        answer_hash = generate_password_hash(normalized_answer)

    cursor.execute("""
        INSERT INTO users (name, email, password_hash, phone, vehicle_plate, vehicle_type,
                           role, security_question, security_answer_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name.strip(), email, hashed_pw, phone.strip(),
          vehicle_plate.strip().upper(), vehicle_type, role,
          security_question, answer_hash,
          time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); new_id = cursor.lastrowid; conn.close()
    return {"success": True, "user_id": new_id, "message": "Registration successful!"}


def login_user(email, password) -> dict:
    email = email.strip().lower()
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cursor.fetchone(); conn.close()
    if not user:
        return {"success": False, "error": "Email not found. Please register first."}
    if not check_password_hash(user["password_hash"], password):
        return {"success": False, "error": "Incorrect password. Please try again."}
    return {"success": True, "user": {
        "id": user["id"], "name": user["name"], "email": user["email"],
        "phone": user["phone"], "vehicle_plate": user["vehicle_plate"],
        "vehicle_type": user["vehicle_type"], "role": user["role"],
        "created_at": user["created_at"]
    }}


def get_user_by_id(user_id) -> dict:
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, vehicle_plate, vehicle_type, role FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone(); conn.close()
    return dict(user) if user else None


def is_admin(user_id) -> bool:
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone(); conn.close()
    return row["role"] == "admin" if row else False


def get_all_users() -> list:
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.vehicle_plate, u.role, u.created_at,
               COALESCE(
                   (SELECT s.vehicle_type FROM sessions s
                    WHERE s.user_id = u.id
                    ORDER BY (s.status = 'active') DESC, s.entry_time DESC
                    LIMIT 1),
                   u.vehicle_type
               ) AS vehicle_type
        FROM users u
        ORDER BY u.created_at DESC
    """)
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


# ── Forgot Password — Security Question Flow ───────────────────────────────────

def get_security_question_for_email(email: str) -> dict:
    """
    Step 1 of password recovery: look up the user's security question by email.
    Returns the question WITHOUT revealing whether the email exists in a way
    that leaks user enumeration beyond what's necessary for the flow to work.
    """
    email = email.strip().lower()
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, name, security_question FROM users WHERE email=?", (email,))
    user = cursor.fetchone(); conn.close()

    if not user:
        return {"success": False, "error": "No account found with that email address."}
    if not user["security_question"]:
        return {"success": False, "error": "This account has no security question set. Please contact admin."}

    return {
        "success": True,
        "user_id": user["id"],
        "name": user["name"],
        "security_question": user["security_question"]
    }


def verify_security_answer(email: str, answer: str) -> dict:
    """
    Step 2 of password recovery: verify the submitted answer against the
    stored hash. Normalizes case/whitespace the same way registration did.
    """
    email = email.strip().lower()
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, security_answer_hash FROM users WHERE email=?", (email,))
    user = cursor.fetchone(); conn.close()

    if not user or not user["security_answer_hash"]:
        return {"success": False, "error": "Unable to verify. Please contact admin."}

    normalized_answer = answer.strip().lower()
    if not check_password_hash(user["security_answer_hash"], normalized_answer):
        return {"success": False, "error": "Incorrect answer. Please try again."}

    return {"success": True, "user_id": user["id"]}


def reset_password(user_id: int, new_password: str) -> dict:
    """
    Step 3 of password recovery: set a new password after the security
    answer has been verified. Uses the same hashing as registration.
    """
    if len(new_password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters."}

    hashed_pw = generate_password_hash(new_password)
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed_pw, user_id))
    conn.commit(); conn.close()

    return {"success": True, "message": "Password reset successful! Please login with your new password."}
