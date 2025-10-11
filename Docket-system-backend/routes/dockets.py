from flask import Blueprint, jsonify, request, send_file
import os
from datetime import datetime
from io import BytesIO
import qrcode
import mysql.connector
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from dotenv import load_dotenv
import hashlib
import secrets
from utils.auth import jwt_required




# Load environment variables
load_dotenv()

# Blueprint
dockets_bp = Blueprint("dockets", __name__)

# ---------------- Helper: Database Connection ----------------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "docket_system"),
    )

# ---------------- Helper: Generate PDF Docket ----------------
def generate_docket_pdf(student, courses, exam_type, qr_data):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # ---------------- Header ----------------
    logo_path = "frontend/cavendish-logo.png"
    if os.path.exists(logo_path):
        p.drawInlineImage(logo_path, 50, height - 100, width=100, height=50)

    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, height - 70, "CAVENDISH UNIVERSITY ZAMBIA")
    p.setFont("Helvetica-Bold", 14)
    p.drawCentredString(width / 2, height - 100, f"{exam_type.upper()} DOCKET")

    # ---------------- Student Info ----------------
    p.setFont("Helvetica", 12)
    y = height - 150
    p.drawString(50, y, f"Name: {student['first_name']} {student['last_name']}")
    p.drawString(50, y - 20, f"Student Number: {student['student_number']}")
    p.drawString(50, y - 40, f"Programme: {student['programme_name']}")

    # ---------------- Table Header ----------------
    y -= 80
    p.setFont("Helvetica-Bold", 12)
    col1_x = 50
    col2_x = 350
    row_height = 20
    p.drawString(col1_x, y, "Course Name")
    p.drawString(col2_x, y, "Invigilator Signature")
    p.line(50, y - 5, width - 50, y - 5)
    y -= row_height

    # ---------------- Table Rows ----------------
    p.setFont("Helvetica", 11)
    for course in courses:
        p.drawString(col1_x, y, course["course_name"])
        p.drawString(col2_x, y, "________________________")
        y -= row_height
        if y < 150:
            p.showPage()
            y = height - 100

    # ---------------- Signatures ----------------
    y -= 40
    p.drawString(50, y, "Verification Officer: ______________________")
    p.drawString(350, y, "Student Signature: ________________________")

    # ---------------- QR Code ----------------
    qr_img = qrcode.make(qr_data)
    qr_path = f"temp_qr_{student['student_number']}.png"
    qr_img.save(qr_path)
    p.drawInlineImage(qr_path, width - 180, 60, 100, 100)
    os.remove(qr_path)

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

# ---------------- Route: Check Eligibility ----------------
@dockets_bp.route("/eligibility/<student_id>", methods=["GET"])
def check_eligibility(student_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT ca1_status, ca2_status, exam_status FROM clearances WHERE student_id=%s LIMIT 1",
        (student_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"ok": False, "error": "No clearance records found."}), 404

    eligibility_list = [
        {"exam_type": "ca1", "eligible": row["ca1_status"] == "eligible"},
        {"exam_type": "ca2", "eligible": row["ca2_status"] == "eligible"},
        {"exam_type": "exam", "eligible": row["exam_status"] == "eligible"},
    ]
    return jsonify({"ok": True, "eligibility": eligibility_list})

