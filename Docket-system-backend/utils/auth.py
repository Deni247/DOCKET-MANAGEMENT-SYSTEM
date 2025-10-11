from functools import wraps
from flask import request, jsonify
import jwt
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please-and-use-long-random")
JWT_ALGO = "HS256"

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
