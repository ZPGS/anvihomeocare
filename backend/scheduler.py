import sqlite3
from datetime import datetime, timedelta

DB = "medbuddy.db"

def auto_expire_reserved():
    """
    Auto-cancel RESERVED appointments older than 2 hours
    and free their slots.
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    now = datetime.now()
    expiry_time = now - timedelta(hours=2)

    rows = c.execute("""
        SELECT id, slot_id, created_at
        FROM appointments
        WHERE status = 'RESERVED'
    """).fetchall()

    for r in rows:
        created = datetime.fromisoformat(r["created_at"])
        if created < expiry_time:
            # Cancel appointment
            c.execute("""
                UPDATE appointments
                SET status = 'CANCELLED'
                WHERE id = ?
            """, (r["id"],))

            # Free slot
            c.execute("""
                UPDATE slots
                SET is_booked = 0
                WHERE id = ?
            """, (r["slot_id"],))

            print(f"⏳ Auto-expired appointment ID {r['id']}")

    conn.commit()
    conn.close()


def send_reminders():
    """
    Mark reminder_sent = 1 for CONFIRMED appointments
    30 minutes before start time (safe Phase-1).
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    now = datetime.now()

    rows = c.execute("""
        SELECT id, patient_name, mobile,
               appointment_date, slot_time
        FROM appointments
        WHERE status = 'CONFIRMED'
          AND reminder_sent = 0
    """).fetchall()

    for r in rows:
        start_time = r["slot_time"].split("-")[0].strip()
        appt_time = datetime.strptime(
            f"{r['appointment_date']} {start_time}",
            "%Y-%m-%d %H:%M"
        )

        if appt_time - timedelta(minutes=30) <= now <= appt_time:
            c.execute("""
                UPDATE appointments
                SET reminder_sent = 1
                WHERE id = ?
            """, (r["id"],))

            print(
                f"🔔 Reminder triggered for "
                f"{r['patient_name']} ({r['mobile']})"
            )

    conn.commit()
    conn.close()