# ---------------- Route: Generate Docket ----------------
@dockets_bp.route("/generate", methods=["POST"])
def generate_docket():
    data = request.json
    student_id = data.get("student_id")
    exam_type = data.get("exam_type")

    if not student_id or not exam_type:
        return jsonify({"ok": False, "error": "Missing parameters"}), 400

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    # Check clearance
    cur.execute(
        "SELECT ca1_status, ca2_status, exam_status FROM clearances WHERE student_id=%s LIMIT 1",
        (student_id,),
    )
    clearance = cur.fetchone()
    if not clearance:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "error": "No clearance record found."}), 404

    status_map = {
        "ca1": clearance["ca1_status"],
        "ca2": clearance["ca2_status"],
        "exam": clearance["exam_status"]
    }
    if status_map.get(exam_type) != "eligible":
        cur.close()
        conn.close()
        return jsonify({
            "ok": False,
            "error": f"Not eligible for {exam_type.upper()} docket. Please visit the Retentions Office."
        }), 403

    # ---------------- Fetch student info ----------------
    cur.execute("""
        SELECT s.id, s.first_name, s.last_name, s.student_number, s.programme_id, p.programme_name
        FROM students s
        JOIN programmes p ON s.programme_id = p.programme_id
        WHERE s.id = %s
    """, (student_id,))
    student = cur.fetchone()

    cur.execute("""
        SELECT c.course_name
        FROM enrollments e
        JOIN curriculum cu ON e.curriculum_id = cu.curriculum_id
        JOIN courses c ON cu.course_id = c.course_id
        WHERE e.student_id = %s
        ORDER BY c.course_name ASC
    """, (student_id,))
    courses = cur.fetchall()

    if not student:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "error": "Student not found."}), 404
    if not courses:
        cur.close()
        conn.close()
        return jsonify({"ok": False, "error": "No enrolled courses found."}), 404

    # ---------------- Generate QR data and token ----------------
    token_value = secrets.token_urlsafe(16)
    token_hash = hashlib.sha256(token_value.encode()).hexdigest()  # ✅ hash for secure storage
    qr_data = f"{student['student_number']}_{exam_type}_{token_value}"

    try:
        # ---------------- Ensure token key exists for verification ----------------
        cur.execute("SELECT key_id, secret_key FROM token_keys WHERE status='active' LIMIT 1")
        key_row = cur.fetchone()
        if not key_row:
            # No active key exists, create one
            new_secret_key = secrets.token_urlsafe(32)
            cur.execute("""
                INSERT INTO token_keys (key_name, secret_key, created_at, status)
                VALUES (%s, %s, NOW(), %s)
            """, ("default_verification_key", new_secret_key, "active"))
            token_key_id = cur.lastrowid
            secret_key_for_docket = new_secret_key
        else:
            token_key_id = key_row["key_id"]
            secret_key_for_docket = key_row["secret_key"]

        # ---------------- Save to dockets table ----------------
        cur.execute("""
            INSERT INTO dockets (student_id, programme_id, exam_type, qr_code, issued_at, status, printed_count, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        """, (
            student['id'],
            student['programme_id'],
            exam_type,
            qr_data,
            datetime.now(),
            "issued",
            1
        ))
        docket_id = cur.lastrowid

        # ---------------- Save to docket_tokens table ----------------
        cur.execute("""
            INSERT INTO docket_tokens (docket_id, token_hash, issued_at, status)
            VALUES (%s, %s, %s, %s)
        """, (
            docket_id,
            token_hash,
            datetime.now(),
            "active"
        ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"ok": False, "error": f"Failed to save docket/token: {e}"}), 500

    cur.close()
    conn.close()

    # ---------------- Generate PDF ----------------
    pdf_buffer = generate_docket_pdf(student, courses, exam_type, qr_data)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{student['student_number']}_{exam_type}_Docket.pdf",
        mimetype="application/pdf"
    )

@dockets_bp.route("/payments", methods=["GET"])
@jwt_required(role="admin")
def get_payments():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT s.id, s.first_name, s.last_name, s.student_number, p.programme_name, sb.total_fee, sb.amount_paid, sb.balance
        FROM students s
        JOIN programmes p ON s.programme_id = p.programme_id
        LEFT JOIN student_balances sb ON s.id = sb.student_id
        GROUP BY s.id
        ORDER BY s.last_name, s.first_name
    """)
    students = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({"ok": True, "students": students})


@dockets_bp.route("/students/search", methods=["GET"])
@jwt_required(role="admin")
def search_students():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"ok": True, "students": []})

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    search_query = f"%{query}%"
    cur.execute("""
        SELECT s.id, s.first_name, s.last_name, s.student_number, p.programme_name, sb.total_fee, sb.amount_paid, sb.balance
        FROM students s
        JOIN programmes p ON s.programme_id = p.programme_id
        LEFT JOIN student_balances sb ON s.id = sb.student_id
        WHERE s.first_name LIKE %s OR s.last_name LIKE %s OR s.student_number LIKE %s
        GROUP BY s.id
        ORDER BY s.last_name, s.first_name
    """, (search_query, search_query, search_query))
    students = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({"ok": True, "students": students})

@dockets_bp.route("/payments/update", methods=["POST"])
@jwt_required(role="admin")
def update_payment():
    data = request.json
    student_number = data.get("student_number")
    amount = data.get("amount")

    if not student_number or not amount:
        return jsonify({"ok": False, "error": "Missing parameters"}), 400

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        conn.start_transaction()

        # Get student_id and programme_id from students table
        cur.execute("SELECT id, programme_id FROM students WHERE student_number = %s", (student_number,))
        student = cur.fetchone()
        if not student:
            cur.close()
            conn.close()
            return jsonify({"ok": False, "error": "Student not found"}), 404
        
        student_id = student["id"]
        programme_id = student["programme_id"]

        # Insert into payments table
        cur.execute("""
            INSERT INTO payments (student_id, programme_id, amount, payment_type, payment_date, payment_status)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        """, (student_id, programme_id, amount, "General", "completed"))

        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": f"Failed to update payment: {e}"}), 500
    finally:
        cur.close()
        conn.close()

    return jsonify({"ok": True})
