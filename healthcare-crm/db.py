import os
import mysql.connector
from mysql.connector import Error
import psycopg2


def get_db_connection():
    """Database connection for Local + Render"""

    try:

        # Render / Online Database
        if os.getenv("RENDER"):

            return psycopg2.connect(
                host="dpg-d80ntkjtqb8s738cia80-a",
                port=5432,
                database="healthcare_db_4xtq",
                user="healthcare_db_4xtq_user",
                password="6yko1ws4fGPmSkBiaLxRYy07cfZR7Ttn"
            )

        # Localhost Database
        else:

            return mysql.connector.connect(
                host=os.getenv("DB_HOST", "localhost"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", "Amaan@123"),
                database=os.getenv("DB_NAME", "healthcare_crm"),
            )

    except Exception as e:
        print("Database connection error:", e)
        raise
