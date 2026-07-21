"""
Module: Payment Engine
======================
Handles UPI payment simulation for parking bills.

Real-world explanation (for viva):
  In production, this module would call Razorpay/PayU/PayTM Payment Gateway API.
  The gateway verifies the UPI ID, debits the user's account, and returns
  a transaction ID confirming payment.

  For this demo: we simulate the gateway response — generate a realistic
  transaction ID (format: TXN + timestamp + random digits, same format
  used by real UPI systems), save to DB, and return success.
  This is standard practice for academic projects.
"""

import time, random, string, re
from database.db_setup import get_connection


def generate_transaction_id() -> str:
    """
    Generate a realistic UPI transaction ID.
    Real UPI format: TXN + 12 alphanumeric characters
    Example: TXN4F8A2B9C1D3E5
    """
    chars = string.ascii_uppercase + string.digits
    rand_part = ''.join(random.choices(chars, k=14))
    return f"TXN{rand_part}"


def validate_upi_id(upi_id: str) -> dict:
    """
    Simulate UPI ID validation.
    Real system: calls NPCI API to verify UPI ID exists.
    Simulation: checks format (anything@bankname) and returns valid.

    Valid formats: name@okaxis, name@ybl, name@paytm, name@upi etc.
    """
    upi_id = upi_id.strip()
    if not upi_id or '@' not in upi_id:
        return {"valid": False, "error": "Invalid UPI ID. Format: yourname@bankname"}
    parts = upi_id.split('@')
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return {"valid": False, "error": "Invalid UPI ID format."}
    # Simulate processing delay (real UPI takes 1-3 seconds)
    return {"valid": True, "upi_id": upi_id,
            "bank": parts[1].upper(), "name": parts[0].title()}


def process_upi_payment(bill_id: int, session_id: int, user_id: int,
                        vehicle_plate: str, amount: float, upi_id: str) -> dict:
    """
    Process a UPI payment for a parking bill.

    Steps (simulated):
      1. Validate UPI ID format
      2. Simulate gateway processing (1-2 second delay in real systems)
      3. Generate transaction ID
      4. Save payment record to DB
      5. Return success response with receipt

    Returns dict with transaction_id, status, receipt details.
    """
    # Step 1: Validate UPI ID
    validation = validate_upi_id(upi_id)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    # Step 2: Generate transaction ID (simulated gateway response)
    txn_id  = generate_transaction_id()
    paid_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # Step 3: Save to payments table
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments
          (bill_id, session_id, user_id, vehicle_plate, amount,
           payment_method, upi_id, transaction_id, status, paid_at)
        VALUES (?, ?, ?, ?, ?, 'upi', ?, ?, 'success', ?)
    """, (bill_id, session_id, user_id, vehicle_plate.upper(),
          amount, upi_id.strip(), txn_id, paid_at))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "success":        True,
        "payment_id":     payment_id,
        "transaction_id": txn_id,
        "upi_id":         upi_id,
        "amount":         amount,
        "amount_display": f"₹{amount:.0f}",
        "vehicle_plate":  vehicle_plate.upper(),
        "paid_at":        paid_at,
        "status":         "SUCCESS",
        "gateway":        "UPI / NPCI (Simulated)",
        "message":        f"Payment of ₹{amount:.0f} successful!"
    }


def luhn_checksum(card_number: str) -> bool:
    """
    Standard Luhn algorithm — same check real card networks (Visa/
    Mastercard/RuPay) use to catch typos in a card number.
    """
    digits = [int(d) for d in card_number]
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def mask_card_number(card_number: str) -> str:
    """Return a display-safe masked card number, e.g. '**** **** **** 1234'."""
    digits = ''.join(ch for ch in card_number if ch.isdigit())
    last4 = digits[-4:] if len(digits) >= 4 else digits
    return f"**** **** **** {last4}"


def validate_card(card_number: str, card_holder: str, expiry: str, cvv: str) -> dict:
    """
    Simulate card validation (debit or credit — the checks are identical).
    Real system: this data would go straight to a PCI-DSS compliant
    gateway (Razorpay/PayU/Stripe) over TLS; the app itself never touches
    it. Simulation: format + Luhn + expiry checks only, nothing is sent
    anywhere.
    """
    card_number = (card_number or "").replace(" ", "").replace("-", "")
    card_holder = (card_holder or "").strip()
    expiry      = (expiry or "").strip()
    cvv         = (cvv or "").strip()

    if not card_holder:
        return {"valid": False, "error": "Please enter the name on the card."}
    if not card_number.isdigit() or not (13 <= len(card_number) <= 19):
        return {"valid": False, "error": "Card number must be 13-19 digits."}
    if not luhn_checksum(card_number):
        return {"valid": False, "error": "Invalid card number."}
    if not re.match(r'^(0[1-9]|1[0-2])\/\d{2}$', expiry):
        return {"valid": False, "error": "Expiry must be in MM/YY format."}
    exp_month, exp_year = expiry.split('/')
    exp_year = 2000 + int(exp_year)
    now = time.localtime()
    if (exp_year, int(exp_month)) < (now.tm_year, now.tm_mon):
        return {"valid": False, "error": "Card has expired."}
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return {"valid": False, "error": "CVV must be 3-4 digits."}

    return {"valid": True, "card_holder": card_holder,
            "masked_number": mask_card_number(card_number)}


def process_card_payment(bill_id: int, session_id: int, user_id: int,
                         vehicle_plate: str, amount: float, card_number: str,
                         card_holder: str, expiry: str, cvv: str,
                         card_type: str = "debit") -> dict:
    """
    Process a Debit/Credit card payment for a parking bill.

    card_type: 'debit' or 'credit' — stored as payment_method
               'debit_card' / 'credit_card' respectively.

    Steps (simulated, mirrors process_upi_payment):
      1. Validate card details (format, Luhn, expiry, CVV)
      2. Simulate gateway processing
      3. Generate transaction ID
      4. Save payment record to DB (masked card number only — the raw
         card number and CVV are NEVER stored, exactly like a real
         PCI-DSS compliant integration)
      5. Return success response with receipt
    """
    card_type = "credit" if str(card_type).lower() == "credit" else "debit"

    validation = validate_card(card_number, card_holder, expiry, cvv)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    txn_id  = generate_transaction_id()
    paid_at = time.strftime("%Y-%m-%d %H:%M:%S")
    method  = f"{card_type}_card"
    masked  = validation["masked_number"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments
          (bill_id, session_id, user_id, vehicle_plate, amount,
           payment_method, payment_ref, transaction_id, status, paid_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'success', ?)
    """, (bill_id, session_id, user_id, vehicle_plate.upper(),
          amount, method, masked, txn_id, paid_at))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "success":        True,
        "payment_id":     payment_id,
        "transaction_id": txn_id,
        "card_holder":    validation["card_holder"],
        "masked_number":  masked,
        "card_type":      card_type,
        "amount":         amount,
        "amount_display": f"₹{amount:.0f}",
        "vehicle_plate":  vehicle_plate.upper(),
        "paid_at":        paid_at,
        "status":         "SUCCESS",
        "gateway":        f"{card_type.title()} Card / NPCI-VISA-Mastercard (Simulated)",
        "message":        f"Payment of ₹{amount:.0f} successful!"
    }


