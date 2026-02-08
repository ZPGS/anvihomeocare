from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import sqlite3, io, os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import jwt
from functools import wraps

from scheduler import auto_expire_reserved, send_reminders

# =================================================
# APP SETUP
# =================================================
app = Flask(__name__)

from flask_cors import CORS

CORS(
    app,
    supports_credentials=False,
    origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://anvihomeocare.netlify.app",
        "https://www.anvihomeocare.netlify.app"
    ]
)



# =================================================
# JWT CONFIG
# =================================================
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret")
JWT_ALGO = "HS256"
JWT_EXP_MINUTES = 60

# =================================================
# DB CONFIG
# =================================================
DB = "medbuddy.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# =================================================
# JWT HELPERS
# =================================================
def create_token():
    payload = {
        "admin": True,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

    # PyJWT < 2 returned bytes, >=2 returns str
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return token


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401

        token = auth.split(" ", 1)[1]

        try:
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return fn(*args, **kwargs)
    return wrapper

# =================================================
# SCHEDULER (Render-safe)
# =================================================
if os.environ.get("RUN_SCHEDULER") == "1":
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_expire_reserved, "interval", minutes=10)
    scheduler.add_job(send_reminders, "interval", minutes=5)
    scheduler.start()

# =================================================
# HEALTH
# =================================================
@app.route("/")
def health():
    return jsonify({"status": "ok"})

# =================================================
# PATIENT APIs
# =================================================
@app.route("/api/slots")
def available_slots():
    conn = db()
    rows = conn.execute(
        "SELECT * FROM slots WHERE is_booked=0 ORDER BY slot_date,start_time"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/book", methods=["POST"])
def book():
    f = request.json
    conn = db()

    slot = conn.execute(
        "SELECT * FROM slots WHERE id=? AND is_booked=0",
        (f["slot_id"],)
    ).fetchone()

    if not slot:
        conn.close()
        return jsonify({"error": "Slot not available"}), 400

    count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] + 1
    code = f"MB-{datetime.now().strftime('%Y%m%d')}-{str(count).zfill(4)}"
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO appointments (
            confirmation_code, patient_name, mobile, address,
            slot_id, appointment_date, slot_time,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?, ?)
    """, (
        code,
        f["patient_name"],
        f["mobile"],
        f["address"],
        slot["id"],
        slot["slot_date"],
        f'{slot["start_time"]}-{slot["end_time"]}',
        now,
        now
    ))

    conn.execute(
        "UPDATE slots SET is_booked=1 WHERE id=?",
        (slot["id"],)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "confirmation_code": code
    })


@app.route("/api/status", methods=["POST"])
def status():
    conn = db()
    appt = conn.execute(
        "SELECT * FROM appointments WHERE confirmation_code=?",
        (request.json["confirmation_code"],)
    ).fetchone()
    conn.close()

    if not appt:
        return jsonify({"error": "Not found"}), 404

    return jsonify(dict(appt))


@app.route("/api/history", methods=["POST"])
def history():
    conn = db()
    rows = conn.execute(
        "SELECT * FROM appointments WHERE mobile=? ORDER BY created_at DESC",
        (request.json["mobile"],)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/cancel/<code>", methods=["POST"])
def cancel(code):
    conn = db()
    appt = conn.execute(
        "SELECT slot_id,status FROM appointments WHERE confirmation_code=?",
        (code,)
    ).fetchone()

    if appt and appt["status"] == "RESERVED":
        conn.execute(
            "UPDATE appointments SET status='CANCELLED' WHERE confirmation_code=?",
            (code,)
        )
        conn.execute(
            "UPDATE slots SET is_booked=0 WHERE id=?",
            (appt["slot_id"],)
        )
        conn.commit()

    conn.close()
    return jsonify({"success": True})

# =================================================
# PDF
# =================================================
@app.route("/api/appointment/pdf/<code>")
def appointment_pdf(code):
    conn = db()
    a = conn.execute(
        "SELECT * FROM appointments WHERE confirmation_code=?",
        (code,)
    ).fetchone()
    conn.close()

    if not a:
        return jsonify({"error": "Not found"}), 404

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = 760

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(180, y, "Appointment Slip")
    y -= 50

    pdf.setFont("Helvetica", 11)
    fields = [
        ("Confirmation", a["confirmation_code"]),
        ("Patient", a["patient_name"]),
        ("Mobile", a["mobile"]),
        ("Date", a["appointment_date"]),
        ("Time", a["slot_time"]),
        ("Status", a["status"]),
    ]

    for k, v in fields:
        pdf.drawString(100, y, f"{k}: {v}")
        y -= 30

    pdf.showPage()
    pdf.save()
    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name=f"{code}.pdf",
        mimetype="application/pdf"
    )

# =================================================
# ADMIN APIs (JWT)
# =================================================
@app.route("/api/admin/login", methods=["POST", "OPTIONS"])
def admin_login():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid request"}), 400

    if data.get("username") == "admin" and data.get("password") == "admin123":
        return jsonify({"token": create_token()})

    return jsonify({"error": "Invalid credentials"}), 401



@app.route("/api/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = db()

    appointments = conn.execute(
        "SELECT * FROM appointments ORDER BY appointment_date DESC, slot_time ASC"
    ).fetchall()

    slots = conn.execute(
        "SELECT * FROM slots ORDER BY slot_date,start_time"
    ).fetchall()

    settings = conn.execute(
        "SELECT * FROM admin_settings WHERE id=1"
    ).fetchone()

    stats = {
        "total": conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
        "reserved": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE status='RESERVED'"
        ).fetchone()[0],
        "confirmed": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE status='CONFIRMED'"
        ).fetchone()[0],
        "today": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE appointment_date = DATE('now')"
        ).fetchone()[0],
    }

    conn.close()

    return jsonify({
        "appointments": [dict(a) for a in appointments],
        "slots": [dict(s) for s in slots],
        "settings": dict(settings) if settings else {},
        "stats": stats
    })


@app.route("/api/admin/slots", methods=["POST"])
@admin_required
def add_slot():
    f = request.json
    conn = db()
    conn.execute(
        "INSERT INTO slots VALUES (NULL,?,?,?,0)",
        (f["slot_date"], f["start_time"], f["end_time"])
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/admin/update/<int:id>", methods=["POST"])
@admin_required
def admin_update(id):
    f = request.json
    conn = db()
    conn.execute("""
        UPDATE appointments
        SET status=?, meeting_link=?, admin_remarks=?, updated_at=?
        WHERE id=?
    """, (
        f["status"],
        f["meeting_link"],
        f["remarks"],
        datetime.now().isoformat(),
        id
    ))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/admin/settings", methods=["POST"])
@admin_required
def admin_settings():
    f = request.json
    conn = db()
    conn.execute("""
        UPDATE admin_settings
        SET doctor_whatsapp=?, upi_link=?, default_amount=?
        WHERE id=1
    """, (
        f["doctor_whatsapp"],
        f["upi_link"],
        f["default_amount"]
    ))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# =================================================
# RUN
# =================================================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
