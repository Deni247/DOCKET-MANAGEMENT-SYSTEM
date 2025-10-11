import os
import sys
import mysql.connector
from passlib.hash import bcrypt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "docket_system"),
    )

def hash_admin_passwords():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("SELECT admin_id, password FROM admins WHERE password IS NOT NULL")
        admins = cur.fetchall()

        for admin in admins:
            password_hash = bcrypt.hash(admin["password"])
            cur.execute("UPDATE admins SET password_hash = %s, password = NULL WHERE admin_id = %s", (password_hash, admin["admin_id"]))

        conn.commit()
        print(f"{len(admins)} admin passwords hashed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"An error occurred: {e}")

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    hash_admin_passwords()