def process_cash_payment(bill_id: int, session_id: int, user_id: int,
                         vehicle_plate: str, amount: float,
                         collected_by: str = "Gate Attendant") -> dict:
    """
    Record a Cash payment for a parking bill.

    Real system: an on-site attendant/kiosk operator collects the cash
    and marks the bill paid; no payment gateway is involved.
    Simulation: we just generate a receipt/transaction ID and save the
    record straight away as 'success', same shape as UPI/Card so the
    rest of the app (receipts, admin reports, revenue totals) treats it
    identically.
    """
    collected_by = (collected_by or "Gate Attendant").strip() or "Gate Attendant"

    txn_id  = generate_transaction_id()
    paid_at = time.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments
          (bill_id, session_id, user_id, vehicle_plate, amount,
           payment_method, payment_ref, transaction_id, status, paid_at)
        VALUES (?, ?, ?, ?, ?, 'cash', ?, ?, 'success', ?)
    """, (bill_id, session_id, user_id, vehicle_plate.upper(),
          amount, f"Collected by: {collected_by}", txn_id, paid_at))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "success":        True,
        "payment_id":     payment_id,
        "transaction_id": txn_id,
        "collected_by":   collected_by,
        "amount":         amount,
        "amount_display": f"₹{amount:.0f}",
        "vehicle_plate":  vehicle_plate.upper(),
        "paid_at":        paid_at,
        "status":         "SUCCESS",
        "gateway":        "Cash (Manual)",
        "message":        f"Cash payment of ₹{amount:.0f} recorded successfully!"
    }


def get_payment_by_bill(bill_id: int) -> dict:
    """Check if a bill has already been paid."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE bill_id=?", (bill_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_payments(user_id: int) -> list:
    """Get all payments made by a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM payments WHERE user_id=?
        ORDER BY paid_at DESC
    """, (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_all_payments(limit=100) -> list:
    """Admin: get all payment records."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, u.name as user_name, u.email as user_email
        FROM payments p
        LEFT JOIN users u ON u.id = p.user_id
        ORDER BY p.paid_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_today_payment_revenue() -> float:
    """Sum of all successful payments today."""
    today = time.strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM payments
        WHERE paid_at LIKE ? AND status='success'
    """, (f"{today}%",))
    rev = float(cursor.fetchone()[0])
    conn.close()
    return rev
