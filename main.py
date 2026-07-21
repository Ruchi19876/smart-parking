"""
main.py — ONE FILE TO RUN EVERYTHING
======================================
Run this file to start the entire Smart Parking System:

    python main.py

What happens when you run this:
  1. Database is created (parking.db) with all tables
  2. 36 parking slots are seeded across 4 zones
  3. Default admin account is created (credentials printed to terminal)
  4. Flask web server starts on http://localhost:5000
  5. Browser opens automatically to the Login page (local only)

Requirements: Python 3.8+  |  pip install -r requirements.txt
"""

import os
import sys
import time
import threading

# ── Add the dashboard folder to Python path so Flask can find templates/static ──
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, DASHBOARD_DIR)

# ── Import and initialize the database first ────────────────────────────────────
from database.db_setup import setup_database, add_payments_table
setup_database()
add_payments_table()

# ── Now import the Flask app ────────────────────────────────────────────────────
from dashboard.app import app

# ── Print startup banner to terminal ────────────────────────────────────────────
def print_banner():
    print("\n")
    print("╔══════════════════════════════════════════════════════╗")
    print("║      🅿  SMART PARKING MANAGEMENT SYSTEM             ║")
    print("║      Powered by IoT Sensors + Data Analytics         ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"\n  ✅  Server started: http://localhost:5000")
    print(f"  📊  Admin Dashboard: http://localhost:5000/admin/dashboard")
    print(f"  📈  Analytics:       http://localhost:5000/admin/analytics")
    print(f"\n  🔑  Admin Login:")
    print(f"       Email   : admin@parking.com")
    print(f"       Password: Admin@1234")
    print(f"\n  🚗  Simulated sensors: Ultrasonic HC-SR04, IR Gate, RFID/ANPR")
    print(f"  💾  Database: parking.db (SQLite)")
    print(f"\n  ⚠   Press CTRL+C to stop the server")
    print(f"\n{'─'*56}\n")


if __name__ == "__main__":
    print_banner()

    # Open browser automatically only when running locally (not on Render)
    IS_RENDER = os.environ.get("RENDER", False)
    if not IS_RENDER:
        try:
            import webbrowser
            def open_browser():
                time.sleep(1.5)
                webbrowser.open("http://localhost:5000")
            browser_thread = threading.Thread(target=open_browser, daemon=True)
            browser_thread.start()
        except Exception:
            pass

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )
