from flask import Blueprint, jsonify, request, send_file
import os
from datetime import datetime
from io import BytesIO

import qrcode
import mysql.connector
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from dotenv import load_dotenv

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
def generate_docket_pdf(student, courses, exam_type):
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
    qr_data = f"{student['student_number']}_{exam_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
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

    # Convert to frontend-compatible format
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

    # Fetch student info
    cur.execute("""
        SELECT s.id, s.first_name, s.last_name, s.student_number, p.programme_name
        FROM students s
        JOIN programmes p ON s.programme_id = p.programme_id
        WHERE s.id = %s
    """, (student_id,))
    student = cur.fetchone()

    # ✅ FIXED: Proper indentation for course fetching block
    cur.execute("""
        SELECT c.course_name
        FROM enrollments e
        JOIN curriculum cu ON e.curriculum_id = cu.curriculum_id
        JOIN courses c ON cu.course_id = c.course_id
        WHERE e.student_id = %s
        ORDER BY c.course_name ASC
    """, (student_id,))
    courses = cur.fetchall()

    cur.close()
    conn.close()

    if not student:
        return jsonify({"ok": False, "error": "Student not found."}), 404
    if not courses:
        return jsonify({"ok": False, "error": "No enrolled courses found."}), 404

    pdf_buffer = generate_docket_pdf(student, courses, exam_type)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{student['student_number']}_{exam_type}_Docket.pdf",
        mimetype="application/pdf"
    )

