"""
wsgi.py — Entry point for Render / Gunicorn
Run locally : gunicorn wsgi:app
Render uses : gunicorn wsgi:app
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "dashboard"))

from database.db_setup import setup_database, add_payments_table
setup_database()
add_payments_table()

from dashboard.app import app

if __name__ == "__main__":
    app.run()
