import sqlite3
from datetime import datetime

DB = "medbuddy.db"

conn = sqlite3.connect(DB)
c = conn.cursor()

# ---------------- SLOTS ----------------
c.execute("""
CREATE TABLE slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_booked INTEGER DEFAULT 0
)
""")

# ---------------- APPOINTMENTS ----------------
c.execute("""
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    confirmation_code TEXT UNIQUE,

    patient_name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    address TEXT NOT NULL,

    slot_id INTEGER NOT NULL,
    appointment_date TEXT NOT NULL,
    slot_time TEXT NOT NULL,

    amount INTEGER NOT NULL DEFAULT 500,
    payment_ref TEXT,

    status TEXT NOT NULL DEFAULT 'RESERVED',
    meeting_link TEXT,
    admin_remarks TEXT,

    reminder_sent INTEGER DEFAULT 0,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
""")

# ---------------- ADMIN SETTINGS ----------------
c.execute("""
CREATE TABLE admin_settings (
    id INTEGER PRIMARY KEY,
    doctor_whatsapp TEXT,
    upi_link TEXT,
    default_amount INTEGER,

    reservation_message TEXT,
    confirmation_message TEXT,
    reminder_message TEXT
)
""")

# ---------------- DEFAULT SETTINGS ----------------
reservation_message = (
    "Hello {{name}},\n\n"
    "Your appointment has been RESERVED.\n\n"
    "📅 Date: {{date}}\n"
    "⏰ Time: {{time}}\n\n"
    "💰 Consultation Fee: ₹{{amount}}\n\n"
    "Please complete the payment using the UPI link below and share the payment screenshot or transaction ID.\n\n"
    "🔗 Pay via UPI:\n"
    "upi://pay?pa={{upi}}&am={{amount}}&cu=INR\n\n"
    "UPI ID (manual):\n"
    "{{upi}}\n\n"
    "Thank you,\n"
    "Dr. Shweta Chandrakant Zungare"
)


confirmation_message = (
    "Hello {{name}},\n\n"
    "Your appointment is CONFIRMED.\n\n"
    "Confirmation No: {{code}}\n"
    "📅 Date: {{date}}\n"
    "⏰ Time: {{time}}\n\n"
    "Meeting Link:\n"
    "{{meeting_link}}\n\n"
    "Download Receipt:\n"
    "{{receipt_link}}\n\n"
    "Thank you,\n"
    "Dr. Shweta Chandrakant Zungare"
)

reminder_message = (
    "Hello {{name}},\n\n"
    "This is a reminder for your consultation today.\n\n"
    "⏰ Time: {{time}}\n\n"
    "Please join on time.\n\n"
    "Dr. Shweta Chandrakant Zungare"
)

c.execute("""
INSERT INTO admin_settings (
    id,
    doctor_whatsapp,
    upi_link,
    default_amount,
    reservation_message,
    confirmation_message,
    reminder_message
) VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    1,
    "919588460141",
    "9588460141@ybl",
    500,
    reservation_message,
    confirmation_message,
    reminder_message
))

conn.commit()
conn.close()

print("✅ Fresh database initialized successfully")