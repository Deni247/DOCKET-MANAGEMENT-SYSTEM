from flask import Blueprint, jsonify, request
import json
import os
from utils.auth import jwt_required

# Blueprint for admin controls
admin_controls_bp = Blueprint("admin_controls", __name__)

# Define file paths securely within the backend directory
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(backend_dir))
SETTINGS_FILE = os.path.join(project_root, 'Docket-system-backend', 'exam_settings.json')
BLOCKLIST_FILE = os.path.join(project_root, 'Docket-system-backend', 'blocked_students.json')

# Helper function to read JSON files
def read_json_file(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return a default structure if file is missing or corrupt
        if 'settings' in file_path:
            return {"active_exam": "ca1"}
        else:
            return []

# Helper function to write JSON files
def write_json_file(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# --- Routes for Exam Settings ---
@admin_controls_bp.route("/settings", methods=["GET"])
@jwt_required(role="admin")
def get_exam_settings():
    settings = read_json_file(SETTINGS_FILE)
    return jsonify({"ok": True, "settings": settings})

@admin_controls_bp.route("/settings", methods=["POST"])
@jwt_required(role="admin")
def update_exam_settings():
    data = request.json
    active_exam = data.get("active_exam")

    if active_exam not in ["ca1", "ca2", "exam"]:
        return jsonify({"ok": False, "error": "Invalid exam type specified."}), 400

    settings = {"active_exam": active_exam}
    write_json_file(SETTINGS_FILE, settings)
    return jsonify({"ok": True, "message": f"Active exam set to {active_exam}."})

# --- Routes for Student Blocklist ---
@admin_controls_bp.route("/blocked-students", methods=["GET"])
@jwt_required(role="admin")
def get_blocked_students():
    blocklist = read_json_file(BLOCKLIST_FILE)
    return jsonify({"ok": True, "blocked_students": blocklist})

@admin_controls_bp.route("/students/<student_number>/block", methods=["POST"])
@jwt_required(role="admin")
def block_student(student_number):
    blocklist = read_json_file(BLOCKLIST_FILE)
    if student_number not in blocklist:
        blocklist.append(student_number)
        write_json_file(BLOCKLIST_FILE, blocklist)
    return jsonify({"ok": True, "message": f"Student {student_number} has been blocked."})

@admin_controls_bp.route("/students/<student_number>/unblock", methods=["POST"])
@jwt_required(role="admin")
def unblock_student(student_number):
    blocklist = read_json_file(BLOCKLIST_FILE)
    if student_number in blocklist:
        blocklist.remove(student_number)
        write_json_file(BLOCKLIST_FILE, blocklist)
    return jsonify({"ok": True, "message": f"Student {student_number} has been unblocked."})
