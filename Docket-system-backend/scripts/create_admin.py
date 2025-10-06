# scripts/create_admin.py
import os
from dotenv import load_dotenv
import mysql.connector
from passlib.hash import bcrypt

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)
cur = conn.cursor()
username = input("admin username: ")
pw = input("admin password (will be hashed): ")
pw_hash = bcrypt.hash(pw)
# adapt column names to your admins table
cur.execute("INSERT INTO admins (username, password_hash) VALUES (%s, %s)", (username, pw_hash))
conn.commit()
cur.close()
conn.close()
print("Admin created.")
