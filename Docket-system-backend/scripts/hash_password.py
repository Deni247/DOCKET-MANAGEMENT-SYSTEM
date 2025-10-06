# scripts/hash_passwords.py
import os
from dotenv import load_dotenv
import mysql.connector
from passlib.hash import bcrypt

load_dotenv()

def get_conn():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        autocommit=False
    )

def hash_students():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, password, password_hash FROM students WHERE password IS NOT NULL AND password_hash IS NULL")
    rows = cur.fetchall()
    print(f"Found {len(rows)} students to hash")
    for student in rows:
        plain = student['password']
        if plain is None:
            print(f"Student {student['id']} has no password, skipping.")
            continue
        if isinstance(plain, str):
            plain_bytes = plain.encode('utf-8')
        else:
            plain_bytes = plain
        if len(plain_bytes) > 72:
            print(f"Warning: Student {student['id']} password > 72 bytes, truncating.")
        plain_bytes = plain_bytes[:72]
        try:
            hashed = bcrypt.hash(plain_bytes)
        except Exception as e:
            print(f"Error hashing student {student['id']}: {e}")
            continue
        cur2 = conn.cursor()
        cur2.execute("UPDATE students SET password_hash=%s WHERE id=%s", (hashed, student['id']))
        cur2.close()
    conn.commit()

def hash_admins():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT admin_id, password, password_hash FROM admins WHERE password IS NOT NULL AND password_hash IS NULL")
    rows = cur.fetchall()
    print(f"Found {len(rows)} admins to hash")
    for r in rows:
        plain = r['password']
        if plain is None:
            print(f"Admin {r['admin_id']} has no password, skipping.")
            continue
        if isinstance(plain, str):
            plain_bytes = plain.encode('utf-8')
        else:
            plain_bytes = plain
        if len(plain_bytes) > 72:
            print(f"Warning: Admin {r['admin_id']} password > 72 bytes, truncating.")
        plain_bytes = plain_bytes[:72]
        try:
            hashed = bcrypt.hash(plain_bytes)
        except Exception as e:
            print(f"Error hashing admin {r['admin_id']}: {e}")
            continue
        cur2 = conn.cursor()
        cur2.execute("UPDATE admins SET password_hash=%s WHERE admin_id=%s", (hashed, r['admin_id']))
        cur2.close()
    conn.commit()

if __name__ == "__main__":
    hash_students()
    hash_admins()
    print("Done. Verify and then NULL or DROP the plaintext password columns.")
