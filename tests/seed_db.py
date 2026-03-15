import os
import sys
import sqlite3

# Adjust path to find dashboard
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set working directory to dashboard to ensure db is created there
os.chdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard"))

from dashboard.app import app, init_db, get_db

with app.app_context():
    init_db()
    db = get_db()
    db.execute('''
        INSERT INTO leads (rubro_slug, empresa, ciudad, url, email, telefono, status)
        VALUES ('portones_automaticos', 'Portones Pepito', 'Buenos Aires', 'http://www.example.com', 'pepito@test.com', '12345678', 'nuevo')
    ''')
    db.commit()
    print("DB initialized and dummy lead inserted.")
