import os
import datetime
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector
from dotenv import load_dotenv
import jwt
from passlib.hash import bcrypt

# Load environment variables
load_dotenv()

# Flask app setup
# Construct the absolute path to the frontend directory for robust static file serving
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)
frontend_dir = os.path.join(project_root, "Docket-system-frontend", "frontend")

app = Flask(
    __name__,
    static_folder=frontend_dir,   # Use the correct absolute path
    static_url_path=""
)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please-and-use-long-random")
JWT_ALGO = "HS256"
JWT_EXP_SECONDS = int(os.getenv("JWT_EXP_SECONDS", 60 * 60 * 8))  # 8 hours


# -------------------- Database Connection --------------------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "docket_system"),
        autocommit=False
    )


# -------------------- JWT Auth Decorator --------------------
def jwt_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            token = None

            if auth.startswith("Bearer "):
                token = auth.split(" ", 1)[1]
            else:
                token = request.cookies.get("access_token")

            if not token:
                return jsonify({"ok": False, "error": "Missing token"}), 401

            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            except jwt.ExpiredSignatureError:
                return jsonify({"ok": False, "error": "Token expired"}), 401
            except Exception as e:
                return jsonify({"ok": False, "error": f"Invalid token: {e}"}), 401

            if role and payload.get("role") != role:
                return jsonify({"ok": False, "error": "Forbidden"}), 403

            request.user = payload
            return f(*args, **kwargs)
        return wrapper
    return decorator


# -------------------- Routes --------------------
@app.route("/api")
def home():
    return jsonify({"message": "Docket System Backend Running ✅"})


@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.json or {}
        username = data.get("student_number")
        password = data.get("password")
        role = data.get("role", "student")
        use_cookie = data.get("use_cookie", False)

        if not username or not password:
            return jsonify({"ok": False, "error": "Missing credentials"}), 400

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        if role == "admin":
            cur.execute(
                "SELECT admin_id AS id, username, password_hash FROM admins WHERE username=%s LIMIT 1",
                (username,)
            )
        else:
            cur.execute(
                "SELECT id, student_number, password_hash, first_name, last_name "
                "FROM students WHERE student_number=%s LIMIT 1",
                (username,)
            )

        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user or not user.get("password_hash"):
            return jsonify({"ok": False, "error": "Invalid credentials"}), 401

        if not bcrypt.verify(password, user["password_hash"]):
            return jsonify({"ok": False, "error": "Invalid credentials"}), 401

        now = datetime.datetime.utcnow()
        payload = {
            "sub": str(user["id"]),
            "role": role,
            "iat": now,
            "exp": now + datetime.timedelta(seconds=JWT_EXP_SECONDS)
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

        resp = jsonify({
            "ok": True,
            "token": token,
            "user": {
                "id": user["id"],
                "first_name": user.get("first_name"),
                "last_name": user.get("last_name"),
                "role": role
            }
        })

        if use_cookie:
            resp.set_cookie(
                "access_token",
                token,
                httponly=True,
                samesite="Lax"
            )
        return resp

    except mysql.connector.Error as err:
        # General handler for database errors (e.g., connection failed)
        # In a real app, you would log this error `app.logger.error(err)`
        return jsonify({"ok": False, "error": "Connection error. Please try again later."}), 500


@app.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    resp = jsonify({"ok": True})
    resp.set_cookie("access_token", "", expires=0)
    return resp


@app.route("/me", methods=["GET"])
@jwt_required()
def me():
    payload = request.user
    return jsonify({"ok": True, "user": payload})


# -------------------- Serve Frontend --------------------
@app.route("/")
def serve_index():
    """Serve student portal HTML"""
    return send_from_directory(app.static_folder, "students-portal.html")


@app.route("/<path:path>")
def serve_static_files(path):
    """Serve static frontend files (HTML, CSS, JS, etc.)"""
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    else:
        return jsonify({"error": "File not found"}), 404


# -------------------- Register Blueprints --------------------
from routes.dockets import dockets_bp
from routes.verification import verification_bp
from routes.admin_controls import admin_controls_bp
app.register_blueprint(dockets_bp, url_prefix="/dockets")
app.register_blueprint(verification_bp, url_prefix="/verification")
app.register_blueprint(admin_controls_bp, url_prefix="/admin")


# -------------------- Run Server --------------------
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1')