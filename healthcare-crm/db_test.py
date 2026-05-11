from db import get_db_connection

try:
    conn = get_db_connection()
    print("===================================")
    print("   DATABASE CONNECTED SUCCESSFULLY")
    print("===================================")
    conn.close()
except Exception as e:
    print("Database connection failed:", e)